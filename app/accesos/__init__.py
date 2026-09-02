from flask import Blueprint

bp = Blueprint('accesos', __name__)

from app.accesos import routes