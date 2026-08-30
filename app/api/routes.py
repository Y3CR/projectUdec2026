from flask import request, jsonify, current_app
from datetime import datetime
from app import db
from app.api import bp
from app.models import User, Espacio, Solicitud

# Clave secreta para autenticar el ESP32
API_KEY = 'ucundinamarca-rfid-2024'


def verificar_api_key():
    key = request.headers.get('X-API-KEY', '')
    return key == API_KEY


@bp.route('/acceso', methods=['POST'])
def registrar_acceso():
    """
    Recibe datos del ESP32/RC522 y registra el evento de acceso.
    Body JSON esperado:
    {
        "uid_tarjeta": "A1B2C3D4",
        "usuario_email": "docente@ucundinamarca.edu.co",
        "espacio_codigo": "LAB-SIS-01",
        "tipo_evento": "entrada",
        "metodo": "rfid",
        "autorizado": true
    }
    """
    # Verificar API key
    if not verificar_api_key():
        return jsonify({'error': 'No autorizado', 'code': 401}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON inválido'}), 400

    # Campos requeridos
    uid_tarjeta    = data.get('uid_tarjeta', '').strip().upper()
    usuario_email  = data.get('usuario_email', '').strip().lower()
    espacio_codigo = data.get('espacio_codigo', '').strip().upper()
    tipo_evento    = data.get('tipo_evento', 'entrada')
    metodo         = data.get('metodo', 'rfid')
    autorizado     = data.get('autorizado', False)

    if not uid_tarjeta or not espacio_codigo:
        return jsonify({'error': 'uid_tarjeta y espacio_codigo son requeridos'}), 400

    # Buscar usuario
    usuario = User.query.filter_by(email=usuario_email).first()
    usuario_id = usuario.id if usuario else None

    # Buscar espacio
    espacio = Espacio.query.filter_by(codigo=espacio_codigo).first()
    espacio_id = espacio.id if espacio else None

    # Verificar si tiene solicitud aprobada activa (solo si el usuario existe)
    acceso_valido = False
    if usuario and espacio and autorizado:
        ahora = datetime.utcnow()
        solicitud_activa = Solicitud.query.filter(
            Solicitud.usuario_id == usuario.id,
            Solicitud.espacio_id == espacio.id,
            Solicitud.estado == 'aprobada',
            Solicitud.fecha_inicio <= ahora,
            Solicitud.fecha_fin >= ahora
        ).first()
        acceso_valido = solicitud_activa is not None
    
    # Guardar registro de acceso
    from app.models import RegistroAcceso
    registro = RegistroAcceso(
        uid_tarjeta=uid_tarjeta,
        usuario_id=usuario_id,
        espacio_id=espacio_id,
        tipo_evento=tipo_evento,
        metodo=metodo,
        autorizado=acceso_valido,
        motivo_denegacion=None if acceso_valido else _motivo_denegacion(
            usuario, espacio, autorizado
        ),
        fecha_evento=datetime.utcnow()
    )
    db.session.add(registro)
    db.session.commit()

    # Respuesta al ESP32
    return jsonify({
        'success': True,
        'registro_id': registro.id,
        'autorizado': acceso_valido,
        'mensaje': 'Acceso permitido' if acceso_valido else 'Acceso denegado',
        'usuario': f"{usuario.nombre} {usuario.apellido}" if usuario else 'Desconocido',
        'espacio': espacio.nombre if espacio else espacio_codigo,
        'tipo_evento': tipo_evento,
        'timestamp': datetime.utcnow().isoformat()
    }), 200


@bp.route('/acceso/estado', methods=['GET'])
def estado_api():
    """Endpoint de prueba para verificar que la API está activa."""
    return jsonify({
        'status': 'online',
        'sistema': 'UCundinamarca Préstamos',
        'timestamp': datetime.utcnow().isoformat()
    }), 200


def _motivo_denegacion(usuario, espacio, autorizado_hardware):
    if not autorizado_hardware:
        return 'Tarjeta no registrada en el sistema'
    if not usuario:
        return 'Usuario no encontrado'
    if not usuario.activo:
        return 'Cuenta de usuario inactiva'
    if not espacio:
        return 'Espacio no encontrado'
    return 'Sin reserva activa para este espacio y horario'
