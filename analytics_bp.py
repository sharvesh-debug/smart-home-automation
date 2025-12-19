# analytics_bp.py (Corrected)

from flask import Blueprint, render_template, session, redirect, url_for, jsonify, request, current_app
from flask_sqlalchemy import SQLAlchemy
from datetime import date,datetime, timedelta, timezone # Import timezone
import json
from functools import wraps
import calendar
import logging
import time

# ... (rest of imports and setup)

# Create the blueprint
analytics_bp = Blueprint('analytics', __name__, template_folder='templates')

# We'll import db and models after app context is available
db = None
PowerConsumption = None
PowerSettings = None

def init_analytics_db(database):
    """Initialize database reference - called from main app"""
    global db, PowerConsumption, PowerSettings
    db = database
    
    # Define models here to avoid circular imports
    class PowerConsumption(db.Model):
        __tablename__ = 'power_consumption'
        
        id = db.Column(db.Integer, primary_key=True)
        device_name = db.Column(db.String(50), nullable=False)
        device_id = db.Column(db.Integer, nullable=False)
        power_rating = db.Column(db.Float, nullable=False, default=0.0)
        start_time = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)) # Use UTC
        end_time = db.Column(db.DateTime)
        duration_minutes = db.Column(db.Float, default=0.0)
        units_consumed = db.Column(db.Float, default=0.0)
        is_active = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc)) # Use UTC

    class PowerSettings(db.Model):
        __tablename__ = 'power_settings'
        
        id = db.Column(db.Integer, primary_key=True)
        device_name = db.Column(db.String(50), nullable=False, unique=True)
        device_id = db.Column(db.Integer, nullable=False)
        power_rating = db.Column(db.Float, nullable=False, default=100.0)
        updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)) # Use UTC

    # Make models globally available
    globals()['PowerConsumption'] = PowerConsumption
    globals()['PowerSettings'] = PowerSettings
    
    # Create tables
    with current_app.app_context():
        db.create_all()
            
        # Initialize default power settings if they don't exist
        if not PowerSettings.query.first():
            default_settings = [
                PowerSettings(device_name='socket1', device_id=1, power_rating=100.0),
                PowerSettings(device_name='socket2', device_id=2, power_rating=100.0),
                PowerSettings(device_name='water_pump', device_id=3, power_rating=500.0)
            ]
            for setting in default_settings:
                db.session.add(setting)
            db.session.commit()
            logging.info("Default power settings initialized")
    
    return PowerConsumption, PowerSettings

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- CORRECTED BILL CALCULATION ---
def calculate_tneb_bill(total_units):
    """Correctly calculate TNEB bill based on total consumption."""
    if total_units <= 400:
        return 0.0

    rate = 0.0
    if 401 <= total_units <= 500:
        rate = 6.45
    elif 501 <= total_units <= 600:
        rate = 8.55
    elif 601 <= total_units <= 800:
        rate = 9.65
    elif 801 <= total_units <= 1000:
        rate = 10.70
    elif total_units > 1000:
        rate = 11.80

    total_bill = total_units * rate
    return round(total_bill, 2)


def get_monthly_consumption(year, month):
    """Get total power consumption for a specific month using UTC dates"""
    if not db or not PowerConsumption:
        return 0.0
        
    start_date = datetime(year, month, 1, tzinfo=timezone.utc) # Make timezone-aware
    
    # Correctly calculate the end date for the next month
    if month == 12:
        end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    
    try:
        from sqlalchemy import func, and_
        total_units = db.session.query(func.sum(PowerConsumption.units_consumed)).filter(
            and_(
                PowerConsumption.start_time >= start_date,
                PowerConsumption.start_time < end_date, # Use < for exclusive end
                PowerConsumption.end_time.isnot(None)
            )
        ).scalar() or 0.0
        
        return round(total_units, 3)
    except Exception as e:
        logging.error(f"Error getting monthly consumption: {e}")
        return 0.0

def log_device_start(device_name, device_id):
    if not db or not PowerConsumption or not PowerSettings:
        logging.warning("Database not initialized for power monitoring")
        return None
    try:
        settings = PowerSettings.query.filter_by(device_name=device_name).first()
        power_rating = settings.power_rating if settings else 100.0
        
        consumption = PowerConsumption(
            device_name=device_name,
            device_id=device_id,
            power_rating=power_rating,
            start_time=datetime.now(timezone.utc), # Use UTC
            is_active=True
        )
        db.session.add(consumption)
        db.session.commit()
        logging.info(f"Started monitoring {device_name} with power rating {power_rating}W")
        return consumption.id
    except Exception as e:
        logging.error(f"Error starting device monitoring: {e}")
        return None

def log_device_stop(device_name, device_id):
    if not db or not PowerConsumption:
        logging.warning("Database not initialized for power monitoring")
        return 0.0
    try:
        consumption = PowerConsumption.query.filter_by(
            device_name=device_name, device_id=device_id, is_active=True
        ).order_by(PowerConsumption.start_time.desc()).first()
        
        if consumption:
            end_time = datetime.now(timezone.utc) # Use UTC
            duration = (end_time - consumption.start_time).total_seconds() / 60
            units_consumed = (consumption.power_rating * duration) / (60 * 1000)
            
            consumption.end_time = end_time
            consumption.duration_minutes = duration
            consumption.units_consumed = units_consumed
            consumption.is_active = False
            
            db.session.commit()
            logging.info(f"Stopped monitoring {device_name}: {units_consumed:.4f} kWh consumed")
            return units_consumed
        return 0.0
    except Exception as e:
        logging.error(f"Error stopping device monitoring: {e}")
        return 0.0


@analytics_bp.route('/analytics')
@login_required
def analytics():
    settings_dict = {'socket1': 100, 'socket2': 100, 'water_pump': 500}
    if db and PowerSettings:
        try:
            settings = PowerSettings.query.all()
            for setting in settings:
                settings_dict[setting.device_name] = setting.power_rating
        except Exception as e:
            logging.error(f"Error loading settings for template: {e}")
    
    # loading monthly states data
    today = date.today()
    
    current_year = today.year
    current_month = today.month
    monthconsump=get_monthly_consumption(current_year ,current_month)
    bill=calculate_tneb_bill( monthconsump)
    return render_template('analytics.html', active_page='analytics', settings=settings_dict, monthconsump=monthconsump,bill=bill)


# --- CORRECTED DAILY CONSUMPTION API ---
@analytics_bp.route('/api/analytics/daily_consumption', methods=['GET'])

def daily_consumption_api():
    """API for the last 7 days of power consumption."""
    if not db or not PowerConsumption:
        return jsonify({'success': False, 'error': 'Database not initialized'})
        
    try:
        from sqlalchemy import func, and_, cast, Date

        # --- FIX: Use UTC for all date operations ---
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=6)
        
        # Query daily consumption, casting start_time to DATE for grouping
        daily_data = db.session.query(
            cast(PowerConsumption.start_time, Date).label('date'),
            func.sum(PowerConsumption.units_consumed).label('total_units')
        ).filter(
            and_(
                PowerConsumption.start_time >= start_date.replace(hour=0, minute=0, second=0),
                PowerConsumption.start_time <= end_date,
                PowerConsumption.end_time.isnot(None)
            )
        ).group_by(cast(PowerConsumption.start_time, Date)).all()
        
        data_dict = {row.date.strftime('%Y-%m-%d'): round(row.total_units, 3) for row in daily_data}
        
        result = []
        # Loop through the last 7 days to ensure all days are present
        for i in range(7):
            current_date = (start_date + timedelta(days=i)).date()
            date_str = current_date.strftime('%Y-%m-%d')
            result.append({
                'date': date_str,
                'units': data_dict.get(date_str, 0.0)
            })
        
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logging.error(f"Error getting daily consumption: {e}")
        return jsonify({'success': False, 'error': str(e)})


# --- CORRECTED DEVICE CONSUMPTION API ---
@analytics_bp.route('/api/analytics/device_consumption', methods=['GET'])

def device_consumption_api():
    """API endpoint for device-wise consumption for today (UTC)."""
    if not db or not PowerConsumption:
        return jsonify({'success': False, 'error': 'Database not initialized'})
        
    try:
        from sqlalchemy import func, and_
        
        # --- FIX: Use UTC for 'today' ---
        today_utc = datetime.now(timezone.utc).date()
        start_of_day = datetime.combine(today_utc, datetime.min.time(), tzinfo=timezone.utc)
        
        device_data = db.session.query(
            PowerConsumption.device_name,
            func.sum(PowerConsumption.units_consumed).label('total_units')
        ).filter(
            and_(
                PowerConsumption.start_time >= start_of_day,
                PowerConsumption.end_time.isnot(None)
            )
        ).group_by(PowerConsumption.device_name).all()
        
        devices = ['socket1', 'socket2', 'water_pump']
        device_labels = {'socket1': 'Socket 1', 'socket2': 'Socket 2', 'water_pump': 'Water Pump'}
        data_dict = {row.device_name: round(row.total_units, 3) for row in device_data}
        
        result = [
            {'device': label, 'units': data_dict.get(device_name, 0.0)}
            for device_name, label in device_labels.items()
        ]
        
        return jsonify({'success': True, 'data': result})
        
    except Exception as e:
        logging.error(f"Error getting device consumption: {e}")
        return jsonify({'success': False, 'error': str(e)})

@analytics_bp.route('/api/analytics/power_settings', methods=['GET'])

def get_power_settings():
    """Get current power settings for all devices"""
    if not db or not PowerSettings:
        return jsonify({'success': False, 'error': 'Database not initialized'})
    try:
        settings = PowerSettings.query.all()
        settings_dict = {s.device_name: s.power_rating for s in settings}
        return jsonify({'success': True, 'settings': settings_dict})
    except Exception as e:
        logging.error(f"Error getting power settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

@analytics_bp.route('/api/analytics/power_settings', methods=['POST'])

def update_power_settings():
    if not db or not PowerSettings:
        return jsonify({'success': False, 'error': 'Database not initialized'})
    try:
        data = request.get_json()
        device_name = data.get('device_name')
        power_rating = float(data.get('power_rating', 0))
        
        if not device_name or power_rating <= 0:
            return jsonify({'success': False, 'error': 'Invalid input data'})
        
        setting = PowerSettings.query.filter_by(device_name=device_name).first()
        if setting:
            setting.power_rating = power_rating
        else:
            device_id_map = {'socket1': 1, 'socket2': 2, 'water_pump': 3}
            setting = PowerSettings(
                device_name=device_name,
                device_id=device_id_map.get(device_name, 1),
                power_rating=power_rating
            )
            db.session.add(setting)
        
        db.session.commit()
        logging.info(f"Power setting updated for {device_name}: {power_rating}W")
        return jsonify({'success': True, 'message': 'Settings updated successfully'})
    except Exception as e:
        db.session.rollback() # Rollback transaction on error
        logging.error(f"Error updating power settings: {e}")
        return jsonify({'success': False, 'error': str(e)})

# --- CORRECTED MONTHLY STATS API ---
@analytics_bp.route('/api/analytics/monthly_stats')

def monthly_stats_api():
    """Get monthly consumption and bill calculation."""
    try:
        # --- FIX: Use UTC consistently ---
        now = datetime.now(timezone.utc)
        current_month_units = get_monthly_consumption(now.year, now.month)
        
        bill_amount = calculate_tneb_bill(current_month_units)
        
        return jsonify({
            'success': True,
            'data': {
                'month': calendar.month_name[now.month],
                'year': now.year,
                'total_units': current_month_units,
                'bill_amount': bill_amount
            }
        })
    except Exception as e:
        logging.error(f"Error getting monthly stats: {e}")
        return jsonify({'success': False, 'error': str(e)})

# Utility functions to be called from other blueprints
def start_device_monitoring(device_name, device_id):
    return log_device_start(device_name, device_id)

def stop_device_monitoring(device_name, device_id):
    return log_device_stop(device_name, device_id)
