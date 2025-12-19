from main import app,db
from extensions import  automation_manager
import time
import requests
from collections import deque
from threading import Lock, Thread
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, send_from_directory, session, jsonify, request, Response, make_response, url_for, redirect, flash
from flask_sqlalchemy import SQLAlchemy

from state import latest_environment_data, aqi_monitor
import cv2
import numpy as np
import os
import logging
import sys
import atexit
from models import Automation
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('smart_home.log')
    ]
)
logger = logging.getLogger('SmartHome')

# --- Import Custom Modules ---
from camera import Camera
from security import FaceRecognitionSecurity

# --- Hardware Library Import ---
IS_PI = False  # Default to False
dht_sensor = None
permission_request_state = {}
permission_request_active = False
thread_lock = Lock()
detected = False

try:
    import board
    import adafruit_dht
    import RPi.GPIO as GPIO
    IS_PI = True
    logger.info("Running on Raspberry Pi hardware")
except (ImportError, RuntimeError):
    logger.info("Running in development mode (non-Pi environment)")

# --- Hardware Configuration ---
RELAY_PIN = 21
RAIN_SENSOR_PIN = 17
GAS_SENSOR_PIN = 27
INTERNAL_TOKEN = "your_secret_token_here"

if IS_PI:
    # Initialize DHT sensor
    dht_sensor = adafruit_dht.DHT11(board.D4, use_pulseio=False)
    logger.info("DHT11 sensor initialized")
    
    # Initialize GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Relay setup (ensure starts in OFF position)
    GPIO.setup(RELAY_PIN, GPIO.OUT)
    GPIO.output(RELAY_PIN, GPIO.LOW)
    GPIO.cleanup(RELAY_PIN)
    logger.info("Relay initialized to LOW state")
    
    # Sensor inputs
    GPIO.setup(RAIN_SENSOR_PIN, GPIO.IN)
    GPIO.setup(GAS_SENSOR_PIN, GPIO.IN)
    logger.info("Sensor GPIOs initialized")

# Weather API Configuration
API_KEY = "52f6959fe33354369e79f4a40ee8995b"
LATITUDE = "11.0168"
LONGITUDE = "76.9558"
API_URL = f"https://api.openweathermap.org/data/2.5/weather?lat={LATITUDE}&lon={LONGITUDE}&appid={API_KEY}&units=metric"
MY_HOME_SECRET = "u7w@!8sdfg$kl2#q"
# start threading AQI data
# After your existing sensor setup

aqi_monitor.start_monitoring()
# --- App Initialization & Global State ---


app.secret_key = 'u7w@!8sdfg$kl2#q'
app.config['INTERNAL_TOKEN'] = INTERNAL_TOKEN

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///myhome.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

thread_lock = Lock()

permission_request_state = {}
notifications_list = deque(maxlen=20)
sensor_states = {
    "rain": None,
    "gas": None,
}
# intializing data base for water threshold values
# Add after other model definitions in app.py
class WaterTankSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lower_threshold = db.Column(db.Integer, default=0)
    upper_threshold = db.Column(db.Integer, default=100)
    
# data  base to store automation details 
# Add to your models section in app.py

# data base to store user log  in door lock
class AccessLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    entries = db.Column(db.JSON, nullable=False, default=list)  # Stores list of access entries

    def __repr__(self):
        return f'<AccessLog {self.date} - {len(self.entries)} entries>'
# --- Helper Functions ---
def unlock_door():
    """Control door unlock mechanism with proper power management"""
    logger.info("Starting door unlock sequence")
    
    if IS_PI:
        GPIO.setup(RELAY_PIN, GPIO.OUT)
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        logger.info("RELAY ACTIVATED - Door unlocked")
        time.sleep(5)
        GPIO.cleanup(RELAY_PIN)
        logger.info("RELAY DEACTIVATED - Door locked")
    else:
        logger.info("Door unlock simulated (development mode)")
    
    logger.info("Door unlock sequence completed")

def trigger_security_action():
    global permission_request_active, current_unknown_face, detected
    
    logger.info("Security action triggered - unknown face detected")
    permission_request_active = True
    current_unknown_face = security_system.last_detected_face
    detected = True
    logger.info("Permission request activated, detected flag set to True")

# --- Authentication Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def add_notification(icon, color, text, link="#"):
    """Add notification to the global notifications list (thread-safe)"""
    with thread_lock:
        new_notification = {
            "icon": icon,
            "color": color,
            "text": text,
            "time": time.strftime("%H:%M"),
            "link": link,
            "read": False,
            "timestamp": time.time()
        }
        notifications_list.appendleft(new_notification)
        logger.info(f"Notification: {text}")

# --- Camera and Security Initialization ---
camera = None
security_system = None

camera = Camera(record_to_cloud=True)
logger.info("Camera initialized successfully")
atexit.register(camera.stop)
# Initialize security system
security_system = FaceRecognitionSecurity(
    camera, 
    permission_request_state, 
    unlock_door, 
    add_notification,
    trigger_security_action
)
logger.info("Security system initialized")

def read_dht_sensor():
    """Read DHT11 sensor with robust error handling"""
    if not IS_PI or not dht_sensor:
        return 0, 0  # Default values for dev mode
        
    try:
        temperature = dht_sensor.temperature
        humidity = dht_sensor.humidity
        
        # Validate readings
        if temperature is None or humidity is None:
            return 0, 0
            
        return temperature, humidity
    
    except Exception as e:
        logger.error(f"DHT sensor error: {e}")
        return 0, 0

def read_sensors():
    """Read all sensors with robust error handling"""
    sensor_data = {
        "temp": 0,
        "humidity": 0,
        "is_raining": False,
        "gas_detected": False,
    }
    
    if not IS_PI:
        return sensor_data
        
    # Read DHT sensor
    temp, humidity = read_dht_sensor()
    sensor_data["temp"] = temp
    sensor_data["humidity"] = humidity
        
    # Read rain sensor (active low)
    is_raining = GPIO.input(RAIN_SENSOR_PIN) == GPIO.LOW
    sensor_data["is_raining"] = is_raining
        
    # Check for state change
    if sensor_states["rain"] is not None and sensor_states["rain"] != is_raining:
        if is_raining:
            add_notification("fa-cloud-rain", "info", "Rain detected by sensor", "/dashboard")
        else:
            add_notification("fa-sun", "success", "Rain has stopped", "/dashboard")
        sensor_states["rain"] = is_raining
    
    # Read gas sensor (active high)
    gas_detected = GPIO.input(GAS_SENSOR_PIN) == GPIO.LOW
    sensor_data["gas_detected"] = gas_detected
        
    # Check for state change
    if sensor_states["gas"] is not None and sensor_states["gas"] != gas_detected:
        if gas_detected:
            add_notification("fa-smog", "danger", "Gas leak detected!", "/alerts")
        else:
            add_notification("fa-wind", "success", "Gas level back to normal", "/alerts")
    sensor_states["gas"] = gas_detected
    
    return sensor_data

# --- Context Processor for Global Template Variables ---
@app.context_processor
def inject_global_vars():
    with thread_lock:
        unread_count = sum(1 for n in notifications_list if not n.get('read', False))
        has_permission_request = (
            bool(permission_request_state) and 
            permission_request_state.get('active', False) and
            security_system and 
            security_system.last_detected_face is not None
        )
    return dict(
        unread_count=unread_count,
        active_page=None,
        is_pi=IS_PI,
        camera_available=camera is not None,
        security_available=security_system is not None,
        detected=has_permission_request 
    )

@app.route('/api/permission_status')
@login_required
def permission_status():
    """Check if there's an active permission request"""
    try:
        with thread_lock:
            active = bool(permission_request_state and permission_request_state.get('active', False))
            has_face_image = bool(security_system and security_system.last_detected_face is not None)
            
        return jsonify({
            'active': active,
            'has_face_image': has_face_image,
            'timestamp': permission_request_state.get('timestamp') if permission_request_state else None
        })
    except Exception as e:
        logger.error(f"Error checking permission status: {e}")
        return jsonify({'active': False, 'has_face_image': False})

@app.context_processor
def inject_notification_count():
    with thread_lock:
        unread_count = sum(1 for n in notifications_list if not n.get('read', False))
    return {'unread_count': unread_count}

# --- Authentication Routes ---
LI = False

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        secret_key = request.form.get('secret_key')
        if secret_key == MY_HOME_SECRET:
            LI = True
            session['authenticated'] = True
            session.permanent = True
            flash('Successfully logged in!', 'success')
            print("success")
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid secret key. Please try again.', 'error')
            render_template('login.html')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    with thread_lock:
        # Create weather dictionary for template
        weather = {
            "temp": latest_environment_data.get("temp", 25.0),
            "humidity": latest_environment_data.get("humidity", 50),
            "rain_chance": latest_environment_data.get("rain_chance", 0),
            "status": latest_environment_data.get("status", "Loading..."),
            "city": "Coimbatore",
            "is_raining": latest_environment_data.get("is_raining", False),
            "gas_detected": latest_environment_data.get("gas_detected", False),
            "last_updated": time.strftime("%H:%M:%S", time.localtime(
                latest_environment_data.get("last_updated", time.time())
            ))
        }
    aqi_data = aqi_monitor.get_data()
    aqi_data["last_updated"] = time.strftime("%H:%M:%S", time.localtime(aqi_data["last_updated"]))
    return render_template('dashboard.html', active_page='dashboard', weather=weather, camera=camera, security_system=security_system,aqi=aqi_data)

# Import and register blueprints
from conrol_bp import control_bp
from watertank import water_bp
from smartcontrol_bp import smartcontrol_bp
from watermonitor_bp import watermonitor_bp
app.register_blueprint(watermonitor_bp)
# Import analytics blueprint and initialize database
from analytics_bp import analytics_bp, init_analytics_db
#assist area
from assist import assist_bp
app.register_blueprint(assist_bp)

#importing automation
# Add to imports

from automation_bp import automation_bp
# After other blueprint registrations
app.register_blueprint(automation_bp)

# Initialize analytics database
with app.app_context():
    PowerConsumption, PowerSettings = init_analytics_db(db)
    logger.info("Analytics database initialized")
    if not WaterTankSettings.query.first():
        default_settings = WaterTankSettings()
        db.session.add(default_settings)
    if not AccessLog.query.first():
        db.session.add(AccessLog()) 
    db.session.commit()
    automation_manager.start()
    db.create_all()
   

# Register blueprints
app.register_blueprint(water_bp, url_prefix='/water')
app.register_blueprint(control_bp, url_prefix='/')
app.register_blueprint(smartcontrol_bp, url_prefix='/')
app.register_blueprint(analytics_bp, url_prefix='/')

@app.route('/security')
@login_required
def security():
    return render_template('security.html', active_page='security', security_system=security_system)

@app.route('/notifications')
@login_required
def notifications():
    with thread_lock:
        for notification in notifications_list:
            notification['read'] = True
        unread_count = 0 
        
    return render_template('notifications.html', active_page='notifications', notifications=notifications_list, unread_count=unread_count)

@app.route('/face_image')
@login_required
def face_image():
    """Serve the detected face image"""
    if not security_system or not security_system.last_detected_face:
        return jsonify({'error': 'No face image available'}), 404
    
    face_data = security_system.last_detected_face
    
    # Create response with face image data
    response = make_response(face_data)
    response.headers['Content-Type'] = 'image/jpeg'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def add_face_boxes_to_frame(frame):
    """Add face detection boxes to the video frame"""
    # Resize for faster face detection
    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        
    # Find face locations
    face_locations = security_system.face_locations(rgb_small_frame)
        
    if face_locations and security_system:
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
            
        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            # Scale back up face locations
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4
                
            # Determine if this is a known face
            name = "Unknown"
            color = (0, 0, 255)  # Red for unknown
                
            with security_system.data_lock:
                if security_system.known_face_encodings:
                    matches = face_recognition.compare_faces(
                        security_system.known_face_encodings, face_encoding, tolerance=0.6)
                    if True in matches:
                        first_match_index = matches.index(True)
                        name = security_system.known_face_names[first_match_index]
                        color = (0, 255, 0)  # Green for known
                
            # Draw rectangle and label
            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, cv2.FILLED)
            font = cv2.FONT_HERSHEY_DUPLEX
            cv2.putText(frame, name, (left + 6, bottom - 6), font, 0.6, (255, 255, 255), 1)
    
    return frame

# --- Live Video Streaming Route ---
def generate_video_stream(camera_instance):
    """Generate video frames for streaming"""
    while True:
        frame = camera_instance.get_frame()
        if frame is None:
            # Create offline image
            offline_img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(offline_img, "Camera Offline", (180, 240), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            frame = offline_img
            time.sleep(1)
            
        (flag, encodedImage) = cv2.imencode(".jpg", frame)
        if not flag:
            continue
                
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + 
              bytearray(encodedImage) + b'\r\n')

@app.route('/video_feed')
@login_required
def video_feed():
    """Video streaming route"""
    if camera is None:
        # Return static offline image
        offline_img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(offline_img, "Camera Unavailable", (150, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        (flag, encodedImage) = cv2.imencode(".jpg", offline_img)
        return Response(bytearray(encodedImage), mimetype='image/jpeg')
    
    return Response(generate_video_stream(camera), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

# --- API Endpoints for the Frontend ---
@app.route('/api/environment')

def api_environment():
    """Return current environment data"""
    with thread_lock:
        # Create response with all sensor data
        data = {
            "temp": latest_environment_data.get("temp", 25.0),
            "humidity": latest_environment_data.get("humidity", 50),
            "rain_chance": latest_environment_data.get("rain_chance", 0),
            "status": latest_environment_data.get("status", "Loading"),
            "is_raining": latest_environment_data.get("is_raining", False),
            "gas_detected": latest_environment_data.get("gas_detected", False),
            "last_updated": time.strftime("%H:%M:%S", time.localtime(
                latest_environment_data.get("last_updated", time.time())
            ))
        }
        return jsonify(data)

@app.route('/api/notifications')

def api_notifications():
    """Return notifications and permission requests"""
    with thread_lock:
        unread_count = sum(1 for n in notifications_list if not n.get('read', False))
        response = {
            'notifications': list(notifications_list),
            'unread_count': unread_count,
            'permission_request': permission_request_state.copy()
        }
    return jsonify(response)
# route for aqi
@app.route('/api/aqi')
def api_aqi():
    """Return current AQI data"""
    aqi_data = aqi_monitor.get_data()
    return jsonify(aqi_data)

@app.route('/api/access_log')
@login_required
def get_access_log():
    """Get access log entries for a specific date"""
    date_str = request.args.get('date')
    
    if not date_str:
        return jsonify({"error": "Date parameter required"}), 400
    
    try:
        # Convert to date object
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    
    # Query database
    log_entry = AccessLog.query.filter_by(date=target_date).first()
    
    if log_entry:
        return jsonify(log_entry.entries)
    else:
        return jsonify([])
@app.route('/api/security_action', methods=['POST'])

def security_action():
    global detected, permission_request_active
    """Handle security actions (allow/deny access)"""
   
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'No data provided'}), 400
            
    action = data.get('action')
    name = data.get('name')
    
    if action == 'allowonce'  and name:
        detected = False
        permission_request_active = False
        with thread_lock:
            permission_request_state.clear()
        success = security_system.add_new_face_acessed(name, None)
        add_notification(f"fa-user-plus", "highlight", 
                               "New user {name}  was temporarily allowed", "/security")
        
        print("allowing temporarily  and storing the  info")
        unlock_door()
        try:

            today = datetime.utcnow().date()
            log_entry = AccessLog.query.filter_by(date=today).first()
    
            if not log_entry:
                
                log_entry = AccessLog(date=today)
                db.session.add(log_entry)
    
            # Create new access entry
            access_entry = {
        "name": name,
        "time": datetime.utcnow().strftime("%H:%M:%S"),
        "type": "temporary" if action == "allowonce" else "permanent"
              }
    
    # Update entries list
            entries = log_entry.entries
            entries.append(access_entry)
            log_entry.entries = entries
    
            db.session.commit()
            logger.info(f"Access logged for {name} at {access_entry['time']}")
        except Exception as e:
            logger.error(f"Error logging access: {e}")
            db.session.rollback()
        time.sleep(15)
        return jsonify({'status': 'success', 'message': 'New user was temporarily allowed'})
    
    if action == 'allow' and name:
        with thread_lock:
            permission_request_state.clear()
        detected = False
        permission_request_active = False
        
        if not security_system:
            return jsonify({'status': 'error', 'message': 'Security system not available'}), 500
                
        # Add the new face
        success = security_system.add_new_face(name, None)
        unlock_door()
        if success:
            
# Inside the security_action route - add this after unlocking the door
            try:
                today = datetime.utcnow().date()
                log_entry = AccessLog.query.filter_by(date=today).first()
    
                if not log_entry:
                    log_entry = AccessLog(date=today)
                    db.session.add(log_entry)
    
    # Create new access entry
                access_entry = {
        "name": name,
        "time": datetime.utcnow().strftime("%H:%M:%S"),
        "type": "temporary" if action == "allowonce" else "permanent"
                }
    
    # Update entries list
                entries = log_entry.entries
                entries.append(access_entry)
                log_entry.entries = entries
    
                db.session.commit()
                logger.info(f"Access logged for {name} at {access_entry['time']}")
            except Exception as e:
                logger.error(f"Error logging access: {e}")
                db.session.rollback()
            add_notification("fa-user-plus", "highlight", 
                               f"New user '{name}' was registered and granted access.", "/security")
            return jsonify({'status': 'success', 'message': f'User {name} added.'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to add user'}), 500

    elif action == 'deny':
        # Clear the state to dismiss the request
        with thread_lock:
            permission_request_state.clear()
    
        add_notification("fa-user-slash", "info", "Access for unknown person was denied.", "/security")
        detected = False
        permission_request_active = False
        return jsonify({'status': 'denied', 'message': 'Access denied.'})

    return jsonify({'status': 'error', 'message': 'Invalid action'}) 
# Add in app.py after other routes
@app.route('/api/water/thresholds', methods=['GET', 'POST'])
@login_required
def water_thresholds():
    settings = WaterTankSettings.query.first()
    if not settings:
        settings = WaterTankSettings()
        db.session.add(settings)
        db.session.commit()
    
    if request.method == 'POST':
        data = request.get_json()
        settings.lower_threshold = data.get('lower', settings.lower_threshold)
        settings.upper_threshold = data.get('upper', settings.upper_threshold)
        db.session.commit()
        return jsonify({'status': 'success'})
    
    return jsonify({
        'lower': settings.lower_threshold,
        'upper': settings.upper_threshold
    })
# --- Background Data-Gathering Threads ---
def environment_data_thread():
    """Background thread for collecting environment data"""
    logger.info("Starting environment data thread...")
    
    # Initial state for sensors
    global sensor_states
    sensor_states = {
        "rain": None,
        "gas": None,
    }
    
    # Initial notification
    add_notification("fa-server", "info", "Environment monitoring started", "/")
    
    while True:
        try:
            # Read local sensors
            sensor_data = read_sensors()
            local_temp = sensor_data["temp"]
            local_humidity = sensor_data["humidity"]
            is_raining_now = sensor_data["is_raining"]
            gas_detected = sensor_data["gas_detected"]
                
            # Get weather data from API
            weather_data = None
                
            response = requests.get(API_URL, timeout=5)
            response.raise_for_status()
            weather_data = response.json()

            # Process and combine data
            final_temp = local_temp
            final_humidity = local_humidity
            rain_chance = 0
            status = "Initializing"
                
            if weather_data:
                api_temp = weather_data['main']['temp']
                api_humidity = weather_data['main']['humidity']
                print(api_temp, api_humidity)
                    
                # Combine local and API data if both available
                if local_temp is not None:
                    final_temp = (local_temp + api_temp) / 2
                else:
                    final_temp = api_temp
                        
                if local_humidity is not None:
                    final_humidity = (local_humidity + api_humidity) / 2
                else:
                    final_humidity = api_humidity
                    
                # Determine rain status
                description = weather_data['weather'][0]['description'].lower()
                if is_raining_now:
                    rain_chance, status = 100, "Raining Now"
                elif 'rain' in description:
                    rain_chance, status = 80, "Rain Likely"
                else:
                    humidity_chance = int((final_humidity - 60) * 1.5) if final_humidity > 60 else 0
                    cloud_chance = weather_data.get('clouds', {}).get('all', 0) // 4
                    rain_chance = min(max(humidity_chance, cloud_chance), 75)
                    status = weather_data['weather'][0]['description'].title()
            else:
                # Use sensor data only if API fails
                if is_raining_now:
                    rain_chance, status = 100, "Raining (Sensor)"
                else:
                    rain_chance, status = 0, "No Data"
                
            # Update global data
            with thread_lock:
                latest_environment_data.update({
                    "temp": round(final_temp),
                    "humidity": round(final_humidity),
                    "rain_chance": rain_chance,
                    "status": status,
                    "is_raining": is_raining_now,
                    "gas_detected": gas_detected,
                    "last_updated": time.time()
                })
                
            time.sleep(25)  # Update every 25 seconds
            print(final_temp, final_humidity, status)
            
        except Exception as e:
            logger.error(f"Error in environment data thread: {e}")
            time.sleep(30)  # Wait longer on error

# --- Run the Application ---
if __name__ == '__main__':
    
    # Start background threads
    env_thread = Thread(target=environment_data_thread, daemon=True)
    env_thread.start()
    automation_manager.start()
    
    # Start security processing if available
    if camera and security_system:
        security_system.load_known_faces()
        security_system.acessed_person_()
        sec_thread = Thread(target=security_system.process_frames, daemon=True)
        sec_thread.start()
        logger.info("Security thread started")
    else:
        logger.warning("Security thread not started - camera or security system unavailable")
    
    logger.info("--- Starting Secure Smart Home Server ---")
    
    # Check if SSL certificates exist
    ssl_context = None
    if os.path.exists('cert.pem') and os.path.exists('key.pem'):
        ssl_context = ('cert.pem', 'key.pem')
        logger.info("SSL enabled - starting HTTPS server")
    else:
        logger.warning("SSL disabled - starting HTTP server")
    
    app.run(host='0.0.0.0', port=5000, debug=False,ssl_context=  ssl_context ,use_reloader=False)
