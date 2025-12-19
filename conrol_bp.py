from flask import Blueprint, render_template, session, redirect, url_for, jsonify
import requests
from functools import wraps
import logging

control_bp = Blueprint('control', __name__, template_folder='templates')

# ESP8266 Configuration - UPDATE THESE VALUES
ESP_IP = "192.168.8.170"  # Replace with your ESP's local IP
device_states = {
    'socket1': 'off',
    'socket2': 'off',
    'water_pump': 'off'
}

# Hardware Configuration - Update if using different GPIO pins
SOCKET1_PIN = 5   # D1 - Controls first socket
SOCKET2_PIN = 4   # D2 - Controls second socket
PUMP_PIN = 14     # D5 - Controls water pump

# Device monitoring state
device_monitoring = {
    'socket1': {'active': False, 'session_id': None},
    'socket2': {'active': False, 'session_id': None},
    'water_pump': {'active': False, 'session_id': None}
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def start_power_monitoring(device_name, device_id):
    """Start power monitoring for a device"""
    try:
        from analytics_bp import start_device_monitoring
        session_id = start_device_monitoring(device_name, device_id)
        device_monitoring[device_name] = {'active': True, 'session_id': session_id}
        logging.info(f"Started power monitoring for {device_name} (ID: {device_id})")
        return session_id
    except Exception as e:
        logging.error(f"Failed to start power monitoring for {device_name}: {e}")
        return None

def stop_power_monitoring(device_name, device_id):
    """Stop power monitoring for a device"""
    try:
        from analytics_bp import stop_device_monitoring
        units_consumed = stop_device_monitoring(device_name, device_id)
        device_monitoring[device_name] = {'active': False, 'session_id': None}
        logging.info(f"Stopped power monitoring for {device_name}. Consumed: {units_consumed} kWh")
        return units_consumed
    except Exception as e:
        logging.error(f"Failed to stop power monitoring for {device_name}: {e}")
        return 0.0

@control_bp.route('/control')
@login_required
def index():
    return render_template('controls_hub.html', active_page='control')

@control_bp.route('/control/power')
@login_required
def power_control():
    return render_template('power_controls.html')

@control_bp.route('/control/motor')
@login_required
def motor_control():
    return render_template('water_controls.html')

@control_bp.route('/api/control/state')

def get_device_states():
    return jsonify(device_states)
@control_bp.route('/control/socket/<int:socket_id>/<state>')

def control_socket(socket_id, state):
    """Control power socket with analytics integration"""
    # Map socket ID to GPIO pin and device name
    pin_map = {
        1: SOCKET1_PIN,
        2: SOCKET2_PIN
    }
    
    device_map = {
        1: 'socket1',
        2: 'socket2'
    }
    
    if socket_id not in pin_map:
        return jsonify({'status': 'error', 'message': 'Invalid socket ID'}), 400
        
    device_name = device_map[socket_id]
    value = 1 if state == 'on' else 0
    device_name = f'socket{socket_id}'
    device_states[device_name] = state
    try:
        # Send command to ESP
        response = requests.get(
            f"http://{ESP_IP}/control",
            params={'pin': pin_map[socket_id], 'state': value},
            timeout=3
        )
        
        if response.status_code == 200:
            # Handle power monitoring
            if state == 'on':
                if not device_monitoring[device_name]['active']:
                    start_power_monitoring(device_name, socket_id)
            else:
                if device_monitoring[device_name]['active']:
                    units_consumed = stop_power_monitoring(device_name, socket_id)
                    
            return jsonify({
                'status': 'success',
                'message': f'Socket {socket_id} turned {state.upper()}',
                'device': device_name,
                'state': state,
                'monitoring': device_monitoring[device_name]['active']
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': f'ESP communication failed: {response.status_code}'
            }), 500
            
    except requests.exceptions.RequestException as e:
        logging.error(f"ESP communication error: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to communicate with ESP device'
        }), 500

@control_bp.route('/control/pump/<state>')
def control_pump(state):
    """Control water pump with analytics integration"""
    device_name = 'water_pump'
    device_id = 3
    value = 1 if state == 'on' else 0
    device_states['water_pump'] = state
    try:
        # Send command to ESP
        response = requests.get(
            f"http://{ESP_IP}/control",
            params={'pin': PUMP_PIN, 'state': value},
            timeout=3
        )
        
        if response.status_code == 200:
            # Handle power monitoring
            if state == 'on':
                if not device_monitoring[device_name]['active']:
                    start_power_monitoring(device_name, device_id)
            else:
                if device_monitoring[device_name]['active']:
                    units_consumed = stop_power_monitoring(device_name, device_id)
                    
            return jsonify({
                'status': 'success',
                'message': f'Water pump turned {state.upper()}',
                'device': device_name,
                'state': state,
                'monitoring': device_monitoring[device_name]['active']
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': f'ESP communication failed: {response.status_code}'
            }), 500
            
    except requests.exceptions.RequestException as e:
        logging.error(f"ESP communication error: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to communicate with ESP device'
        }), 500

@control_bp.route('/api/control/status')
def get_control_status():
    """Get current status of all controlled devices"""
    try:
        status = {
            'socket1': {
                'monitoring': device_monitoring['socket1']['active'],
                'session_id': device_monitoring['socket1']['session_id']
            },
            'socket2': {
                'monitoring': device_monitoring['socket2']['active'],
                'session_id': device_monitoring['socket2']['session_id']
            },
            'water_pump': {
                'monitoring': device_monitoring['water_pump']['active'],
                'session_id': device_monitoring['water_pump']['session_id']
            }
        }
        
        return jsonify({
            'status': 'success',
            'devices': status
        }), 200
        
    except Exception as e:
        logging.error(f"Error getting control status: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to get device status'
        }), 500

@control_bp.route('/control/emergency_stop')
@login_required
def emergency_stop():
    """Emergency stop all devices and power monitoring"""
    try:
        results = []
        
        # Stop all sockets
        for socket_id in [1, 2]:
            device_name = f'socket{socket_id}'
            pin = SOCKET1_PIN if socket_id == 1 else SOCKET2_PIN
            
            try:
                # Turn off device
                response = requests.get(
                    f"http://{ESP_IP}/control",
                    params={'pin': pin, 'state': 0},
                    timeout=2
                )
                
                # Stop monitoring
                if device_monitoring[device_name]['active']:
                    stop_power_monitoring(device_name, socket_id)
                
                results.append(f'Socket {socket_id}: OFF')
                
            except Exception as e:
                results.append(f'Socket {socket_id}: ERROR - {str(e)}')
        
        # Stop water pump
        try:
            response = requests.get(
                f"http://{ESP_IP}/control",
                params={'pin': PUMP_PIN, 'state': 0},
                timeout=2
            )
            
            if device_monitoring['water_pump']['active']:
                stop_power_monitoring('water_pump', 3)
            
            results.append('Water Pump: OFF')
            
        except Exception as e:
            results.append(f'Water Pump: ERROR - {str(e)}')
        
        return jsonify({
            'status': 'success',
            'message': 'Emergency stop executed',
            'results': results
        }), 200
        
    except Exception as e:
        logging.error(f"Emergency stop error: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Emergency stop failed'
        }), 500
