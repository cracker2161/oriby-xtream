from flask import Flask, render_template, request, jsonify, session
import requests
import json
import m3u8
from datetime import datetime
import logging
import secrets
import os

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class XtreamClient:
    def __init__(self, server, username, password):
        self.server = server.rstrip('/')
        self.username = username
        self.password = password
        self.base_url = f"{self.server}/player_api.php"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def authenticate(self):
        try:
            params = {
                'username': self.username,
                'password': self.password
            }
            logger.debug(f"Authentication attempt for user: {self.username}")
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Authentication error: {str(e)}")
            return {'error': str(e)}

    def get_live_categories(self):
        try:
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_live_categories'
            }
            logger.debug("Fetching live categories")
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Retrieved {len(data) if isinstance(data, list) else 0} categories")
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Categories error: {str(e)}")
            return {'error': str(e)}

    def get_live_streams(self, category_id=None):
        try:
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_live_streams'
            }
            if category_id:
                params['category_id'] = category_id

            logger.debug(f"Fetching streams for category: {category_id}")
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"Retrieved {len(data) if isinstance(data, list) else 0} streams")
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Streams error: {str(e)}")
            return {'error': str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/connect', methods=['POST'])
def connect():
    try:
        data = request.json
        if not all(key in data for key in ['server', 'username', 'password']):
            raise ValueError("All fields are required")

        logger.info(f"Connection attempt from: {data['username']}")
        client = XtreamClient(data['server'], data['username'], data['password'])
        auth = client.authenticate()

        if auth and not auth.get('error'):
            session['server'] = data['server']
            session['username'] = data['username']
            session['password'] = data['password']
            session['auth_time'] = datetime.now().timestamp()
            logger.info(f"Successful login: {data['username']}")
            return jsonify({
                'status': 'success',
                'data': auth
            })

        error_msg = auth.get('error', 'Login failed')
        logger.warning(f"Failed login: {data['username']} - {error_msg}")
        return jsonify({
            'status': 'error',
            'message': error_msg
        })

    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/categories')
def categories():
    try:
        if 'username' not in session:
            return jsonify({'error': 'Not authorized'})

        client = XtreamClient(
            session['server'],
            session['username'],
            session['password']
        )
        categories = client.get_live_categories()

        if isinstance(categories, list):
            return jsonify(categories)
        else:
            logger.error(f"Invalid categories response: {categories}")
            return jsonify({'error': 'Error loading categories'})

    except Exception as e:
        logger.error(f"Categories route error: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/streams')
def streams():
    try:
        if 'username' not in session:
            return jsonify({'error': 'Not authorized'})

        category_id = request.args.get('category_id')
        client = XtreamClient(
            session['server'],
            session['username'],
            session['password']
        )
        streams = client.get_live_streams(category_id)

        if isinstance(streams, list):
            return jsonify(streams)
        else:
            logger.error(f"Invalid streams response: {streams}")
            return jsonify({'error': 'Error loading channels'})

    except Exception as e:
        logger.error(f"Streams route error: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/logout')
def logout():
    try:
        username = session.get('username', 'unknown')
        session.clear()
        logger.info(f"User logged out: {username}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
