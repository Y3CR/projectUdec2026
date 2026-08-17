from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length
 
 
class LoginForm(FlaskForm):
    email = StringField('Correo institucional', validators=[
        DataRequired(message='El correo es obligatorio.'),
        Email(message='Ingresa un correo válido.'),
        Length(max=150)
    ])
    password = PasswordField('Contraseña', validators=[
        DataRequired(message='La contraseña es obligatoria.')
    ])
    remember_me = BooleanField('Recordarme')
    submit = SubmitField('Ingresar')
 