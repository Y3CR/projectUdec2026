from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from functools import wraps
import json
import pytz
from app import db
from app.prestamos import bp
from app.models import Solicitud, Espacio, Recurso, User, DispositivoRFID, PermisoAcceso

BOGOTA_TZ = pytz.timezone('America/Bogota')


def ahora_bogota():
    return datetime.now(BOGOTA_TZ).replace(tzinfo=None)


def usuario_regular_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.get_role_name() not in ['docente', 'estudiante', 'invitado', 'administrador']:
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated


def operador_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.get_role_name() not in ['operador', 'administrador']:
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── Solicitar acceso RFID o recurso ───────────────────────────────────────────

@bp.route('/solicitar', methods=['GET', 'POST'])
@login_required
@usuario_regular_required
def solicitar():
    recursos = Recurso.query.filter(Recurso.cantidad_disponible > 0).all()
    dispositivos = DispositivoRFID.query.filter_by(activo=True).all()

    if request.method == 'POST':
        tipo = request.form.get('tipo', '')

        if tipo == 'rfid':
            # UID viene del usuario, no de un campo manual
            uid_tarjeta = current_user.uid_tarjeta
            dispositivos_ids = request.form.getlist('dispositivos_ids')
            motivo = request.form.get('motivo', '').strip()

            errores = []
            if not uid_tarjeta:
                flash('No tienes una tarjeta RFID asignada. Acércate a administración.', 'warning')
                return redirect(url_for('prestamos.solicitar'))
            if not dispositivos_ids:
                errores.append('Debes seleccionar al menos un dispositivo RFID.')

            if errores:
                for e in errores:
                    flash(e, 'danger')
                return render_template('prestamos/solicitar.html',
                                        recursos=recursos, dispositivos=dispositivos,
                                        data=request.form)

            # Verificar que no tenga ya permiso activo
            for did in dispositivos_ids:
                existente = PermisoAcceso.query.filter_by(
                    usuario_id=current_user.id,
                    dispositivo_id=int(did),
                    activo=True
                ).first()
                if existente:
                    disp = DispositivoRFID.query.get(int(did))
                    flash(f'Ya tienes acceso activo al dispositivo {disp.nombre}.', 'warning')
                    return render_template('prestamos/solicitar.html',
                                            recursos=recursos, dispositivos=dispositivos,
                                            data=request.form)

            solicitud = Solicitud(
                usuario_id=current_user.id,
                tipo='rfid',
                uid_tarjeta=uid_tarjeta,
                dispositivos_solicitados=json.dumps([int(d) for d in dispositivos_ids]),
                motivo=motivo,
                estado='pendiente'
            )
            db.session.add(solicitud)
            db.session.commit()
            _notificar_nueva_solicitud(solicitud)
            flash('Solicitud de acceso RFID enviada. Pendiente de aprobación.', 'success')
            return redirect(url_for('prestamos.mis_solicitudes'))


        elif tipo == 'recurso':
            recurso_id = request.form.get('recurso_id', type=int)
            fecha_inicio_str = request.form.get('fecha_inicio', '')
            fecha_fin_str = request.form.get('fecha_fin', '')
            motivo = request.form.get('motivo', '').strip()

            errores = []
            if not recurso_id:
                errores.append('Debes seleccionar un recurso.')
            fecha_inicio = fecha_fin = None
            if fecha_inicio_str and fecha_fin_str:
                try:
                    fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%dT%H:%M')
                    fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%dT%H:%M')
                    if fecha_inicio >= fecha_fin:
                        errores.append('La fecha de fin debe ser posterior a la de inicio.')
                    if fecha_inicio < ahora_bogota() - timedelta(minutes=5):
                        errores.append('La fecha de inicio no puede ser en el pasado.')
                except ValueError:
                    errores.append('Formato de fecha inválido.')
            else:
                errores.append('Las fechas son obligatorias para recursos.')

            if errores:
                for e in errores:
                    flash(e, 'danger')
                return render_template('prestamos/solicitar.html',
                                       recursos=recursos, dispositivos=dispositivos,
                                       data=request.form)

            recurso = Recurso.query.get(recurso_id)
            if not recurso or recurso.cantidad_disponible <= 0:
                flash('El recurso seleccionado no está disponible.', 'danger')
                return render_template('prestamos/solicitar.html',
                                       recursos=recursos, dispositivos=dispositivos,
                                       data=request.form)

            solicitud = Solicitud(
                usuario_id=current_user.id,
                tipo='recurso',
                recurso_id=recurso_id,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                motivo=motivo,
                estado='pendiente'
            )
            db.session.add(solicitud)
            db.session.commit()
            _notificar_nueva_solicitud(solicitud)
            flash('Solicitud de recurso enviada. Pendiente de aprobación.', 'success')
            return redirect(url_for('prestamos.mis_solicitudes'))

        else:
            flash('Tipo de solicitud inválido.', 'danger')

    return render_template('prestamos/solicitar.html',
                           recursos=recursos, dispositivos=dispositivos, data={})


# ── Mis solicitudes ────────────────────────────────────────────────────────────

@bp.route('/mis-solicitudes')
@login_required
@usuario_regular_required
def mis_solicitudes():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)
    if per_page not in [15, 30, 50]:
        per_page = 15
    estado_filtro = request.args.get('estado', '')

    query = Solicitud.query.filter_by(usuario_id=current_user.id)
    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)

    solicitudes = query.order_by(Solicitud.fecha_creacion.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('prestamos/mis_solicitudes.html',
                           solicitudes=solicitudes,
                           estado_filtro=estado_filtro,
                           per_page=per_page)


# ── Gestionar solicitudes (operador) ──────────────────────────────────────────

@bp.route('/gestionar')
@login_required
@operador_required
def gestionar():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)
    if per_page not in [15, 30, 50]:
        per_page = 15
    estado_filtro = request.args.get('estado', 'pendiente')
    tipo_filtro = request.args.get('tipo', '')

    query = Solicitud.query
    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)
    if tipo_filtro:
        query = query.filter_by(tipo=tipo_filtro)

    solicitudes = query.order_by(Solicitud.fecha_creacion.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('prestamos/gestionar.html',
                           solicitudes=solicitudes,
                           estado_filtro=estado_filtro,
                           tipo_filtro=tipo_filtro,
                           per_page=per_page)


@bp.route('/aprobar/<int:solicitud_id>', methods=['POST'])
@login_required
@operador_required
def aprobar(solicitud_id):
    solicitud = Solicitud.query.get_or_404(solicitud_id)

    if solicitud.estado != 'pendiente':
        flash('Solo se pueden aprobar solicitudes pendientes.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    if solicitud.tipo == 'rfid':
        # Crear PermisoAcceso automáticamente para cada dispositivo solicitado
        dispositivos_ids = solicitud.get_dispositivos_ids()
        permisos_creados = []
        for did in dispositivos_ids:
            dispositivo = DispositivoRFID.query.get(did)
            if not dispositivo:
                continue
            # Evitar duplicados
            existente = PermisoAcceso.query.filter_by(
                uid_tarjeta=solicitud.uid_tarjeta,
                dispositivo_id=did,
                activo=True
            ).first()
            if not existente:
                permiso = PermisoAcceso(
                    usuario_id=solicitud.usuario_id,
                    dispositivo_id=did,
                    uid_tarjeta=solicitud.uid_tarjeta,
                    activo=True
                )
                db.session.add(permiso)
                permisos_creados.append(dispositivo.nombre)

        solicitud.estado = 'aprobada'
        solicitud.operador_id = current_user.id
        solicitud.fecha_gestion = ahora_bogota()
        db.session.commit()
        _notificar_resultado(solicitud)
        flash(f'Solicitud #{solicitud.id} aprobada. '
              f'Permisos creados para: {", ".join(permisos_creados) if permisos_creados else "ninguno nuevo"}.', 'success')

    elif solicitud.tipo == 'recurso':
        if solicitud.recurso:
            if solicitud.recurso.cantidad_disponible <= 0:
                flash('No se puede aprobar: recurso sin unidades disponibles.', 'danger')
                return redirect(url_for('prestamos.gestionar'))
            solicitud.recurso.cantidad_disponible -= 1
            if solicitud.recurso.cantidad_disponible == 0:
                solicitud.recurso.estado = 'prestado'

        solicitud.estado = 'aprobada'
        solicitud.operador_id = current_user.id
        solicitud.fecha_gestion = ahora_bogota()
        db.session.commit()
        _notificar_resultado(solicitud)
        flash(f'Solicitud #{solicitud.id} aprobada correctamente.', 'success')

    return redirect(url_for('prestamos.gestionar'))


@bp.route('/rechazar/<int:solicitud_id>', methods=['POST'])
@login_required
@operador_required
def rechazar(solicitud_id):
    solicitud = Solicitud.query.get_or_404(solicitud_id)

    if solicitud.estado != 'pendiente':
        flash('Solo se pueden rechazar solicitudes pendientes.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    motivo_rechazo = request.form.get('motivo_rechazo', '').strip()
    if not motivo_rechazo:
        flash('Debes indicar el motivo del rechazo.', 'danger')
        return redirect(url_for('prestamos.gestionar'))

    solicitud.estado = 'rechazada'
    solicitud.motivo_rechazo = motivo_rechazo
    solicitud.operador_id = current_user.id
    solicitud.fecha_gestion = ahora_bogota()
    db.session.commit()
    _notificar_resultado(solicitud)
    flash(f'Solicitud #{solicitud.id} rechazada.', 'info')
    return redirect(url_for('prestamos.gestionar'))


@bp.route('/cancelar/<int:solicitud_id>', methods=['POST'])
@login_required
@operador_required
def cancelar(solicitud_id):
    solicitud = Solicitud.query.get_or_404(solicitud_id)

    if solicitud.estado not in ['pendiente', 'aprobada']:
        flash('Solo se pueden cancelar solicitudes pendientes o aprobadas.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    motivo = request.form.get('motivo_cancelacion', '').strip()
    if not motivo:
        flash('Debes indicar el motivo de la cancelación.', 'danger')
        return redirect(url_for('prestamos.gestionar'))

    # Si era RFID aprobada, desactivar los permisos creados
    if solicitud.tipo == 'rfid' and solicitud.estado == 'aprobada':
        for did in solicitud.get_dispositivos_ids():
            permiso = PermisoAcceso.query.filter_by(
                uid_tarjeta=solicitud.uid_tarjeta,
                dispositivo_id=did,
                usuario_id=solicitud.usuario_id
            ).first()
            if permiso:
                permiso.activo = False

    # Si era recurso aprobado, devolver unidad
    if solicitud.tipo == 'recurso' and solicitud.estado == 'aprobada' and solicitud.recurso:
        solicitud.recurso.cantidad_disponible += 1
        if solicitud.recurso.cantidad_disponible > 0:
            solicitud.recurso.estado = 'disponible'

    solicitud.estado = 'rechazada'
    solicitud.motivo_rechazo = f'[CANCELADA] {motivo}'
    solicitud.operador_id = current_user.id
    solicitud.fecha_gestion = ahora_bogota()
    db.session.commit()
    flash(f'Solicitud #{solicitud.id} cancelada correctamente.', 'info')
    return redirect(url_for('prestamos.gestionar'))


@bp.route('/devolucion/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
@operador_required
def devolucion(solicitud_id):
    solicitud = Solicitud.query.get_or_404(solicitud_id)

    if solicitud.estado != 'aprobada' or solicitud.tipo != 'recurso':
        flash('Solo aplica para recursos aprobados.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    if request.method == 'POST':
        estado_devolucion = request.form.get('estado_devolucion', '')
        novedad = request.form.get('novedad_devolucion', '').strip()

        if estado_devolucion not in ['bueno', 'dañado', 'perdido']:
            flash('Selecciona el estado del recurso.', 'danger')
            return render_template('prestamos/devolucion_form.html', solicitud=solicitud)

        solicitud.fecha_devolucion_real = ahora_bogota()
        solicitud.estado_devolucion = estado_devolucion
        solicitud.novedad_devolucion = novedad or None
        solicitud.estado = 'devuelta'
        solicitud.calcular_tiempo_uso()

        if solicitud.recurso:
            if estado_devolucion == 'bueno':
                solicitud.recurso.cantidad_disponible += 1
                solicitud.recurso.estado = 'disponible'
            elif estado_devolucion == 'dañado':
                solicitud.recurso.estado = 'dañado'
            elif estado_devolucion == 'perdido':
                solicitud.recurso.cantidad_total = max(0, solicitud.recurso.cantidad_total - 1)
                if solicitud.recurso.cantidad_total == 0:
                    solicitud.recurso.estado = 'dado_de_baja'

        db.session.commit()
        horas = (solicitud.tiempo_uso_minutos or 0) // 60
        mins = (solicitud.tiempo_uso_minutos or 0) % 60
        flash(f'Devolución registrada. Tiempo de uso: {horas}h {mins}min.', 'success')
        return redirect(url_for('prestamos.gestionar'))

    return render_template('prestamos/devolucion_form.html', solicitud=solicitud)


# ── Notificaciones ─────────────────────────────────────────────────────────────

def _notificar_nueva_solicitud(solicitud):
    try:
        from flask_mail import Message
        from app import mail
        msg = Message(
            subject=f'Nueva solicitud #{solicitud.id} — UCundinamarca',
            recipients=[solicitud.usuario.email],
            body=(f'Hola {solicitud.usuario.nombre},\n\n'
                  f'Tu solicitud #{solicitud.id} fue recibida y está pendiente.\n\n'
                  f'Tipo: {solicitud.tipo.upper()}\n'
                  f'Sistema de Préstamos — UCundinamarca')
        )
        mail.send(msg)
    except Exception:
        pass


def _notificar_resultado(solicitud):
    try:
        from flask_mail import Message
        from app import mail
        estado = '✅ APROBADA' if solicitud.estado == 'aprobada' else '❌ RECHAZADA'
        msg = Message(
            subject=f'Solicitud #{solicitud.id} {estado} — UCundinamarca',
            recipients=[solicitud.usuario.email],
            body=(f'Hola {solicitud.usuario.nombre},\n\n'
                  f'Tu solicitud #{solicitud.id} fue {solicitud.estado}.\n'
                  f'{f"Motivo: {solicitud.motivo_rechazo}" if solicitud.motivo_rechazo else ""}\n\n'
                  f'Sistema de Préstamos — UCundinamarca')
        )
        mail.send(msg)
    except Exception:
        pass