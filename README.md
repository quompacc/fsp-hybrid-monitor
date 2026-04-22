# ⚡ Hybrid Energy Monitor

Ein schlankes **Energie-Management-System** für Photovoltaik-Anlagen mit Hybridwechselrichter, Batteriespeicher und Netzeinspeisung. Das System liest Echtzeitdaten von Wechselrichter, Stromzähler und Batterie aus, visualisiert sie in einem Web-Dashboard und sendet sie an HomeAssistant via MQTT.

> Hinweis: Beispiel-/Produktivdaten und Screenshots sind in der Public-Version bewusst entfernt.

---

## ✨ Features

- **Echtzeit-Dashboard** – Energiefluss, Wechselrichter, Phasendaten, Batterie-Modulstatus
- **HomeAssistant Integration** – MQTT Auto-Discovery, ~20 Sensoren sofort verfügbar
- **Wettervorhersage** – Open-Meteo API, 3-Tage Solar-Vorschau
- **Plausibilitätsprüfung** – Unplausible Messwerte werden verworfen, letzter gültiger Wert bleibt erhalten (wichtig bei RS485 Bus-Kollisionen)
- **Read-Only** – keine automatische WR-Steuerung, nur sichere Datenerfassung
- **Systemd Service** – automatischer Start und Neustart bei Absturz
- **Healthcheck Timer** – prüft alle 5 Minuten ob Dashboard erreichbar ist
- **Hardware Watchdog** – Pi startet sich bei Totalabsturz automatisch neu

---

## 🔌 Kompatible Hardware

### Wechselrichter
Das System nutzt [mpp-solar](https://github.com/jblance/mpp-solar) zur WR-Kommunikation. Damit sind alle WR mit **PI17INFINI-Protokoll** kompatibel, u.a.:

| Hersteller | Modell |
|------------|--------|
| FSP | Endurace PRO Hybrid 10–15kW |
| Voltronic / Axpert | King, Max, VM III |
| Luxpower | SNA Serie |
| Must Solar | PH1800 Serie |
| Growatt | SPF Serie |
| PIP-Serie | PIP-4048, PIP-5048 |

> Weitere kompatible Geräte: siehe [mpp-solar Protokoll-Liste](https://github.com/jblance/mpp-solar/tree/master/mppsolar/protocols)

### Stromzähler
- **Eastron SDM630** – 3-Phasen Modbus RTU RS485 (empfohlen)
- Andere SDM-Modelle möglich (SDM120, SDM230) mit Anpassung der Register

### Batteriesystem
- **Pylontech US2000C / US3000C** – RS232 Console
- Weitere Pylontech-Modelle mit identischem Console-Protokoll

### Logger
- **Raspberry Pi** 3B+ / 4 / 5 (empfohlen: Pi 4 oder 5)

---

## 🏗️ Architektur

```
Geräte                    Leser                  Verarbeitung        Ausgabe

/dev/hidraw0  ──►  read_inverter.py  ──┐
                                       ├──►  scheduler.py  ──►  app.py  ──►  Browser
/dev/ttyUSB1  ──►  read_sdm630.py   ──┤         │
                                       │         ├──►  mqtt_client.py  ──►  HomeAssistant
/dev/ttyUSB0  ──►  read_pylontech.py──┘         │
                                                 └──►  db.py (SQLite)
```

**Polling-Intervalle:**
- Wechselrichter: alle 15 Sekunden
- SDM630: alle 30 Sekunden (Bus-Kollision mit WR beachten)
- Pylontech: alle 60 Sekunden
- Wetterdaten: alle 30 Minuten

---

## 📁 Projektstruktur

```
ems/
├── dashboard/
│   ├── app.py              # Flask Web-App (Read-Only API)
│   ├── config.py           # Konfiguration (Ports, MQTT, Koordinaten)
│   ├── scheduler.py        # APScheduler – Datenerfassung
│   ├── mqtt_client.py      # MQTT Publisher + HA Auto-Discovery
│   ├── db.py               # SQLite Datenbankzugriff
│   ├── weather.py          # Open-Meteo Wettervorhersage
│   └── templates/
│       └── index.html      # Dashboard Frontend (vanilla JS)
├── inverter/
│   └── read_inverter.py    # WR Kommunikation via mpp-solar
├── sdm630/
│   └── read_sdm630.py      # Modbus RS485 + Plausibilitätsprüfung
├── pylontech/
│   └── read_pylontech.py   # Pylontech Console Parser
├── ems-healthcheck.sh      # Healthcheck Script
├── ems-healthcheck.service # Systemd Service für Healthcheck
└── ems-healthcheck.timer   # Systemd Timer (alle 5 Minuten)
```

---

## 🚀 Installation

### Voraussetzungen

```bash
sudo apt update
sudo apt install python3-pip python3-venv git curl
```

### Repository klonen

```bash
git clone https://github.com/dein-user/pv-ems.git
cd pv-ems

python3 -m venv venv
source venv/bin/activate
pip install flask apscheduler paho-mqtt pyserial requests mpp-solar
```

### Konfiguration

```bash
nano dashboard/config.py
```

```python
# MQTT / HomeAssistant
MQTT_HOST     = '127.0.0.1'     # oder IP deines MQTT-Brokers
MQTT_PORT     = 1883
MQTT_USER     = '<mqtt-user>'
MQTT_PASSWORD = '<mqtt-password>'
MQTT_PREFIX   = 'ems'

# Standort für Wettervorhersage
WEATHER_LAT   = 48.123          # Breitengrad
WEATHER_LON   = 12.456          # Längengrad

# Flask
HOST  = '0.0.0.0'
PORT  = 5000
DEBUG = False
```

### Geräte-Ports prüfen

```bash
ls -la /dev/ttyUSB* /dev/hidraw*

# Welches USB-Gerät ist was?
udevadm info /dev/ttyUSB0 | grep -E "ID_MODEL|ID_SERIAL"
udevadm info /dev/ttyUSB1 | grep -E "ID_MODEL|ID_SERIAL"
```

Ports in den jeweiligen Leser-Skripten anpassen:
- `inverter/read_inverter.py` → `/dev/hidraw0`
- `sdm630/read_sdm630.py` → z.B. `/dev/ttyUSB1`
- `pylontech/read_pylontech.py` → z.B. `/dev/ttyUSB0`

### Testen

```bash
# Jedes Gerät einzeln testen
python3 inverter/read_inverter.py
python3 sdm630/read_sdm630.py
python3 pylontech/read_pylontech.py

# Dashboard starten
python3 dashboard/app.py
# Aufruf: http://raspberry-pi-ip:5000
```

---

## ⚙️ Systemd Service

```bash
sudo nano /etc/systemd/system/ems-dashboard.service
```

```ini
[Unit]
Description=EMS Dashboard
After=network-online.target
Wants=network-online.target

[Service]
User=pi
Group=pi
WorkingDirectory=/home/pi/ems
Environment="PATH=/home/pi/ems/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/pi/ems/venv/bin/python dashboard/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable ems-dashboard
sudo systemctl start ems-dashboard
```

### Healthcheck Timer

```bash
sudo cp ems-healthcheck.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/ems-healthcheck.sh
sudo cp ems-healthcheck.service /etc/systemd/system/
sudo cp ems-healthcheck.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ems-healthcheck.timer
sudo systemctl start ems-healthcheck.timer
```

### Hardware Watchdog (empfohlen)

```bash
echo 'dtparam=watchdog=on' | sudo tee -a /boot/firmware/config.txt
sudo apt install watchdog -y
```

`/etc/watchdog.conf`:
```
watchdog-device = /dev/watchdog
watchdog-timeout = 15
max-load-1 = 24
```

```bash
sudo systemctl enable watchdog
sudo systemctl start watchdog
```

---

## 📡 MQTT Sensoren in HomeAssistant

Nach dem Start einmal **"HA Discovery senden"** im Dashboard klicken – alle Sensoren erscheinen automatisch in HomeAssistant.

| Sensor | Topic | Einheit |
|--------|-------|---------|
| Akku SOC | `ems/pylontech/avg_soc` | % |
| Akku Spannung | `ems/pylontech/avg_voltage` | V |
| Akku Strom | `ems/pylontech/total_current` | A |
| Akku Module | `ems/pylontech/module_count` | – |
| Netzbezug | `ems/sdm630/bezug` | W |
| Einspeisung | `ems/sdm630/einspeisung` | W |
| Bezug Gesamt | `ems/sdm630/import_energy` | kWh |
| Einspeisung Gesamt | `ems/sdm630/export_energy` | kWh |
| Netzleistung | `ems/sdm630/total_power` | W |
| Solar Leistung | `ems/inverter/solar_power` | W |
| PV Gesamtertrag | `ems/inverter/pv_total_energy` | kWh |
| WR Akkuspannung | `ems/inverter/battery_voltage` | V |
| WR Akku SOC | `ems/inverter/battery_capacity` | % |
| WR Temperatur | `ems/inverter/temp_inner` | °C |
| WR Modus | `ems/inverter/mode` | – |

---

## ⚠️ Wichtige Hinweise

> **Das Dashboard ist bewusst Read-Only.** Es werden keine WR-Einstellungen automatisch verändert. Manuelle Konfiguration des Wechselrichters nur direkt am Gerät oder über mpp-solar CLI.

> **RS485 Bus-Kollisionen:** Wenn WR und SDM630 auf demselben RS485-Bus hängen, kann es zu Kollisionen kommen. Das System fängt diese ab und behält den letzten plausiblen Wert. Polling-Intervall mindestens 30 Sekunden empfohlen.

> **Batteriesicherheit:** BATDV (Entladespannungsgrenzen) niemals automatisiert setzen. Falsche Werte können den BMS zum Schutzabschalten bringen.

---

## 📦 Abhängigkeiten

| Paket | Verwendung |
|-------|------------|
| [mpp-solar](https://github.com/jblance/mpp-solar) | WR Kommunikation (PI17INFINI Protokoll) |
| [Flask](https://flask.palletsprojects.com/) | Web Framework |
| [APScheduler](https://apscheduler.readthedocs.io/) | Task Scheduling |
| [paho-mqtt](https://pypi.org/project/paho-mqtt/) | MQTT Client |
| [pyserial](https://pyserial.readthedocs.io/) | RS485 / RS232 Kommunikation |
| [Open-Meteo](https://open-meteo.com/) | Wettervorhersage API (kostenlos, kein API-Key nötig) |

---

## 📄 Lizenz

MIT License – frei verwendbar, anpassbar und weitergabe erlaubt.
