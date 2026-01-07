from django.apps import AppConfig
import os

class MainappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mainapp"

    def ready(self):
        # If using MariaDB/MySQL with PyMySQL, provide MySQLdb shim
        if os.getenv("DB_ENGINE", "").lower() in ("mariadb", "mysql"):
            try:
                import pymysql
                pymysql.install_as_MySQLdb()
            except Exception:
                pass
