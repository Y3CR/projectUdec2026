from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from functools import wraps
import pytz
from app import db
from app.prestamos import bp
from app.models import Solicitud, Espacio, Recurso, User

# Zona horaria de Colombia
BOGOTA_TZ = pytz.timezone('America/Bogota')

def ahora_bogota():
    """Retorna la fecha/hora actual en Colombia, sin tzinfo (naive), para comparar con fechas del formulario."""
    return datetime.now(BOGOTA_TZ).replace(tzinfo=None)


# ── Decoradores ────────────────────────────────────────────────────────────────

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
            flash('Acceso denegado. Solo operadores.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── HU-9 / HU-10: Crear solicitud ─────────────────────────────────────────────

@bp.route('/solicitar', methods=['GET', 'POST'])
@login_required
@usuario_regular_required
def solicitar():
    espacios = Espacio.query.filter_by(disponible=True).all()
    recursos = Recurso.query.filter(Recurso.cantidad_disponible > 0).all()

    if request.method == 'POST':
        tipo = request.form.get('tipo', '')
        espacio_id = request.form.get('espacio_id', type=int)
        recurso_id = request.form.get('recurso_id', type=int)
        fecha_inicio_str = request.form.get('fecha_inicio', '')
        fecha_fin_str = request.form.get('fecha_fin', '')
        motivo = request.form.get('motivo', '').strip()

        # Validaciones básicas
        errores = []
        if tipo not in ['espacio', 'recurso']:
            errores.append('Debes seleccionar el tipo de solicitud.')
        if not fecha_inicio_str or not fecha_fin_str:
            errores.append('Las fechas de inicio y fin son obligatorias.')

        fecha_inicio = None
        fecha_fin = None

        if fecha_inicio_str and fecha_fin_str:
            try:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%dT%H:%M')
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%dT%H:%M')
                if fecha_inicio >= fecha_fin:
                    errores.append('La fecha de fin debe ser posterior a la de inicio.')
                # ✅ CORREGIDO: comparar contra hora actual en Bogotá con margen de 5 minutos
                if fecha_inicio < ahora_bogota() - timedelta(minutes=5):
                    errores.append('La fecha de inicio no puede ser en el pasado.')
            except ValueError:
                errores.append('Formato de fecha inválido.')

        if tipo == 'espacio' and not espacio_id:
            errores.append('Debes seleccionar un espacio.')
        if tipo == 'recurso' and not recurso_id:
            errores.append('Debes seleccionar un recurso.')

        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('prestamos/solicitar.html',
                                   espacios=espacios, recursos=recursos, data=request.form)

        # HU-9/10 escenario 2: verificar disponibilidad con cruce de fechas
        if tipo == 'espacio':
            espacio = Espacio.query.get(espacio_id)
            if not espacio or not espacio.disponible:
                flash('El espacio seleccionado no está disponible.', 'danger')
                return render_template('prestamos/solicitar.html',
                                       espacios=espacios, recursos=recursos, data=request.form)

            cruce = Solicitud.query.filter(
                Solicitud.espacio_id == espacio_id,
                Solicitud.estado == 'aprobada',
                Solicitud.fecha_inicio < fecha_fin,
                Solicitud.fecha_fin > fecha_inicio
            ).first()
            if cruce:
                flash('El espacio ya tiene una reserva aprobada en ese horario. '
                      'Selecciona otro horario.', 'danger')
                return render_template('prestamos/solicitar.html',
                                       espacios=espacios, recursos=recursos, data=request.form)

        if tipo == 'recurso':
            recurso = Recurso.query.get(recurso_id)
            if not recurso or recurso.cantidad_disponible <= 0:
                flash('El recurso seleccionado no está disponible.', 'danger')
                return render_template('prestamos/solicitar.html',
                                       espacios=espacios, recursos=recursos, data=request.form)

        # Crear solicitud
        solicitud = Solicitud(
            usuario_id=current_user.id,
            tipo=tipo,
            espacio_id=espacio_id if tipo == 'espacio' else None,
            recurso_id=recurso_id if tipo == 'recurso' else None,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            motivo=motivo,
            estado='pendiente'
        )
        db.session.add(solicitud)
        db.session.commit()

        _notificar_nueva_solicitud(solicitud)

        flash('Solicitud enviada correctamente. Estado: Pendiente de aprobación.', 'success')
        return redirect(url_for('prestamos.mis_solicitudes'))

    return render_template('prestamos/solicitar.html',
                           espacios=espacios, recursos=recursos, data={})


# ── HU-18/19: Mis solicitudes ──────────────────────────────────────────────────

@bp.route('/mis-solicitudes')
@login_required
@usuario_regular_required
def mis_solicitudes():
    page = request.args.get('page', 1, type=int)
    estado_filtro = request.args.get('estado', '')

    query = Solicitud.query.filter_by(usuario_id=current_user.id)
    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)

    solicitudes = query.order_by(Solicitud.fecha_creacion.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    return render_template('prestamos/mis_solicitudes.html',
                           solicitudes=solicitudes, estado_filtro=estado_filtro)


# ── HU-11: Gestionar solicitudes (operador) ────────────────────────────────────

@bp.route('/gestionar')
@login_required
@operador_required
def gestionar():
    page = request.args.get('page', 1, type=int)
    estado_filtro = request.args.get('estado', 'pendiente')
    tipo_filtro = request.args.get('tipo', '')

    query = Solicitud.query
    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)
    if tipo_filtro:
        query = query.filter_by(tipo=tipo_filtro)

    solicitudes = query.order_by(Solicitud.fecha_creacion.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    return render_template('prestamos/gestionar.html',
                           solicitudes=solicitudes,
                           estado_filtro=estado_filtro,
                           tipo_filtro=tipo_filtro)


@bp.route('/aprobar/<int:solicitud_id>', methods=['POST'])
@login_required
@operador_required
def aprobar(solicitud_id):
    solicitud = Solicitud.query.get_or_404(solicitud_id)

    if solicitud.estado != 'pendiente':
        flash('Solo se pueden aprobar solicitudes pendientes.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    if solicitud.tipo == 'espacio' and solicitud.espacio:
        cruce = Solicitud.query.filter(
            Solicitud.espacio_id == solicitud.espacio_id,
            Solicitud.estado == 'aprobada',
            Solicitud.id != solicitud_id,
            Solicitud.fecha_inicio < solicitud.fecha_fin,
            Solicitud.fecha_fin > solicitud.fecha_inicio
        ).first()
        if cruce:
            flash('No se puede aprobar: el espacio ya tiene una reserva en ese horario.', 'danger')
            return redirect(url_for('prestamos.gestionar'))

    if solicitud.tipo == 'recurso' and solicitud.recurso:
        if solicitud.recurso.cantidad_disponible <= 0:
            flash('No se puede aprobar: el recurso no tiene unidades disponibles.', 'danger')
            return redirect(url_for('prestamos.gestionar'))
        solicitud.recurso.cantidad_disponible -= 1
        if solicitud.recurso.cantidad_disponible == 0:
            solicitud.recurso.estado = 'prestado'

    solicitud.estado = 'aprobada'
    solicitud.operador_id = current_user.id
    # ✅ CORREGIDO: usar hora de Bogotá
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
    # ✅ CORREGIDO: usar hora de Bogotá
    solicitud.fecha_gestion = ahora_bogota()
    db.session.commit()

    _notificar_resultado(solicitud)
    flash(f'Solicitud #{solicitud.id} rechazada.', 'info')
    return redirect(url_for('prestamos.gestionar'))


# ── HU-15: Registrar devolución ────────────────────────────────────────────────

@bp.route('/devolucion/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
@operador_required
def devolucion(solicitud_id):
    solicitud = Solicitud.query.get_or_404(solicitud_id)

    if solicitud.estado != 'aprobada':
        flash('Solo se pueden registrar devoluciones de solicitudes aprobadas.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    if solicitud.tipo != 'recurso':
        flash('Las devoluciones aplican solo a recursos físicos.', 'warning')
        return redirect(url_for('prestamos.gestionar'))

    if request.method == 'POST':
        estado_devolucion = request.form.get('estado_devolucion', '')
        novedad = request.form.get('novedad_devolucion', '').strip()

        if estado_devolucion not in ['bueno', 'dañado', 'perdido']:
            flash('Selecciona el estado del recurso al momento de la devolución.', 'danger')
            return render_template('prestamos/devolucion_form.html', solicitud=solicitud)

        # ✅ CORREGIDO: usar hora de Bogotá
        solicitud.fecha_devolucion_real = ahora_bogota()
        solicitud.estado_devolucion = estado_devolucion
        solicitud.novedad_devolucion = novedad if novedad else None
        solicitud.estado = 'devuelta'

        solicitud.calcular_tiempo_uso()

        if solicitud.recurso:
            if estado_devolucion == 'bueno':
                solicitud.recurso.cantidad_disponible += 1
                if solicitud.recurso.cantidad_disponible > 0:
                    solicitud.recurso.estado = 'disponible'
            elif estado_devolucion == 'dañado':
                solicitud.recurso.estado = 'dañado'
            elif estado_devolucion == 'perdido':
                solicitud.recurso.cantidad_total = max(0, solicitud.recurso.cantidad_total - 1)
                solicitud.recurso.estado = 'dado_de_baja' if solicitud.recurso.cantidad_total == 0 else solicitud.recurso.estado

        db.session.commit()

        horas = solicitud.tiempo_uso_minutos // 60 if solicitud.tiempo_uso_minutos else 0
        minutos = solicitud.tiempo_uso_minutos % 60 if solicitud.tiempo_uso_minutos else 0
        flash(f'Devolución registrada. Tiempo de uso: {horas}h {minutos}min.', 'success')
        return redirect(url_for('prestamos.gestionar'))

    return render_template('prestamos/devolucion_form.html', solicitud=solicitud)


# ── Helpers de notificación (HU-21) ───────────────────────────────────────────

def _notificar_nueva_solicitud(solicitud):
    try:
        from flask_mail import Message
        from app import mail
        msg = Message(
            subject=f'Nueva solicitud #{solicitud.id} — UCundinamarca',
            recipients=[solicitud.usuario.email],
            body=(
                f'Hola {solicitud.usuario.nombre},\n\n'
                f'Tu solicitud #{solicitud.id} de {solicitud.tipo} ha sido recibida '
                f'y está pendiente de aprobación.\n\n'
                f'Item: {solicitud.get_item_nombre()}\n'
                f'Desde: {solicitud.fecha_inicio.strftime("%d/%m/%Y %H:%M")}\n'
                f'Hasta: {solicitud.fecha_fin.strftime("%d/%m/%Y %H:%M")}\n\n'
                f'Te notificaremos cuando sea gestionada.\n\n'
                f'Sistema de Préstamos — UCundinamarca'
            )
        )
        mail.send(msg)
    except Exception:
        pass


def _notificar_resultado(solicitud):
    try:
        from flask_mail import Message
        from app import mail
        if solicitud.estado == 'aprobada':
            asunto = f'✅ Solicitud #{solicitud.id} aprobada — UCundinamarca'
            cuerpo = (
                f'Hola {solicitud.usuario.nombre},\n\n'
                f'Tu solicitud #{solicitud.id} ha sido APROBADA.\n\n'
                f'Item: {solicitud.get_item_nombre()}\n'
                f'Desde: {solicitud.fecha_inicio.strftime("%d/%m/%Y %H:%M")}\n'
                f'Hasta: {solicitud.fecha_fin.strftime("%d/%m/%Y %H:%M")}\n\n'
                f'Sistema de Préstamos — UCundinamarca'
            )
        else:
            asunto = f'❌ Solicitud #{solicitud.id} rechazada — UCundinamarca'
            cuerpo = (
                f'Hola {solicitud.usuario.nombre},\n\n'
                f'Tu solicitud #{solicitud.id} ha sido RECHAZADA.\n\n'
                f'Motivo: {solicitud.motivo_rechazo}\n\n'
                f'Sistema de Préstamos — UCundinamarca'
            )
        msg = Message(subject=asunto, recipients=[solicitud.usuario.email], body=cuerpo)
        mail.send(msg)
    except Exception:
        pass