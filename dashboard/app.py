"""
EMS Dashboard - Flask Web App (Read-Only)
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, jsonify, request
from db import init_db, get_history
from scheduler import start_scheduler, latest
from mqtt_client import publish_ha_discovery
from config import HOST, PORT, DEBUG

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    rec, reason = latest['recommendation']
    return jsonify({
        'inverter':       latest['inverter'],
        'sdm630':         latest['sdm630'],
        'pylontech':      latest['pylontech'],
        'weather':        latest['weather'],
        'recommendation': {'action': rec, 'reason': reason},
        'last_update':    latest['last_update'],
    })

@app.route('/api/history/<device>')
def api_history(device):
    hours = int(request.args.get('hours', 24))
    table_map = {
        'inverter':  'inverter_data',
        'sdm630':    'sdm630_data',
        'pylontech': 'pylontech_data',
    }
    table = table_map.get(device)
    if not table:
        return jsonify({'error': 'Unknown device'}), 404
    return jsonify(get_history(table, hours))

@app.route('/api/weather')
def api_weather():
    from weather import get_forecast, get_solar_recommendation
    forecast = get_forecast()
    if forecast:
        soc = latest['pylontech'].get('avg_soc', 50)
        rec, reason = get_solar_recommendation(forecast, soc)
        return jsonify({'forecast': forecast, 'recommendation': rec, 'reason': reason})
    return jsonify({'error': 'Keine Wetterdaten'}), 503

@app.route('/api/mqtt/discovery', methods=['POST'])
def api_mqtt_discovery():
    try:
        publish_ha_discovery()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    init_db()
    scheduler = start_scheduler()
    try:
        publish_ha_discovery()
    except Exception as e:
        print(f'MQTT Discovery Fehler beim Start: {e}')
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
