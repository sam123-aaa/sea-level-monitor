from flask import Blueprint, request, jsonify, current_app
from sqlalchemy import text
from datetime import datetime
import pandas as pd
import numpy as np
import json
import logging
import math
import re
from .security import token_required, Authentication
from .models import User, ApiAccessLog
from .database_config import db

# Создаем Blueprint для API
api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = logging.getLogger(__name__)


def log_access(user_id, endpoint, params):
    """Логирование доступа к API"""
    try:
        log_entry = ApiAccessLog(
            user_id=user_id,
            endpoint=endpoint,
            query_params=json.dumps(dict(params)) if params else None,
            access_time=datetime.now()
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log access: {e}")
        db.session.rollback()


@api_bp.route('/auth/login', methods=['POST'])
def login():
    """Аутентификация пользователя"""
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Username and password required'}), 400

    # Ищем пользователя в БД
    user = User.query.filter_by(username=username).first()

    if user and Authentication.verify_password(password,
            user.password_hash if isinstance(user.password_hash, bytes) else user.password_hash.encode()):
        token = Authentication.generate_token(
            user.user_id,
            user.username,
            current_app.config['SECRET_KEY'],
            access_level=user.access_level or 1
        )
        return jsonify({
            'token': token,
            'user_id': user.user_id,
            'username': user.username,
            'access_level': user.access_level or 1
        })

    return jsonify({'message': 'Invalid credentials'}), 401


@api_bp.route('/sea-level/regions/max-rise', methods=['GET'])
@token_required
def get_regions_max_rise():
    """Поиск регионов с максимальной скоростью подъема уровня моря"""

    # Логируем доступ
    log_access(request.user['user_id'], '/api/sea-level/regions/max-rise', request.args)

    try:
        zones = db.session.execute(text(
            'SELECT region_name, country, latitude, longitude, population, risk_level FROM risk_zones'
        )).all()
        gauges = db.session.execute(text(
            'SELECT station_id, station_name, latitude, longitude FROM tide_gauges WHERE latitude IS NOT NULL AND longitude IS NOT NULL'
        )).all()
        aggregates = db.session.execute(text(
            'SELECT station_id, AVG(relative_change_rate_mm_per_year), MAX(mean_sea_level_mm) '
            'FROM tide_gauge_measurements GROUP BY station_id'
        )).all()
        by_station = {row[0]: (row[1], row[2]) for row in aggregates}

        def distance_km(lat1, lon1, lat2, lon2):
            radius = 6371.0
            a1, a2 = math.radians(lat1), math.radians(lat2)
            da, db = math.radians(lat2-lat1), math.radians(lon2-lon1)
            value = math.sin(da/2)**2 + math.cos(a1)*math.cos(a2)*math.sin(db/2)**2
            return 2*radius*math.asin(min(1, math.sqrt(value)))

        regions = []
        for zone in zones:
            closest = None
            if zone[2] is not None and zone[3] is not None and gauges:
                closest = min(gauges, key=lambda g: distance_km(zone[2], zone[3], g[2], g[3]))
            rate, level = by_station.get(closest[0], (None, None)) if closest else (None, None)
            regions.append({'region': zone[0], 'country': zone[1],
                'avg_rise_rate': float(rate) if rate is not None else 0,
                'max_level': float(level) if level is not None else 0,
                'population': zone[4], 'risk_level': zone[5],
                'latitude': zone[2], 'longitude': zone[3],
                'nearest_station': closest[1] if closest else None})
        regions.sort(key=lambda r: r['avg_rise_rate'], reverse=True)
        return jsonify(regions[:10])
    except Exception as e:
        logger.error(f"Database query failed: {e}")
        return jsonify({'error': 'Failed to fetch data'}), 500


@api_bp.route('/sea-level/port/<port_name>', methods=['GET'])
@token_required
def get_port_sea_level_chart(port_name):
    """Выдача графика изменения уровня для конкретного портового города"""

    log_access(request.user['user_id'], f'/api/sea-level/port/{port_name}', request.args)

    query = """
    SELECT 
        tgm.measurement_date,
        tgm.mean_sea_level_mm,
        tgm.relative_change_rate_mm_per_year
    FROM tide_gauge_measurements tgm
    JOIN tide_gauges tg ON tg.station_id = tgm.station_id
    WHERE LOWER(tg.station_name) LIKE LOWER(:port_name)
    ORDER BY tgm.measurement_date
    """

    try:
        df = pd.read_sql(text(query), db.engine, params={'port_name': f'%{port_name}%'})

        if df.empty:
            return jsonify({'error': 'Port not found'}), 404

        # Создание графика
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import os

        plt.figure(figsize=(12, 6))
        plt.plot(pd.to_datetime(df['measurement_date']), df['mean_sea_level_mm'], 'b-', linewidth=2)
        plt.title(f'Уровень моря в порту {port_name}')
        plt.xlabel('Дата')
        plt.ylabel('Уровень моря (мм)')
        plt.grid(True, alpha=0.3)

        # Сохраняем график
        safe_port_name = re.sub(r'[^A-Za-z0-9_-]+', '_', port_name).strip('_') or 'station'
        chart_filename = f"{safe_port_name}_sea_level.png"
        chart_path = os.path.join('static', 'charts', chart_filename)

        # Создаем папку если её нет
        os.makedirs(os.path.dirname(chart_path), exist_ok=True)

        plt.savefig(chart_path, dpi=100, bbox_inches='tight')
        plt.close()

        # Рассчитываем тренд
        z = np.polyfit(range(len(df)), df['mean_sea_level_mm'], 1)
        trend = z[0]  # мм в день

        return jsonify({
            'port_name': port_name,
            'chart_url': f'/static/charts/{chart_filename}',
            'data_points': len(df),
            'latest_level': float(df['mean_sea_level_mm'].iloc[-1]),
            'earliest_level': float(df['mean_sea_level_mm'].iloc[0]),
            'total_change': float(df['mean_sea_level_mm'].iloc[-1] - df['mean_sea_level_mm'].iloc[0]),
            'trend_mm_per_year': float(trend * 365)  # переводим в мм/год
        })
    except Exception as e:
        logger.error(f"Failed to generate chart: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/flooded-areas/calculation', methods=['POST'])
@token_required
def calculate_flooded_areas():
    """Расчет площади земель, которые уйдут под воду при подъеме на 1 метр"""

    data = request.get_json(silent=True) or {}
    sea_level_rise = data.get('rise_meters', 1.0)  # в метрах
    try:
        sea_level_rise = float(sea_level_rise)
        if not 0 < sea_level_rise <= 100:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'rise_meters must be greater than 0 and at most 100'}), 400

    query = """
    SELECT 
        region_name,
        area_sqkm,
        avg_elevation_m,
        population,
        critical_infrastructure
    FROM risk_zones
    WHERE avg_elevation_m <= :sea_level_rise
    """

    try:
        result = db.session.execute(text(query), {'sea_level_rise': sea_level_rise})

        total_flooded_area = 0
        affected_population = 0
        affected_regions = []

        for row in result:
            area = float(row[1]) if row[1] else 0
            pop = row[3] if row[3] else 0

            total_flooded_area += area
            affected_population += pop
            affected_regions.append({
                'region': row[0],
                'area_sqkm': area,
                'population': pop,
                'infrastructure': row[4] if row[4] else []
            })

        return jsonify({
            'sea_level_rise_m': sea_level_rise,
            'total_flooded_area_sqkm': round(total_flooded_area, 2),
            'affected_population': affected_population,
            'affected_regions': affected_regions,
            'regions_count': len(affected_regions),
            'calculation_date': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Flood calculation failed: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/storm-surges/analysis', methods=['GET'])
@token_required
def analyze_storm_surges():
    """Учет частоты штормовых нагонов и их связи с абсолютным уровнем моря"""

    region_id = request.args.get('region_id')
    years = request.args.get('years', 5, type=int)

    query = """
    SELECT CAST(strftime('%Y', event_date) AS INTEGER) AS year,
           COUNT(*) AS surge_count, AVG(surge_height_m) AS avg_surge_height,
           AVG(mean_sea_level_at_event_mm) AS avg_sea_level
    FROM storm_surges
    WHERE (:region_id IS NULL OR region_id = :region_id)
      AND event_date >= date('now', :period)
    GROUP BY strftime('%Y', event_date) ORDER BY year
    """

    try:
        region_id = int(region_id) if region_id else None
        result = db.session.execute(text(query), {'region_id': region_id, 'period': f'-{max(1, min(years, 100))} years'})

        analysis = []
        correlation = None

        for row in result:
            analysis.append({
                'year': int(row[0]),
                'surge_count': row[1],
                'avg_surge_height': float(row[2]) if row[2] else 0,
                'avg_sea_level': float(row[3]) if row[3] else 0
            })
        if len(analysis) > 1:
            counts = [item['surge_count'] for item in analysis]
            levels = [item['avg_sea_level'] for item in analysis]
            if np.std(counts) and np.std(levels):
                correlation = float(np.corrcoef(counts, levels)[0, 1])

        return jsonify({
            'region_id': region_id,
            'years_analyzed': years,
            'data': analysis,
            'correlation_surges_sea_level': correlation,
            'total_surges': sum(item['surge_count'] for item in analysis)
        })
    except Exception as e:
        logger.error(f"Storm surge analysis failed: {e}")
        return jsonify({'error': str(e)}), 500


@api_bp.route('/stations', methods=['GET'])
@token_required
def get_stations():
    """Получение списка всех мареографических станций"""

    query = """
    SELECT 
        station_id,
        station_name,
        country,
        latitude,
        longitude,
        ocean_basin,
        is_active
    FROM tide_gauges
    ORDER BY country, station_name
    """

    try:
        result = db.session.execute(text(query))

        stations = []
        for row in result:
            stations.append({
                'station_id': row[0],
                'station_name': row[1],
                'country': row[2],
                'latitude': float(row[3]) if row[3] else None,
                'longitude': float(row[4]) if row[4] else None,
                'ocean_basin': row[5],
                'is_active': row[6]
            })

        return jsonify(stations)
    except Exception as e:
        logger.error(f"Failed to fetch stations: {e}")
        return jsonify({'error': str(e)}), 500
