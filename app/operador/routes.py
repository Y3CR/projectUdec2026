from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.operador import bp
from app.models import (Espacio, TipoEspacio, Recurso, CategoriaRecurso,
                        DispositivoRFID, PermisoAcceso, HorarioGlobal, User)


def operador_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.get_role_name() not in ['operador', 'administrador']:
            flash('Acceso denegado. Solo operadores o administradores.', 'danger')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ── Dashboard operador ─────────────────────────────────────────────────────────

@bp.route('/dashboard')
@login_required
@operador_required
def dashboard():
    stats = {
        'total_espacios': Espacio.query.count(),
        'espacios_disponibles': Espacio.query.filter_by(disponible=True).count(),
        'total_recursos': Recurso.query.count(),
        'recursos_disponibles': Recurso.query.filter_by(estado='disponible').count(),
        'total_dispositivos': DispositivoRFID.query.count(),
        'dispositivos_activos': DispositivoRFID.query.filter_by(activo=True).count(),
        'total_permisos': PermisoAcceso.query.count(),
        'permisos_activos': PermisoAcceso.query.filter_by(activo=True).count(),
    }
    horario = HorarioGlobal.query.filter_by(activo=True).first()
    return render_template('operador/dashboard.html', stats=stats, horario=horario)


# ════════════════════════════════════════════════════════════════════════════════
# ESPACIOS
# ════════════════════════════════════════════════════════════════════════════════

@bp.route('/espacios')
@login_required
@operador_required
def espacios():
    page = request.args.get('page', 1, type=int)
    busqueda = request.args.get('q', '')
    tipo_filtro = request.args.get('tipo', 0, type=int)
    disponible_filtro = request.args.get('disponible', '')

    query = Espacio.query.join(TipoEspacio)
    if busqueda:
        query = query.filter(
            (Espacio.nombre.ilike(f'%{busqueda}%')) |
            (Espacio.codigo.ilike(f'%{busqueda}%')) |
            (Espacio.ubicacion.ilike(f'%{busqueda}%'))
        )
    if tipo_filtro:
        query = query.filter(Espacio.tipo_id == tipo_filtro)
    if disponible_filtro == '1':
        query = query.filter(Espacio.disponible == True)
    elif disponible_filtro == '0':
        query = query.filter(Espacio.disponible == False)

    espacios_paginados = query.order_by(Espacio.fecha_creacion.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    tipos = TipoEspacio.query.all()
    return render_template('operador/espacios.html',
                           espacios=espacios_paginados, tipos=tipos,
                           busqueda=busqueda, tipo_filtro=tipo_filtro,
                           disponible_filtro=disponible_filtro)


@bp.route('/espacios/nuevo', methods=['GET', 'POST'])
@login_required
@operador_required
def nuevo_espacio():
    tipos = TipoEspacio.query.all()
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        codigo = request.form.get('codigo', '').strip().upper()
        tipo_id = request.form.get('tipo_id', type=int)
        capacidad = request.form.get('capacidad', 1, type=int)
        ubicacion = request.form.get('ubicacion', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        disponible = request.form.get('disponible') == 'on'

        errores = _validar_espacio(nombre, codigo, tipo_id, capacidad)
        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('operador/espacio_form.html', tipos=tipos,
                                   accion='Registrar', data=request.form)

        if Espacio.query.filter_by(codigo=codigo).first():
            flash(f'Ya existe un espacio con el código {codigo}.', 'danger')
            return render_template('operador/espacio_form.html', tipos=tipos,
                                   accion='Registrar', data=request.form)

        espacio = Espacio(nombre=nombre, codigo=codigo, tipo_id=tipo_id,
                          capacidad=capacidad, ubicacion=ubicacion,
                          descripcion=descripcion, disponible=disponible)
        db.session.add(espacio)
        db.session.commit()
        flash(f'Espacio "{nombre}" registrado exitosamente.', 'success')
        return redirect(url_for('operador.espacios'))

    return render_template('operador/espacio_form.html', tipos=tipos,
                           accion='Registrar', data={})


@bp.route('/espacios/<int:espacio_id>/editar', methods=['GET', 'POST'])
@login_required
@operador_required
def editar_espacio(espacio_id):
    espacio = Espacio.query.get_or_404(espacio_id)
    tipos = TipoEspacio.query.all()
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        codigo = request.form.get('codigo', '').strip().upper()
        tipo_id = request.form.get('tipo_id', type=int)
        capacidad = request.form.get('capacidad', 1, type=int)
        ubicacion = request.form.get('ubicacion', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        disponible = request.form.get('disponible') == 'on'

        errores = _validar_espacio(nombre, codigo, tipo_id, capacidad)
        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('operador/espacio_form.html', tipos=tipos,
                                   accion='Editar', data=request.form, espacio=espacio)

        existente = Espacio.query.filter_by(codigo=codigo).first()
        if existente and existente.id != espacio_id:
            flash(f'Ya existe otro espacio con el código {codigo}.', 'danger')
            return render_template('operador/espacio_form.html', tipos=tipos,
                                   accion='Editar', data=request.form, espacio=espacio)

        espacio.nombre = nombre
        espacio.codigo = codigo
        espacio.tipo_id = tipo_id
        espacio.capacidad = capacidad
        espacio.ubicacion = ubicacion
        espacio.descripcion = descripcion
        espacio.disponible = disponible
        db.session.commit()
        flash('Espacio actualizado correctamente.', 'success')
        return redirect(url_for('operador.espacios'))

    return render_template('operador/espacio_form.html', tipos=tipos,
                           accion='Editar', data={}, espacio=espacio)


@bp.route('/espacios/<int:espacio_id>/eliminar', methods=['POST'])
@login_required
@operador_required
def eliminar_espacio(espacio_id):
    espacio = Espacio.query.get_or_404(espacio_id)
    nombre = espacio.nombre
    db.session.delete(espacio)
    db.session.commit()
    flash(f'Espacio "{nombre}" eliminado correctamente.', 'success')
    return redirect(url_for('operador.espacios'))


# ════════════════════════════════════════════════════════════════════════════════
# RECURSOS
# ════════════════════════════════════════════════════════════════════════════════

@bp.route('/recursos')
@login_required
@operador_required
def recursos():
    page = request.args.get('page', 1, type=int)
    busqueda = request.args.get('q', '')
    categoria_filtro = request.args.get('categoria', 0, type=int)
    estado_filtro = request.args.get('estado', '')

    query = Recurso.query.join(CategoriaRecurso)
    if busqueda:
        query = query.filter(
            (Recurso.nombre.ilike(f'%{busqueda}%')) |
            (Recurso.codigo.ilike(f'%{busqueda}%'))
        )
    if categoria_filtro:
        query = query.filter(Recurso.categoria_id == categoria_filtro)
    if estado_filtro:
        query = query.filter(Recurso.estado == estado_filtro)

    recursos_paginados = query.order_by(Recurso.fecha_creacion.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    categorias = CategoriaRecurso.query.all()
    estados = ['disponible', 'prestado', 'mantenimiento', 'dañado', 'dado_de_baja']
    return render_template('operador/recursos.html',
                           recursos=recursos_paginados, categorias=categorias,
                           estados=estados, busqueda=busqueda,
                           categoria_filtro=categoria_filtro, estado_filtro=estado_filtro)


@bp.route('/recursos/nuevo', methods=['GET', 'POST'])
@login_required
@operador_required
def nuevo_recurso():
    categorias = CategoriaRecurso.query.all()
    estados = ['disponible', 'prestado', 'mantenimiento', 'dañado', 'dado_de_baja']
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        serial = request.form.get('serial', '').strip().upper()
        codigo_interno = request.form.get('codigo_interno', '').strip().upper()
        categoria_id = request.form.get('categoria_id', type=int)
        descripcion = request.form.get('descripcion', '').strip()
        estado = request.form.get('estado', 'disponible')

        errores = _validar_recurso(nombre, serial, codigo_interno, categoria_id, estado, estados)
        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Registrar', data=request.form)

        if Recurso.query.filter_by(serial=serial).first():
            flash(f'Ya existe un recurso con el serial {serial}.', 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Registrar', data=request.form)

        if Recurso.query.filter_by(codigo_interno=codigo_interno).first():
            flash(f'Ya existe un recurso con el código {codigo_interno}.', 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Registrar', data=request.form)

        recurso = Recurso(nombre=nombre, serial=serial, codigo_interno=codigo_interno,
                          categoria_id=categoria_id, descripcion=descripcion, estado=estado)
        db.session.add(recurso)
        db.session.commit()
        flash(f'Recurso "{nombre}" registrado exitosamente.', 'success')
        return redirect(url_for('operador.recursos'))

    return render_template('operador/recurso_form.html', categorias=categorias,
                           estados=estados, accion='Registrar', data={})


@bp.route('/recursos/<int:recurso_id>/editar', methods=['GET', 'POST'])
@login_required
@operador_required
def editar_recurso(recurso_id):
    recurso = Recurso.query.get_or_404(recurso_id)
    categorias = CategoriaRecurso.query.all()
    estados = ['disponible', 'prestado', 'mantenimiento', 'dañado', 'dado_de_baja']
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        serial = request.form.get('serial', '').strip().upper()
        codigo_interno = request.form.get('codigo_interno', '').strip().upper()
        categoria_id = request.form.get('categoria_id', type=int)
        descripcion = request.form.get('descripcion', '').strip()
        estado = request.form.get('estado', 'disponible')

        errores = _validar_recurso(nombre, serial, codigo_interno, categoria_id, estado, estados)
        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Editar', data=request.form, recurso=recurso)

        s = Recurso.query.filter_by(serial=serial).first()
        if s and s.id != recurso_id:
            flash(f'Ya existe otro recurso con el serial {serial}.', 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Editar', data=request.form, recurso=recurso)

        c = Recurso.query.filter_by(codigo_interno=codigo_interno).first()
        if c and c.id != recurso_id:
            flash(f'Ya existe otro recurso con el código {codigo_interno}.', 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Editar', data=request.form, recurso=recurso)

        recurso.nombre = nombre
        recurso.serial = serial
        recurso.codigo_interno = codigo_interno
        recurso.categoria_id = categoria_id
        recurso.descripcion = descripcion
        recurso.estado = estado
        db.session.commit()
        flash('Recurso actualizado correctamente.', 'success')
        return redirect(url_for('operador.recursos'))

    return render_template('operador/recurso_form.html', categorias=categorias,
                           estados=estados, accion='Editar', data={}, recurso=recurso)
    recurso = Recurso.query.get_or_404(recurso_id)
    categorias = CategoriaRecurso.query.all()
    estados = ['disponible', 'prestado', 'mantenimiento', 'dañado', 'dado_de_baja']
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        codigo = request.form.get('codigo', '').strip().upper()
        categoria_id = request.form.get('categoria_id', type=int)
        descripcion = request.form.get('descripcion', '').strip()
        estado = request.form.get('estado', 'disponible')
        cantidad_total = request.form.get('cantidad_total', 1, type=int)
        cantidad_disponible = request.form.get('cantidad_disponible', 1, type=int)

        errores = _validar_recurso(nombre, codigo, categoria_id, cantidad_total,
                                   cantidad_disponible, estado, estados)
        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Editar', data=request.form,
                                   recurso=recurso)

        existente = Recurso.query.filter_by(codigo=codigo).first()
        if existente and existente.id != recurso_id:
            flash(f'Ya existe otro recurso con el código {codigo}.', 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Editar', data=request.form,
                                   recurso=recurso)

        recurso.nombre = nombre
        recurso.codigo = codigo
        recurso.categoria_id = categoria_id
        recurso.descripcion = descripcion
        recurso.estado = estado
        recurso.cantidad_total = cantidad_total
        recurso.cantidad_disponible = cantidad_disponible
        db.session.commit()
        flash('Recurso actualizado correctamente.', 'success')
        return redirect(url_for('operador.recursos'))

    return render_template('operador/recurso_form.html', categorias=categorias,
                           estados=estados, accion='Editar', data={}, recurso=recurso)


@bp.route('/recursos/<int:recurso_id>/eliminar', methods=['POST'])
@login_required
@operador_required
def eliminar_recurso(recurso_id):
    recurso = Recurso.query.get_or_404(recurso_id)
    nombre = recurso.nombre
    db.session.delete(recurso)
    db.session.commit()
    flash(f'Recurso "{nombre}" eliminado correctamente.', 'success')
    return redirect(url_for('operador.recursos'))


# ════════════════════════════════════════════════════════════════════════════════
# DISPOSITIVOS RFID
# ════════════════════════════════════════════════════════════════════════════════

@bp.route('/dispositivos')
@login_required
@operador_required
def dispositivos():
    page = request.args.get('page', 1, type=int)
    dispositivos_paginados = DispositivoRFID.query.order_by(
        DispositivoRFID.fecha_creacion.desc()
    ).paginate(page=page, per_page=10, error_out=False)
    return render_template('operador/dispositivos.html',
                           dispositivos=dispositivos_paginados)


@bp.route('/dispositivos/nuevo', methods=['GET', 'POST'])
@login_required
@operador_required
def nuevo_dispositivo():
    espacios = Espacio.query.all()
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        codigo = request.form.get('codigo', '').strip().upper()
        espacio_id = request.form.get('espacio_id', type=int) or None
        descripcion = request.form.get('descripcion', '').strip()
        activo = request.form.get('activo') == 'on'

        if not nombre or not codigo:
            flash('Nombre y código son obligatorios.', 'danger')
            return render_template('operador/dispositivo_form.html',
                                   espacios=espacios, accion='Registrar', data=request.form)

        if DispositivoRFID.query.filter_by(codigo=codigo).first():
            flash(f'Ya existe un dispositivo con el código {codigo}.', 'danger')
            return render_template('operador/dispositivo_form.html',
                                   espacios=espacios, accion='Registrar', data=request.form)

        dispositivo = DispositivoRFID(nombre=nombre, codigo=codigo,
                                      espacio_id=espacio_id,
                                      descripcion=descripcion, activo=activo)
        db.session.add(dispositivo)
        db.session.commit()
        flash(f'Dispositivo "{nombre}" registrado exitosamente.', 'success')
        return redirect(url_for('operador.dispositivos'))

    return render_template('operador/dispositivo_form.html',
                           espacios=espacios, accion='Registrar', data={})


@bp.route('/dispositivos/<int:dispositivo_id>/editar', methods=['GET', 'POST'])
@login_required
@operador_required
def editar_dispositivo(dispositivo_id):
    dispositivo = DispositivoRFID.query.get_or_404(dispositivo_id)
    espacios = Espacio.query.all()
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        codigo = request.form.get('codigo', '').strip().upper()
        espacio_id = request.form.get('espacio_id', type=int) or None
        descripcion = request.form.get('descripcion', '').strip()
        activo = request.form.get('activo') == 'on'

        if not nombre or not codigo:
            flash('Nombre y código son obligatorios.', 'danger')
            return render_template('operador/dispositivo_form.html',
                                   espacios=espacios, accion='Editar',
                                   data=request.form, dispositivo=dispositivo)

        existente = DispositivoRFID.query.filter_by(codigo=codigo).first()
        if existente and existente.id != dispositivo_id:
            flash(f'Ya existe otro dispositivo con el código {codigo}.', 'danger')
            return render_template('operador/dispositivo_form.html',
                                   espacios=espacios, accion='Editar',
                                   data=request.form, dispositivo=dispositivo)

        dispositivo.nombre = nombre
        dispositivo.codigo = codigo
        dispositivo.espacio_id = espacio_id
        dispositivo.descripcion = descripcion
        dispositivo.activo = activo
        db.session.commit()
        flash('Dispositivo actualizado correctamente.', 'success')
        return redirect(url_for('operador.dispositivos'))

    return render_template('operador/dispositivo_form.html',
                           espacios=espacios, accion='Editar',
                           data={}, dispositivo=dispositivo)


@bp.route('/dispositivos/<int:dispositivo_id>/eliminar', methods=['POST'])
@login_required
@operador_required
def eliminar_dispositivo(dispositivo_id):
    dispositivo = DispositivoRFID.query.get_or_404(dispositivo_id)
    nombre = dispositivo.nombre
    db.session.delete(dispositivo)
    db.session.commit()
    flash(f'Dispositivo "{nombre}" eliminado.', 'success')
    return redirect(url_for('operador.dispositivos'))


# ════════════════════════════════════════════════════════════════════════════════
# PERMISOS DE ACCESO
# ════════════════════════════════════════════════════════════════════════════════

@bp.route('/permisos')
@login_required
@operador_required
def permisos():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)
    if per_page not in [15, 30, 50]:
        per_page = 15
    dispositivo_filtro = request.args.get('dispositivo_id', 0, type=int)

    # Obtener UIDs únicos con paginación
    query = db.session.query(
        PermisoAcceso.uid_tarjeta,
        PermisoAcceso.usuario_id
    ).distinct()

    if dispositivo_filtro:
        query = query.filter(PermisoAcceso.dispositivo_id == dispositivo_filtro)

    total_uids = query.count()
    uids_pagina = query.offset((page - 1) * per_page).limit(per_page).all()

    # Para cada UID obtener todos sus permisos agrupados
    class GrupoPermiso:
        def __init__(self, usuario, uid_tarjeta, permisos):
            self.usuario = usuario
            self.uid_tarjeta = uid_tarjeta
            self.permisos = permisos

    grupos = []
    for uid_tarjeta, usuario_id in uids_pagina:
        usuario = User.query.get(usuario_id)
        q = PermisoAcceso.query.filter_by(uid_tarjeta=uid_tarjeta, usuario_id=usuario_id)
        if dispositivo_filtro:
            q = q.filter_by(dispositivo_id=dispositivo_filtro)
        perms = q.all()
        grupos.append(GrupoPermiso(usuario, uid_tarjeta, perms))

    # Objeto de paginación manual
    import math
    class PageInfo:
        def __init__(self, page, per_page, total):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = math.ceil(total / per_page) if total else 1
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1
            self.next_num = page + 1

        def iter_pages(self):
            for p in range(1, self.pages + 1):
                yield p

    page_info = PageInfo(page, per_page, total_uids)
    dispositivos = DispositivoRFID.query.filter_by(activo=True).all()

    return render_template('operador/permisos.html',
                           grupos=grupos,
                           page_info=page_info,
                           dispositivos=dispositivos,
                           dispositivo_filtro=dispositivo_filtro,
                           per_page=per_page)


@bp.route('/permisos/nuevo', methods=['GET', 'POST'])
@login_required
@operador_required
def nuevo_permiso():
    dispositivos = DispositivoRFID.query.filter_by(activo=True).all()
    usuarios = User.query.filter_by(activo=True).order_by(User.nombre).all()

    if request.method == 'POST':
        usuario_id = request.form.get('usuario_id', type=int)
        dispositivo_id = request.form.get('dispositivo_id', type=int)
        uid_tarjeta = request.form.get('uid_tarjeta', '').strip().upper()
        hora_inicio = request.form.get('hora_inicio', '').strip() or None
        hora_fin = request.form.get('hora_fin', '').strip() or None
        activo = request.form.get('activo') == 'on'

        errores = []
        if not usuario_id:
            errores.append('Debes seleccionar un usuario.')
        if not dispositivo_id:
            errores.append('Debes seleccionar un dispositivo.')
        if not uid_tarjeta:
            errores.append('El UID de la tarjeta es obligatorio.')
        if hora_inicio and hora_fin and hora_inicio >= hora_fin:
            errores.append('La hora de fin debe ser posterior a la de inicio.')

        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('operador/permiso_form.html',
                                   dispositivos=dispositivos, usuarios=usuarios,
                                   accion='Registrar', data=request.form)

        # Verificar que no exista ya ese permiso
        existente = PermisoAcceso.query.filter_by(
            uid_tarjeta=uid_tarjeta,
            dispositivo_id=dispositivo_id
        ).first()
        if existente:
            flash('Ya existe un permiso para esa tarjeta en ese dispositivo.', 'danger')
            return render_template('operador/permiso_form.html',
                                   dispositivos=dispositivos, usuarios=usuarios,
                                   accion='Registrar', data=request.form)

        permiso = PermisoAcceso(
            usuario_id=usuario_id,
            dispositivo_id=dispositivo_id,
            uid_tarjeta=uid_tarjeta,
            hora_inicio=hora_inicio,
            hora_fin=hora_fin,
            activo=activo
        )
        db.session.add(permiso)
        db.session.commit()
        flash('Permiso de acceso registrado correctamente.', 'success')
        return redirect(url_for('operador.permisos'))

    return render_template('operador/permiso_form.html',
                           dispositivos=dispositivos, usuarios=usuarios,
                           accion='Registrar', data={})


@bp.route('/permisos/<int:permiso_id>/editar', methods=['GET', 'POST'])
@login_required
@operador_required
def editar_permiso(permiso_id):
    permiso = PermisoAcceso.query.get_or_404(permiso_id)
    dispositivos = DispositivoRFID.query.filter_by(activo=True).all()
    usuarios = User.query.filter_by(activo=True).order_by(User.nombre).all()

    if request.method == 'POST':
        usuario_id = request.form.get('usuario_id', type=int)
        dispositivo_id = request.form.get('dispositivo_id', type=int)
        uid_tarjeta = request.form.get('uid_tarjeta', '').strip().upper()
        hora_inicio = request.form.get('hora_inicio', '').strip() or None
        hora_fin = request.form.get('hora_fin', '').strip() or None
        activo = request.form.get('activo') == 'on'

        if not usuario_id or not dispositivo_id or not uid_tarjeta:
            flash('Usuario, dispositivo y UID son obligatorios.', 'danger')
            return render_template('operador/permiso_form.html',
                                   dispositivos=dispositivos, usuarios=usuarios,
                                   accion='Editar', data=request.form, permiso=permiso)

        permiso.usuario_id = usuario_id
        permiso.dispositivo_id = dispositivo_id
        permiso.uid_tarjeta = uid_tarjeta
        permiso.hora_inicio = hora_inicio
        permiso.hora_fin = hora_fin
        permiso.activo = activo
        db.session.commit()
        flash('Permiso actualizado correctamente.', 'success')
        return redirect(url_for('operador.permisos'))

    return render_template('operador/permiso_form.html',
                           dispositivos=dispositivos, usuarios=usuarios,
                           accion='Editar', data={}, permiso=permiso)


@bp.route('/permisos/<int:permiso_id>/eliminar', methods=['POST'])
@login_required
@operador_required
def eliminar_permiso(permiso_id):
    permiso = PermisoAcceso.query.get_or_404(permiso_id)
    db.session.delete(permiso)
    db.session.commit()
    flash('Permiso eliminado correctamente.', 'success')
    return redirect(url_for('operador.permisos'))


# ════════════════════════════════════════════════════════════════════════════════
# HORARIO GLOBAL
# ════════════════════════════════════════════════════════════════════════════════

@bp.route('/horario', methods=['GET', 'POST'])
@login_required
@operador_required
def horario_global():
    horario = HorarioGlobal.query.first()
    if request.method == 'POST':
        hora_inicio = request.form.get('hora_inicio', '').strip()
        hora_fin = request.form.get('hora_fin', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        activo = request.form.get('activo') == 'on'

        if not hora_inicio or not hora_fin:
            flash('Hora de inicio y fin son obligatorias.', 'danger')
            return render_template('operador/horario_global.html', horario=horario)

        if hora_inicio >= hora_fin:
            flash('La hora de fin debe ser posterior a la de inicio.', 'danger')
            return render_template('operador/horario_global.html', horario=horario)

        if horario:
            horario.hora_inicio = hora_inicio
            horario.hora_fin = hora_fin
            horario.descripcion = descripcion
            horario.activo = activo
        else:
            horario = HorarioGlobal(hora_inicio=hora_inicio, hora_fin=hora_fin,
                                    descripcion=descripcion, activo=activo)
            db.session.add(horario)

        db.session.commit()
        flash('Horario global actualizado correctamente.', 'success')
        return redirect(url_for('operador.horario_global'))

    return render_template('operador/horario_global.html', horario=horario)

# ════════════════════════════════════════════════════════════════════════════════
# ASIGNAR TARJETA RFID A USUARIOS
# ════════════════════════════════════════════════════════════════════════════════

@bp.route('/usuarios')
@login_required
@operador_required
def usuarios_tarjetas():
    """Lista de usuarios para asignar tarjetas RFID."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)
    if per_page not in [15, 30, 50]:
        per_page = 15
    busqueda = request.args.get('q', '')

    ## query = User.query.filter(
    ##    User.role.has(db.or_(
    ##        User.role_id == r.id for r in []
    ##    ))
    ##)
    # Traer todos los usuarios activos excepto admin
    query = User.query.filter_by(activo=True).filter(
        ~User.role.has(name='administrador')
    )
    if busqueda:
        query = query.filter(
            (User.nombre.ilike(f'%{busqueda}%')) |
            (User.apellido.ilike(f'%{busqueda}%')) |
            (User.email.ilike(f'%{busqueda}%'))
        )

    usuarios_paginados = query.order_by(User.nombre).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('operador/usuarios_tarjetas.html',
                           usuarios=usuarios_paginados,
                           busqueda=busqueda,
                           per_page=per_page)


@bp.route('/usuarios/<int:user_id>/tarjeta', methods=['GET', 'POST'])
@login_required
@operador_required
def asignar_tarjeta(user_id):
    """El operador asigna o actualiza el UID de la tarjeta RFID de un usuario."""
    usuario = User.query.get_or_404(user_id)

    if request.method == 'POST':
        uid = request.form.get('uid_tarjeta', '').strip().upper()

        if uid:
            existente = User.query.filter_by(uid_tarjeta=uid).first()
            if existente and existente.id != user_id:
                flash(f'El UID {uid} ya está asignado a {existente.nombre} {existente.apellido}.', 'danger')
                return render_template('admin/asignar_tarjeta.html', usuario=usuario)
            usuario.uid_tarjeta = uid
            flash(f'Tarjeta {uid} asignada correctamente a {usuario.nombre} {usuario.apellido}.', 'success')
        else:
            usuario.uid_tarjeta = None
            flash(f'Tarjeta removida para {usuario.nombre} {usuario.apellido}.', 'info')

        db.session.commit()
        return redirect(url_for('operador.usuarios_tarjetas'))

    return render_template('admin/asignar_tarjeta.html', usuario=usuario)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validar_espacio(nombre, codigo, tipo_id, capacidad):
    errores = []
    if not nombre:
        errores.append('El nombre del espacio es obligatorio.')
    if not codigo:
        errores.append('El código del espacio es obligatorio.')
    if not tipo_id:
        errores.append('Debes seleccionar un tipo de espacio.')
    if capacidad < 1:
        errores.append('La capacidad debe ser al menos 1.')
    return errores


def _validar_recurso(nombre, serial, codigo_interno, categoria_id, estado, estados_validos):
    errores = []
    if not nombre:
        errores.append('El nombre del recurso es obligatorio.')
    if not serial:
        errores.append('El serial es obligatorio.')
    if not codigo_interno:
        errores.append('El código interno es obligatorio.')
    if not categoria_id:
        errores.append('Debes seleccionar una categoría.')
    if estado not in estados_validos:
        errores.append('El estado seleccionado no es válido.')
    return errores

# ── Categorías de recurso (operador) ──────────────────────────────────────────

@bp.route('/categorias-recurso')
@login_required
@operador_required
def categorias_recurso():
    categorias = CategoriaRecurso.query.order_by(CategoriaRecurso.nombre).all()
    return render_template('admin/categorias_recurso.html',
                           categorias=categorias,
                           endpoint_nueva='operador.nueva_categoria_recurso',
                           endpoint_eliminar='operador.eliminar_categoria_recurso')


@bp.route('/categorias-recurso/nueva', methods=['POST'])
@login_required
@operador_required
def nueva_categoria_recurso():
    nombre = request.form.get('nombre', '').strip()
    if not nombre:
        flash('El nombre es obligatorio.', 'danger')
        return redirect(url_for('operador.categorias_recurso'))
    if CategoriaRecurso.query.filter_by(nombre=nombre).first():
        flash('Ya existe una categoría con ese nombre.', 'danger')
        return redirect(url_for('operador.categorias_recurso'))
    db.session.add(CategoriaRecurso(nombre=nombre))
    db.session.commit()
    flash(f'Categoría "{nombre}" creada.', 'success')
    return redirect(url_for('operador.categorias_recurso'))


@bp.route('/categorias-recurso/<int:cat_id>/eliminar', methods=['POST'])
@login_required
@operador_required
def eliminar_categoria_recurso(cat_id):
    cat = CategoriaRecurso.query.get_or_404(cat_id)
    if cat.recursos.count() > 0:
        flash(f'No puedes eliminar "{cat.nombre}" porque tiene recursos asociados.', 'danger')
        return redirect(url_for('operador.categorias_recurso'))
    db.session.delete(cat)
    db.session.commit()
    flash(f'Categoría "{cat.nombre}" eliminada.', 'success')
    return redirect(url_for('operador.categorias_recurso'))