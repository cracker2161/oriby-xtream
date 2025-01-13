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
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
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

            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                for stream in data:
                    stream_id = stream.get('stream_id')
                    if stream_id:
                        stream['stream_url'] = f"{self.server}/live/{self.username}/{self.password}/{stream_id}"
                        stream['direct_source'] = f"{self.server}/live/{self.username}/{self.password}/{stream_id}"
                        stream['m3u8_url'] = f"{self.server}/live/{self.username}/{self.password}/{stream_id}.m3u8"

            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Streams error: {str(e)}")
            return {'error': str(e)}

    def get_stream_info(self, stream_id):
        try:
            params = {
                'username': self.username,
                'password': self.password,
                'action': 'get_short_epg',
                'stream_id': stream_id
            }
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Stream info error: {str(e)}")
            return {'error': str(e)}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/connect', methods=['POST'])
def connect():
    try:
        data = request.json
        client = XtreamClient(data['server'], data['username'], data['password'])
        auth = client.authenticate()

        if auth and not auth.get('error'):
            session['server'] = data['server']
            session['username'] = data['username']
            session['password'] = data['password']
            session['auth_time'] = datetime.now().timestamp()
            return jsonify({
                'status': 'success',
                'data': auth
            })

        return jsonify({
            'status': 'error',
            'message': auth.get('error', 'Login failed')
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
        return jsonify(categories)

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
        return jsonify(streams)

    except Exception as e:
        logger.error(f"Streams route error: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/stream_info/<int:stream_id>')
def stream_info(stream_id):
    try:
        if 'username' not in session:
            return jsonify({'error': 'Not authorized'})

        client = XtreamClient(
            session['server'],
            session['username'],
            session['password']
        )
        info = client.get_stream_info(stream_id)
        return jsonify(info)

    except Exception as e:
        logger.error(f"Stream info error: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/account_info')
def account_info():
    try:
        if 'username' not in session:
            return jsonify({'error': 'Not authorized'})

        client = XtreamClient(
            session['server'],
            session['username'],
            session['password']
        )
        auth_data = client.authenticate()
        
        if 'user_info' in auth_data:
            exp_date = auth_data['user_info'].get('exp_date', 0)
            if exp_date:
                exp_datetime = datetime.fromtimestamp(int(exp_date))
                return jsonify({
                    'status': 'success',
                    'expiry_date': exp_datetime.strftime('%Y-%m-%d %H:%M:%S')
                })
        
        return jsonify({'error': 'Could not fetch account information'})

    except Exception as e:
        logger.error(f"Account info error: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/logout')
def logout():
    try:
        session.clear()
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({'error': str(e)})

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not Found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal Server Error'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
