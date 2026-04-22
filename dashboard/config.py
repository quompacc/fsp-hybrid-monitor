"""
Konfiguration für Hybrid Energy Monitor.
Sensible Werte bitte über lokale Anpassung oder ENV-Variablen setzen.
"""
import os

_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Geräte
INVERTER_PORT   = os.getenv('INVERTER_PORT', '/dev/hidraw0')
SDM630_PORT     = os.getenv('SDM630_PORT', '/dev/ttyUSB0')
SDM630_BAUDRATE = int(os.getenv('SDM630_BAUDRATE', '19200'))
SDM630_ADDRESS  = int(os.getenv('SDM630_ADDRESS', '1'))
PYLONTECH_PORT  = os.getenv('PYLONTECH_PORT', '/dev/ttyUSB1')

# MQTT (HomeAssistant Mosquitto)
MQTT_HOST     = os.getenv('MQTT_HOST', '127.0.0.1')
MQTT_PORT     = int(os.getenv('MQTT_PORT', '1883'))
MQTT_USER     = os.getenv('MQTT_USER', '')
MQTT_PASSWORD = os.getenv('MQTT_PASSWORD', '')
MQTT_PREFIX   = os.getenv('MQTT_PREFIX', 'ems')

# Wettervorhersage (Open-Meteo, kein API Key nötig)
LATITUDE  = float(os.getenv('LATITUDE', '48.137154'))
LONGITUDE = float(os.getenv('LONGITUDE', '11.576124'))
LOCATION  = os.getenv('LOCATION', 'Site')

# Automatik-Schwellen
SOC_LOW       = 20    # % - unter diesem SOC immer AC-Laden erlauben
SOC_HIGH      = 90    # % - über diesem SOC kein AC-Laden nötig
SUN_HOURS_MIN = 3     # h - ab dieser Sonnenstundenzahl: kein AC-Laden
SUN_HOURS_MAX = 6     # h - ab dieser Sonnenstundenzahl: Solar reicht sicher

# Datenbank
DB_PATH = os.getenv('DB_PATH', os.path.join(_BASE_DIR, 'data', 'ems.db'))

# Web-Server
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '5000'))
DEBUG = os.getenv('DEBUG', 'false').lower() in ('1', 'true', 'yes', 'on')
