# EMS Dashboard Konfiguration
# Bitte anpassen!

# Geräte
INVERTER_PORT   = '/dev/hidraw0'
SDM630_PORT     = '/dev/ttyUSB0'
SDM630_BAUDRATE = 19200
SDM630_ADDRESS  = 1
PYLONTECH_PORT  = '/dev/ttyUSB1'

# MQTT (HomeAssistant Mosquitto)
MQTT_HOST     = '192.168.1.11'   # <-- HomeAssistant IP anpassen!
MQTT_PORT     = 1883
MQTT_USER     = 'mqtt'
MQTT_PASSWORD = 'mqtt'   # <-- Anpassen!
MQTT_PREFIX   = 'ems'

# Wettervorhersage (Open-Meteo, kein API Key nötig)
LATITUDE  = 49.0
LONGITUDE = 11.82
LOCATION  = 'Painten'

# Automatik-Schwellen
SOC_LOW       = 20    # % - unter diesem SOC immer AC-Laden erlauben
SOC_HIGH      = 90    # % - über diesem SOC kein AC-Laden nötig
SUN_HOURS_MIN = 3     # h - ab dieser Sonnenstundenzahl: kein AC-Laden
SUN_HOURS_MAX = 6     # h - ab dieser Sonnenstundenzahl: Solar reicht sicher

# Datenbank
DB_PATH = '/home/eduard/ems/data/ems.db'

# Web-Server
HOST = '0.0.0.0'
PORT = 5000
DEBUG = False
