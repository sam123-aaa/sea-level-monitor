from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import os

Base = declarative_base()


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

    # Проверяем, есть ли уже данные
    if db_session.query(User).first():
        return

    # Создаем тестового пользователя
    from backend.security import Authentication
    hashed = Authentication.hash_password('password123')
    user = User(
        username='admin',
        email='admin@example.com',
        password_hash=hashed,
        research_group='Main Lab',
        access_level=5
    )
    db_session.add(user)

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
    db_session.add_all(stations)

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
    db_session.add_all(risk_zones)

    # Добавляем тестовые измерения
    from datetime import timedelta
    import random

    # Измерения для станций
    base_date = datetime(2020, 1, 1)
    for i, station in enumerate(stations):
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
    db_session.add_all(satellites)

    db_session.commit()
    print(" Тестовые данные успешно добавлены!")