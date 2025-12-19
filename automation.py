# automation.py
import time
import threading
from datetime import datetime, time as dt_time
from flask import current_app,Flask
import RPi.GPIO as GPIO
import requests
from main import app
from state import latest_environment_data, aqi_monitor
from conrol_bp import device_states
from flask_sqlalchemy import SQLAlchemy
from models import  Automation
db = SQLAlchemy()

class AutomationManager:
    def __init__(self):
        self.running = False
        self.thread = None
        self.actions_map = {
            'unlock_door': self.unlock_door,
            'turn_on_socket1': lambda: self.control_device('socket1', 'on'),
            'turn_off_socket1': lambda: self.control_device('socket1', 'off'),
            'turn_on_socket2': lambda: self.control_device('socket2', 'on'),
            'turn_off_socket2': lambda: self.control_device('socket2', 'off'),
            'turn_on_pump': lambda: self.control_device('water_pump', 'on'),
            'turn_off_pump': lambda: self.control_device('water_pump', 'off'),
        }
        self.variables_map = {
            'temperature': self.get_temperature,
            'humidity': self.get_humidity,
            'rain_chance': self.get_rain_chance,
            'aqi': self.get_aqi,
            'water_level': self.get_water_level,
            'is_raining': self.get_is_raining,
            'gas_detected': self.get_gas_detected
        }

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
            current_app.logger.info("Automation manager started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        current_app.logger.info("Automation manager stopped")

    def run(self):
        while self.running:
            with app.app_context():
                try:
                    automations = Automation.query.filter_by(enabled=True).all()
                    now = datetime.now()

                    for automation in automations:
                        if automation.automation_type == 'value':
                            self.check_value_automation(automation)
                        elif automation.automation_type == 'time':
                            self.check_time_automation(automation, now)

                    time.sleep(10)  # Check every 10 seconds
                except Exception as e:
                    current_app.logger.error(f"Automation error: {str(e)}")
                    time.sleep(30)

    def check_value_automation(self, automation):
        value_getter = self.variables_map.get(automation.variable)
        if not value_getter:
            return

        current_value = value_getter()
        if current_value is None:
            return

        if automation.min_value <= current_value <= automation.max_value:
            self.trigger_action(automation.action)

    def check_time_automation(self, automation, now):
        if automation.trigger_time and now.time() >= automation.trigger_time:
            # Check if we haven't triggered today
            last_triggered = getattr(automation, 'last_triggered', None)
            if last_triggered is None or last_triggered.date() < now.date():
                self.trigger_action(automation.action)
                automation.last_triggered = now
                db.session.commit()

    def trigger_action(self, action_name):
        action_func = self.actions_map.get(action_name)
        if action_func:
            try:
                action_func()
                current_app.logger.info(f"Triggered action: {action_name}")
            except Exception as e:
                current_app.logger.error(f"Action failed: {action_name} - {str(e)}")

    def get_temperature(self):
        return latest_environment_data.get('temp')

    def get_humidity(self):
        return latest_environment_data.get('humidity')

    def get_rain_chance(self):
        return latest_environment_data.get('rain_chance')

    def get_aqi(self):
        return aqi_monitor.get_data().get('aqi')

    def get_water_level(self):
        # This would need to be implemented based on your water tank system
        return 75  # Placeholder - implement based on your system

    def get_is_raining(self):
        return 1 if latest_environment_data.get('is_raining') else 0

    def get_gas_detected(self):
        return 1 if latest_environment_data.get('gas_detected') else 0

    def unlock_door(self):
        current_app.logger.info("Automation: Unlocking door")
        IS_PI = True
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

    def control_device(self, device, state):
        # Implement your device control logic
        current_app.logger.info(f"Automation: Turning {state} {device}")

        device_states[device] = state
        # Add actual control logic here
        if device == "water_pump":
            requests.get(f"https://127.0.0.1:5000/control/pump/{state}", headers=headers, timeout=3, verify=False)
            response = f"Turning {state} the water pump"
        elif device == "socket1":
            requests.get(f"https://127.0.0.1:5000/control/socket/1/{state}", headers=headers, timeout=3, verify=False)
            response = f"Turning {state} socket one"
        elif device == "socket2":
            requests.get(f"https://127.0.0.1:5000/control/socket/2/{state}", headers=headers, timeout=3, verify=False)
            response = f"Turning {state} socket two"
        print(response)

# Initialize the automation manager
automation_manager = AutomationManager()

