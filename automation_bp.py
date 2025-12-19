# automation_bp.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from main import app
from  main import db

from functools import wraps
from flask import session
from models import  Automation



automation_bp = Blueprint('automation', __name__, url_prefix='/automation')
# --- Authentication Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
    
@automation_bp.route('/')
@login_required
def automation_dashboard():
    automations = Automation.query.all()
    return render_template('automation.html', automations=automations)

@automation_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_automation():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        automation_type = request.form['type']
        
        new_automation = Automation(
            title=title,
            description=description,
            automation_type=automation_type,
            enabled=True
        )
        
        if automation_type == 'value':
            new_automation.variable = request.form['variable']
            new_automation.min_value = float(request.form['min_value'])
            new_automation.max_value = float(request.form['max_value'])
            new_automation.action = request.form['value_action']
        else:
            time_str = request.form['trigger_time']
            new_automation.trigger_time = datetime.strptime(time_str, '%H:%M').time()
            new_automation.action = request.form['time_action']
        
        db.session.add(new_automation)
        db.session.commit()
        flash('Automation created successfully!', 'success')
        return redirect(url_for('automation.automation_dashboard'))
    
    return render_template('create_automation.html')

@automation_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_automation(id):
    automation = Automation.query.get_or_404(id)
    db.session.delete(automation)
    db.session.commit()
    flash('Automation deleted successfully!', 'success')
    return redirect(url_for('automation.automation_dashboard'))
