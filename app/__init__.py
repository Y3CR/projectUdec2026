from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Debes iniciar sesión para acceder a esta página.'
    login_manager.login_message_category = 'warning'

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.operador import bp as operador_bp
    app.register_blueprint(operador_bp, url_prefix='/operador')

    from app.prestamos import bp as prestamos_bp
    app.register_blueprint(prestamos_bp, url_prefix='/prestamos')

    from app.reportes import bp as reportes_bp
    app.register_blueprint(reportes_bp, url_prefix='/reportes')

    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    csrf.exempt(api_bp)

    from app.accesos import bp as accesos_bp
    app.register_blueprint(accesos_bp, url_prefix='/accesos')

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    with app.app_context():
        db.create_all()
        _seed_data()

    return app


def _seed_data():
    from app.models import User, Role, TipoEspacio, CategoriaRecurso

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
        print('✅ Admin creado: admin@ucundinamarca.edu.co / Admin123*')

    tipos = ['Salón de clase', 'Laboratorio', 'Auditorio', 'Sala de reuniones', 'Cancha deportiva', 'Biblioteca']
    for t in tipos:
        if not TipoEspacio.query.filter_by(nombre=t).first():
            db.session.add(TipoEspacio(nombre=t))
    db.session.commit()

    categorias = ['Equipos de cómputo', 'Equipos audiovisuales', 'Material deportivo', 'Herramientas', 'Mobiliario', 'Instrumentos musicales']
    for c in categorias:
        if not CategoriaRecurso.query.filter_by(nombre=c).first():
            db.session.add(CategoriaRecurso(nombre=c))
    db.session.commit()