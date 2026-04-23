# ⚡ PV-EMS Dashboard

Ein schlankes **Energie-Management-System** für Photovoltaik-Anlagen mit Hybridwechselrichter, Batteriespeicher und Netzeinspeisung. Das System liest Echtzeitdaten von Wechselrichter, Stromzähler und Batterie aus, visualisiert sie in einem Web-Dashboard und sendet sie an HomeAssistant via MQTT.

> **Entstanden aus der Praxis** – entwickelt für eine 15kW PV-Anlage mit 14.4 kWh Batteriespeicher.

![Dashboard Screenshot](docs/docs/EMS FSP 15KW Hybrid System Übersicht.png)
![Dashboard Screenshot](docs/docs/EMS FSP 15KW Hybrid System Verlauf.png)

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
|---|---|
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

## 🚀 Installation

### Option A – Docker (empfohlen)

```bash
# 1) Repository klonen
git clone https://github.com/quompacc/fsp-hybrid-monitor.git
cd fsp-hybrid-monitor

# 2) Konfiguration anlegen
cp .env.example .env
nano .env   # MQTT, Standort, Ports anpassen

# 3) Starten
docker compose up -d
```

Dashboard erreichbar unter: `http://<pi-ip>:5000`

> **Geräte-Ports prüfen** bevor du startest:
> ```bash
> ls -la /dev/ttyUSB* /dev/hidraw*
> udevadm info /dev/ttyUSB0 | grep -E "ID_MODEL|ID_SERIAL"
> ```
> Ports in `.env` entsprechend anpassen.

---

### Option B – Manuell (ohne Docker)

#### Voraussetzungen

```bash
sudo apt update
sudo apt install python3-pip python3-venv git curl
```

#### Setup

```bash
git clone https://github.com/quompacc/fsp-hybrid-monitor.git
cd fsp-hybrid-monitor

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Konfiguration

Alle Werte können über Umgebungsvariablen oder eine `.env` Datei gesetzt werden:

```bash
cp .env.example .env
nano .env
```

#### Testen

```bash
# Jedes Gerät einzeln testen
python3 inverter/read_inverter.py
python3 sdm630/read_sdm630.py
python3 pylontech/read_pylontech.py

# Dashboard starten
python3 dashboard/app.py
# Aufruf: http://raspberry-pi-ip:5000
```

#### Systemd Service

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
WorkingDirectory=/home/pi/fsp-hybrid-monitor
Environment="PATH=/home/pi/fsp-hybrid-monitor/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/pi/fsp-hybrid-monitor/venv/bin/python dashboard/app.py
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

#### Healthcheck Timer

```bash
sudo cp ems-healthcheck.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/ems-healthcheck.sh
sudo cp ems-healthcheck.service /etc/systemd/system/
sudo cp ems-healthcheck.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ems-healthcheck.timer
```

#### Hardware Watchdog (empfohlen)

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
sudo systemctl enable --now watchdog
```

---

## 🏗️ Architektur

```
Geräte                    Leser                  Verarbeitung        Ausgabe

/dev/hidraw0  ──►  read_inverter.py  ──┐
                                       ├──►  scheduler.py  ──►  app.py  ──►  Browser
/dev/ttyUSB0  ──►  read_sdm630.py   ──┤         │
                                       │         ├──►  mqtt_client.py  ──►  HomeAssistant
/dev/ttyUSB1  ──►  read_pylontech.py──┘         │
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
fsp-hybrid-monitor/
├── dashboard/
│   ├── app.py              # Flask Web-App (Read-Only API)
│   ├── config.py           # Konfiguration via ENV-Variablen
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
├── data/                   # SQLite Datenbank (auto-erstellt)
├── docs/                   # Screenshots
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── start_ems.sh
```

---

## 📡 MQTT Sensoren in HomeAssistant

Nach dem Start einmal **"HA Discovery senden"** im Dashboard klicken – alle Sensoren erscheinen automatisch in HomeAssistant.

| Sensor | Topic | Einheit |
|---|---|---|
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
|---|---|
| [mpp-solar](https://github.com/jblance/mpp-solar) | WR Kommunikation (PI17INFINI Protokoll) |
| [Flask](https://flask.palletsprojects.com/) | Web Framework |
| [APScheduler](https://apscheduler.readthedocs.io/) | Task Scheduling |
| [paho-mqtt](https://pypi.org/project/paho-mqtt/) | MQTT Client |
| [pyserial](https://pyserial.readthedocs.io/) | RS485 / RS232 Kommunikation |
| [Open-Meteo](https://open-meteo.com/) | Wettervorhersage API (kostenlos, kein API-Key nötig) |

---

## 📄 Lizenz

MIT License – frei verwendbar, anpassbar und weitergebbar.
