from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Inicializar extensiones
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # Configurar login_manager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Debes iniciar sesión para acceder a esta página.'
    login_manager.login_message_category = 'warning'

    # Registrar blueprints
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Ruta raíz → redirige al login
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    # Crear tablas si no existen
    with app.app_context():
        db.create_all()
        _seed_default_admin()

    return app


def _seed_default_admin():
    """Crea el administrador por defecto si no existe ningún usuario."""
    from app.models import User, Role
    
    # Crear roles si no existen
    roles_data = [
        ('administrador', 'Administrador del sistema'),
        ('docente', 'Docente universitario'),
        ('estudiante', 'Estudiante universitario'),
        ('operador', 'Operador de recursos y espacios'),
        ('invitado', 'Usuario invitado temporal'),
    ]
    for name, desc in roles_data:
        if not Role.query.filter_by(name=name).first():
            db.session.add(Role(name=name, description=desc))
    db.session.commit()

    # Crear admin por defecto si no existe
    if not User.query.filter_by(email='admin@ucundinamarca.edu.co').first():
        admin_role = Role.query.filter_by(name='administrador').first()
        admin = User(
            nombre='Administrador',
            apellido='Sistema',
            email='admin@ucundinamarca.edu.co',
            role_id=admin_role.id,
            activo=True
        )
        admin.set_password('Admin123*')
        db.session.add(admin)
        db.session.commit()
        print('✅ Admin por defecto creado: admin@ucundinamarca.edu.co / Admin123*')