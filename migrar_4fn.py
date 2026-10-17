import sqlite3, shutil, json, datetime
DB = "ucundinamarca.db"
shutil.copy(DB, f"{DB}.bak_{datetime.datetime.now():%Y%m%d_%H%M%S}")
c = sqlite3.connect(DB)
c.execute("PRAGMA foreign_keys=OFF")
print("SQLite", sqlite3.sqlite_version)

c.executescript("""
CREATE TABLE IF NOT EXISTS tarjetas(
  id INTEGER PRIMARY KEY,
  uid VARCHAR(50) NOT NULL UNIQUE,
  usuario_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
  fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS solicitud_dispositivos(
  solicitud_id INTEGER NOT NULL REFERENCES solicitudes(id),
  dispositivo_id INTEGER NOT NULL REFERENCES dispositivos_rfid(id),
  PRIMARY KEY(solicitud_id, dispositivo_id));
""")

c.execute("""INSERT OR IGNORE INTO tarjetas(uid, usuario_id)
  SELECT TRIM(uid_tarjeta), id FROM users
  WHERE uid_tarjeta IS NOT NULL AND TRIM(uid_tarjeta)<>''""")

bad = c.execute("""SELECT COUNT(*) FROM permisos_acceso p JOIN users u ON u.id=p.usuario_id
  WHERE IFNULL(u.uid_tarjeta,'')<>p.uid_tarjeta""").fetchone()[0]
print("permisos con UID distinto al del usuario:", bad)

disp = {r[0] for r in c.execute("SELECT id FROM dispositivos_rfid")}
for sid, js in c.execute("SELECT id, dispositivos_solicitados FROM solicitudes "
                         "WHERE dispositivos_solicitados IS NOT NULL").fetchall():
    try: ids = {int(i) for i in json.loads(js)}
    except Exception: continue
    for d in ids & disp:
        c.execute("INSERT OR IGNORE INTO solicitud_dispositivos VALUES(?,?)", (sid, d))

c.execute("ALTER TABLE users DROP COLUMN uid_tarjeta")
c.execute("ALTER TABLE permisos_acceso DROP COLUMN uid_tarjeta")
c.execute("ALTER TABLE solicitudes DROP COLUMN dispositivos_solicitados")
c.commit()
for t in ("tarjetas", "solicitud_dispositivos"):
    print(t, c.execute(f"select count(*) from {t}").fetchone()[0])
c.close