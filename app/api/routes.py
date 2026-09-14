from flask import request, jsonify
from datetime import datetime
from app import db
from app.api import bp
from app.models import User, Espacio, DispositivoRFID, PermisoAcceso, HorarioGlobal, RegistroAcceso
import pytz

BOGOTA_TZ = pytz.timezone('America/Bogota')
API_KEY = 'ucundinamarca-rfid-2024'


def ahora_bogota():
    return datetime.now(BOGOTA_TZ).replace(tzinfo=None)


def verificar_api_key():
    return request.headers.get('X-API-KEY', '') == API_KEY


@bp.route('/acceso', methods=['POST'])
def registrar_acceso():
    if not verificar_api_key():
        return jsonify({'error': 'No autorizado', 'code': 401}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'JSON inválido'}), 400

    uid_tarjeta        = data.get('uid_tarjeta', '').strip().upper()
    dispositivo_codigo = data.get('dispositivo_codigo', '').strip().upper()
    tipo_evento        = data.get('tipo_evento', 'entrada')
    metodo             = data.get('metodo', 'rfid')

    if not uid_tarjeta or not dispositivo_codigo:
        return jsonify({'error': 'uid_tarjeta y dispositivo_codigo son requeridos'}), 400

    ahora = ahora_bogota()

    # Buscar dispositivo
    dispositivo = DispositivoRFID.query.filter_by(
        codigo=dispositivo_codigo, activo=True
    ).first()

    if not dispositivo:
        registro = RegistroAcceso(
            uid_tarjeta=uid_tarjeta,
            tipo_evento=tipo_evento,
            metodo=metodo,
            autorizado=False,
            motivo_denegacion='Dispositivo RFID no registrado o inactivo',
            fecha_evento=ahora
        )
        db.session.add(registro)
        db.session.commit()
        return jsonify({
            'success': True,
            'autorizado': False,
            'mensaje': 'Dispositivo no reconocido',
            'registro_id': registro.id,
            'timestamp': ahora.isoformat()
        }), 200

    # Verificar horario global
    horario_global = HorarioGlobal.query.filter_by(activo=True).first()
    if horario_global and not horario_global.en_horario_permitido(ahora):
        registro = RegistroAcceso(
            uid_tarjeta=uid_tarjeta,
            dispositivo_id=dispositivo.id,
            espacio_id=dispositivo.espacio_id,
            tipo_evento=tipo_evento,
            metodo=metodo,
            autorizado=False,
            motivo_denegacion=f'Fuera del horario permitido ({horario_global.hora_inicio} - {horario_global.hora_fin})',
            fecha_evento=ahora
        )
        db.session.add(registro)
        db.session.commit()
        return jsonify({
            'success': True,
            'autorizado': False,
            'mensaje': f'Acceso fuera de horario ({horario_global.hora_inicio} - {horario_global.hora_fin})',
            'registro_id': registro.id,
            'timestamp': ahora.isoformat()
        }), 200

    # Buscar permiso de acceso
    permiso = PermisoAcceso.query.filter_by(
        uid_tarjeta=uid_tarjeta,
        dispositivo_id=dispositivo.id,
        activo=True
    ).first()

    acceso_valido = False
    motivo_denegacion = None
    usuario = None

    if not permiso:
        motivo_denegacion = 'Tarjeta sin permiso para este dispositivo'
    else:
        usuario = permiso.usuario
        if not usuario.activo:
            motivo_denegacion = 'Cuenta de usuario inactiva'
        elif not permiso.en_horario_permitido(ahora, horario_global):
            h_ini = permiso.hora_inicio or (horario_global.hora_inicio if horario_global else '?')
            h_fin = permiso.hora_fin or (horario_global.hora_fin if horario_global else '?')
            motivo_denegacion = f'Fuera del horario asignado ({h_ini} - {h_fin})'
        else:
            acceso_valido = True

    registro = RegistroAcceso(
        uid_tarjeta=uid_tarjeta,
        usuario_id=usuario.id if usuario else None,
        espacio_id=dispositivo.espacio_id,
        dispositivo_id=dispositivo.id,
        tipo_evento=tipo_evento,
        metodo=metodo,
        autorizado=acceso_valido,
        motivo_denegacion=motivo_denegacion,
        fecha_evento=ahora
    )
    db.session.add(registro)
    db.session.commit()

    return jsonify({
        'success': True,
        'autorizado': acceso_valido,
        'mensaje': 'Acceso permitido' if acceso_valido else 'Acceso denegado',
        'usuario': f"{usuario.nombre} {usuario.apellido}" if usuario else 'Desconocido',
        'espacio': dispositivo.espacio.nombre if dispositivo.espacio else dispositivo_codigo,
        'dispositivo': dispositivo.codigo,
        'tipo_evento': tipo_evento,
        'motivo': motivo_denegacion,
        'timestamp': ahora.isoformat()
    }), 200


@bp.route('/acceso/estado', methods=['GET'])
def estado_api():
    horario = HorarioGlobal.query.filter_by(activo=True).first()
    return jsonify({
        'status': 'online',
        'sistema': 'UCundinamarca Préstamos',
        'horario_global': f"{horario.hora_inicio} - {horario.hora_fin}" if horario else 'No configurado',
        'timestamp': ahora_bogota().isoformat()
    }), 200