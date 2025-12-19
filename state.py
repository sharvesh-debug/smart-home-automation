# state.py
import time
from aqi import AQIMonitor

# Weather API Configuration
API_KEY = "52f6959fe33354369e79f4a40ee8995b"
LATITUDE = "11.0168"
LONGITUDE = "76.9558"

latest_environment_data = {
    "temp": 0,
    "humidity": 0,
    "rain_chance": 0,
    "status": "Initializing",
    "is_raining": False,
    "gas_detected": False,
    "last_updated": time.time()
}

aqi_monitor = AQIMonitor(API_KEY, LATITUDE, LONGITUDE)
aqi_monitor.start_monitoring()
