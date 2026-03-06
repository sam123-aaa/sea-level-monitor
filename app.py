import os
import logging
from flask import Flask, render_template, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime

# Загружаем переменные окружения
load_dotenv()

# Импортируем наши модули
from backend.database_config import db_config
from backend.models import Base, init_test_data
from backend.api import api_bp
from backend.security import BackupManager

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
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = db_config.database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JSON_AS_ASCII'] = False  # Для поддержки кириллицы

# Инициализация расширений
db = SQLAlchemy(app)
CORS(app)

# Регистрируем blueprint API
app.register_blueprint(api_bp)

# Инициализируем менеджер бэкапов
backup_manager = BackupManager(os.getenv('BACKUP_PATH', './backups'))

# Создаем необходимые папки
os.makedirs('static/charts', exist_ok=True)
os.makedirs('logs', exist_ok=True)
os.makedirs('backups', exist_ok=True)


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


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


@app.route('/reset-db')
def reset_database():
    """Сброс базы данных (для разработки)"""
    try:
        # Удаляем файл базы данных
        db_path = 'sea_level.db'
        if os.path.exists(db_path):
            os.remove(db_path)

        # Создаем таблицы заново
        with app.app_context():
            Base.metadata.create_all(db.engine)
            # Инициализируем тестовые данные
            init_test_data(db.session)

        return jsonify({'status': 'success', 'message': 'Database reset complete'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/backup/create', methods=['POST'])
def create_backup():
    """Создание резервной копии данных"""
    try:
        # Просто копируем файл базы данных
        import shutil
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backups/sea_level_backup_{timestamp}.db"

        shutil.copy2('sea_level.db', backup_file)

        return jsonify({
            'status': 'success',
            'message': 'Backup created successfully',
            'file': backup_file
        })
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


if __name__ == '__main__':
    with app.app_context():
        # Создаем таблицы в БД если их нет
        if not os.path.exists('sea_level.db'):
            Base.metadata.create_all(db.engine)
            init_test_data(db.session)
            logger.info(" База данных создана и заполнена тестовыми данными")
        else:
            logger.info(" База данных уже существует")

    # Запускаем приложение
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('DEBUG', 'False').lower() == 'true'
    )