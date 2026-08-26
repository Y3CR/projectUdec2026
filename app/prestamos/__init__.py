from flask import Blueprint

bp = Blueprint('prestamos', __name__)

from app.prestamos import routes