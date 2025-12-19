import threading
import time
from flask import Blueprint, render_template, jsonify, session, redirect, url_for
import RPi.GPIO as GPIO
from functools import wraps
import requests
import os

water_bp = Blueprint('water', __name__, template_folder='templates')

# Configuration
GPIO.setmode(GPIO.BCM)
TRIG_PIN = 22  # Physical Pin 15
ECHO_PIN = 23  # Physical Pin 16
TANK_HEIGHT = 15  # Height of tank in cm

# Shared variables
current_level = 0  # Starting at 50% for demo

# Setup GPIO
GPIO.setup(TRIG_PIN, GPIO.OUT)
GPIO.setup(ECHO_PIN, GPIO.IN)
GPIO.output(TRIG_PIN, False)
time.sleep(0.5)  # Allow sensor to settle
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
def calculate_volume(distance_cm):
    """Convert distance to volume percentage"""
    height_water = TANK_HEIGHT - distance_cm
    return max(0, min(100, int((height_water / TANK_HEIGHT) * 100)))

def read_sensor():
    global current_level
    while True:
        try:
            # Send trigger pulse
            GPIO.output(TRIG_PIN, True)
            time.sleep(0.00001)
            GPIO.output(TRIG_PIN, False)
            
            # Wait for echo response
            pulse_start = time.time()
            pulse_end = time.time()
            
            timeout = time.time() + 0.04  # 40ms timeout
            
            while GPIO.input(ECHO_PIN) == 0 and time.time() < timeout:
                pulse_start = time.time()
                
            while GPIO.input(ECHO_PIN) == 1 and time.time() < timeout:
                pulse_end = time.time()
                
            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * 17150  # Speed of sound
            distance = round(distance, 2)
            
            # Filter invalid readings
            if 2 < distance < TANK_HEIGHT * 1.2:
                current_level = calculate_volume(distance)
            current_level = calculate_volume(distance)
            # water tank automation
            thresholds = get_thresholds()
            if current_level < thresholds['lower']:
                control_pump('on')
            elif current_level > thresholds['upper']:
                control_pump('off')
                
        except Exception as e:
            print("here is eror")
            print(f"Sensor error: {e}")
        time.sleep(5)  # Read every 5 seconds
        
def get_thresholds():
    try:
        response = requests.get('http://localhost:5000/api/water/thresholds', timeout=2)
        return response.json()
    except:
        return {'lower': 0, 'upper': 100}
        
def control_pump(state):
    token = os.environ.get('INTERNAL_TOKEN', 'supersecrettoken')
    headers = {'X-Internal-Token': token}
    try:
        requests.post(
            f'http://localhost:5000/internal/control/pump/{state}',
            headers=headers,
            timeout=2
        )
    except:
        print("eror occured when get the data from pump")

# Start sensor thread
sensor_thread = threading.Thread(target=read_sensor, daemon=True)
sensor_thread.start()


@water_bp.route('/update_level')
def update_level():
    print(current_level)
    return jsonify(level=current_level)

@water_bp.route('/watercontrol')
@login_required
def water_dashboard():
    return render_template('tank.html', level=current_level)

