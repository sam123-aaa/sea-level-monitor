import os
from dotenv import load_dotenv

load_dotenv()


class DatabaseConfig:
    # Для Amvera используем /data, для локальной разработки - текущую папку
    DB_PATH = "/data/sea_level.db" if os.getenv('AMVERA') else "sea_level.db"

    @property
    def database_url(self):
        return f"sqlite:///{self.DB_PATH}"


db_config = DatabaseConfig()