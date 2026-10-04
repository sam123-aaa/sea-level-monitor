"""Cached adapters for public, live weather and water-level data sources."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import logging
import math
import time

from sqlalchemy import text

from .database_config import db

logger = logging.getLogger(__name__)
_cache = {}
_cache_lock = Lock()


def _get_json(url, timeout=12):
    request = Request(url, headers={"User-Agent": "SeaLevelMonitor/1.0 (educational project)", "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _cached(key, ttl, factory):
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < ttl:
            return cached[1]
    result = factory()
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)
    return result


def _distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1, math.sqrt(a)))


def _zones():
    rows = db.session.execute(text(
        "SELECT zone_id, region_name, country, latitude, longitude FROM risk_zones "
        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL ORDER BY zone_id"
    )).all()
    return [{"id": row[0], "region": row[1], "country": row[2], "latitude": float(row[3]), "longitude": float(row[4])} for row in rows]


def _database_stations():
    rows = db.session.execute(text(
        "SELECT station_id, station_name, country, latitude, longitude FROM tide_gauges "
        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL ORDER BY station_id"
    )).all()
    return [{"id": row[0], "name": row[1], "country": row[2], "latitude": float(row[3]), "longitude": float(row[4])} for row in rows]


def _weather_for_zone(zone):
    query = urlencode({
        "latitude": zone["latitude"], "longitude": zone["longitude"],
        "current": "temperature_2m,precipitation,rain,wind_speed_10m,weather_code",
        "timezone": "UTC",
    })
    data = _get_json("https://api.open-meteo.com/v1/forecast?" + query)
    current = data.get("current") or {}
    return {
        "time": current.get("time"), "interval_seconds": current.get("interval"),
        "temperature_c": current.get("temperature_2m"),
        "precipitation_mm": current.get("precipitation"), "rain_mm": current.get("rain"),
        "wind_kmh": current.get("wind_speed_10m"), "weather_code": current.get("weather_code"),
        "source": "Open-Meteo (модельная оценка)",
    }


def _station_list():
    data = _get_json("https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=waterlevels&units=metric")
    return data.get("stations") or data.get("stationList") or []


def _noaa_at_zone(zone, stations):
    nearby = []
    for station in stations:
        try:
            distance = _distance_km(zone["latitude"], zone["longitude"], float(station["lat"]), float(station.get("lng", station.get("lon"))))
            if distance <= 100 and station.get("tidal") and station.get("floodlevels"):
                nearby.append((distance, station))
        except (TypeError, ValueError, KeyError):
            continue
    if not nearby:
        return None
    distance, station = min(nearby, key=lambda item: item[0])
    sid = station["id"]
    base = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/" + sid
    query = urlencode({"date": "latest", "station": sid, "product": "water_level", "datum": "STND", "time_zone": "gmt", "units": "metric", "format": "json", "application": "SeaLevelMonitor"})
    water, datum, thresholds = _get_json("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?" + query), _get_json(base + "/datums.json?units=metric"), _get_json(base + "/floodlevels.json?units=metric")
    observations = water.get("data") or []
    if not observations:
        return {"station": station.get("name"), "station_id": sid, "latitude": station.get("lat"), "longitude": station.get("lng"), "distance_km": round(distance, 1), "available": False, "source": "NOAA CO-OPS"}
    try:
        observed_stage = float(observations[-1]["v"])
        mhhw_record = next(item for item in datum.get("datums", []) if item.get("name") == "MHHW")
        mhhw_stage = float(mhhw_record["value"])
        level_mhhw = observed_stage - mhhw_stage
    except (ValueError, TypeError, KeyError, StopIteration):
        level_mhhw, mhhw_stage = None, None
    nos = [(name, thresholds.get(name)) for name in ("nos_minor", "nos_moderate", "nos_major") if thresholds.get(name) is not None]
    status = "нет порогов"
    if level_mhhw is not None and nos:
        exceeded = [name for name, limit in nos if level_mhhw >= float(limit)]
        status = ("превышен " + exceeded[-1].replace("nos_", "NOS ").replace("_", " ")) if exceeded else "ниже порога NOS Minor"
    return {
        "station": station.get("name"), "station_id": sid, "latitude": float(station["lat"]),
        "longitude": float(station.get("lng", station.get("lon"))), "distance_km": round(distance, 1),
        "time": observations[-1].get("t"), "level_mhhw_m": round(level_mhhw, 3) if level_mhhw is not None else None,
        "nos_minor_m": thresholds.get("nos_minor"), "nos_moderate_m": thresholds.get("nos_moderate"),
        "nos_major_m": thresholds.get("nos_major"), "status": status, "available": level_mhhw is not None,
        "datum": "MHHW", "source": "NOAA CO-OPS: наблюдение переведено в MHHW; пороги NOS",
    }


def live_conditions():
    """Return model-based current weather and nearest qualifying NOAA gauge per zone."""
    def build():
        zones = _zones()
        database_stations = _database_stations()
        with ThreadPoolExecutor(max_workers=8) as pool:
            station_future = pool.submit(_station_list)
            weather_futures = {z["id"]: pool.submit(_weather_for_zone, z) for z in zones}
            try:
                stations = station_future.result()
            except Exception:
                logger.exception("NOAA station list unavailable")
                stations = []
            gauge_futures = {
                (item["type"], item["id"]): pool.submit(_noaa_at_zone, item, stations)
                for item in ([({"type": "zone", **z}) for z in zones] + [{"type": "station", **s} for s in database_stations])
            } if stations else {}
            output = []
            for zone in zones:
                item = dict(zone)
                try:
                    item["weather"] = weather_futures[zone["id"]].result()
                except Exception:
                    logger.exception("Weather request failed for %s", zone["region"])
                    item["weather"] = None
                try:
                    item["water_gauge"] = gauge_futures[("zone", zone["id"])].result() if gauge_futures else None
                except Exception:
                    logger.exception("NOAA gauge request failed for %s", zone["region"])
                    item["water_gauge"] = None
                output.append(item)
            monitored_stations = []
            for station in database_stations:
                item = dict(station)
                try:
                    item["water_gauge"] = gauge_futures[("station", station["id"])].result() if gauge_futures else None
                except Exception:
                    logger.exception("NOAA gauge request failed for station %s", station["name"])
                    item["water_gauge"] = None
                monitored_stations.append(item)
        return {"updated_at": datetime.now(timezone.utc).isoformat(), "zones": output, "stations": monitored_stations}

    return _cached("live-conditions", 600, build)


def radar_metadata():
    def build():
        data = _get_json("https://api.rainviewer.com/public/weather-maps.json")
        past = data.get("radar", {}).get("past", [])
        if not data.get("host") or not past:
            raise ValueError("Radar provider returned no frames")
        return {"host": data["host"], "frames": past, "generated": data.get("generated"), "source": "RainViewer"}
    return _cached("radar-metadata", 300, build)
