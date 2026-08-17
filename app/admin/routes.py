from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.admin import bp
from app.models import User, Role


# ── Decorador: solo administradores ───────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.get_role_name() != 'administrador':
            flash('Acceso denegado. Solo administradores.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


# ── Dashboard ─────────────────────────────────────────────────────────────────
@bp.route('/dashboard')
@login_required
def dashboard():
    stats = {
        'total_usuarios': User.query.count(),
        'usuarios_activos': User.query.filter_by(activo=True).count(),
        'total_roles': Role.query.count(),
    }
    return render_template('admin/dashboard.html', stats=stats)


# ── Listado de usuarios (HU-2) ────────────────────────────────────────────────
@bp.route('/usuarios')
@login_required
@admin_required
def usuarios():
    page = request.args.get('page', 1, type=int)
    busqueda = request.args.get('q', '')
    query = User.query.join(Role)
    if busqueda:
        query = query.filter(
            (User.nombre.ilike(f'%{busqueda}%')) |
            (User.apellido.ilike(f'%{busqueda}%')) |
            (User.email.ilike(f'%{busqueda}%'))
        )
    usuarios_paginados = query.order_by(User.fecha_creacion.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    return render_template('admin/users.html', usuarios=usuarios_paginados, busqueda=busqueda)


# ── Crear usuario (HU-2) ───────────────────────────────────────────────────────
@bp.route('/usuarios/nuevo', methods=['GET', 'POST'])
@login_required
@admin_required
def nuevo_usuario():
    roles = Role.query.all()

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        apellido = request.form.get('apellido', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role_id = request.form.get('role_id', type=int)
        activo = request.form.get('activo') == 'on'

        errores = _validar_usuario(nombre, apellido, email, password, role_id, roles)

        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('admin/user_form.html', roles=roles, accion='Crear',
                                   data=request.form)

        # Verificar email único
        if User.query.filter_by(email=email).first():
            flash('Ya existe un usuario con ese correo.', 'danger')
            return render_template('admin/user_form.html', roles=roles, accion='Crear',
                                   data=request.form)

        usuario = User(
            nombre=nombre,
            apellido=apellido,
            email=email,
            role_id=role_id,
            activo=activo
        )
        usuario.set_password(password)
        db.session.add(usuario)
        db.session.commit()
        flash(f'Usuario {nombre} {apellido} creado exitosamente.', 'success')
        return redirect(url_for('admin.usuarios'))

    return render_template('admin/user_form.html', roles=roles, accion='Crear', data={})


# ── Editar usuario (HU-2 y HU-3) ──────────────────────────────────────────────
@bp.route('/usuarios/<int:user_id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    roles = Role.query.all()

    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        apellido = request.form.get('apellido', '').strip()
        email = request.form.get('email', '').strip().lower()
        role_id = request.form.get('role_id', type=int)
        activo = request.form.get('activo') == 'on'
        nueva_password = request.form.get('password', '').strip()

        errores = _validar_usuario(nombre, apellido, email, None, role_id, roles,
                                   es_edicion=True)
        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('admin/user_form.html', roles=roles, accion='Editar',
                                   data=request.form, usuario=usuario)

        # Verificar email único (excluyendo el usuario actual)
        existente = User.query.filter_by(email=email).first()
        if existente and existente.id != user_id:
            flash('Ya existe otro usuario con ese correo.', 'danger')
            return render_template('admin/user_form.html', roles=roles, accion='Editar',
                                   data=request.form, usuario=usuario)

        usuario.nombre = nombre
        usuario.apellido = apellido
        usuario.email = email
        usuario.role_id = role_id
        usuario.activo = activo
        if nueva_password:
            usuario.set_password(nueva_password)
        db.session.commit()
        flash('Usuario actualizado correctamente.', 'success')
        return redirect(url_for('admin.usuarios'))

    return render_template('admin/user_form.html', roles=roles, accion='Editar',
                           data={}, usuario=usuario)


# ── Eliminar usuario ───────────────────────────────────────────────────────────
@bp.route('/usuarios/<int:user_id>/eliminar', methods=['POST'])
@login_required
@admin_required
def eliminar_usuario(user_id):
    usuario = User.query.get_or_404(user_id)
    if usuario.id == current_user.id:
        flash('No puedes eliminar tu propio usuario.', 'warning')
        return redirect(url_for('admin.usuarios'))
    nombre = f'{usuario.nombre} {usuario.apellido}'
    db.session.delete(usuario)
    db.session.commit()
    flash(f'Usuario {nombre} eliminado.', 'success')
    return redirect(url_for('admin.usuarios'))


# ── Gestión de roles (HU-3) ───────────────────────────────────────────────────
@bp.route('/roles')
@login_required
@admin_required
def roles():
    todos_roles = Role.query.all()
    return render_template('admin/roles.html', roles=todos_roles)


# ── Helper de validación ───────────────────────────────────────────────────────
def _validar_usuario(nombre, apellido, email, password, role_id, roles_disponibles,
                     es_edicion=False):
    errores = []
    allowed_domain = current_app.config['ALLOWED_EMAIL_DOMAIN']

    if not nombre:
        errores.append('El nombre es obligatorio.')
    if not apellido:
        errores.append('El apellido es obligatorio.')
    if not email:
        errores.append('El correo es obligatorio.')
    elif '@' not in email:
        errores.append('El correo no tiene un formato válido.')

    if not role_id:
        errores.append('Debes seleccionar un rol.')
    else:
        role = next((r for r in roles_disponibles if r.id == role_id), None)
        if role is None:
            errores.append('El rol seleccionado no es válido.')
        elif role.name in ['administrador', 'docente', 'estudiante', 'operador']:
            # HU-2 escenario 3: validar dominio institucional
            if email and not email.endswith(f'@{allowed_domain}'):
                errores.append(
                    f'Los usuarios con rol "{role.name}" deben usar un correo '
                    f'con dominio @{allowed_domain}.'
                )

    if not es_edicion and not password:
        errores.append('La contraseña es obligatoria para nuevos usuarios.')
    elif not es_edicion and password and len(password) < 8:
        errores.append('La contraseña debe tener al menos 8 caracteres.')

    return errores