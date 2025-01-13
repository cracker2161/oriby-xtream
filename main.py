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

# Configure logging with both file and console handlers
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
            logger.debug(f"Authenticating user: {self.username}")
            response = self.session.get(self.base_url, params=params, timeout=15)
            response.raise_for_status()
            auth_data = response.json()
            
            # Log successful authentication
            if 'user_info' in auth_data:
                logger.info(f"Successful authentication for user: {self.username}")
                # Add expiry date to response
                if 'exp_date' in auth_data['user_info']:
                    exp_date = datetime.fromtimestamp(int(auth_data['user_info']['exp_date']))
                    auth_data['user_info']['formatted_exp_date'] = exp_date.strftime('%Y-%m-%d %H:%M:%S')
            
            return auth_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Authentication error for user {self.username}: {str(e)}")
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
            categories = response.json()
            
            # Sort categories by name
            if isinstance(categories, list):
                categories.sort(key=lambda x: x.get('category_name', ''))
                logger.info(f"Successfully retrieved {len(categories)} categories")
            
            return categories
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
            streams = response.json()

            # Process and format stream URLs
            if isinstance(streams, list):
                for stream in streams:
                    stream_id = stream.get('stream_id')
                    if stream_id:
                        stream['stream_url'] = f"{self.server}/live/{self.username}/{self.password}/{stream_id}"
                        stream['direct_source'] = f"{self.server}/live/{self.username}/{self.password}/{stream_id}"
                        stream['m3u8_url'] = f"{self.server}/live/{self.username}/{self.password}/{stream_id}.m3u8"
                
                # Sort streams by name
                streams.sort(key=lambda x: x.get('name', ''))
                logger.info(f"Successfully retrieved {len(streams)} streams")

            return streams
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
            logger.debug(f"Fetching stream info for ID: {stream_id}")
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
        if not all(key in data for key in ['server', 'username', 'password']):
            raise ValueError("Missing required login parameters")

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

        error_msg = auth.get('error', 'Authentication failed')
        logger.warning(f"Failed login attempt: {data['username']} - {error_msg}")
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
        username = session.get('username', 'unknown')
        session.clear()
        logger.info(f"User logged out: {username}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return jsonify({'error': str(e)})

@app.route('/export_playlist')
def export_playlist():
    try:
        if 'username' not in session:
            return jsonify({'error': 'Not authorized'})

        client = XtreamClient(
            session['server'],
            session['username'],
            session['password']
        )
        streams = client.get_live_streams()
        
        if isinstance(streams, list):
            playlist_content = "#EXTM3U\n"
            for stream in streams:
                playlist_content += f"#EXTINF:-1,{stream.get('name', 'Unknown')}\n"
                playlist_content += f"{stream.get('stream_url', '')}.m3u8\n"
            
            return jsonify({
                'status': 'success',
                'playlist': playlist_content
            })
        
        return jsonify({'error': 'Could not generate playlist'})

    except Exception as e:
        logger.error(f"Export playlist error: {str(e)}")
        return jsonify({'error': str(e)})

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not Found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({'error': 'Internal Server Error'}), 500

if __name__ == '__main__':
    # Ensure the log directory exists
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Set to False in production
    app.run(debug=True, host='0.0.0.0', port=5000)
