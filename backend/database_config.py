import os


class DatabaseConfig:
    # Для Amvera используем /data, для локальной разработки - текущую папку
    DB_PATH = "/data/sea_level.db" if "AMVERA" in os.environ else "sea_level.db"

    @property
    def database_url(self):
        return f"sqlite:///{self.DB_PATH}"


db_config = DatabaseConfig()