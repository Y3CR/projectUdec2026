from flask import render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from functools import wraps
import json
import io
import pytz
from app import db
from app.prestamos import bp
from app.models import (Solicitud, Espacio, Recurso, User,
                        DispositivoRFID, PermisoAcceso)

BOGOTA_TZ = pytz.timezone('America/Bogota')


def ahora_bogota():
    return datetime.now(BOGOTA_TZ).replace(tzinfo=None)


def usuario_regular_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.get_role_name() not in ['docente', 'estudiante',
                                                  'invitado', 'administrador']:
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


def _verificar_demoras_automatico():
    """Verifica y actualiza demoras sin necesidad de acción manual."""
    ahora = ahora_bogota()
    solicitudes_vencidas = Solicitud.query.filter(
        Solicitud.tipo == 'recurso',
        Solicitud.estado == 'entregado',
        Solicitud.fecha_fin.isnot(None)
    ).all()

    cambios = False
    for s in solicitudes_vencidas:
        fecha_limite = s.fecha_fin_efectiva()
        if fecha_limite and ahora > fecha_limite:
            s.estado = 'en_demora'
            cambios = True
            _notificar_demora(s)

    if cambios:
        db.session.commit()


# ── Solicitar ──────────────────────────────────────────────────────────────────

@bp.route('/solicitar', methods=['GET', 'POST'])
@login_required
@usuario_regular_required
def solicitar():
    recursos = Recurso.query.filter_by(estado='disponible').all()
    dispositivos = DispositivoRFID.query.filter_by(activo=True).all()

    if request.method == 'POST':
        tipo = request.form.get('tipo', '')

        if tipo == 'rfid':
            uid_tarjeta = current_user.uid_tarjeta
            dispositivos_ids = request.form.getlist('dispositivos_ids')
            motivo = request.form.get('motivo', '').strip()

            if not uid_tarjeta:
                flash('No tienes tarjeta RFID asignada.', 'warning')
                return redirect(url_for('prestamos.solicitar'))
            if not dispositivos_ids:
                flash('Debes seleccionar al menos un dispositivo.', 'danger')
                return render_template('prestamos/solicitar.html',
                                       recursos=recursos,
                                       dispositivos=dispositivos,
                                       data=request.form)

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
                                           recursos=recursos,
                                           dispositivos=dispositivos,
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
            flash('Solicitud de acceso RFID enviada.', 'success')
            return redirect(url_for('prestamos.mis_solicitudes'))

        elif tipo == 'recurso':
            recurso_id = request.form.get('recurso_id', type=int)
            # Solo fecha_fin: cuándo planea devolver
            fecha_fin_str = request.form.get('fecha_fin', '')
            motivo = request.form.get('motivo', '').strip()

            errores = []
            if not recurso_id:
                errores.append('Debes seleccionar un recurso.')

            fecha_fin = None
            if fecha_fin_str:
                try:
                    fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%dT%H:%M')
                    if fecha_fin <= ahora_bogota():
                        errores.append('La fecha de devolución debe ser futura.')
                except ValueError:
                    errores.append('Formato de fecha inválido.')
            else:
                errores.append('La fecha estimada de devolución es obligatoria.')

            if errores:
                for e in errores:
                    flash(e, 'danger')
                return render_template('prestamos/solicitar.html',
                                       recursos=recursos,
                                       dispositivos=dispositivos,
                                       data=request.form)

            recurso = Recurso.query.get(recurso_id)
            if not recurso or not recurso.esta_disponible():
                flash('El recurso seleccionado no está disponible.', 'danger')
                return render_template('prestamos/solicitar.html',
                                       recursos=recursos,
                                       dispositivos=dispositivos,
                                       data=request.form)

            solicitud = Solicitud(
                usuario_id=current_user.id,
                tipo='recurso',
                recurso_id=recurso_id,
                fecha_fin=fecha_fin,
                motivo=motivo,
                estado='pendiente'
            )
            db.session.add(solicitud)
            db.session.commit()
            _notificar_nueva_solicitud(solicitud)
            flash('Solicitud enviada. Pendiente de aprobación.', 'success')
            return redirect(url_for('prestamos.mis_solicitudes'))

        else:
            flash('Tipo de solicitud inválido.', 'danger')

    return render_template('prestamos/solicitar.html',
                           recursos=recursos,
                           dispositivos=dispositivos,
                           data={})


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


# ── Gestionar (operador) ───────────────────────────────────────────────────────

@bp.route('/gestionar')
@login_required
@operador_required
def gestionar():
    
    _verificar_demoras_automatico()

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
        dispositivos_ids = solicitud.get_dispositivos_ids()
        permisos_creados = []
        for did in dispositivos_ids:
            dispositivo = DispositivoRFID.query.get(did)
            if not dispositivo:
                continue
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
              f'Permisos: {", ".join(permisos_creados) if permisos_creados else "ya existían"}.', 'success')

    elif solicitud.tipo == 'recurso':
        if not solicitud.recurso or not solicitud.recurso.esta_disponible():
            flash('El recurso no está disponible.', 'danger')
            return redirect(url_for('prestamos.gestionar'))

        # Al aprobar un recurso pasa a "aprobada" esperando entrega física
        solicitud.recurso.estado = 'reservado'
        solicitud.estado = 'aprobada'
        solicitud.operador_id = current_user.id
        solicitud.fecha_gestion = ahora_bogota()
        db.session.commit()
        _notificar_resultado(solicitud)
        flash(f'Solicitud #{solicitud.id} aprobada. '
              f'Pendiente de entrega física al usuario.', 'success')

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

    if solicitud.tipo == 'recurso' and solicitud.recurso:
        solicitud.recurso.estado = 'disponible'

    solicitud.estado = 'rechazada'
    solicitud.motivo_rechazo = motivo_rechazo
    solicitud.operador_id = current_user.id
    solicitud.fecha_gestion = ahora_bogota()
    db.session.commit()
    _notificar_resultado(solicitud)
    flash(f'Solicitud #{solicitud.id} rechazada.', 'info')
    return redirect(url_for('prestamos.gestionar'))


@bp.route('/entregar/<int:solicitud_id>', methods=['POST'])
@login_required
@operador_required
def entregar(solicitud_id):
    """El operador entrega físicamente el recurso. Aquí empieza el tiempo."""
    solicitud = Solicitud.query.get_or_404(solicitud_id)
    if solicitud.estado != 'aprobada' or solicitud.tipo != 'recurso':
        flash('Solo se pueden entregar recursos aprobados.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    # La fecha_inicio se registra en este momento
    solicitud.fecha_inicio = ahora_bogota()
    solicitud.estado = 'entregado'
    if solicitud.recurso:
        solicitud.recurso.estado = 'prestado'
    db.session.commit()

    _notificar_entrega(solicitud)
    flash(f'Recurso entregado. Tiempo iniciado: '
          f'{solicitud.fecha_inicio.strftime("%d/%m/%Y %H:%M")}.', 'success')
    return redirect(url_for('prestamos.gestionar'))


@bp.route('/devolucion/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
@operador_required
def devolucion(solicitud_id):
    solicitud = Solicitud.query.get_or_404(solicitud_id)

    # Permitir devolución tanto de 'entregado' como de 'en_demora'
    if solicitud.tipo != 'recurso' or solicitud.estado not in ['entregado', 'en_demora']:
        flash('Solo aplica para recursos en uso o en demora.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    if request.method == 'POST':
        estado_devolucion = request.form.get('estado_devolucion', '')
        novedad = request.form.get('novedad_devolucion', '').strip()

        if estado_devolucion not in ['bueno', 'dañado', 'perdido']:
            flash('Selecciona el estado del recurso.', 'danger')
            return render_template('prestamos/devolucion_form.html',
                                   solicitud=solicitud)

        solicitud.fecha_devolucion_real = ahora_bogota()
        solicitud.estado_devolucion = estado_devolucion
        solicitud.novedad_devolucion = novedad or None
        solicitud.estado = 'devuelta'
        solicitud.calcular_tiempo_uso()

        if solicitud.recurso:
            if estado_devolucion == 'bueno':
                solicitud.recurso.estado = 'disponible'
            elif estado_devolucion == 'dañado':
                solicitud.recurso.estado = 'dañado'
            elif estado_devolucion == 'perdido':
                solicitud.recurso.estado = 'dado_de_baja'

        db.session.commit()
        horas = (solicitud.tiempo_uso_minutos or 0) // 60
        mins = (solicitud.tiempo_uso_minutos or 0) % 60
        flash(f'Devolución registrada. Tiempo de uso: {horas}h {mins}min.',
              'success')
        return redirect(url_for('prestamos.gestionar'))

    return render_template('prestamos/devolucion_form.html', solicitud=solicitud)

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

    if solicitud.tipo == 'rfid' and solicitud.estado == 'aprobada':
        for did in solicitud.get_dispositivos_ids():
            permiso = PermisoAcceso.query.filter_by(
                uid_tarjeta=solicitud.uid_tarjeta,
                dispositivo_id=did,
                usuario_id=solicitud.usuario_id
            ).first()
            if permiso:
                permiso.activo = False

    if solicitud.tipo == 'recurso' and solicitud.recurso:
        solicitud.recurso.estado = 'disponible'

    solicitud.estado = 'rechazada'
    solicitud.motivo_rechazo = f'[CANCELADA] {motivo}'
    solicitud.operador_id = current_user.id
    solicitud.fecha_gestion = ahora_bogota()
    db.session.commit()
    flash(f'Solicitud #{solicitud.id} cancelada.', 'info')
    return redirect(url_for('prestamos.gestionar'))


# ── Mis recursos en uso ────────────────────────────────────────────────────────

@bp.route('/mis-recursos')
@login_required
@usuario_regular_required
def mis_recursos():
    recursos_activos = Solicitud.query.filter_by(
        usuario_id=current_user.id,
        tipo='recurso',
        estado='entregado'
    ).order_by(Solicitud.fecha_inicio.desc()).all()
    return render_template('prestamos/mis_recursos.html',
                           recursos_activos=recursos_activos,
                           ahora=ahora_bogota())


@bp.route('/extender/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
@usuario_regular_required
def extender_plazo(solicitud_id):
    solicitud = Solicitud.query.get_or_404(solicitud_id)

    if solicitud.usuario_id != current_user.id:
        flash('No tienes permiso para esta acción.', 'danger')
        return redirect(url_for('prestamos.mis_recursos'))

    if solicitud.tipo != 'recurso' or solicitud.estado not in ['aprobada', 'entregado']:
        flash('Solo puedes extender recursos aprobados o en uso.', 'warning')
        return redirect(url_for('prestamos.mis_solicitudes'))

    # Fecha mínima: la fecha de fin actual
    fecha_minima = solicitud.fecha_fin_efectiva()
    fecha_minima_str = (
        fecha_minima.strftime('%Y-%m-%dT%H:%M') if fecha_minima else ''
    )

    if request.method == 'POST':
        nueva_fecha_str = request.form.get('nueva_fecha_fin', '')
        try:
            nueva_fecha = datetime.strptime(nueva_fecha_str, '%Y-%m-%dT%H:%M')
            fecha_actual = solicitud.fecha_fin_efectiva()
            if fecha_actual and nueva_fecha <= fecha_actual:
                flash('La nueva fecha debe ser posterior a la fecha de fin actual.',
                      'danger')
                return render_template('prestamos/extender_plazo.html',
                                       solicitud=solicitud,
                                       fecha_minima=fecha_minima_str)
            solicitud.fecha_fin_extendida = nueva_fecha
            db.session.commit()
            flash(f'Plazo extendido hasta '
                  f'{nueva_fecha.strftime("%d/%m/%Y %H:%M")}.', 'success')
            _notificar_extension(solicitud)
            return redirect(url_for('prestamos.mis_solicitudes'))
        except ValueError:
            flash('Formato de fecha inválido.', 'danger')

    return render_template('prestamos/extender_plazo.html',
                           solicitud=solicitud,
                           fecha_minima=fecha_minima_str)

# ── QR personal del usuario ────────────────────────────────────────────────────

@bp.route('/qr-personal')
@login_required
def qr_personal():
    """Muestra el QR personal del usuario con su historial."""
    return render_template('prestamos/qr_personal.html',
                           usuario=current_user)


@bp.route('/qr-personal/imagen')
@login_required
def qr_personal_imagen():
    """Genera la imagen PNG del QR personal."""
    import qrcode
    from flask import request as req

    base_url = req.host_url.rstrip('/')
    url = f"{base_url}/prestamos/perfil-publico/{current_user.id}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#1b4332', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png',
                     download_name=f'qr_{current_user.id}.png')


@bp.route('/perfil-publico/<int:user_id>')
@login_required
def perfil_publico(user_id):
    """
    Página que se abre al escanear el QR personal.
    Muestra nombre, rol e historial de préstamos.
    Accesible para operadores y el propio usuario.
    """
    if (current_user.get_role_name() not in ['operador', 'administrador']
            and current_user.id != user_id):
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('admin.dashboard'))

    usuario = User.query.get_or_404(user_id)

    activos = Solicitud.query.filter_by(
        usuario_id=user_id, tipo='recurso', estado='entregado'
    ).order_by(Solicitud.fecha_inicio.desc()).all()

    aprobados_rfid = Solicitud.query.filter_by(
        usuario_id=user_id, tipo='rfid', estado='aprobada'
    ).order_by(Solicitud.fecha_creacion.desc()).all()

    devueltos = Solicitud.query.filter_by(
        usuario_id=user_id, tipo='recurso', estado='devuelta'
    ).order_by(Solicitud.fecha_devolucion_real.desc()).limit(10).all()

    rechazados = Solicitud.query.filter(
        Solicitud.usuario_id == user_id,
        Solicitud.estado == 'rechazada'
    ).order_by(Solicitud.fecha_creacion.desc()).limit(5).all()

    return render_template('prestamos/perfil_publico.html',
                           usuario=usuario,
                           activos=activos,
                           aprobados_rfid=aprobados_rfid,
                           devueltos=devueltos,
                           rechazados=rechazados)


# ── QR de comprobante (operador escanea para entregar) ─────────────────────────

@bp.route('/comprobante/<int:solicitud_id>/imagen')
@login_required
def comprobante_qr_imagen(solicitud_id):
    """QR que al escanearse lleva al operador a confirmar la entrega."""
    import qrcode
    from flask import request as req

    solicitud = Solicitud.query.get_or_404(solicitud_id)
    if solicitud.usuario_id != current_user.id and \
       current_user.get_role_name() not in ['operador', 'administrador']:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('admin.dashboard'))

    base_url = req.host_url.rstrip('/')
    url = f"{base_url}/prestamos/confirmar-entrega/{solicitud_id}"

    qr = qrcode.QRCode(version=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#1b4332', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png',
                     download_name=f'comprobante_{solicitud_id}.png')


@bp.route('/confirmar-entrega/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
@operador_required
def confirmar_entrega_qr(solicitud_id):
    """El operador escanea el QR de comprobante y confirma la entrega."""
    solicitud = Solicitud.query.get_or_404(solicitud_id)

    if solicitud.estado != 'aprobada' or solicitud.tipo != 'recurso':
        flash('Esta solicitud no está en estado de entrega.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    if request.method == 'POST':
        solicitud.fecha_inicio = ahora_bogota()
        solicitud.estado = 'entregado'
        if solicitud.recurso:
            solicitud.recurso.estado = 'prestado'
        db.session.commit()
        _notificar_entrega(solicitud)
        flash(f'✅ Entrega confirmada vía QR. '
              f'Recurso: {solicitud.get_item_nombre()}. '
              f'Inicio: {solicitud.fecha_inicio.strftime("%d/%m/%Y %H:%M")}.', 'success')
        return redirect(url_for('prestamos.gestionar'))

    return render_template('prestamos/confirmar_entrega.html', solicitud=solicitud)


# ── QR de devolución (operador escanea para recibir) ──────────────────────────

@bp.route('/devolucion-qr/<int:solicitud_id>/imagen')
@login_required
@operador_required
def devolucion_qr_imagen(solicitud_id):
    """QR que al escanearse lleva al formulario de devolución."""
    import qrcode
    from flask import request as req

    solicitud = Solicitud.query.get_or_404(solicitud_id)
    base_url = req.host_url.rstrip('/')
    url = f"{base_url}/prestamos/devolucion/{solicitud_id}"

    qr = qrcode.QRCode(version=1,
                       error_correction=qrcode.constants.ERROR_CORRECT_H,
                       box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#c0392b', back_color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return send_file(buffer, mimetype='image/png',
                     download_name=f'devolucion_{solicitud_id}.png')


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
                  f'Sistema de Préstamos — UCundinamarca')
        )
        mail.send(msg)
    except Exception:
        pass


def _notificar_resultado(solicitud):
    try:
        from flask_mail import Message
        from app import mail
        usuario = solicitud.usuario
        if solicitud.estado == 'aprobada':
            if solicitud.tipo == 'rfid':
                asunto = f'✅ Acceso RFID aprobado — UCundinamarca'
                cuerpo = (
                    f'Hola {usuario.nombre},\n\n'
                    f'Tu solicitud #{solicitud.id} de acceso RFID fue APROBADA.\n'
                    f'Tu tarjeta {solicitud.uid_tarjeta} ha sido registrada.\n\n'
                    f'Sistema de Préstamos — UCundinamarca'
                )
            else:
                asunto = f'✅ Solicitud #{solicitud.id} aprobada — Pasa a recoger'
                cuerpo = (
                    f'Hola {usuario.nombre},\n\n'
                    f'Tu solicitud #{solicitud.id} fue APROBADA.\n\n'
                    f'Recurso: {solicitud.get_item_nombre()}\n'
                    f'Devolución estimada: '
                    f'{solicitud.fecha_fin.strftime("%d/%m/%Y %H:%M") if solicitud.fecha_fin else "—"}\n\n'
                    f'Acércate a la administración con tu QR de comprobante '
                    f'para retirar el recurso.\n\n'
                    f'Sistema de Préstamos — UCundinamarca'
                )
        else:
            asunto = f'❌ Solicitud #{solicitud.id} rechazada — UCundinamarca'
            cuerpo = (
                f'Hola {usuario.nombre},\n\n'
                f'Tu solicitud #{solicitud.id} fue RECHAZADA.\n'
                f'Motivo: {solicitud.motivo_rechazo}\n\n'
                f'Sistema de Préstamos — UCundinamarca'
            )
        msg = Message(subject=asunto, recipients=[usuario.email], body=cuerpo)
        mail.send(msg)
    except Exception:
        pass


def _notificar_entrega(solicitud):
    try:
        from flask_mail import Message
        from app import mail
        msg = Message(
            subject=f'📦 Recurso entregado — Solicitud #{solicitud.id}',
            recipients=[solicitud.usuario.email],
            body=(
                f'Hola {solicitud.usuario.nombre},\n\n'
                f'El recurso "{solicitud.get_item_nombre()}" fue entregado.\n'
                f'Inicio: {solicitud.fecha_inicio.strftime("%d/%m/%Y %H:%M")}\n'
                f'Devolución estimada: '
                f'{solicitud.fecha_fin_efectiva().strftime("%d/%m/%Y %H:%M") if solicitud.fecha_fin_efectiva() else "—"}\n\n'
                f'Sistema de Préstamos — UCundinamarca'
            )
        )
        mail.send(msg)
    except Exception:
        pass
    
    # ── Verificar demoras (llamar desde un endpoint o tarea programada) ────────────

@bp.route('/verificar-demoras', methods=['POST'])
@login_required
@operador_required
def verificar_demoras():
    """
    Marca como 'en_demora' las solicitudes entregadas cuya fecha
    de fin ya pasó y envía alertas por correo.
    """
    ahora = ahora_bogota()
    demoras_nuevas = 0

    solicitudes_vencidas = Solicitud.query.filter(
        Solicitud.tipo == 'recurso',
        Solicitud.estado == 'entregado',
        Solicitud.fecha_fin.isnot(None)
    ).all()

    for s in solicitudes_vencidas:
        fecha_limite = s.fecha_fin_efectiva()
        if fecha_limite and ahora > fecha_limite:
            s.estado = 'en_demora'
            demoras_nuevas += 1
            _notificar_demora(s)

    if demoras_nuevas > 0:
        db.session.commit()

    flash(f'Verificación completada. {demoras_nuevas} préstamo(s) marcado(s) '
          f'en demora.', 'warning' if demoras_nuevas > 0 else 'success')
    return redirect(url_for('prestamos.gestionar'))


def _notificar_demora(solicitud):
    """Envía correo al usuario avisando que está en demora."""
    try:
        from flask_mail import Message
        from app import mail
        fecha_limite = solicitud.fecha_fin_efectiva()
        msg = Message(
            subject='⚠️ Préstamo vencido — Por favor entrega el recurso',
            recipients=[solicitud.usuario.email],
            html=f'''
            <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:0 auto;">
                <div style="background:#dc3545;padding:24px;border-radius:12px 12px 0 0;
                            text-align:center;">
                    <h2 style="color:white;margin:0;">⚠️ Préstamo vencido</h2>
                    <p style="color:#ffcdd2;margin:4px 0 0;">
                        Sistema de Préstamos · UCundinamarca
                    </p>
                </div>
                <div style="background:#ffffff;padding:32px;border:1px solid #e0e0e0;
                            border-top:none;border-radius:0 0 12px 12px;">
                    <p style="font-size:16px;">
                        Hola <strong>{solicitud.usuario.nombre}</strong>,
                    </p>
                    <p style="color:#555;">
                        El tiempo de préstamo del siguiente recurso
                        <strong>ha vencido</strong> y aún no ha sido devuelto:
                    </p>

                    <div style="background:#fff3cd;border:1px solid #ffc107;
                                border-radius:8px;padding:16px;margin:20px 0;">
                        <p style="margin:0;font-size:15px;">
                            <strong>📦 Recurso:</strong>
                            {solicitud.get_item_nombre()}
                        </p>
                        <p style="margin:8px 0 0;color:#666;">
                            <strong>Fecha límite:</strong>
                            {fecha_limite.strftime("%d/%m/%Y %H:%M") if fecha_limite else "—"}
                        </p>
                    </div>

                    <p style="color:#555;">Por favor <strong>acércate lo antes posible</strong>
                    a la administración para entregar el recurso.</p>

                    <p style="color:#555;">Si necesitas más tiempo, solicita una
                    <strong>extensión de plazo</strong> desde el sistema antes de que
                    se tomen medidas adicionales.</p>

                    <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                    <p style="color:#aaa;font-size:11px;text-align:center;">
                        Sistema de Préstamos · Universidad de Cundinamarca · Ext. Facatativá
                    </p>
                </div>
            </div>
            ''',
            body=(
                f'Hola {solicitud.usuario.nombre},\n\n'
                f'El préstamo de "{solicitud.get_item_nombre()}" ha vencido.\n'
                f'Fecha límite: {fecha_limite.strftime("%d/%m/%Y %H:%M") if fecha_limite else "—"}\n\n'
                f'Por favor acércate a la administración a entregar el recurso '
                f'o solicita una extensión desde el sistema.\n\n'
                f'Sistema de Préstamos — UCundinamarca'
            )
        )
        mail.send(msg)
    except Exception as e:
        print(f'Error enviando alerta de demora: {e}')