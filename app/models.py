from app import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    users = db.relationship('User', backref='role', lazy='dynamic')

    def __repr__(self):
        return f'<Role {self.name}>'


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    
    # Control de intentos fallidos (HU-1, escenario 2)
    intentos_fallidos = db.Column(db.Integer, default=0)
    bloqueado_hasta = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def esta_bloqueado(self):
        """Verifica si la cuenta está bloqueada por intentos fallidos."""
        if self.bloqueado_hasta and datetime.utcnow() < self.bloqueado_hasta:
            return True
        return False

    def registrar_intento_fallido(self, max_intentos=5, minutos_bloqueo=15):
        """Incrementa intentos y bloquea si supera el límite."""
        from datetime import timedelta
        self.intentos_fallidos += 1
        if self.intentos_fallidos >= max_intentos:
            self.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=minutos_bloqueo)
        db.session.commit()

    def resetear_intentos(self):
        """Resetea los intentos al iniciar sesión exitosamente."""
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        db.session.commit()

    def get_role_name(self):
        return self.role.name if self.role else 'sin_rol'

    def __repr__(self):
        return f'<User {self.email}>'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))