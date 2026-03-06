import os
from dotenv import load_dotenv

load_dotenv()


class DatabaseConfig:
    # Для SQLite используем файл базы данных
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sea_level.db')

    @property
    def database_url(self):
        return f"sqlite:///{self.DB_PATH}"


db_config = DatabaseConfig()