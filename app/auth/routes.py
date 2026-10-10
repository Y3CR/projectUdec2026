from flask import render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, current_user
from datetime import datetime
from app import db
from app.auth import bp
from app.auth.forms import LoginForm
from app.models import User


# ── Login ──────────────────────────────────────────────────────────────────────

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
            flash(f'Cuenta bloqueada temporalmente. '
                  f'Intenta de nuevo en {minutos_restantes} minuto(s).', 'danger')
            return render_template('auth/login.html', form=form)

        role_name = user.get_role_name()
        allowed_domain = current_app.config['ALLOWED_EMAIL_DOMAIN']
        roles_institucionales = ['administrador', 'docente', 'estudiante', 'operador']

        if role_name in roles_institucionales and not email.endswith(f'@{allowed_domain}'):
            flash(f'Solo se permiten correos con dominio @{allowed_domain}.', 'danger')
            return render_template('auth/login.html', form=form)

        if not user.check_password(password):
            user.registrar_intento_fallido(
                max_intentos=current_app.config['MAX_LOGIN_ATTEMPTS'],
                minutos_bloqueo=current_app.config['LOCK_TIME_MINUTES']
            )
            intentos_restantes = (current_app.config['MAX_LOGIN_ATTEMPTS']
                                  - user.intentos_fallidos)
            if intentos_restantes > 0:
                flash(f'Credenciales incorrectas. '
                      f'Te quedan {intentos_restantes} intento(s).', 'danger')
            else:
                flash(f'Cuenta bloqueada por '
                      f'{current_app.config["LOCK_TIME_MINUTES"]} minutos.', 'danger')
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


# ── Logout ─────────────────────────────────────────────────────────────────────

@bp.route('/logout')
def logout():
    logout_user()
    session.pop('_user_id', None)
    session.pop('_fresh', None)
    session.pop('_id', None)
    session.modified = True
    return redirect(url_for('auth.login'))


# ── Recuperar contraseña — paso 1: pedir correo ────────────────────────────────

@bp.route('/recuperar', methods=['GET', 'POST'])
def recuperar_password():
    if '_user_id' in session:
        return _redirect_by_role(current_user)

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        # Siempre mostrar el mismo mensaje por seguridad
        # (no revelar si el correo existe o no)
        flash('Si ese correo está registrado, recibirás un enlace en los '
              'próximos minutos. Revisa también tu carpeta de spam.', 'info')

        if user and user.activo:
            _enviar_email_recuperacion(user)

        return redirect(url_for('auth.recuperar_password'))

    return render_template('auth/recuperar_password.html')


# ── Recuperar contraseña — paso 2: nueva contraseña ───────────────────────────

@bp.route('/nueva-password/<token>', methods=['GET', 'POST'])
def nueva_password(token):
    if '_user_id' in session:
        return _redirect_by_role(current_user)

    user = _verificar_token(token)
    if not user:
        flash('El enlace no es válido o ha expirado (válido 30 minutos). '
              'Solicita uno nuevo.', 'danger')
        return redirect(url_for('auth.recuperar_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirmar = request.form.get('confirmar', '')

        errores = []
        if len(password) < 8:
            errores.append('La contraseña debe tener al menos 8 caracteres.')
        if password != confirmar:
            errores.append('Las contraseñas no coinciden.')

        if errores:
            for e in errores:
                flash(e, 'danger')
            return render_template('auth/nueva_password.html', token=token)

        user.set_password(password)
        user.intentos_fallidos = 0
        user.bloqueado_hasta = None
        db.session.commit()

        flash('Contraseña actualizada correctamente. Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/nueva_password.html', token=token)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _generar_token(user):
    from itsdangerous import URLSafeTimedSerializer
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return s.dumps(user.email, salt='recuperar-password')


def _verificar_token(token, max_age=1800):  # 30 minutos
    from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='recuperar-password', max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None
    return User.query.filter_by(email=email).first()


def _enviar_email_recuperacion(user):
    try:
        from flask_mail import Message
        from app import mail
        token = _generar_token(user)
        enlace = url_for('auth.nueva_password', token=token, _external=True)
        msg = Message(
            subject='🔐 Recuperación de contraseña — UCundinamarca',
            recipients=[user.email],
            html=f'''
            <div style="font-family:Segoe UI,sans-serif;max-width:520px;margin:0 auto;">
                <div style="background:#1b4332;padding:24px;border-radius:12px 12px 0 0;text-align:center;">
                    <h2 style="color:white;margin:0;">Sistema de Préstamos</h2>
                    <p style="color:#b7e4c7;margin:4px 0 0;">Universidad de Cundinamarca</p>
                </div>
                <div style="background:#ffffff;padding:32px;border:1px solid #e0e0e0;
                            border-top:none;border-radius:0 0 12px 12px;">
                    <p style="font-size:16px;">Hola <strong>{user.nombre}</strong>,</p>
                    <p style="color:#555;">Recibimos una solicitud para restablecer la
                    contraseña de tu cuenta institucional.</p>

                    <div style="text-align:center;margin:28px 0;">
                        <a href="{enlace}"
                           style="background:#1b4332;color:white;padding:14px 32px;
                                  border-radius:8px;text-decoration:none;
                                  font-weight:600;font-size:15px;display:inline-block;">
                            🔑 Restablecer contraseña
                        </a>
                    </div>

                    <p style="color:#888;font-size:13px;">
                        Este enlace es válido por <strong>30 minutos</strong>.
                        Si no solicitaste este cambio, ignora este mensaje —
                        tu contraseña no será modificada.
                    </p>
                    <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
                    <p style="color:#aaa;font-size:11px;text-align:center;">
                        Sistema de Préstamos · Universidad de Cundinamarca · Ext. Facatativá
                    </p>
                </div>
            </div>
            ''',
            body=f'Hola {user.nombre},\n\nRestablece tu contraseña aquí:\n{enlace}\n\n'
                 f'Válido por 30 minutos.\n\nSistema de Préstamos — UCundinamarca'
        )
        mail.send(msg)
    except Exception as e:
        print(f'Error enviando email de recuperación: {e}')


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