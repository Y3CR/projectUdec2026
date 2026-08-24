from flask import Blueprint

bp = Blueprint('operador', __name__)

from app.operador import routes