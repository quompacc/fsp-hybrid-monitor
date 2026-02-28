"""
Hintergrund-Scheduler für Datenabruf und Automatik
"""
import sys
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

sys.path.insert(0, '/home/eduard/ems/inverter')
sys.path.insert(0, '/home/eduard/ems/sdm630')
sys.path.insert(0, '/home/eduard/ems/pylontech')
sys.path.insert(0, '/home/eduard/mpp-solar')

# Shared state
latest = {
    'inverter':       {},
    'sdm630':         {},
    'pylontech':      {},
    'weather':        None,
    'recommendation': ('unknown', 'Noch kein Wetter geladen'),
    'last_update':    {}
}

def collect_inverter():
    try:
        import read_inverter
        data     = read_inverter.run_command('GS')
        mod_data = read_inverter.run_command('MOD')
        et_data  = read_inverter.run_command('ET')
        if not data:
            return
        if not data.get('ac_input_voltage_r') and not data.get('battery_voltage'):
            print('Inverter: ungültige Daten, überspringe')
            return
        if mod_data:
            data.update(mod_data)
        if et_data:
            data['pv_total_energy'] = et_data.get('generated_energy_total', 0)
        latest['inverter'] = data
        from datetime import datetime
        latest['last_update']['inverter'] = datetime.now().isoformat()
        from db import insert_inverter
        insert_inverter(data)
        from mqtt_client import publish_inverter
        publish_inverter(data)
    except Exception as e:
        print(f'Inverter Fehler: {e}')

def collect_sdm630():
    try:
        import read_sdm630
        data = read_sdm630.read_all()
        if not data:
            return
        result = {k: v for k, (v, u) in data.items()}
        pw = result.get('Gesamt Aktivleistung')
        if pw is None:
            return
        latest['sdm630'] = result
        from datetime import datetime
        latest['last_update']['sdm630'] = datetime.now().isoformat()
        from db import insert_sdm630
        insert_sdm630(result)
        from mqtt_client import publish_sdm630
        publish_sdm630(result)
    except Exception as e:
        print(f'SDM630 Fehler: {e}')

def collect_pylontech():
    try:
        import read_pylontech
        data = read_pylontech.read_all()
        if not data:
            return
        v   = data.get('avg_voltage_v', 0)
        soc = data.get('avg_soc', 0)
        if not v or float(v) < 40 or float(v) > 60:
            print(f'Pylontech: ungültige Spannung {v}V, überspringe')
            return
        if soc is not None and float(soc) == 0 and data.get('module_count', 0) > 0:
            print('Pylontech: SOC=0 bei aktiven Modulen, überspringe')
            return
        latest['pylontech'] = data
        from datetime import datetime
        latest['last_update']['pylontech'] = datetime.now().isoformat()
        from db import insert_pylontech
        insert_pylontech(data)
        from mqtt_client import publish_pylontech
        publish_pylontech(data)
    except Exception as e:
        print(f'Pylontech Fehler: {e}')

def collect_weather():
    try:
        from weather import get_forecast, get_solar_recommendation
        forecast = get_forecast()
        if forecast:
            latest['weather'] = forecast
            soc = latest['pylontech'].get('avg_soc', 50)
            rec, reason = get_solar_recommendation(forecast, soc)
            latest['recommendation'] = (rec, reason)
            from db import get_db
            conn = get_db()
            conn.execute('''INSERT INTO weather_data
                (today_sun, tomorrow_sun, temp_max, description)
                VALUES (?,?,?,?)''',
                (forecast['today']['sun_hours'],
                 forecast['tomorrow']['sun_hours'],
                 forecast['tomorrow']['temp_max'],
                 forecast['tomorrow']['description']))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f'Wetter Fehler: {e}')

def apply_auto_control():
    try:
        rec, reason = latest['recommendation']
        soc = latest['pylontech'].get('avg_soc', 50)
        if rec != 'unknown':
            from controller import apply_weather_recommendation
            result = apply_weather_recommendation(rec, soc, source='auto')
            print(f'Auto-Steuerung: {result} ({reason})')
    except Exception as e:
        print(f'Auto-Steuerung Fehler: {e}')

def start_scheduler():
    scheduler = BackgroundScheduler(timezone='Europe/Berlin')

    scheduler.add_job(collect_inverter,   IntervalTrigger(seconds=15), id='inverter',     replace_existing=True)
    scheduler.add_job(collect_sdm630,     IntervalTrigger(seconds=30), id='sdm630',       replace_existing=True)
    scheduler.add_job(collect_pylontech,  IntervalTrigger(seconds=60), id='pylontech',    replace_existing=True)
    scheduler.add_job(collect_weather,    IntervalTrigger(minutes=30), id='weather',      replace_existing=True)
    # Auto-Control deaktiviert - zu riskant
    # scheduler.add_job(apply_auto_control, IntervalTrigger(hours=1),    id='auto_control', replace_existing=True)

    scheduler.start()

    import time
    time.sleep(1)

    collect_weather()
    collect_inverter()
    collect_sdm630()
    collect_pylontech()

    return scheduler
