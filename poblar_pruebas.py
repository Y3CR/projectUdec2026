import os
import random
from datetime import datetime, timedelta

from dotenv import load_dotenv
from faker import Faker
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

load_dotenv()

from app import db
import app.models as m

fake = Faker("es_CO")
Faker.seed(42)
random.seed(42)

src = create_engine("sqlite:///ucundinamarca.db")
dst = create_engine(URL.create(
    "mssql+pyodbc",
    host=os.environ["DB_HOST"],
    database=os.environ["DB_NAME"],
    query={"driver": "ODBC Driver 17 for SQL Server",
           "Trusted_Connection": "yes"},
))
Session = sessionmaker(bind=dst)
s = Session()

HOY = datetime.now()
INICIO = HOY - timedelta(days=30)

def uid_unico():
    while True:
        u = "".join(random.choice("0123456789ABCDEF") for _ in range(8))
        if not s.execute(select(m.Tarjeta).where(m.Tarjeta.uid == u)).first():
            return u

def codigo_unico(modelo, campo, prefijo, n=4):
    while True:
        c = f"{prefijo}-{random.randint(1000, 9999)}"
        if not s.execute(select(modelo).where(getattr(modelo, campo) == c)).first():
            return c

# ── 1. Roles base ──────────────────────────────────────────────────────────────
roles = {}
for r in s.execute(select(m.Role)).scalars():
    roles[r.name] = r
for name, desc in [("docente", "Docente universitario"),
                   ("estudiante", "Estudiante universitario"),
                   ("operador", "Operador de recursos y espacios")]:
    if name not in roles:
        rol = m.Role(name=name, description=desc)
        s.add(rol)
        s.flush()
        roles[name] = rol

# ── 2. Tipos de espacio y categorías ──────────────────────────────────────────
tipos = {}
for t in s.execute(select(m.TipoEspacio)).scalars():
    tipos[t.nombre] = t
for nombre in ["Salón de clase", "Laboratorio", "Auditorio",
               "Sala de reuniones", "Cancha deportiva", "Biblioteca"]:
    if nombre not in tipos:
        t = m.TipoEspacio(nombre=nombre)
        s.add(t)
        s.flush()
        tipos[nombre] = t

cats = {}
for c in s.execute(select(m.CategoriaRecurso)).scalars():
    cats[c.nombre] = c
for nombre in ["Equipos de cómputo", "Equipos audiovisuales",
               "Material deportivo", "Herramientas", "Mobiliario",
               "Instrumentos musicales"]:
    if nombre not in cats:
        c = m.CategoriaRecurso(nombre=nombre)
        s.add(c)
        s.flush()
        cats[nombre] = c

# ── 3. Espacios nuevos ─────────────────────────────────────────────────────────
espacios_nuevos = [
    ("Laboratorio de Redes", "LAB-RED-01", "Laboratorio", 30, "Bloque B - Piso 2"),
    ("Laboratorio de Electrónica", "LAB-ELE-01", "Laboratorio", 25, "Bloque B - Piso 1"),
    ("Auditorio Principal", "AUD-PRIN-01", "Auditorio", 300, "Bloque Central"),
    ("Sala de Reuniones A", "SALA-REA-01", "Sala de reuniones", 12, "Bloque A - Piso 3"),
    ("Sala de Reuniones B", "SALA-REA-02", "Sala de reuniones", 8, "Bloque A - Piso 3"),
    ("Cancha de Fútbol", "CAN-FUT-01", "Cancha deportiva", 22, "Zona Deportiva"),
    ("Cancha de Baloncesto", "CAN-BAS-01", "Cancha deportiva", 20, "Zona Deportiva"),
    ("Biblioteca Central", "BIB-CEN-01", "Biblioteca", 150, "Bloque C - Piso 1"),
    ("Salón 201", "SAL-201", "Salón de clase", 40, "Bloque A - Piso 2"),
    ("Salón 305", "SAL-305", "Salón de clase", 35, "Bloque A - Piso 3"),
]
espacios = list(s.execute(select(m.Espacio)).scalars())
for nombre, codigo, tipo, cap, ubic in espacios_nuevos:
    if not s.execute(select(m.Espacio).where(m.Espacio.codigo == codigo)).first():
        e = m.Espacio(nombre=nombre, codigo=codigo, tipo_id=tipos[tipo].id,
                      capacidad=cap, ubicacion=ubic, disponible=True)
        s.add(e)
        s.flush()
        espacios.append(e)

# ── 4. Dispositivos RFID nuevos ────────────────────────────────────────────────
dispositivos = list(s.execute(select(m.DispositivoRFID)).scalars())
for e in espacios:
    cod = f"RFID-{e.codigo}"
    if not s.execute(select(m.DispositivoRFID).where(m.DispositivoRFID.codigo == cod)).first():
        d = m.DispositivoRFID(nombre=f"Lector {e.nombre}", codigo=cod,
                              espacio_id=e.id, activo=True)
        s.add(d)
        s.flush()
        dispositivos.append(d)

# ── 5. Recursos nuevos ─────────────────────────────────────────────────────────
recursos_base = [
    ("Portátil Lenovo ThinkPad", "Equipos de cómputo", "PORT"),
    ("Portátil HP ProBook", "Equipos de cómputo", "PORT"),
    ("Proyector Epson", "Equipos audiovisuales", "PROY"),
    ("Parlante Bluetooth JBL", "Equipos audiovisuales", "PARL"),
    ("Micrófono Inalámbrico", "Equipos audiovisuales", "MIC"),
    ("Balón de Fútbol", "Material deportivo", "BALON"),
    ("Balón de Baloncesto", "Material deportivo", "BALON"),
    ("Red de Voleibol", "Material deportivo", "RED"),
    ("Taladro Eléctrico", "Herramientas", "HERR"),
    ("Multímetro Digital", "Herramientas", "MULT"),
    ("Mesa Plegable", "Mobiliario", "MESA"),
    ("Silla Acolchada", "Mobiliario", "SILLA"),
    ("Guitarra Acústica", "Instrumentos musicales", "GUIT"),
    ("Teclado Musical", "Instrumentos musicales", "TECL"),
]
recursos = list(s.execute(select(m.Recurso)).scalars())
for nombre, cat, pref in recursos_base:
    cod = f"{pref}-{random.randint(100, 999)}"
    if not s.execute(select(m.Recurso).where(m.Recurso.codigo == cod)).first():
        r = m.Recurso(nombre=nombre, codigo=cod,
                      serial=f"SN-{random.randint(100000, 999999)}",
                      codigo_interno=cod, categoria_id=cats[cat].id,
                      estado="disponible")
        s.add(r)
        s.flush()
        recursos.append(r)

# ── 6. Usuarios nuevos ─────────────────────────────────────────────────────────
usuarios = []
for i in range(10):
    nombre, apellido = fake.first_name(), fake.last_name()
    email = f"{nombre.lower()}.{apellido.lower()}{i+1}@ucundinamarca.edu.co"
    if s.execute(select(m.User).where(m.User.email == email)).first():
        continue
    u = m.User(nombre=nombre, apellido=apellido, email=email,
               role_id=roles["docente"].id, activo=True)
    u.set_password("Prueba123*")
    s.add(u)
    s.flush()
    s.add(m.Tarjeta(uid=uid_unico(), usuario_id=u.id))
    usuarios.append(u)

for i in range(10):
    nombre, apellido = fake.first_name(), fake.last_name()
    email = f"{nombre.lower()}.{apellido.lower()}{i+11}@ucundinamarca.edu.co"
    if s.execute(select(m.User).where(m.User.email == email)).first():
        continue
    u = m.User(nombre=nombre, apellido=apellido, email=email,
               role_id=roles["estudiante"].id, activo=True)
    u.set_password("Prueba123*")
    s.add(u)
    s.flush()
    s.add(m.Tarjeta(uid=uid_unico(), usuario_id=u.id))
    usuarios.append(u)

s.commit()
print(f"Usuarios nuevos: {len(usuarios)}")

# ── 7. Solicitudes y permisos RFID ─────────────────────────────────────────────
operador = s.execute(select(m.User).where(m.User.email == "admin@ucundinamarca.edu.co")).scalar_one()
for u in usuarios:
    for d in random.sample(dispositivos, k=random.randint(1, 3)):
        if s.execute(select(m.PermisoAcceso).where(
                m.PermisoAcceso.usuario_id == u.id,
                m.PermisoAcceso.dispositivo_id == d.id)).first():
            continue
        fecha = INICIO + timedelta(days=random.randint(0, 29),
                                   hours=random.randint(6, 20))
        sol = m.Solicitud(usuario_id=u.id, tipo="rfid",
                          uid_tarjeta=u.tarjeta.uid, motivo=fake.sentence(),
                          estado="aprobada", operador_id=operador.id,
                          fecha_gestion=fecha, fecha_creacion=fecha)
        s.add(sol)
        s.flush()
        s.add(m.SolicitudDispositivo(solicitud_id=sol.id, dispositivo_id=d.id))
        s.add(m.PermisoAcceso(usuario_id=u.id, dispositivo_id=d.id, activo=True,
                              fecha_creacion=fecha))
s.commit()

# ── 8. Solicitudes de recursos ─────────────────────────────────────────────────
estados = ["pendiente", "aprobada", "entregado", "devuelta", "rechazada"]
for u in usuarios:
        r = random.choice(recursos)
        rec = s.get(m.Recurso, r.id)
        fecha = INICIO + timedelta(days=random.randint(0, 29),
                                   hours=random.randint(6, 20))
        estado = random.choice(estados)
        fin = fecha + timedelta(days=random.randint(1, 5))
        sol = m.Solicitud(usuario_id=u.id, tipo="recurso", recurso_id=rec.id,
                          fecha_fin=fin, motivo=fake.sentence(),
                          estado=estado, operador_id=operador.id,
                          fecha_gestion=fecha, fecha_creacion=fecha)
        if estado in ("entregado", "devuelta"):
            sol.fecha_inicio = fecha + timedelta(hours=1)
            rec.estado = "prestado" if estado == "entregado" else "disponible"
        if estado == "devuelta":
            sol.fecha_devolucion_real = sol.fecha_inicio + timedelta(hours=random.randint(2, 48))
            sol.estado_devolucion = random.choice(["bueno", "bueno", "dañado"])
            sol.calcular_tiempo_uso()
        if estado == "rechazada":
            sol.motivo_rechazo = fake.sentence()
        if estado == "pendiente":
            sol.operador_id = None
            sol.fecha_gestion = None
        s.add(sol)
s.commit()

# ── 9. Registros de acceso coherentes ──────────────────────────────────────────
for u in usuarios:
    permisos = s.execute(select(m.PermisoAcceso).where(
        m.PermisoAcceso.usuario_id == u.id)).scalars().all()
    for _ in range(random.randint(3, 8)):
        p = random.choice(permisos)
        d = s.get(m.DispositivoRFID, p.dispositivo_id)
        entrada = INICIO + timedelta(days=random.randint(0, 29),
                                     hours=random.randint(6, 20),
                                     minutes=random.randint(0, 59))
        autorizado = random.random() > 0.15
        reg = m.RegistroAcceso(uid_tarjeta=u.tarjeta.uid, usuario_id=u.id,
                               espacio_id=d.espacio_id, dispositivo_id=d.id,
                               tipo_evento="entrada", metodo="rfid",
                               autorizado=autorizado, fecha_evento=entrada)
        if not autorizado:
            reg.motivo_denegacion = random.choice([
                "Fuera de horario permitido",
                "Tarjeta sin permiso para este dispositivo",
                "Usuario inactivo"])
        else:
            salida = entrada + timedelta(minutes=random.randint(30, 240))
            reg_sal = m.RegistroAcceso(uid_tarjeta=u.tarjeta.uid, usuario_id=u.id,
                                       espacio_id=d.espacio_id, dispositivo_id=d.id,
                                       tipo_evento="salida", metodo="rfid",
                                       autorizado=True, fecha_evento=salida,
                                       tiempo_permanencia_minutos=int((salida-entrada).total_seconds()/60))
            s.add(reg_sal)
        s.add(reg)
s.commit()

# ── 10. Resumen ────────────────────────────────────────────────────────────────
print("Espacios:", s.execute(select(m.Espacio)).scalars().all().__len__())
print("Dispositivos:", len(s.execute(select(m.DispositivoRFID)).scalars().all()))
print("Recursos:", len(s.execute(select(m.Recurso)).scalars().all()))
print("Solicitudes:", len(s.execute(select(m.Solicitud)).scalars().all()))
print("Permisos:", len(s.execute(select(m.PermisoAcceso)).scalars().all()))
print("Registros:", len(s.execute(select(m.RegistroAcceso)).scalars().all()))
s.close()