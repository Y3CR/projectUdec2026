from flask import Blueprint

bp = Blueprint('reportes', __name__)

from app.reportes import routes