import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = 'clave-nueva-2026-ucundinamarca'

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'ucundinamarca.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    MAX_LOGIN_ATTEMPTS = 5
    LOCK_TIME_MINUTES = 15

    ALLOWED_EMAIL_DOMAIN = 'ucundinamarca.edu.co'

    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'gestionudec2026@gmail.com'
    MAIL_PASSWORD = 'dkmghbexmlxaugnd'
    MAIL_DEFAULT_SENDER = 'gestionudec2026@gmail.com'
    
    
    ##################para el correo @ucundinamarca###############
   # MAIL_SERVER   = 'smtp.office365.com'
   # MAIL_PORT     = 587
   # MAIL_USE_TLS  = True
   # MAIL_USERNAME = 'tu_correo@ucundinamarca.edu.co'
   # MAIL_PASSWORD = 'tu_contraseña_institucional'
   # MAIL_DEFAULT_SENDER = 'tu_correo@ucundinamarca.edu.co'