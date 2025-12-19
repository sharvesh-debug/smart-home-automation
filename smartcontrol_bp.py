from flask import Blueprint, render_template, session, redirect, url_for
import requests
from functools import wraps

#setting the object
smartcontrol_bp = Blueprint('smartcontrol', __name__, template_folder='templates')
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
# home assistant configuration 

HOME_ASSISTANT_URL = "rasberipi ip:8123"
HA_TOKEN =" "

@smartcontrol_bp.route('/smartcontrol')
@login_required
def index():
    return redirect(f"{HOME_ASSISTANT_URL}?auth_token={HA_TOKEN}")
