# aqi.py
import time
import requests
import logging
from threading import Lock, Thread

logger = logging.getLogger('SmartHome.AQI')

class AQIMonitor:
    def __init__(self, api_key, latitude, longitude):
        self.api_key = api_key
        self.latitude = latitude
        self.longitude = longitude
        self.lock = Lock()
        self.aqi_data = {
            "aqi": 0,
            "category": "N/A",
            "main_pollutant": "N/A",
            "concentration": 0,
            "advisory": "Initializing...",
            "last_updated": 0
        }
        self.categories = {
            1: "Good",
            2: "Fair",
            3: "Moderate",
            4: "Poor",
            5: "Very Poor"
        }
        self.advisories = {
            1: "Excellent air quality. Perfect for outdoor activities!",
            2: "Acceptable air quality. Enjoy your day outdoors.",
            3: "Sensitive groups should reduce outdoor exertion.",
            4: "Everyone should limit outdoor exposure. Wear a mask if going out.",
            5: "Avoid outdoor activities. Use air purifiers indoors."
        }
        self.pollutant_names = {
            "pm2_5": "PM2.5",
            "pm10": "PM10",
            "o3": "Ozone",
            "no2": "NO₂",
            "so2": "SO₂",
            "co": "CO"
        }

    def fetch_aqi_data(self):
        try:
            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={self.latitude}&lon={self.longitude}&appid={self.api_key}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data and data.get('list'):
                aqi_info = data['list'][0]
                aqi_index = aqi_info['main']['aqi']
                components = aqi_info['components']
                
                # Find main pollutant (highest concentration)
                main_pollutant = max(components, key=components.get)
                concentration = components[main_pollutant]
                
                with self.lock:
                    self.aqi_data = {
                        "aqi": aqi_index,
                        "category": self.categories.get(aqi_index, "N/A"),
                        "main_pollutant": self.pollutant_names.get(main_pollutant, main_pollutant),
                        "concentration": round(concentration, 2),
                        "advisory": self.advisories.get(aqi_index, "N/A"),
                        "last_updated": time.time()
                    }
                return True
        except Exception as e:
            logger.error(f"AQI API error: {e}")
        return False

    def start_monitoring(self):
        def monitor_thread():
            logger.info("Starting AQI monitoring thread")
            while True:
                self.fetch_aqi_data()
                time.sleep(300)  # Update every 5 minutes
                
        Thread(target=monitor_thread, daemon=True).start()

    def get_data(self):
        with self.lock:
            return self.aqi_data.copy()
