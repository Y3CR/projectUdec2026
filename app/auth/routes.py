from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, current_user
from datetime import datetime
from app import db
from app.auth import bp
from app.auth.forms import LoginForm
from app.models import User


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if '_user_id' in session:
        return _redirect_by_role(current_user)

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        password = form.password.data

        user = User.query.filter_by(email=email).first()

        if user is None:
            flash('Credenciales incorrectas. Verifica tu correo y contraseña.', 'danger')
            return render_template('auth/login.html', form=form)

        if not user.activo:
            flash('Tu cuenta está desactivada. Contacta al administrador.', 'warning')
            return render_template('auth/login.html', form=form)

        if user.esta_bloqueado():
            minutos_restantes = int(
                (user.bloqueado_hasta - datetime.utcnow()).total_seconds() / 60
            ) + 1
            flash(
                f'Cuenta bloqueada temporalmente. '
                f'Intenta de nuevo en {minutos_restantes} minuto(s).',
                'danger'
            )
            return render_template('auth/login.html', form=form)

        role_name = user.get_role_name()
        allowed_domain = current_app.config['ALLOWED_EMAIL_DOMAIN']
        roles_institucionales = ['administrador', 'docente', 'estudiante', 'operador']

        if role_name in roles_institucionales and not email.endswith(f'@{allowed_domain}'):
            flash(
                f'Solo se permiten correos con dominio @{allowed_domain} para este tipo de usuario.',
                'danger'
            )
            return render_template('auth/login.html', form=form)

        if not user.check_password(password):
            user.registrar_intento_fallido(
                max_intentos=current_app.config['MAX_LOGIN_ATTEMPTS'],
                minutos_bloqueo=current_app.config['LOCK_TIME_MINUTES']
            )
            intentos_restantes = current_app.config['MAX_LOGIN_ATTEMPTS'] - user.intentos_fallidos
            if intentos_restantes > 0:
                flash(
                    f'Credenciales incorrectas. Te quedan {intentos_restantes} intento(s) antes del bloqueo.',
                    'danger'
                )
            else:
                flash(
                    f'Cuenta bloqueada por {current_app.config["LOCK_TIME_MINUTES"]} minutos.',
                    'danger'
                )
            return render_template('auth/login.html', form=form)

        user.resetear_intentos()
        login_user(user, remember=form.remember_me.data)
        session.permanent = True

        flash(f'Bienvenido/a, {user.nombre} {user.apellido}.', 'success')

        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return _redirect_by_role(user)

    return render_template('auth/login.html', form=form)


@bp.route('/logout')
def logout():
    logout_user()
    session.pop('_user_id', None)
    session.pop('_fresh', None)
    session.pop('_id', None)
    session.modified = True
    return redirect(url_for('auth.login'))


def _redirect_by_role(user):
    role_name = user.get_role_name()
    if role_name == 'administrador':
        return redirect(url_for('admin.dashboard'))
    elif role_name == 'operador':
        return redirect(url_for('operador.dashboard'))
    elif role_name in ['docente', 'estudiante']:
        return redirect(url_for('prestamos.mis_solicitudes'))
    elif role_name == 'invitado':
        return redirect(url_for('prestamos.mis_solicitudes'))
    return redirect(url_for('admin.dashboard'))