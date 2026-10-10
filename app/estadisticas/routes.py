from flask import render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
from io import BytesIO
import pytz
from app import db
from app.estadisticas import bp
from app.models import (Solicitud, Recurso, Espacio, User,
                        RegistroAcceso, DispositivoRFID, PermisoAcceso)

BOGOTA_TZ = pytz.timezone('America/Bogota')


def admin_o_operador(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.get_role_name() not in ['administrador', 'operador']:
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated


def _rango_fechas(periodo):
    """Retorna (fecha_inicio, fecha_fin) según el período seleccionado."""
    ahora = datetime.now(BOGOTA_TZ).replace(tzinfo=None)
    if periodo == 'semana':
        return ahora - timedelta(days=7), ahora
    elif periodo == 'mes':
        return ahora - timedelta(days=30), ahora
    elif periodo == 'trimestre':
        return ahora - timedelta(days=90), ahora
    elif periodo == 'anio':
        return ahora - timedelta(days=365), ahora
    else:  # personalizado o todo
        return None, None


# ── Dashboard principal ────────────────────────────────────────────────────────

@bp.route('/dashboard')
@login_required
@admin_o_operador
def dashboard():
    periodo = request.args.get('periodo', 'mes')
    fecha_desde_str = request.args.get('fecha_desde', '')
    fecha_hasta_str = request.args.get('fecha_hasta', '')

    fecha_ini, fecha_fin = _rango_fechas(periodo)

    if periodo == 'personalizado':
        try:
            if fecha_desde_str:
                fecha_ini = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
            if fecha_hasta_str:
                fecha_fin = datetime.strptime(fecha_hasta_str, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            pass

    # ── KPIs resumen ──────────────────────────────────────────────────────────
    q_base = Solicitud.query
    if fecha_ini:
        q_base = q_base.filter(Solicitud.fecha_creacion >= fecha_ini)
    if fecha_fin:
        q_base = q_base.filter(Solicitud.fecha_creacion <= fecha_fin)

    kpis = {
        'total_solicitudes': q_base.count(),
        'aprobadas': q_base.filter(Solicitud.estado.in_(['aprobada', 'entregado', 'devuelta'])).count(),
        'rechazadas': q_base.filter(Solicitud.estado == 'rechazada').count(),
        'en_uso': Solicitud.query.filter_by(estado='entregado', tipo='recurso').count(),
        'recursos_disponibles': Recurso.query.filter_by(estado='disponible').count(),
        'total_recursos': Recurso.query.count(),
        'total_usuarios_activos': User.query.filter_by(activo=True).count(),
        'accesos_rfid': RegistroAcceso.query.filter(
            RegistroAcceso.fecha_evento >= fecha_ini
        ).count() if fecha_ini else RegistroAcceso.query.count(),
    }

    # Usuarios para filtro individual
    #usuarios = User.query.filter(
    #    User.activo == True,
    #    User.role.has(db.or_(
    #        *[User.role_id == r for r in [
    #            db.session.query(db.Column).from_statement(
    #                db.text("SELECT id FROM roles WHERE name IN ('docente','estudiante')")
    #            )
    #        ]]
    #    ))
    #).order_by(User.nombre).all()

    # Más simple: traer docentes y estudiantes
    from app.models import Role
    roles_ids = [r.id for r in Role.query.filter(
        Role.name.in_(['docente', 'estudiante'])
    ).all()]
    usuarios = User.query.filter(
        User.activo == True,
        User.role_id.in_(roles_ids)
    ).order_by(User.nombre).all()

    espacios = Espacio.query.order_by(Espacio.nombre).all()
    recursos_lista = Recurso.query.order_by(Recurso.nombre).all()

    return render_template('estadisticas/dashboard.html',
                           kpis=kpis,
                           periodo=periodo,
                           fecha_desde=fecha_desde_str,
                           fecha_hasta=fecha_hasta_str,
                           usuarios=usuarios,
                           espacios=espacios,
                           recursos_lista=recursos_lista)


# ── APIs de datos para Chart.js ────────────────────────────────────────────────

@bp.route('/api/solicitudes-por-estado')
@login_required
@admin_o_operador
def api_solicitudes_estado():
    periodo = request.args.get('periodo', 'mes')
    fecha_ini, fecha_fin = _rango_fechas(periodo)

    q = Solicitud.query
    if fecha_ini:
        q = q.filter(Solicitud.fecha_creacion >= fecha_ini)
    if fecha_fin:
        q = q.filter(Solicitud.fecha_creacion <= fecha_fin)

    estados = ['pendiente', 'aprobada', 'entregado', 'devuelta', 'rechazada']
    datos = []
    for e in estados:
        datos.append(q.filter(Solicitud.estado == e).count())

    return jsonify({
        'labels': ['Pendiente', 'Aprobada', 'Entregado', 'Devuelta', 'Rechazada'],
        'data': datos,
        'colors': ['#6c757d', '#0d6efd', '#198754', '#0dcaf0', '#dc3545']
    })


@bp.route('/api/solicitudes-por-mes')
@login_required
@admin_o_operador
def api_solicitudes_mes():
    # Últimos 12 meses
    ahora = datetime.now(BOGOTA_TZ).replace(tzinfo=None)
    labels = []
    aprobadas = []
    rechazadas = []
    totales = []

    for i in range(11, -1, -1):
        fecha = ahora - timedelta(days=30 * i)
        mes_ini = fecha.replace(day=1, hour=0, minute=0, second=0)
        if i == 0:
            mes_fin = ahora
        else:
            siguiente = fecha.replace(day=28) + timedelta(days=4)
            mes_fin = siguiente.replace(day=1)

        labels.append(fecha.strftime('%b %Y'))
        total = Solicitud.query.filter(
            Solicitud.fecha_creacion >= mes_ini,
            Solicitud.fecha_creacion < mes_fin
        ).count()
        apr = Solicitud.query.filter(
            Solicitud.fecha_creacion >= mes_ini,
            Solicitud.fecha_creacion < mes_fin,
            Solicitud.estado.in_(['aprobada', 'entregado', 'devuelta'])
        ).count()
        rec = Solicitud.query.filter(
            Solicitud.fecha_creacion >= mes_ini,
            Solicitud.fecha_creacion < mes_fin,
            Solicitud.estado == 'rechazada'
        ).count()
        totales.append(total)
        aprobadas.append(apr)
        rechazadas.append(rec)

    return jsonify({
        'labels': labels,
        'datasets': [
            {'label': 'Total', 'data': totales, 'color': '#1b4332'},
            {'label': 'Aprobadas', 'data': aprobadas, 'color': '#198754'},
            {'label': 'Rechazadas', 'data': rechazadas, 'color': '#dc3545'},
        ]
    })


@bp.route('/api/recursos-mas-solicitados')
@login_required
@admin_o_operador
def api_recursos_solicitados():
    periodo = request.args.get('periodo', 'mes')
    fecha_ini, fecha_fin = _rango_fechas(periodo)

    q = db.session.query(
        Recurso.nombre,
        db.func.count(Solicitud.id).label('total')
    ).join(Solicitud, Solicitud.recurso_id == Recurso.id)

    if fecha_ini:
        q = q.filter(Solicitud.fecha_creacion >= fecha_ini)
    if fecha_fin:
        q = q.filter(Solicitud.fecha_creacion <= fecha_fin)

    resultados = q.group_by(Recurso.id).order_by(
        db.func.count(Solicitud.id).desc()
    ).limit(10).all()

    return jsonify({
        'labels': [r.nombre for r in resultados],
        'data': [r.total for r in resultados],
        'color': '#1b4332'
    })


@bp.route('/api/espacios-mas-accedidos')
@login_required
@admin_o_operador
def api_espacios_accedidos():
    periodo = request.args.get('periodo', 'mes')
    fecha_ini, fecha_fin = _rango_fechas(periodo)

    q = db.session.query(
        Espacio.nombre,
        db.func.count(RegistroAcceso.id).label('total')
    ).join(RegistroAcceso, RegistroAcceso.espacio_id == Espacio.id)

    if fecha_ini:
        q = q.filter(RegistroAcceso.fecha_evento >= fecha_ini)
    if fecha_fin:
        q = q.filter(RegistroAcceso.fecha_evento <= fecha_fin)

    resultados = q.group_by(Espacio.id).order_by(
        db.func.count(RegistroAcceso.id).desc()
    ).limit(8).all()

    colores = ['#1b4332', '#2d6a4f', '#40916c', '#52b788',
               '#74c69d', '#95d5b2', '#b7e4c7', '#d8f3dc']

    return jsonify({
        'labels': [r.nombre for r in resultados],
        'data': [r.total for r in resultados],
        'colors': colores[:len(resultados)]
    })


@bp.route('/api/accesos-por-hora')
@login_required
@admin_o_operador
def api_accesos_hora():
    periodo = request.args.get('periodo', 'mes')
    fecha_ini, fecha_fin = _rango_fechas(periodo)

    horas = list(range(0, 24))
    permitidos = []
    denegados = []

    for h in horas:
        q_base = RegistroAcceso.query.filter(
            db.func.strftime('%H', RegistroAcceso.fecha_evento) == f'{h:02d}'
        )
        if fecha_ini:
            q_base = q_base.filter(RegistroAcceso.fecha_evento >= fecha_ini)
        if fecha_fin:
            q_base = q_base.filter(RegistroAcceso.fecha_evento <= fecha_fin)

        permitidos.append(q_base.filter_by(autorizado=True).count())
        denegados.append(q_base.filter_by(autorizado=False).count())

    return jsonify({
        'labels': [f'{h:02d}:00' for h in horas],
        'datasets': [
            {'label': 'Permitidos', 'data': permitidos, 'color': '#198754'},
            {'label': 'Denegados', 'data': denegados, 'color': '#dc3545'},
        ]
    })


@bp.route('/api/tiempo-uso-promedio')
@login_required
@admin_o_operador
def api_tiempo_uso():
    periodo = request.args.get('periodo', 'mes')
    fecha_ini, fecha_fin = _rango_fechas(periodo)

    q = db.session.query(
        Recurso.nombre,
        db.func.avg(Solicitud.tiempo_uso_minutos).label('promedio')
    ).join(Solicitud, Solicitud.recurso_id == Recurso.id).filter(
        Solicitud.tiempo_uso_minutos.isnot(None)
    )

    if fecha_ini:
        q = q.filter(Solicitud.fecha_creacion >= fecha_ini)
    if fecha_fin:
        q = q.filter(Solicitud.fecha_creacion <= fecha_fin)

    resultados = q.group_by(Recurso.id).order_by(
        db.func.avg(Solicitud.tiempo_uso_minutos).desc()
    ).limit(8).all()

    def fmt(minutos):
        if minutos is None:
            return 0
        return round(minutos / 60, 1)

    return jsonify({
        'labels': [r.nombre for r in resultados],
        'data': [fmt(r.promedio) for r in resultados],
        'color': '#b8901f'
    })


@bp.route('/api/usuarios-mas-activos')
@login_required
@admin_o_operador
def api_usuarios_activos():
    periodo = request.args.get('periodo', 'mes')
    fecha_ini, fecha_fin = _rango_fechas(periodo)

    q = db.session.query(
        User.nombre,
        User.apellido,
        db.func.count(Solicitud.id).label('total')
    ).join(Solicitud, Solicitud.usuario_id == User.id)

    if fecha_ini:
        q = q.filter(Solicitud.fecha_creacion >= fecha_ini)
    if fecha_fin:
        q = q.filter(Solicitud.fecha_creacion <= fecha_fin)

    resultados = q.group_by(User.id).order_by(
        db.func.count(Solicitud.id).desc()
    ).limit(8).all()

    return jsonify({
        'labels': [f'{r.nombre} {r.apellido}' for r in resultados],
        'data': [r.total for r in resultados],
        'color': '#0d6efd'
    })


# ── Estadística individual ─────────────────────────────────────────────────────

@bp.route('/individual')
@login_required
@admin_o_operador
def individual():
    tipo = request.args.get('tipo', 'usuario')
    item_id = request.args.get('id', 0, type=int)
    periodo = request.args.get('periodo', 'mes')
    fecha_ini, fecha_fin = _rango_fechas(periodo)

   
    from app.models import Role
    roles_ids = [r.id for r in Role.query.filter(
        Role.name.in_(['docente', 'estudiante'])
    ).all()]
    usuarios = User.query.filter(
        User.activo == True,
        User.role_id.in_(roles_ids)
    ).order_by(User.nombre).all()

    espacios = Espacio.query.order_by(Espacio.nombre).all()
    recursos_lista = Recurso.query.order_by(Recurso.nombre).all()

    contexto = {
        'tipo': tipo,
        'item_id': item_id,
        'periodo': periodo,
        'usuarios': usuarios,
        'espacios': espacios,
        'recursos_lista': recursos_lista,
        'item': None,
        'datos': {}
    }

    if tipo == 'usuario' and item_id:
        usuario = User.query.get(item_id)
        if usuario:
            q = Solicitud.query.filter_by(usuario_id=item_id)
            if fecha_ini:
                q = q.filter(Solicitud.fecha_creacion >= fecha_ini)
            if fecha_fin:
                q = q.filter(Solicitud.fecha_creacion <= fecha_fin)

            solicitudes = q.all()
            contexto['item'] = usuario
            contexto['datos'] = {
                'total': len(solicitudes),
                'aprobadas': sum(1 for s in solicitudes
                                 if s.estado in ['aprobada', 'entregado', 'devuelta']),
                'rechazadas': sum(1 for s in solicitudes if s.estado == 'rechazada'),
                'en_uso': sum(1 for s in solicitudes if s.estado == 'entregado'),
                'tiempo_total': sum(s.tiempo_uso_minutos or 0 for s in solicitudes),
                'solicitudes': solicitudes[-10:]
            }

    elif tipo == 'recurso' and item_id:
        recurso = Recurso.query.get(item_id)
        if recurso:
            q = Solicitud.query.filter_by(recurso_id=item_id)
            if fecha_ini:
                q = q.filter(Solicitud.fecha_creacion >= fecha_ini)
            if fecha_fin:
                q = q.filter(Solicitud.fecha_creacion <= fecha_fin)

            solicitudes = q.all()
            contexto['item'] = recurso
            contexto['datos'] = {
                'total_solicitudes': len(solicitudes),
                'veces_prestado': sum(1 for s in solicitudes
                                      if s.estado in ['entregado', 'devuelta']),
                'tiempo_promedio': (
                    sum(s.tiempo_uso_minutos or 0 for s in solicitudes) //
                    max(1, sum(1 for s in solicitudes if s.tiempo_uso_minutos))
                ),
                'solicitudes': solicitudes[-10:]
            }

    elif tipo == 'espacio' and item_id:
        espacio = Espacio.query.get(item_id)
        if espacio:
            q = RegistroAcceso.query.filter_by(espacio_id=item_id)
            if fecha_ini:
                q = q.filter(RegistroAcceso.fecha_evento >= fecha_ini)
            if fecha_fin:
                q = q.filter(RegistroAcceso.fecha_evento <= fecha_fin)

            accesos = q.all()
            contexto['item'] = espacio
            contexto['datos'] = {
                'total_accesos': len(accesos),
                'permitidos': sum(1 for a in accesos if a.autorizado),
                'denegados': sum(1 for a in accesos if not a.autorizado),
                'accesos': accesos[-10:]
            }

    return render_template('estadisticas/individual.html', **contexto)


@bp.route('/api/individual/solicitudes-por-mes')
@login_required
@admin_o_operador
def api_individual_solicitudes():
    tipo = request.args.get('tipo', 'usuario')
    item_id = request.args.get('id', 0, type=int)

    ahora = datetime.now(BOGOTA_TZ).replace(tzinfo=None)
    labels = []
    datos = []

    for i in range(11, -1, -1):
        fecha = ahora - timedelta(days=30 * i)
        mes_ini = fecha.replace(day=1, hour=0, minute=0, second=0)
        if i == 0:
            mes_fin = ahora
        else:
            siguiente = fecha.replace(day=28) + timedelta(days=4)
            mes_fin = siguiente.replace(day=1)
        labels.append(fecha.strftime('%b %Y'))

        if tipo == 'usuario':
            c = Solicitud.query.filter(
                Solicitud.usuario_id == item_id,
                Solicitud.fecha_creacion >= mes_ini,
                Solicitud.fecha_creacion < mes_fin
            ).count()
        elif tipo == 'recurso':
            c = Solicitud.query.filter(
                Solicitud.recurso_id == item_id,
                Solicitud.fecha_creacion >= mes_ini,
                Solicitud.fecha_creacion < mes_fin
            ).count()
        elif tipo == 'espacio':
            c = RegistroAcceso.query.filter(
                RegistroAcceso.espacio_id == item_id,
                RegistroAcceso.fecha_evento >= mes_ini,
                RegistroAcceso.fecha_evento < mes_fin
            ).count()
        else:
            c = 0
        datos.append(c)

    return jsonify({'labels': labels, 'data': datos, 'color': '#1b4332'})


# ── Exportar Excel del dashboard ───────────────────────────────────────────────

@bp.route('/exportar/excel')
@login_required
@admin_o_operador
def exportar_excel():
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    periodo = request.args.get('periodo', 'mes')
    fecha_ini, fecha_fin = _rango_fechas(periodo)

    wb = openpyxl.Workbook()
    verde_fill = PatternFill(start_color='1b4332', end_color='1b4332', fill_type='solid')
    header_font = Font(name='Calibri', bold=True, color='FFFFFF', size=11)
    data_font = Font(name='Calibri', size=10)
    center = Alignment(horizontal='center', vertical='center')
    thin = Side(style='thin', color='CCCCCC')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def escribir_hoja(ws, titulo, headers, filas):
        ws.merge_cells(f'A1:{get_column_letter(len(headers))}1')
        ws['A1'] = titulo
        ws['A1'].font = Font(name='Calibri', bold=True, size=13, color='1b4332')
        ws['A1'].alignment = center
        ws.row_dimensions[1].height = 22

        for col, h in enumerate(headers, 1):
            c = ws.cell(row=2, column=col, value=h)
            c.font = header_font
            c.fill = verde_fill
            c.alignment = center
            c.border = border
        ws.row_dimensions[2].height = 18

        for row_num, fila in enumerate(filas, 3):
            alt = PatternFill(
                start_color='f0f7f3' if row_num % 2 == 0 else 'FFFFFF',
                end_color='f0f7f3' if row_num % 2 == 0 else 'FFFFFF',
                fill_type='solid'
            )
            for col, val in enumerate(fila, 1):
                c = ws.cell(row=row_num, column=col, value=val)
                c.font = data_font
                c.alignment = center
                c.border = border
                c.fill = alt

        for col in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 20

    # Hoja 1: Solicitudes
    ws1 = wb.active
    ws1.title = 'Solicitudes'
    q = Solicitud.query
    if fecha_ini:
        q = q.filter(Solicitud.fecha_creacion >= fecha_ini)
    if fecha_fin:
        q = q.filter(Solicitud.fecha_creacion <= fecha_fin)
    solicitudes = q.order_by(Solicitud.fecha_creacion.desc()).all()
    filas1 = []
    for s in solicitudes:
        horas = (s.tiempo_uso_minutos or 0) // 60
        mins = (s.tiempo_uso_minutos or 0) % 60
        filas1.append([
            s.id,
            f'{s.usuario.nombre} {s.usuario.apellido}',
            s.usuario.get_role_name().capitalize(),
            s.tipo.upper(),
            s.get_item_nombre(),
            s.fecha_creacion.strftime('%d/%m/%Y %H:%M'),
            s.fecha_inicio.strftime('%d/%m/%Y %H:%M') if s.fecha_inicio else '—',
            s.fecha_fin_efectiva().strftime('%d/%m/%Y %H:%M') if s.fecha_fin_efectiva() else '—',
            s.estado.capitalize(),
            f'{horas}h {mins}min' if s.tiempo_uso_minutos else '—'
        ])
    escribir_hoja(ws1, f'Solicitudes — Período: {periodo}',
                  ['#', 'Usuario', 'Rol', 'Tipo', 'Item', 'Creada',
                   'Inicio', 'Fin estimado', 'Estado', 'Tiempo uso'],
                  filas1)

    # Hoja 2: Recursos más solicitados
    ws2 = wb.create_sheet('Recursos top')
    res_q = db.session.query(
        Recurso.nombre, Recurso.serial,
        db.func.count(Solicitud.id).label('total')
    ).join(Solicitud, Solicitud.recurso_id == Recurso.id)
    if fecha_ini:
        res_q = res_q.filter(Solicitud.fecha_creacion >= fecha_ini)
    res_top = res_q.group_by(Recurso.id).order_by(
        db.func.count(Solicitud.id).desc()
    ).all()
    escribir_hoja(ws2, 'Recursos más solicitados',
                  ['Recurso', 'Serial', 'Total solicitudes'],
                  [(r.nombre, r.serial or '—', r.total) for r in res_top])

    # Hoja 3: Accesos RFID
    ws3 = wb.create_sheet('Accesos RFID')
    acc_q = RegistroAcceso.query
    if fecha_ini:
        acc_q = acc_q.filter(RegistroAcceso.fecha_evento >= fecha_ini)
    if fecha_fin:
        acc_q = acc_q.filter(RegistroAcceso.fecha_evento <= fecha_fin)
    accesos = acc_q.order_by(RegistroAcceso.fecha_evento.desc()).limit(500).all()
    filas3 = []
    for a in accesos:
        filas3.append([
            a.fecha_evento.strftime('%d/%m/%Y %H:%M:%S'),
            f'{a.usuario.nombre} {a.usuario.apellido}' if a.usuario else 'Desconocido',
            a.espacio.nombre if a.espacio else '—',
            a.dispositivo.codigo if a.dispositivo else '—',
            a.tipo_evento.capitalize(),
            '✅ Permitido' if a.autorizado else '❌ Denegado',
            a.motivo_denegacion or '—'
        ])
    escribir_hoja(ws3, 'Registros de acceso RFID',
                  ['Fecha/Hora', 'Usuario', 'Espacio', 'Dispositivo',
                   'Tipo', 'Resultado', 'Motivo'],
                  filas3)

    # Hoja 4: Usuarios más activos
    ws4 = wb.create_sheet('Usuarios activos')
    usr_q = db.session.query(
        User.nombre, User.apellido,
        db.func.count(Solicitud.id).label('total')
    ).join(Solicitud, Solicitud.usuario_id == User.id)
    if fecha_ini:
        usr_q = usr_q.filter(Solicitud.fecha_creacion >= fecha_ini)
    usr_top = usr_q.group_by(User.id).order_by(
        db.func.count(Solicitud.id).desc()
    ).all()
    escribir_hoja(ws4, 'Usuarios más activos',
                  ['Nombre', 'Apellido', 'Total solicitudes'],
                  [(u.nombre, u.apellido, u.total) for u in usr_top])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre = f"estadisticas_{periodo}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(buf,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=nombre)