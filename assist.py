import threading
import json
import requests
import re
import time
import logging
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from datetime import datetime, timedelta
from flask import Blueprint, render_template, session, request, jsonify, redirect, url_for
from functools import wraps
import RPi.GPIO as GPIO
assist_bp = Blueprint('assist', __name__, template_folder='templates')
# unlock door function 
RELAY_PIN = 21
IS_PI=True
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
# Setup logging
logger = logging.getLogger('AssistMode')
logger.setLevel(logging.INFO)

# Enhanced training data for intent classification
TRAINING_DATA = [
    ("what's the temperature", "temperature"),
    (" temperature", "temperature"),
    ("temperature", "temperature"),
    ("how hot is it outside", "temperature"),
    ("current humidity level", "humidity"),
    ("is it humid", "humidity"),
    ("water tank level", "water_level"),
    ("how much water is left", "water_level"),
    ("turn on socket one", "control_device"),
    ("activate the first socket", "control_device"),
    ("switch off pump", "control_device"),
    ("deactivate water pump", "control_device"),
    ("unlock the front door", "door_unlock"),
    ("open the main entrance", "door_unlock"),
    ("power usage today", "power_usage"),
    ("electricity consumption", "power_usage"),
    ("is there gas detected", "gas_status"),
    ("gas sensor reading", "gas_status"),
    ("is it raining", "rain_status"),
    ("will it rain today", "rain_status"),
    ("socket one status", "device_status"),
    ("is pump running", "device_status"),
    ("who entered yesterday", "access_log"),
    ("visitors today", "access_log"),
    ("show notifications", "notifications"),
    ("recent alerts", "notifications"),
    ("emergency stop all", "emergency_stop"),
    ("what's the current temp", "temperature"),
    ("humidity reading", "humidity"),
    ("water percentage", "water_level"),
    ("activate socket two", "control_device"),
    ("turn off first socket", "control_device"),
    ("open the door", "door_unlock"),
    ("power consumption", "power_usage"),
    ("electricity bill", "power_usage"),
    ("gas detection", "gas_status"),
    ("rain forecast", "rain_status"),
    ("is socket two on", "device_status"),
    ("pump status", "device_status"),
    ("yesterday's visitors", "access_log"),
    ("today's access log", "access_log"),
    ("show recent alerts", "notifications"),
    ("stop all devices", "emergency_stop"),
    ("what's the air quality", "aqi"),
    ("current aqi", "aqi"),
    ("air quality index", "aqi"),
    ("how is the air pollution", "aqi"),
    ("pollution level", "aqi"),
    ("water flow today", "water_flow"),
    ("pipeline usage", "water_flow"),
    ("how much water used", "water_flow"),
    ("water consumption", "water_flow"),
    ("pipeline 1 usage", "water_flow"),
    ("pipeline 2 flow", "water_flow"),
    ("hi","unknown")
]

# Create classifier pipeline
texts, labels = zip(*TRAINING_DATA)
classifier = make_pipeline(
    TfidfVectorizer(ngram_range=(1, 2), max_features=1000),
    LogisticRegression(max_iter=1000, C=1.5)
)
classifier.fit(texts, labels)

# Device mappings
DEVICE_MAPPING = {
    "socket1": ["socket one", "first socket", "socket 1","first switch"],
    "socket2": ["socket two", "second socket", "socket 2"],
    "water_pump": ["pump", "water pump", "motor"],
    "door": ["door", "entrance"]
}

# Conversation history
conversation_history = []


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def parse_time(text):
    """Extract time references from text using regex"""
    text = text.lower()

    if "yesterday" in text:
        return "yesterday"
    elif "tomorrow" in text:
        return "tomorrow"
    elif "today" in text:
        return "today"

    date_pattern = r'(\d{4}-\d{2}-\d{2})|(\d{1,2}/\d{1,2}/\d{4})'
    match = re.search(date_pattern, text)
    if match:
        return match.group(0)

    return "today"


def get_device_entity(text):
    """Extract device entity using keyword matching"""
    text = text.lower()
    for device, aliases in DEVICE_MAPPING.items():
        if any(alias in text for alias in aliases):
            return device
    return None


def get_access_log(time_ref):
    token = "your_secret_token_here"
    headers = {'X-Internal-Token': token}

    today = datetime.now().date()
    if time_ref == "today":
        date_str = today.strftime("%Y-%m-%d")
    elif time_ref == "yesterday":
        date_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            if '-' in time_ref:
                parsed_date = datetime.strptime(time_ref, "%Y-%m-%d").date()
            else:
                parsed_date = datetime.strptime(time_ref, "%m/%d/%Y").date()
            date_str = parsed_date.strftime("%Y-%m-%d")
        except:
            date_str = today.strftime("%Y-%m-%d")

    try:
        response = requests.get(
            f"https://127.0.0.1:5000/api/access_log?date={date_str}",
            headers=headers,
            timeout=3,verify=False
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        logger.error(f"Access log request failed: {e}")
        return []


def process_intent(text):
	
	
    if not text.strip():
        return "unknown", None, None
    print(f"user:{text}")
    try:
        intent = classifier.predict([text])[0]
        logger.info(f"Detected intent: {intent}")
    except Exception as e:
        logger.error(f"Intent classification error: {e}")
        intent = "unknown"

    entity = get_device_entity(text)
    if entity:
        logger.info(f"Detected entity: {entity}")

    if intent in ["access_log", "power_usage"]:
        time_ref = parse_time(text)
        logger.info(f"Time reference: {time_ref}")
        return intent, entity, time_ref

    return intent, entity, None


def execute_action(intent, entity, time_ref=None, text=""):
    response = ""
    action_performed = False

    token = "your_secret_token_here"
    headers = {'X-Internal-Token': token}

    if intent == "temperature":
        res = requests.get("https://127.0.0.1:5000/api/environment", headers=headers, timeout=10,verify=False)
        data = res.json()
        response = f"Current temperature is {data['temp']}°C"

    elif intent == "humidity":
        res = requests.get("https://127.0.0.1:5000/api/environment", headers=headers, timeout=10,verify=False)
        data = res.json()
        response = f"Humidity is at {data['humidity']}%"

    elif intent == "water_level":
        res = requests.get("https://127.0.0.1:5000/water/update_level", headers=headers, timeout=10,verify=False)
        data = res.json()
        response = f"Water tank is at {data['level']}% capacity"

    elif intent == "control_device":
        action = "on" if any(word in text.lower() for word in ["on", "activate", "enable"]) else "off"

        if entity == "water_pump":
            requests.get(f"https://127.0.0.1:5000/control/pump/{action}", headers=headers, timeout=10,verify=False)
            response = f"Turning {action} the water pump"
        elif entity == "socket1":
            requests.get(f"https://127.0.0.1:5000/control/socket/1/{action}", headers=headers, timeout=10,verify=False)
            response = f"Turning {action} socket one"
        elif entity == "socket2":
            requests.get(f"https://127.0.0.1:5000/control/socket/2/{action}", headers=headers, timeout=10,verify=False)
            response = f"Turning {action} socket two"
        else:
            response = "Please specify which device to control"

        action_performed = True

    elif intent == "door_unlock":
        unlock_door()
        response = "Unlocking the front door "
        action_performed = True

    elif intent == "power_usage":
        if not time_ref:
            time_ref = "today"

        res = requests.get("https://127.0.0.1:5000/api/analytics/daily_consumption", headers=headers, timeout=3,verify=False)
        data = res.json()

        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d") if time_ref == "yesterday" else datetime.now().strftime("%Y-%m-%d")

        daily_usage = next((item for item in data['data'] if item['date'] == target_date), None)

        if daily_usage:
            response = f"Power consumption on {time_ref} was {daily_usage['units']} kWh"
        else:
            response = f"No power usage data available for {time_ref}"

    elif intent == "gas_status":
        res = requests.get("https://127.0.0.1:5000/api/environment", headers=headers, timeout=3,verify=False)
        data = res.json()
        status = "detected" if data['gas_detected'] else "not detected"
        response = f"Gas is {status}"

    elif intent == "rain_status":
        res = requests.get("https://127.0.0.1:5000/api/environment", headers=headers, timeout=3,verify=False)
        data = res.json()
        status = "raining" if data['is_raining'] else "not raining"
        chance = data['rain_chance']
        response = f"It is currently {status} with a {chance}% chance of rain today"

    elif intent == "device_status":
        res = requests.get("https://127.0.0.1:5000/api/control/state", headers=headers, timeout=3,verify=False)
        states = res.json()

        if entity == "water_pump":
            status = "running" if states.get('water_pump', 'off') == "on" else "off"
            response = f"Water pump is {status}"
        elif entity == "socket1":
            status = "on" if states.get('socket1', 'off') == "on" else "off"
            response = f"Socket one is {status}"
        elif entity == "socket2":
            status = "on" if states.get('socket2', 'off') == "on" else "off"
            response = f"Socket two is {status}"
        else:
            response = "Please specify which device to check"

    elif intent == "access_log":
        entries = get_access_log(time_ref)

        if not entries:
            response = f"No access entries found for {time_ref}"
        else:
            names = ", ".join(set([entry.get('name', 'Unknown') for entry in entries]))
            response = f"On {time_ref}, the following people entered: {names}"

    elif intent == "notifications":
        res = requests.get("https://127.0.0.1:5000/api/notifications", headers=headers, timeout=3,verify=False)
        data = res.json()

        if not data.get('notifications', []):
            response = "No recent notifications"
        else:
            recent = data['notifications'][:3]
            messages = ". ".join([n.get('text', 'Notification') for n in recent])
            response = f"Recent notifications: {messages}"

    elif intent == "aqi":
        res = requests.get("https://127.0.0.1:5000/api/aqi", 
                          headers=headers, 
                          timeout=10,
                          verify=False)
        if res.status_code == 200:
            data = res.json()
            response = (f"Current AQI is {data['aqi']} ({data['category']}). "
                       f"Main pollutant: {data['main_pollutant']} at {data['concentration']}μg/m³. "
                       f"Advisory: {data['advisory']}")
        else:
            response = "Unable to get air quality data"
    
    elif intent == "water_flow":
        res = requests.get("https://127.0.0.1:5000/watermonitor/api/today",
                          headers=headers,
                          timeout=3,
                          verify=False)
        if res.status_code == 200:
            data = res.json()
            total = data['pipeline1'] + data['pipeline2']
            response = (f"Today's water usage: Pipeline 1: {data['pipeline1']}L, "
                       f"Pipeline 2: {data['pipeline2']}L. Total: {total}L")
        else:
            response = "Unable to get water flow data"
    else:
        response = "I didn't understand that command. Try something like: 'What's the temperature?' or 'Turn on socket one'"

    return response, action_performed


@assist_bp.route('/assistmode')
@login_required
def assist_mode():
    return render_template('assist.html',
                           active_page='assist',
                           history=conversation_history)


@assist_bp.route('/assist/process', methods=['POST'])
@login_required
def process_command():
    global conversation_history

    data = request.json or {}
    text = data.get('text', '').strip()
   
    if not text:
        response = "Please provide a command."
        conversation_history.append({"assistant": response, "type": "response"})
        return jsonify({"status": "error", "text": response})

    # Store user input
    conversation_history.append({"user": text, "type": "input"})
    print(text)
    intent, entity, time_ref = process_intent(text)
    response, action_performed = execute_action(intent, entity, time_ref, text)

    conversation_history.append({
        "assistant": response,
        "type": "response",
        "action_performed": action_performed
    })

    return jsonify({
        "status": "success",
        "text": response,
        "intent": intent,
        "entity": entity,
        "time_ref": time_ref if time_ref else "",
        "should_speak": True
    })


@assist_bp.route('/assist/history', methods=['GET'])
@login_required
def get_history():
    return jsonify({"history": conversation_history})


@assist_bp.route('/assist/clear', methods=['POST'])
@login_required
def clear_history():
    global conversation_history
    conversation_history = []
    return jsonify({"status": "success"})


logger.info("Browser-based Assist Mode initialized successfully")

