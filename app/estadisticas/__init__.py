from flask import Blueprint

bp = Blueprint('estadisticas', __name__)

from app.estadisticas import routes