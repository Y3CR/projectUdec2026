<<<<<<< HEAD
# projectUdec2026
DESARROLLO E IMPLEMENTACIÓN DE UNA PLATAFORMA WEB PARA EL  CONTROL Y LA ADMINISTRACIÓN DE ESPACIOS Y RECURSOS FÍSICOS  UNIVERSITARIOS BASADA EN DATOS DE TECNOLOGÍA DE IDENTIFICACIÓN  INMEDIATA (RFID, QR, CÓDIGO DE BARRAS), EN LA UNIVERSIDAD DE  CUNDINAMARCA, EXTENSIÓN FACATATIVÁ.
=======
# Sistema de Préstamos de Espacios y Recursos — UCundinamarca

Sistema web para gestionar préstamos de espacios físicos y recursos institucionales, construido con Python + Flask.

## Stack tecnológico

- **Backend:** Python 3.10+ / Flask 3.0
- **Base de datos:** SQLite (desarrollo) — fácilmente migrable a PostgreSQL
- **ORM:** Flask-SQLAlchemy
- **Autenticación:** Flask-Login
- **Formularios:** Flask-WTF / WTForms
- **Frontend:** Bootstrap 5 + Bootstrap Icons

---

## Instalación rápida

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd ucundinamarca_prestamos

# 2. Crear entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Ejecutar
python run.py
```

Abre tu navegador en: **http://127.0.0.1:5000/auth/login**

### Credenciales por defecto (admin)
| Campo | Valor |
|---|---|
| Correo | `admin@ucundinamarca.edu.co` |
| Contraseña | `Admin123*` |

> ⚠️ Cambia la contraseña del admin después del primer inicio de sesión.

---

## Sprints

| Sprint | Descripción | Estado |
|---|---|---|
| **Sprint 1** | Autenticación y gestión de usuarios/roles | ✅ Completado |
| Sprint 2 | Gestión de espacios y recursos | 🔜 Pendiente |
| Sprint 3 | Solicitudes, asignación y préstamos | 🔜 Pendiente |
| Sprint 4 | Historial, reportes y exportación | 🔜 Pendiente |
| Sprint 5 | Control de acceso RFID/QR y trazabilidad | 🔜 Pendiente |

---

## Funcionalidades Sprint 1

- ✅ Login con correo y contraseña
- ✅ Validación de dominio `@ucundinamarca.edu.co` para roles internos
- ✅ Bloqueo temporal tras 5 intentos fallidos (15 minutos)
- ✅ Cierre automático de sesión por inactividad (30 minutos)
- ✅ Gestión CRUD de usuarios (admin)
- ✅ Gestión de roles (admin)
- ✅ Panel diferenciado por rol
>>>>>>> 1539b97 (Sprint 1: autenticación, gestión de usuarios y roles)
