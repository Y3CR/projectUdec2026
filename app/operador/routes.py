from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.operador import bp
from app.models import Espacio, TipoEspacio, Recurso, CategoriaRecurso


# ── Decorador: operador o administrador ───────────────────────────────────────
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
    }
    return render_template('operador/dashboard.html', stats=stats)


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
                           espacios=espacios_paginados,
                           tipos=tipos,
                           busqueda=busqueda,
                           tipo_filtro=tipo_filtro,
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

        espacio = Espacio(
            nombre=nombre, codigo=codigo, tipo_id=tipo_id,
            capacidad=capacidad, ubicacion=ubicacion,
            descripcion=descripcion, disponible=disponible
        )
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
                           recursos=recursos_paginados,
                           categorias=categorias,
                           estados=estados,
                           busqueda=busqueda,
                           categoria_filtro=categoria_filtro,
                           estado_filtro=estado_filtro)


@bp.route('/recursos/nuevo', methods=['GET', 'POST'])
@login_required
@operador_required
def nuevo_recurso():
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

        errores = _validar_recurso(nombre, codigo, categoria_id, cantidad_total, cantidad_disponible, estado, estados)
        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Registrar', data=request.form)

        if Recurso.query.filter_by(codigo=codigo).first():
            flash(f'Ya existe un recurso con el código {codigo}.', 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Registrar', data=request.form)

        recurso = Recurso(
            nombre=nombre, codigo=codigo, categoria_id=categoria_id,
            descripcion=descripcion, estado=estado,
            cantidad_total=cantidad_total, cantidad_disponible=cantidad_disponible
        )
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
        codigo = request.form.get('codigo', '').strip().upper()
        categoria_id = request.form.get('categoria_id', type=int)
        descripcion = request.form.get('descripcion', '').strip()
        estado = request.form.get('estado', 'disponible')
        cantidad_total = request.form.get('cantidad_total', 1, type=int)
        cantidad_disponible = request.form.get('cantidad_disponible', 1, type=int)

        errores = _validar_recurso(nombre, codigo, categoria_id, cantidad_total, cantidad_disponible, estado, estados)
        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Editar', data=request.form, recurso=recurso)

        existente = Recurso.query.filter_by(codigo=codigo).first()
        if existente and existente.id != recurso_id:
            flash(f'Ya existe otro recurso con el código {codigo}.', 'danger')
            return render_template('operador/recurso_form.html', categorias=categorias,
                                   estados=estados, accion='Editar', data=request.form, recurso=recurso)

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


# ── Helpers de validación ──────────────────────────────────────────────────────

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


def _validar_recurso(nombre, codigo, categoria_id, cantidad_total, cantidad_disponible, estado, estados_validos):
    errores = []
    if not nombre:
        errores.append('El nombre del recurso es obligatorio.')
    if not codigo:
        errores.append('El código del recurso es obligatorio.')
    if not categoria_id:
        errores.append('Debes seleccionar una categoría.')
    if cantidad_total < 1:
        errores.append('La cantidad total debe ser al menos 1.')
    if cantidad_disponible < 0:
        errores.append('La cantidad disponible no puede ser negativa.')
    if cantidad_disponible > cantidad_total:
        errores.append('La cantidad disponible no puede superar la cantidad total.')
    if estado not in estados_validos:
        errores.append('El estado seleccionado no es válido.')
    return errores