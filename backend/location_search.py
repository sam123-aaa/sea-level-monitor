"""Unicode-aware catalogue search; regions are distinct from gauging stations."""
import math
import re
import unicodedata
from sqlalchemy import text
from .database_config import db


def normalize_name(value):
    value = unicodedata.normalize('NFKC', value).casefold().replace('ё', 'е')
    return ' '.join(re.sub(r'[^\w]+', ' ', value, flags=re.UNICODE).split())


ALIASES = {
    'Санкт-Петербург': ['Петербург', 'СПб', 'Saint Petersburg', 'St Petersburg'],
    'Шанхай': ['Shanghai'],
    'Каспийск (Каспийское море)': ['Каспий', 'Каспийск', 'Каспийское море', 'Kaspiysk', 'Caspian'],
    'Кронштадт': ['Kronstadt'],
    'Венеция': ['Venice'],
    'Новый Орлеан': ['New Orleans'],
    'Токио': ['Tokyo'],
}


def matches(query, name):
    needle = normalize_name(query)
    if query.strip() and not needle:
        return False
    return any(needle in normalize_name(value) for value in [name] + ALIASES.get(name, []))


def distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 12742 * math.asin(min(1, math.sqrt(a)))


def catalogue(query=''):
    stations = db.session.execute(text(
        'SELECT station_id, station_name, country, latitude, longitude, ocean_basin '
        'FROM tide_gauges ORDER BY station_id')).mappings().all()
    regions = db.session.execute(text(
        'SELECT zone_id, region_name, country, latitude, longitude FROM risk_zones ORDER BY zone_id'
    )).mappings().all()
    counts = dict(db.session.execute(text(
        'SELECT station_id, COUNT(*) FROM tide_gauge_measurements GROUP BY station_id')).all())
    result = []
    for row in regions:
        if not matches(query, row['region_name']):
            continue
        nearby = [(distance_km(row['latitude'], row['longitude'], s['latitude'], s['longitude']), s)
                  for s in stations if all(x is not None for x in
                      (row['latitude'], row['longitude'], s['latitude'], s['longitude']))]
        distance, station = min(nearby, key=lambda item: item[0]) if nearby else (None, None)
        if distance is None or distance > 100:
            station, distance = None, None
        result.append(dict(kind='region', id=row['zone_id'], name=row['region_name'],
            country=row['country'], latitude=row['latitude'], longitude=row['longitude'],
            station_id=station['station_id'] if station else None,
            station_name=station['station_name'] if station else None,
            station_distance_km=round(distance, 1) if distance is not None else None,
            measurement_count=counts.get(station['station_id'], 0) if station else 0))
    for row in stations:
        if matches(query, row['station_name']):
            result.append(dict(kind='station', id=row['station_id'], name=row['station_name'],
                country=row['country'], latitude=row['latitude'], longitude=row['longitude'],
                station_id=row['station_id'], station_name=row['station_name'],
                station_distance_km=0, measurement_count=counts.get(row['station_id'], 0)))
    return result
