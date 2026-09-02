from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
from app import db
from app.accesos import bp
from app.models import RegistroAcceso, Espacio, User


# ── Decorador ─────────────────────────────────────────────────────────────────

def operador_o_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.get_role_name() not in ['operador', 'administrador']:
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── HU-20: Dashboard de accesos ───────────────────────────────────────────────

@bp.route('/dashboard')
@login_required
@operador_o_admin
def dashboard():
    # Estadísticas generales
    total = RegistroAcceso.query.count()
    permitidos = RegistroAcceso.query.filter_by(autorizado=True).count()
    denegados = RegistroAcceso.query.filter_by(autorizado=False).count()
    entradas = RegistroAcceso.query.filter_by(tipo_evento='entrada').count()
    salidas = RegistroAcceso.query.filter_by(tipo_evento='salida').count()

    # Alertas: accesos denegados en las últimas 24 horas
    hace_24h = datetime.utcnow() - timedelta(hours=24)
    alertas_recientes = RegistroAcceso.query.filter(
        RegistroAcceso.autorizado == False,
        RegistroAcceso.fecha_evento >= hace_24h
    ).count()

    # Últimos 10 registros
    ultimos = RegistroAcceso.query.order_by(
        RegistroAcceso.fecha_evento.desc()
    ).limit(10).all()

    # Espacios con más accesos
    espacios_stats = db.session.query(
        Espacio.nombre,
        db.func.count(RegistroAcceso.id).label('total')
    ).join(
        RegistroAcceso, RegistroAcceso.espacio_id == Espacio.id
    ).group_by(Espacio.id).order_by(
        db.func.count(RegistroAcceso.id).desc()
    ).limit(5).all()

    stats = {
        'total': total,
        'permitidos': permitidos,
        'denegados': denegados,
        'entradas': entradas,
        'salidas': salidas,
        'alertas_recientes': alertas_recientes,
    }

    return render_template('accesos/dashboard.html',
                           stats=stats,
                           ultimos=ultimos,
                           espacios_stats=espacios_stats)


# ── HU-20: Listado completo de registros ──────────────────────────────────────

@bp.route('/registros')
@login_required
@operador_o_admin
def registros():
    page = request.args.get('page', 1, type=int)
    autorizado_filtro = request.args.get('autorizado', '')
    tipo_filtro = request.args.get('tipo', '')
    espacio_filtro = request.args.get('espacio_id', 0, type=int)
    fecha_desde_str = request.args.get('fecha_desde', '')
    fecha_hasta_str = request.args.get('fecha_hasta', '')

    query = RegistroAcceso.query

    if autorizado_filtro == '1':
        query = query.filter_by(autorizado=True)
    elif autorizado_filtro == '0':
        query = query.filter_by(autorizado=False)
    if tipo_filtro:
        query = query.filter_by(tipo_evento=tipo_filtro)
    if espacio_filtro:
        query = query.filter_by(espacio_id=espacio_filtro)
    if fecha_desde_str:
        try:
            fecha_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
            query = query.filter(RegistroAcceso.fecha_evento >= fecha_desde)
        except ValueError:
            pass
    if fecha_hasta_str:
        try:
            fecha_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(RegistroAcceso.fecha_evento < fecha_hasta)
        except ValueError:
            pass

    registros_paginados = query.order_by(
        RegistroAcceso.fecha_evento.desc()
    ).paginate(page=page, per_page=15, error_out=False)

    espacios = Espacio.query.all()

    return render_template('accesos/registros.html',
                           registros=registros_paginados,
                           espacios=espacios,
                           autorizado_filtro=autorizado_filtro,
                           tipo_filtro=tipo_filtro,
                           espacio_filtro=espacio_filtro,
                           fecha_desde=fecha_desde_str,
                           fecha_hasta=fecha_hasta_str)


# ── HU-20: Alertas de accesos no autorizados ──────────────────────────────────

@bp.route('/alertas')
@login_required
@operador_o_admin
def alertas():
    page = request.args.get('page', 1, type=int)
    fecha_desde_str = request.args.get('fecha_desde', '')
    fecha_hasta_str = request.args.get('fecha_hasta', '')

    query = RegistroAcceso.query.filter_by(autorizado=False)

    if fecha_desde_str:
        try:
            fecha_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
            query = query.filter(RegistroAcceso.fecha_evento >= fecha_desde)
        except ValueError:
            pass
    if fecha_hasta_str:
        try:
            fecha_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(RegistroAcceso.fecha_evento < fecha_hasta)
        except ValueError:
            pass

    alertas_paginadas = query.order_by(
        RegistroAcceso.fecha_evento.desc()
    ).paginate(page=page, per_page=15, error_out=False)

    # Contar alertas últimas 24h
    hace_24h = datetime.utcnow() - timedelta(hours=24)
    alertas_24h = RegistroAcceso.query.filter(
        RegistroAcceso.autorizado == False,
        RegistroAcceso.fecha_evento >= hace_24h
    ).count()

    return render_template('accesos/alertas.html',
                           alertas=alertas_paginadas,
                           alertas_24h=alertas_24h,
                           fecha_desde=fecha_desde_str,
                           fecha_hasta=fecha_hasta_str)


# ── HU-23: Calcular tiempo de permanencia ─────────────────────────────────────

@bp.route('/calcular-permanencia/<int:espacio_id>/<string:uid>')
@login_required
@operador_o_admin
def calcular_permanencia(espacio_id, uid):
    """Calcula el tiempo entre la última entrada y salida de una tarjeta en un espacio."""
    entrada = RegistroAcceso.query.filter_by(
        uid_tarjeta=uid,
        espacio_id=espacio_id,
        tipo_evento='entrada'
    ).order_by(RegistroAcceso.fecha_evento.desc()).first()

    salida = RegistroAcceso.query.filter_by(
        uid_tarjeta=uid,
        espacio_id=espacio_id,
        tipo_evento='salida'
    ).order_by(RegistroAcceso.fecha_evento.desc()).first()

    if entrada and salida and salida.fecha_evento > entrada.fecha_evento:
        delta = salida.fecha_evento - entrada.fecha_evento
        minutos = int(delta.total_seconds() / 60)
        entrada.tiempo_permanencia_minutos = minutos
        salida.tiempo_permanencia_minutos = minutos
        db.session.commit()
        flash(f'Tiempo de permanencia calculado: {minutos // 60}h {minutos % 60}min.', 'success')
    else:
        flash('No se encontró un par entrada/salida válido para calcular.', 'warning')

    return redirect(url_for('accesos.registros'))