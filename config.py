import os
from datetime import timedelta

from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


def _database_uri():
    if os.environ.get('DATABASE_URL'):
        return os.environ['DATABASE_URL']
    if os.environ.get('USE_SQLITE') == '1':
        return 'sqlite:///' + os.path.join(basedir, 'ucundinamarca.db')
    return URL.create(
        "mssql+pyodbc",
        host=os.environ["DB_HOST"],
        database=os.environ["DB_NAME"],
        query={"driver": "ODBC Driver 17 for SQL Server",
               "Trusted_Connection": "yes"},
    ).render_as_string(hide_password=False)


class Config:
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SECRET_KEY = os.environ.get('SECRET_KEY', 'cambia-esto-en-env')

    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    MAX_LOGIN_ATTEMPTS = 5
    LOCK_TIME_MINUTES = 15

    ALLOWED_EMAIL_DOMAIN = 'ucundinamarca.edu.co'

    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'gestionudec2026@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_USERNAME', 'gestionudec2026@gmail.com')