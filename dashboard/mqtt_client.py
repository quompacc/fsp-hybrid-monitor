"""
MQTT Publisher für HomeAssistant
Auto-Discovery + Datenpublishing
"""
import json
import paho.mqtt.client as mqtt
from config import MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASSWORD, MQTT_PREFIX

_client = None

def get_client():
    global _client
    if _client is None or not _client.is_connected():
        _client = mqtt.Client(client_id='hybrid-energy-monitor')
        if MQTT_USER or MQTT_PASSWORD:
            _client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        try:
            _client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            _client.loop_start()
        except Exception as e:
            print(f'MQTT Verbindungsfehler: {e}')
    return _client

def publish(topic, payload, retain=False):
    try:
        c = get_client()
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        c.publish(f'{MQTT_PREFIX}/{topic}', payload, retain=retain)
    except Exception as e:
        print(f'MQTT publish Fehler: {e}')

def publish_ha_discovery():
    """HomeAssistant Auto-Discovery Nachrichten"""
    sensors = [
        # Wechselrichter
        ('inverter/battery_voltage',   'WR Akkuspannung',     'V',    'voltage',     'mdi:battery'),
        ('inverter/battery_capacity',  'WR Akku SOC',         '%',    'battery',     'mdi:battery'),
        ('inverter/battery_current',   'WR Akkustrom',        'A',    'current',     'mdi:current-dc'),
        ('inverter/solar_power',       'Solar Leistung',      'W',    'power',       'mdi:solar-power'),
        ('inverter/ac_input_freq',     'Netz Frequenz WR',    'Hz',   'frequency',   'mdi:sine-wave'),
        ('inverter/temp_inner',        'WR Temperatur',       '°C',   'temperature', 'mdi:thermometer'),
        ('inverter/mode',              'WR Modus',            None,   None,          'mdi:information'),
        ('inverter/pv_total_energy',   'PV Gesamtertrag',     'kWh',  'energy',      'mdi:solar-power'),
        # SDM630
        ('sdm630/total_power',         'Netzleistung',        'W',    'power',       'mdi:home-lightning-bolt'),
        ('sdm630/l1_voltage',          'Spannung L1',         'V',    'voltage',     'mdi:sine-wave'),
        ('sdm630/l2_voltage',          'Spannung L2',         'V',    'voltage',     'mdi:sine-wave'),
        ('sdm630/l3_voltage',          'Spannung L3',         'V',    'voltage',     'mdi:sine-wave'),
        ('sdm630/frequency',           'Netz Frequenz',       'Hz',   'frequency',   'mdi:sine-wave'),
        ('sdm630/bezug',               'Netzbezug',           'W',    'power',       'mdi:transmission-tower-import'),
        ('sdm630/einspeisung',         'Einspeisung',         'W',    'power',       'mdi:transmission-tower-export'),
        ('sdm630/import_energy',       'Bezug Gesamt',        'kWh',  'energy',      'mdi:transmission-tower-import'),
        ('sdm630/export_energy',       'Einspeisung Gesamt',  'kWh',  'energy',      'mdi:transmission-tower-export'),
        # Pylontech
        ('pylontech/avg_soc',          'Akku SOC Gesamt',     '%',    'battery',     'mdi:battery-charging'),
        ('pylontech/avg_voltage',      'Akku Spannung',       'V',    'voltage',     'mdi:battery'),
        ('pylontech/total_current',    'Akku Strom',          'A',    'current',     'mdi:current-dc'),
        ('pylontech/module_count',     'Akku Module',         None,   None,          'mdi:battery-multiple'),
    ]

    c = get_client()
    for topic_suffix, name, unit, device_class, icon in sensors:
        unique_id = topic_suffix.replace('/', '_')
        config = {
            'name':        name,
            'unique_id':   f'ems_{unique_id}',
            'state_topic': f'{MQTT_PREFIX}/{topic_suffix}',
            'icon':        icon,
        }
        if unit:
            config['unit_of_measurement'] = unit
        if device_class:
            config['device_class'] = device_class
        if unit == 'kWh':
            config['state_class'] = 'total_increasing'
        elif unit in ('W', 'V', 'A', '%', 'Hz', '°C'):
            config['state_class'] = 'measurement'

        config['device'] = {
            'identifiers': ['hybrid_energy_monitor'],
            'name':        'Hybrid Energy Monitor',
            'model':       'Hybrid Inverter + Battery + Smart Meter',
            'manufacturer': 'Custom EMS'
        }

        ha_topic = f'homeassistant/sensor/ems/{unique_id}/config'
        c.publish(ha_topic, json.dumps(config), retain=True)

    print('HA Discovery gesendet')

def publish_inverter(d):
    solar_w = round((d.get('solar_input_voltage_1', 0) * d.get('solar_input_current_1', 0) +
                     d.get('solar_input_voltage_2', 0) * d.get('solar_input_current_2', 0)), 1)
    publish('inverter/battery_voltage',  d.get('battery_voltage', 0))
    publish('inverter/battery_capacity', d.get('battery_capacity', 0))
    publish('inverter/battery_current',  d.get('battery_current', 0))
    publish('inverter/solar_power',      solar_w)
    publish('inverter/ac_input_freq',    d.get('ac_input_frequency', 0))
    publish('inverter/temp_inner',       d.get('inner_temperature', 0))
    publish('inverter/mode',             d.get('working_mode', ''))
    pv_total = d.get('pv_total_energy')
    if pv_total:
        publish('inverter/pv_total_energy', int(pv_total), retain=True)

def publish_sdm630(d):
    pw          = d.get('Gesamt Aktivleistung', 0)
    bezug       = round(max(0,  pw), 1)
    einspeisung = round(max(0, -pw), 1)
    publish('sdm630/total_power',  pw)
    publish('sdm630/bezug',        bezug)
    publish('sdm630/einspeisung',  einspeisung)
    publish('sdm630/l1_voltage',   d.get('L1 Spannung', 0))
    publish('sdm630/l2_voltage',   d.get('L2 Spannung', 0))
    publish('sdm630/l3_voltage',   d.get('L3 Spannung', 0))
    publish('sdm630/frequency',    d.get('Frequenz', 0))
    # Energie-Zähler nur publishen wenn vorhanden und plausibel (>100 kWh)
    imp = d.get('Import Energie', 0)
    exp = d.get('Export Energie', 0)
    if imp and float(imp) > 100:
        publish('sdm630/import_energy', imp, retain=True)
    if exp and float(exp) > 100:
        publish('sdm630/export_energy', exp, retain=True)

def publish_pylontech(d):
    publish('pylontech/avg_soc',      d.get('avg_soc', 0))
    publish('pylontech/avg_voltage',  d.get('avg_voltage_v', 0))
    publish('pylontech/total_current', d.get('total_current_a', 0))
    publish('pylontech/module_count', d.get('module_count', 0))
