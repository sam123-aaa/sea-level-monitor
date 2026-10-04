import os
import logging
import secrets
from flask import Flask, render_template, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime

# Загружаем переменные окружения
load_dotenv()

# Импортируем наши модули
from backend.database_config import db, database_url
from backend.models import Base, init_test_data
from backend.api import api_bp
from backend.security import admin_required, token_required

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Создаем приложение
app = Flask(__name__)

# Конфигурация
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or secrets.token_urlsafe(32)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_AS_ASCII'] = False  # Для поддержки кириллицы

# Инициализация расширений
db.init_app(app)
CORS(app)

# Регистрируем blueprint API
app.register_blueprint(api_bp)

# Инициализируем менеджер бэкапов
backup_path = os.getenv('BACKUP_PATH', './backups')

# Создаем необходимые папки
os.makedirs('static/charts', exist_ok=True)
os.makedirs('logs', exist_ok=True)
os.makedirs(backup_path, exist_ok=True)


@app.route('/')
def index():
    """Главная страница"""
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index: {e}")
        return f"Error: {e}", 500


@app.route('/health')
def health_check():
    """Проверка состояния сервиса"""
    status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'database': 'sqlite',
        'version': '1.0.0'
    }
    return jsonify(status)


@app.route('/backup/create', methods=['POST'])
@token_required
@admin_required
def create_backup():
    """Создание резервной копии данных"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_path, f"sea_level_backup_{timestamp}.db")

        if db.engine.dialect.name == 'sqlite':
            import sqlite3
            source_proxy = db.engine.raw_connection()
            source = source_proxy.driver_connection
            destination = sqlite3.connect(backup_file)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source_proxy.close()
            return jsonify({
                'status': 'success',
                'message': 'Backup created successfully',
                'file': backup_file
            })
        return jsonify({'status': 'error', 'message': 'SQLite backup endpoint is unavailable for this database engine'}), 501

    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


# Gunicorn imports the module without executing the __main__ block. Initialize
# the schema and idempotent demonstration data in both local and hosted runs.
with app.app_context():
    Base.metadata.create_all(db.engine)
    if db.engine.dialect.name == 'sqlite':
        # Incremental safeguards for SQLite files created before these rules existed.
        from sqlalchemy import text
        with db.engine.begin() as connection:
            connection.execute(text('CREATE INDEX IF NOT EXISTS ix_measurements_station_date ON tide_gauge_measurements (station_id, measurement_date)'))
            connection.execute(text("CREATE TRIGGER IF NOT EXISTS ck_measurement_quality_insert BEFORE INSERT ON tide_gauge_measurements WHEN NEW.data_quality_score IS NOT NULL AND NEW.data_quality_score NOT BETWEEN 1 AND 10 BEGIN SELECT RAISE(ABORT, 'data_quality_score must be 1..10'); END"))
            connection.execute(text("CREATE TRIGGER IF NOT EXISTS ck_measurement_quality_update BEFORE UPDATE OF data_quality_score ON tide_gauge_measurements WHEN NEW.data_quality_score IS NOT NULL AND NEW.data_quality_score NOT BETWEEN 1 AND 10 BEGIN SELECT RAISE(ABORT, 'data_quality_score must be 1..10'); END"))
            connection.execute(text("CREATE TRIGGER IF NOT EXISTS ck_risk_level_insert BEFORE INSERT ON risk_zones WHEN NEW.risk_level IS NOT NULL AND NEW.risk_level NOT BETWEEN 1 AND 5 BEGIN SELECT RAISE(ABORT, 'risk_level must be 1..5'); END"))
            connection.execute(text("CREATE TRIGGER IF NOT EXISTS ck_risk_level_update BEFORE UPDATE OF risk_level ON risk_zones WHEN NEW.risk_level IS NOT NULL AND NEW.risk_level NOT BETWEEN 1 AND 5 BEGIN SELECT RAISE(ABORT, 'risk_level must be 1..5'); END"))
    init_test_data(db.session)
    logger.info("Database schema is ready")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
