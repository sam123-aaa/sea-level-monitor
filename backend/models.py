from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, Text, CheckConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import os
import secrets
from .database_config import db

Base = db.Model


class TideGauge(Base):
    __tablename__ = 'tide_gauges'

    station_id = Column(Integer, primary_key=True)
    station_name = Column(String(100), nullable=False)
    country = Column(String(50))
    latitude = Column(Float)
    longitude = Column(Float)
    ocean_basin = Column(String(50))
    installation_date = Column(Date)
    is_active = Column(Boolean, default=True)

    measurements = relationship("TideGaugeMeasurement", back_populates="station")


class TideGaugeMeasurement(Base):
    __tablename__ = 'tide_gauge_measurements'

    measurement_id = Column(Integer, primary_key=True)
    station_id = Column(Integer, ForeignKey('tide_gauges.station_id'))
    measurement_date = Column(Date, nullable=False)
    mean_sea_level_mm = Column(Float)
    relative_change_rate_mm_per_year = Column(Float)
    data_quality_score = Column(Integer)

    __table_args__ = (
        CheckConstraint('data_quality_score IS NULL OR data_quality_score BETWEEN 1 AND 10', name='ck_measurement_quality'),
        Index('ix_measurements_station_date', 'station_id', 'measurement_date'),
    )

    station = relationship("TideGauge", back_populates="measurements")


class Satellite(Base):
    __tablename__ = 'satellites'

    satellite_id = Column(Integer, primary_key=True)
    satellite_name = Column(String(50), unique=True, nullable=False)
    operator = Column(String(50))
    launch_date = Column(Date)
    is_active = Column(Boolean, default=True)

    measurements = relationship("SatelliteMeasurement", back_populates="satellite")


class SatelliteMeasurement(Base):
    __tablename__ = 'satellite_measurements'

    measurement_id = Column(Integer, primary_key=True)
    satellite_id = Column(Integer, ForeignKey('satellites.satellite_id'))
    measurement_date = Column(Date, nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    sea_level_mm = Column(Float)
    confidence_interval = Column(Float)

    satellite = relationship("Satellite", back_populates="measurements")


class RiskZone(Base):
    __tablename__ = 'risk_zones'

    zone_id = Column(Integer, primary_key=True)
    region_name = Column(String(100), nullable=False)
    country = Column(String(50))
    area_sqkm = Column(Float)
    avg_elevation_m = Column(Float)
    population = Column(Integer)
    critical_infrastructure = Column(Text)  # В SQLite нет ARRAY
    risk_level = Column(Integer)
    latitude = Column(Float)  # Добавляем координаты для карты
    longitude = Column(Float)
    last_assessment_date = Column(Date)

    __table_args__ = (CheckConstraint('risk_level IS NULL OR risk_level BETWEEN 1 AND 5', name='ck_risk_level'),)

    storm_surges = relationship("StormSurge", back_populates="region")


class StormSurge(Base):
    __tablename__ = 'storm_surges'

    surge_id = Column(Integer, primary_key=True)
    region_id = Column(Integer, ForeignKey('risk_zones.zone_id'))
    event_date = Column(DateTime, nullable=False)
    surge_height_m = Column(Float)
    mean_sea_level_at_event_mm = Column(Float)
    wind_speed_kmh = Column(Float)
    damage_estimate_usd = Column(Float)

    region = relationship("RiskZone", back_populates="storm_surges")


class User(Base):
    __tablename__ = 'users'

    user_id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    research_group = Column(String(100))
    access_level = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.now)


class ApiAccessLog(Base):
    __tablename__ = 'api_access_log'

    log_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.user_id'))
    endpoint = Column(String(100))
    access_time = Column(DateTime, default=datetime.now)
    query_params = Column(Text)


def init_test_data(db_session):
    """Инициализация тестовых данных"""

    # Заполнение идемпотентно: не дублирует справочники и пополняет пустые наборы измерений.
    configured_user = os.getenv('ADMIN_USERNAME')
    configured_password = os.getenv('ADMIN_PASSWORD')
    # Rotate the repository's former demo account without breaking audit-log FKs.
    from backend.security import Authentication
    legacy_user = db_session.query(User).filter_by(username='admin').first()
    if legacy_user and legacy_user.email == 'admin@example.com':
        replacement = configured_password if configured_user == 'admin' and configured_password else secrets.token_urlsafe(32)
        legacy_user.password_hash = Authentication.hash_password(replacement)
        legacy_user.access_level = 5 if configured_user == 'admin' and configured_password else 1
    if configured_user and configured_password:
        configured_account = db_session.query(User).filter_by(username=configured_user).first()
        if configured_account:
            stored_hash = configured_account.password_hash
            stored_hash = stored_hash if isinstance(stored_hash, bytes) else stored_hash.encode()
            if not Authentication.verify_password(configured_password, stored_hash):
                configured_account.password_hash = Authentication.hash_password(configured_password)
            configured_account.access_level = 5
        else:
            db_session.add(User(username=configured_user, email=os.getenv('ADMIN_EMAIL', 'admin@localhost'),
                password_hash=Authentication.hash_password(configured_password),
                research_group='Main Lab', access_level=5))

    # Добавляем тестовые станции
    stations = [
        TideGauge(station_name='Кронштадт', country='Россия', latitude=59.99, longitude=29.77,
                  ocean_basin='Балтийское море', installation_date=datetime(1980, 1, 1), is_active=True),
        TideGauge(station_name='Венеция', country='Италия', latitude=45.44, longitude=12.34,
                  ocean_basin='Адриатическое море', installation_date=datetime(1990, 1, 1), is_active=True),
        TideGauge(station_name='Новый Орлеан', country='США', latitude=29.95, longitude=-90.07,
                  ocean_basin='Мексиканский залив', installation_date=datetime(1985, 1, 1), is_active=True),
        TideGauge(station_name='Токио', country='Япония', latitude=35.68, longitude=139.76,
                  ocean_basin='Тихий океан', installation_date=datetime(1995, 1, 1), is_active=True),
    ]
    for station in stations:
        if not db_session.query(TideGauge).filter_by(station_name=station.station_name).first():
            db_session.add(station)
    db_session.flush()
    stations = db_session.query(TideGauge).order_by(TideGauge.station_id).all()

    # Добавляем тестовые зоны риска
    risk_zones = [
        RiskZone(region_name='Венецианская лагуна', country='Италия', area_sqkm=550,
                 avg_elevation_m=1.2, population=258000, risk_level=5,
                 critical_infrastructure='Порт, Исторический центр, Аэропорт',
                 latitude=45.44, longitude=12.34),
        RiskZone(region_name='Нидерланды (прибрежная зона)', country='Нидерланды', area_sqkm=7500,
                 avg_elevation_m=0.5, population=3500000, risk_level=5,
                 critical_infrastructure='Порты, Дамбы, Аэропорт Схипхол',
                 latitude=52.5, longitude=4.5),
        RiskZone(region_name='Мальдивы', country='Мальдивы', area_sqkm=298,
                 avg_elevation_m=1.5, population=540000, risk_level=5,
                 critical_infrastructure='Аэропорты, Курорты, Столица Мале',
                 latitude=3.2, longitude=73.2),
        RiskZone(region_name='Санкт-Петербург', country='Россия', area_sqkm=1439,
                 avg_elevation_m=3.5, population=5600000, risk_level=3,
                 critical_infrastructure='Порт, Дамба, Метро',
                 latitude=59.93, longitude=30.32),
        RiskZone(region_name='Шанхай', country='Китай', area_sqkm=6340,
                 avg_elevation_m=4.0, population=24000000, risk_level=4,
                 critical_infrastructure='Порт, Финансовый центр, Аэропорты',
                 latitude=31.23, longitude=121.47),
    ]
    for zone in risk_zones:
        if not db_session.query(RiskZone).filter_by(region_name=zone.region_name).first():
            db_session.add(zone)
    db_session.flush()

    # Добавляем тестовые измерения
    from datetime import timedelta
    import random

    # Измерения для станций
    base_date = datetime(2020, 1, 1)
    for i, station in enumerate(stations):
        if db_session.query(TideGaugeMeasurement).filter_by(station_id=station.station_id).first():
            continue
        for year in range(2020, 2025):
            for month in range(1, 13):
                date = datetime(year, month, 15)
                # Разный уровень для разных станций
                if station.station_name == 'Венеция':
                    level = 500 + (year - 2020) * 5 + random.randint(-20, 20)
                elif station.station_name == 'Новый Орлеан':
                    level = 480 + (year - 2020) * 6 + random.randint(-15, 15)
                else:
                    level = 450 + (year - 2020) * 3 + random.randint(-10, 10)

                measurement = TideGaugeMeasurement(
                    station_id=station.station_id,
                    measurement_date=date,
                    mean_sea_level_mm=level,
                    relative_change_rate_mm_per_year=random.uniform(2.5, 8.5),
                    data_quality_score=random.randint(7, 10)
                )
                db_session.add(measurement)

    # Добавляем тестовые спутники
    satellites = [
        Satellite(satellite_name='Jason-3', operator='NASA/NOAA',
                  launch_date=datetime(2016, 1, 17), is_active=True),
        Satellite(satellite_name='Sentinel-6', operator='ESA',
                  launch_date=datetime(2020, 11, 21), is_active=True),
    ]
    for satellite in satellites:
        if not db_session.query(Satellite).filter_by(satellite_name=satellite.satellite_name).first():
            db_session.add(satellite)
    db_session.flush()
    satellites = db_session.query(Satellite).all()

    # Демонстрационные наблюдения имеют учебное назначение и не являются официальным рядом.
    if not db_session.query(SatelliteMeasurement).first():
        for satellite in satellites:
            for offset, (lat, lon, level) in enumerate([(59.9, 30.3, 515.2), (45.4, 12.3, 522.8), (29.9, -90.0, 518.1)]):
                db_session.add(SatelliteMeasurement(satellite_id=satellite.satellite_id,
                    measurement_date=datetime(2024, 1 + offset, 15), latitude=lat,
                    longitude=lon, sea_level_mm=level + offset, confidence_interval=3.5))

    if not db_session.query(StormSurge).first():
        zones = db_session.query(RiskZone).all()
        for idx, zone in enumerate(zones):
            for year in (2022, 2023, 2024):
                db_session.add(StormSurge(region_id=zone.zone_id,
                    event_date=datetime(year, 9, 15), surge_height_m=0.7 + (idx % 3) * 0.25,
                    mean_sea_level_at_event_mm=510 + 2.1 * (year - 2020),
                    wind_speed_kmh=65 + 4 * idx, damage_estimate_usd=125000 * (idx + 1)))

    db_session.commit()
    print(" Тестовые данные успешно добавлены!")
