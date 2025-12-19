from flask import Blueprint, request, jsonify, render_template
from datetime import datetime, timedelta, date
from main import db
import threading
import time
import sqlite3
from flask import current_app
from flask import Flask
from extensions import app

watermonitor_bp = Blueprint('watermonitor', __name__, url_prefix='/watermonitor')

# In-memory storage for current day
current_pipeline1 = 0.0
current_pipeline2 = 0.0
data_lock = threading.Lock()

# Database model
class WaterFlowDaily(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, unique=True, nullable=False, default=date.today)
    pipeline1 = db.Column(db.Float, default=0.0)
    pipeline2 = db.Column(db.Float, default=0.0)

    def __repr__(self):
        return f'<WaterFlowDaily {self.date}: P1={self.pipeline1}L, P2={self.pipeline2}L>'

# API endpoint to receive flow data
@watermonitor_bp.route('/api/flow_data', methods=['POST','PUT'])
def receive_flow_data():
	
    
    global current_pipeline1, current_pipeline2
    print("here is the bug")
    
    data = request.get_json()
    if not data or 'pipeline1' not in data or 'pipeline2' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid data'}), 400
    print(data)   
    try:
        pipeline1 = float(data['pipeline1'])
        pipeline2 = float(data['pipeline2'])
        
        with data_lock:
            current_pipeline1 += pipeline1
            current_pipeline2 += pipeline2
        
        return jsonify({'status': 'success'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Update database every minute
def update_database():
    global current_pipeline1, current_pipeline2
    with app.app_context(): 
        while True:
      
        
            with data_lock:
                if current_pipeline1 > 0 or current_pipeline2 > 0:
                    today = date.today()
                    try:
                        record = WaterFlowDaily.query.filter_by(date=today).first()
                        if record:
                            print("here is the problem")
                            record.pipeline1 += current_pipeline1
                            record.pipeline2 += current_pipeline2
                            db.session.commit()
                            
                        else:
                            record = WaterFlowDaily(
                            date=today,
                            pipeline1=current_pipeline1,
                            pipeline2=current_pipeline2
                            )
                            db.session.add(record)
                    
                        db.session.commit()
                    
                    # Reset counters
                        current_pipeline1 = 0.0
                        current_pipeline2 = 0.0
                    
                    except Exception as e:
                        print(f"Database update error: {str(e)}")

# Start database update thread
db_thread = threading.Thread(target=update_database, daemon=True)
db_thread.start()

# Dashboard route
@watermonitor_bp.route('/')
def water_dashboard():
    # Get last 7 days data
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=6)
    
    # Query database
    records = WaterFlowDaily.query.filter(
        WaterFlowDaily.date >= start_date
    ).order_by(WaterFlowDaily.date.desc()).all()
    
    # Prepare data
    dates = []
    pipeline1_data = []
    pipeline2_data = []
    
    # Fill in missing days with 0
    current_date = start_date
    while current_date <= end_date:
        dates.append(current_date.strftime('%Y-%m-%d'))
        found = False
        for record in records:
            if record.date == current_date:
                pipeline1_data.append(round(record.pipeline1, 2))
                pipeline2_data.append(round(record.pipeline2, 2))
                found = True
                break
        if not found:
            pipeline1_data.append(0.0)
            pipeline2_data.append(0.0)
        current_date += timedelta(days=1)
    
    # Reverse to show latest last
    dates.reverse()
    pipeline1_data.reverse()
    pipeline2_data.reverse()
    
    return render_template('watermonitor.html', 
                           dates=dates, 
                           pipeline1_data=pipeline1_data,
                           pipeline2_data=pipeline2_data,
                           active_page='watermonitor')

# API for current data
@watermonitor_bp.route('/api/current')
def get_current_data():
    with data_lock:
        return jsonify({
            'pipeline1': current_pipeline1,
            'pipeline2': current_pipeline2
        })

@watermonitor_bp.route('/api/today')
def today_water_usage():
    """Return today's water usage totals"""
    today = date.today()
    record = WaterFlowDaily.query.filter_by(date=today).first()
    
    if record:
        return jsonify({
            'pipeline1': record.pipeline1,
            'pipeline2': record.pipeline2
        })
    return jsonify({
        'pipeline1': 0.0,
        'pipeline2': 0.0
    })
