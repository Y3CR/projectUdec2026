import sqlite3
c = sqlite3.connect("ucundinamarca.db")
q = lambda s: c.execute(s).fetchall()

print("integrity:", q("PRAGMA integrity_check"))
print("FK rotas:", q("PRAGMA foreign_key_check"))
print("users sin uid_tarjeta (esperado):", "uid_tarjeta" not in [r[1] for r in q("PRAGMA table_info(users)")])
print("permisos sin uid_tarjeta (esperado):", "uid_tarjeta" not in [r[1] for r in q("PRAGMA table_info(permisos_acceso)")])
print("solicitudes sin JSON (esperado):", "dispositivos_solicitados" not in [r[1] for r in q("PRAGMA table_info(solicitudes)")])
print("tarjetas huérfanas:", q("SELECT id FROM tarjetas WHERE usuario_id NOT IN (SELECT id FROM users)"))
print("sol_disp huérfanos:", q("""SELECT * FROM solicitud_dispositivos
    WHERE solicitud_id NOT IN (SELECT id FROM solicitudes)
       OR dispositivo_id NOT IN (SELECT id FROM dispositivos_rfid)"""))
print("permisos de usuarios sin tarjeta:", q("""SELECT p.id, p.usuario_id FROM permisos_acceso p
    WHERE p.usuario_id NOT IN (SELECT usuario_id FROM tarjetas)"""))
print("solicitudes rfid sin dispositivos:", q("""SELECT id FROM solicitudes WHERE tipo='rfid'
    AND id NOT IN (SELECT solicitud_id FROM solicitud_dispositivos)"""))