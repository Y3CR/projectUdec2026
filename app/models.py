import json
from datetime import datetime, time

from flask_login import UserMixin
from sqlalchemy import select
from sqlalchemy.ext.hybrid import hybrid_property
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, login_manager


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
    intentos_fallidos = db.Column(db.Integer, default=0)
    bloqueado_hasta = db.Column(db.DateTime, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow)

    solicitudes = db.relationship(
        'Solicitud',
        foreign_keys='Solicitud.usuario_id',
        backref='usuario',
        lazy='dynamic'
    )
    permisos_acceso = db.relationship('PermisoAcceso', backref='usuario', lazy='dynamic')
    tarjeta = db.relationship('Tarjeta', backref='usuario', uselist=False,
                              cascade='all, delete-orphan')

    # uid_tarjeta ahora vive en la tabla 'tarjetas'; se mantiene como alias
    @hybrid_property
    def uid_tarjeta(self):
        return self.tarjeta.uid if self.tarjeta else None

    @uid_tarjeta.setter
    def uid_tarjeta(self, v):
        v = (v or '').strip()
        if not v:
            self.tarjeta = None
        elif self.tarjeta:
            self.tarjeta.uid = v
        else:
            self.tarjeta = Tarjeta(uid=v)

    @uid_tarjeta.expression
    def uid_tarjeta(cls):
        return select(Tarjeta.uid).where(Tarjeta.usuario_id == cls.id).scalar_subquery()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def esta_bloqueado(self):
        if self.bloqueado_hasta and datetime.utcnow() < self.bloqueado_hasta:
            return True
        return False

    def registrar_intento_fallido(self, max_intentos=5, minutos_bloqueo=15):
        from datetime import timedelta
        self.intentos_fallidos += 1
        if self.intentos_fallidos >= max_intentos:
            self.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=minutos_bloqueo)
        db.session.commit()

    def resetear_intentos(self):
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        db.session.commit()

    def get_role_name(self):
        return self.role.name if self.role else 'sin_rol'

    def tiene_tarjeta(self):
        return bool(self.tarjeta)

    def __repr__(self):
        return f'<User {self.email}>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Tarjeta(db.Model):
    __tablename__ = 'tarjetas'
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(50), unique=True, nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                           unique=True, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Tarjeta {self.uid}>'


class TipoEspacio(db.Model):
    __tablename__ = 'tipos_espacio'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    espacios = db.relationship('Espacio', backref='tipo', lazy='dynamic')

    def __repr__(self):
        return f'<TipoEspacio {self.nombre}>'


class Espacio(db.Model):
    __tablename__ = 'espacios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    tipo_id = db.Column(db.Integer, db.ForeignKey('tipos_espacio.id'), nullable=False)
    capacidad = db.Column(db.Integer, default=1)
    ubicacion = db.Column(db.String(200))
    descripcion = db.Column(db.Text)
    disponible = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow)
    solicitudes = db.relationship('Solicitud', backref='espacio', lazy='dynamic')
    dispositivos = db.relationship('DispositivoRFID', backref='espacio', lazy='dynamic')

    def __repr__(self):
        return f'<Espacio {self.codigo}>'


class CategoriaRecurso(db.Model):
    __tablename__ = 'categorias_recurso'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), unique=True, nullable=False)
    recursos = db.relationship('Recurso', backref='categoria', lazy='dynamic')

    def __repr__(self):
        return f'<CategoriaRecurso {self.nombre}>'


class Recurso(db.Model):
    __tablename__ = 'recursos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    serial = db.Column(db.String(100), nullable=True)
    codigo_interno = db.Column(db.String(50), nullable=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias_recurso.id'),
                             nullable=False)
    descripcion = db.Column(db.Text)
    estado = db.Column(db.String(50), default='disponible')
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow)
    solicitudes = db.relationship('Solicitud', backref='recurso', lazy='dynamic')
    inventario_scans = db.relationship('InventarioScan', backref='recurso', lazy='dynamic')

    __table_args__ = (
        db.Index('uq_recursos_serial', 'serial', unique=True,
                 mssql_where=db.text('serial IS NOT NULL'),
                 sqlite_where=db.text('serial IS NOT NULL')),
        db.Index('uq_recursos_codigo_interno', 'codigo_interno', unique=True,
                 mssql_where=db.text('codigo_interno IS NOT NULL'),
                 sqlite_where=db.text('codigo_interno IS NOT NULL')),
    )

    def esta_disponible(self):
        return self.estado == 'disponible'

    def __repr__(self):
        return f'<Recurso {self.serial or self.nombre}>'
class Solicitud(db.Model):
    __tablename__ = 'solicitudes'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'rfid' o 'recurso'
    espacio_id = db.Column(db.Integer, db.ForeignKey('espacios.id'), nullable=True)
    recurso_id = db.Column(db.Integer, db.ForeignKey('recursos.id'), nullable=True)
    uid_tarjeta = db.Column(db.String(50), nullable=True)

    # Para recursos: fecha_inicio la pone el sistema al entregar
    # fecha_fin la pone el usuario al solicitar (cuándo planea devolver)
    fecha_inicio = db.Column(db.DateTime, nullable=True)
    fecha_fin = db.Column(db.DateTime, nullable=True)
    fecha_fin_extendida = db.Column(db.DateTime, nullable=True)

    motivo = db.Column(db.Text)

    # Estados recurso: pendiente → aprobada → entregado → devuelta
    # Estados rfid:    pendiente → aprobada → rechazada
    estado = db.Column(db.String(20), default='pendiente')
    motivo_rechazo = db.Column(db.Text)

    operador_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    operador = db.relationship('User', foreign_keys=[operador_id])
    fecha_gestion = db.Column(db.DateTime, nullable=True)

    # Devolución
    fecha_devolucion_real = db.Column(db.DateTime, nullable=True)
    estado_devolucion = db.Column(db.String(50), nullable=True)
    novedad_devolucion = db.Column(db.Text, nullable=True)
    tiempo_uso_minutos = db.Column(db.Integer, nullable=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    dispositivos = db.relationship('SolicitudDispositivo', backref='solicitud',
                                   cascade='all, delete-orphan')

    # Alias de compatibilidad: antes era un JSON en una columna de texto
    @property
    def dispositivos_solicitados(self):
        if not self.dispositivos:
            return None
        return json.dumps([d.dispositivo_id for d in self.dispositivos])

    @dispositivos_solicitados.setter
    def dispositivos_solicitados(self, v):
        if isinstance(v, str):
            try:
                v = json.loads(v) if v else []
            except Exception:
                v = []
        ids = set()
        for i in (v or []):
            try:
                ids.add(int(i))
            except (TypeError, ValueError):
                pass
        self.dispositivos = [SolicitudDispositivo(dispositivo_id=i) for i in ids]

    def fecha_fin_efectiva(self):
        return self.fecha_fin_extendida or self.fecha_fin

    def calcular_tiempo_uso(self):
        if self.fecha_devolucion_real and self.fecha_inicio:
            delta = self.fecha_devolucion_real - self.fecha_inicio
            self.tiempo_uso_minutos = int(delta.total_seconds() / 60)

    def get_item_nombre(self):
        if self.tipo == 'rfid':
            return f'Acceso RFID — {self.uid_tarjeta or "sin UID"}'
        elif self.tipo == 'recurso' and self.recurso:
            return self.recurso.nombre
        return '—'

    def get_dispositivos_ids(self):
        return [d.dispositivo_id for d in self.dispositivos]

    def __repr__(self):
        return f'<Solicitud {self.id} - {self.estado}>'


class SolicitudDispositivo(db.Model):
    __tablename__ = 'solicitud_dispositivos'
    solicitud_id = db.Column(db.Integer, db.ForeignKey('solicitudes.id'),
                             primary_key=True)
    dispositivo_id = db.Column(db.Integer, db.ForeignKey('dispositivos_rfid.id'),
                               primary_key=True)


class DispositivoRFID(db.Model):
    __tablename__ = 'dispositivos_rfid'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    espacio_id = db.Column(db.Integer, db.ForeignKey('espacios.id'), nullable=True)
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    permisos = db.relationship('PermisoAcceso', backref='dispositivo', lazy='dynamic')
    registros = db.relationship('RegistroAcceso', backref='dispositivo', lazy='dynamic')

    def __repr__(self):
        return f'<DispositivoRFID {self.codigo}>'


class HorarioGlobal(db.Model):
    __tablename__ = 'horario_global'
    id = db.Column(db.Integer, primary_key=True)
    hora_inicio = db.Column(db.String(5), nullable=False, default='05:00')
    hora_fin = db.Column(db.String(5), nullable=False, default='22:00')
    activo = db.Column(db.Boolean, default=True)
    descripcion = db.Column(db.String(200))
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow)

    def en_horario_permitido(self, hora_actual):
        try:
            h_ini = [int(x) for x in self.hora_inicio.split(':')]
            h_fin = [int(x) for x in self.hora_fin.split(':')]
            t_ini = time(h_ini[0], h_ini[1])
            t_fin = time(h_fin[0], h_fin[1])
            t_actual = hora_actual.time() if hasattr(hora_actual, 'time') else hora_actual
            return t_ini <= t_actual <= t_fin
        except Exception:
            return True

    def __repr__(self):
        return f'<HorarioGlobal {self.hora_inicio}-{self.hora_fin}>'


class PermisoAcceso(db.Model):
    __tablename__ = 'permisos_acceso'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    dispositivo_id = db.Column(db.Integer, db.ForeignKey('dispositivos_rfid.id'),
                               nullable=False)
    hora_inicio = db.Column(db.String(5), nullable=True)
    hora_fin = db.Column(db.String(5), nullable=True)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    # Derivado de la tarjeta del usuario (solo lectura; el setter se ignora)
    @hybrid_property
    def uid_tarjeta(self):
        return self.usuario.uid_tarjeta if self.usuario else None

    @uid_tarjeta.setter
    def uid_tarjeta(self, v):
        pass

    @uid_tarjeta.expression
    def uid_tarjeta(cls):
        return select(Tarjeta.uid).where(
            Tarjeta.usuario_id == cls.usuario_id).scalar_subquery()

    def en_horario_permitido(self, hora_actual, horario_global=None):
        try:
            t_actual = hora_actual.time() if hasattr(hora_actual, 'time') else hora_actual
            if self.hora_inicio and self.hora_fin:
                h_ini = [int(x) for x in self.hora_inicio.split(':')]
                h_fin = [int(x) for x in self.hora_fin.split(':')]
                t_ini = time(h_ini[0], h_ini[1])
                t_fin = time(h_fin[0], h_fin[1])
                return t_ini <= t_actual <= t_fin
            if horario_global and horario_global.activo:
                return horario_global.en_horario_permitido(hora_actual)
            return True
        except Exception:
            return True

    def __repr__(self):
        return f'<PermisoAcceso usuario={self.usuario_id} disp={self.dispositivo_id}>'


class RegistroAcceso(db.Model):
    __tablename__ = 'registros_acceso'
    id = db.Column(db.Integer, primary_key=True)
    uid_tarjeta = db.Column(db.String(50), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    usuario = db.relationship('User', foreign_keys=[usuario_id])
    espacio_id = db.Column(db.Integer, db.ForeignKey('espacios.id'), nullable=True)
    espacio = db.relationship('Espacio', foreign_keys=[espacio_id])
    dispositivo_id = db.Column(db.Integer, db.ForeignKey('dispositivos_rfid.id'),
                               nullable=True)
    tipo_evento = db.Column(db.String(20), default='entrada')
    metodo = db.Column(db.String(20), default='rfid')
    autorizado = db.Column(db.Boolean, default=False)
    motivo_denegacion = db.Column(db.String(200), nullable=True)
    fecha_evento = db.Column(db.DateTime, default=datetime.utcnow)
    tiempo_permanencia_minutos = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f'<RegistroAcceso {self.id}>'


# ── Inventario ─────────────────────────────────────────────────────────────────

class InventarioScan(db.Model):
    __tablename__ = 'inventario_scans'
    id = db.Column(db.Integer, primary_key=True)
    recurso_id = db.Column(db.Integer, db.ForeignKey('recursos.id'), nullable=False)
    operador_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    operador = db.relationship('User', foreign_keys=[operador_id])
    fecha_scan = db.Column(db.DateTime, default=datetime.utcnow)
    observacion = db.Column(db.Text)
    sesion_inventario = db.Column(db.String(50))

    def __repr__(self):
        return f'<InventarioScan recurso={self.recurso_id}>'