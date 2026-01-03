import eventlet
eventlet.monkey_patch()

import sys
import os
import json
import logging
import threading
import queue
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Add current directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.magento_auth import get_magento_token
from services.medusa_auth import get_medusa_token
from connectors.magento_connector import MagentoConnector
from connectors.medusa_connector import MedusaConnector

# Import migrators
from migrators.product_migrator import migrate_products
from migrators.category_migrator import migrate_categories
from migrators.customer_migrator import migrate_customers
from migrators.order_migrator import migrate_orders
import config
import re

def _sanitize_url(url):
    """
    If running in Docker, replace localhost/127.0.0.1 with host.docker.internal
    to allow users to type 'localhost' naturally.
    """
    if os.environ.get('DOCKER_CONTAINER') and url:
        return re.sub(r'://(localhost|127\.0\.0\.1)', '://host.docker.internal', url)
    return url

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# Global state
migration_state = {
    'running': False,
    'stop_requested': False,
    'magento_token': None,
    'medusa_token': None,
    'cached_products': None,
    'cached_categories': None,
}

# Custom Logger to emit to Socket.IO
class SocketIOLogger:
    def __init__(self):
        self.buffer = ""

    def write(self, message):
        if message:
            sys.__stdout__.write(message)  # Write to console as well
            socketio.emit('log', {'data': message})

    def flush(self):
        sys.__stdout__.flush()

# Redirect stdout/stderr specifically requires careful handling in threaded/eventlet env
# For simplicity, we'll manually emit logs in our customized print functions if we were rewriting the core logic,
# but since we want to capture existing prints, we'll try to redirect, but this can be tricky with eventlet.
# Instead, we will use a custom print function injected into builtins or just rely on the existing logger usage if it was configurable.
# Since the existing code uses `print` heavily, we might need a wrapper.

class StreamToSocket:
    def write(self, text):
        sys.__stdout__.write(text)
        socketio.emit('log', {'data': text})
    def flush(self):
        sys.__stdout__.flush()

# We will monkeypatch sys.stdout for the duration of the migration if possible, 
# or just rely on specific log calls if we modify the core utils.
# Given the user constraints, let's try to capture output by overriding sys.stdout in the worker thread.

@app.route('/')
def index():
    # Load defaults from config.py
    defaults = {
        'magento': getattr(config, 'MAGENTO', {}),
        'medusa': getattr(config, 'MEDUSA', {})
    }
    return render_template('index.html', defaults=defaults)

@app.route('/api/test-magento', methods=['POST'])
def test_magento():
    data = request.json
    base_url = _sanitize_url(data.get('base_url'))
    username = data.get('username')
    password = data.get('password')
    verify_ssl = data.get('verify_ssl', False)

    try:
        def logger(msg):
             # Simple logger to stdout which we might capture later, or just ignore for auth test
             print(msg)

        token = get_magento_token(base_url, username, password, verify_ssl=verify_ssl, logger=logger)
        migration_state['magento_token'] = token
        return jsonify({'success': True, 'token': token})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/test-medusa', methods=['POST'])
def test_medusa():
    data = request.json
    base_url = _sanitize_url(data.get('base_url'))
    email = data.get('email')
    password = data.get('password')

    try:
        def logger(msg):
             print(msg)

        token = get_medusa_token(base_url, email, password, logger=logger)
        migration_state['medusa_token'] = token
        return jsonify({'success': True, 'token': token})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/fetch-entities', methods=['POST'])
def fetch_entities():
    # Helper to fetch lists for selection (products, categories, etc.)
    # Implementation similar to app_gui.py but adapted for web
    data = request.json
    entity_type = data.get('type')
    
    magento_config = data.get('magento_config')
    if magento_config and 'base_url' in magento_config:
        magento_config['base_url'] = _sanitize_url(magento_config['base_url'])

    token = migration_state.get('magento_token')
    
    if not token and magento_config:
         # Try to auto-login if token missing but config provided
         try:
            token = get_magento_token(
                magento_config['base_url'], 
                magento_config['username'], 
                magento_config['password'], 
                verify_ssl=magento_config.get('verify_ssl', False)
            )
            migration_state['magento_token'] = token
         except Exception as e:
             return jsonify({'success': False, 'error': f"Login failed: {str(e)}"})
    
    if not token:
        return jsonify({'success': False, 'error': "Not authenticated with Magento"})

    client = MagentoConnector(magento_config['base_url'], token, magento_config.get('verify_ssl', False))
    
    items = []
    try:
        if entity_type == 'products':
            # Fetch first 1000 items or so for selection
            res = client.get_products(page=1, page_size=200, fields="items[id,name,sku]")
            for p in res.get('items', []):
                items.append({'id': p.get('id'), 'label': f"[{p.get('id')}] {p.get('sku')} - {p.get('name')}"})
        
        elif entity_type == 'categories':
            res = client.get_categories(page=1, page_size=1000, fields="items[id,name,level]")
            for c in res.get('items', []):
                if c.get('level') == 0: continue
                items.append({'id': c.get('id'), 'label': f"[{c.get('id')}] {c.get('name')}"})

        elif entity_type == 'customers':
            res = client.get_customers(page=1, page_size=200)
            for c in res.get('items', []):
                 items.append({'id': c.get('id'), 'label': f"[{c.get('id')}] {c.get('email')}"})
        
        elif entity_type == 'orders':
            res = client.get_orders(page=1, page_size=50)
            for o in res.get('items', []):
                oid = o.get('entity_id')
                inc = o.get('increment_id')
                total = o.get('grand_total')
                items.append({
                    'id': oid, 
                    'label': f"[{oid}] Order #{inc} - ${total}"
                })
                 
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

class Args:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def run_migration_task(config_data):
    # Set stdout to our socket emitter
    original_stdout = sys.stdout
    sys.stdout = StreamToSocket()
    
    try:
        migration_state['running'] = True
        
        # Prepare args
        args = Args(
            limit=int(config_data.get('limit', 0)),
            dry_run=config_data.get('dry_run', False),
            max_workers=int(config_data.get('max_workers', 10)),
            product_ids=config_data.get('product_ids'),
            category_ids=config_data.get('category_ids'),
            order_ids=config_data.get('order_ids'),
            customer_ids=config_data.get('customer_ids'),
            finalize_orders=config_data.get('finalize_orders', True),
            verify_ssl=config_data['magento'].get('verify_ssl', False),
            category_strategy="list", # Default as per CLI
            skip_init_log=True
        )
        
        selected_entities = config_data.get('entities', [])
        
        # Setup Connectors
        magento = MagentoConnector(
            base_url=_sanitize_url(config_data['magento']['base_url']),
            token=migration_state['magento_token'],
            verify_ssl=args.verify_ssl
        )
        
        medusa = MedusaConnector(
            base_url=_sanitize_url(config_data['medusa']['base_url']),
            api_token=migration_state['medusa_token']
        )
        
        print(f"🚀 Starting Migration [Limit: {args.limit}, Dry-run: {args.dry_run}]")
        
        mg_to_medusa_map = {}

        if 'categories' in selected_entities and not migration_state.get('stop_requested'):
            mg_to_medusa_map = migrate_categories(magento, medusa, args)
            
        if 'customers' in selected_entities and not migration_state.get('stop_requested'):
            migrate_customers(magento, medusa, args)
            
        if 'products' in selected_entities and not migration_state.get('stop_requested'):
            migrate_products(magento, medusa, args, mg_to_medusa_map=mg_to_medusa_map)
            
        if 'orders' in selected_entities and not migration_state.get('stop_requested'):
            migrate_orders(magento, medusa, args)
            
        print("Migration process finished.")
        socketio.emit('status_update', {'running': False, 'message': 'Completed'})

    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc(file=sys.stdout)
        socketio.emit('status_update', {'running': False, 'error': str(e)})
    finally:
        migration_state['running'] = False
        migration_state['stop_requested'] = False
        sys.stdout = original_stdout

@app.route('/api/start', methods=['POST'])
def start_migration():
    if migration_state['running']:
        return jsonify({'success': False, 'error': 'Migration is already running'})
        
    config_data = request.json
    
    # Check tokens
    if not migration_state.get('magento_token') or not migration_state.get('medusa_token'):
         return jsonify({'success': False, 'error': 'Please authenticate both Magento and Medusa first.'})
    
    thread = threading.Thread(target=run_migration_task, args=(config_data,))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
def stop_migration():
    if migration_state['running']:
        migration_state['stop_requested'] = True
        return jsonify({'success': True, 'message': 'Stop requested...'})
    return jsonify({'success': False, 'error': 'Not running'})

if __name__ == '__main__':
    # Get port from env
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
