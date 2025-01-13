from flask import Flask, render_template, request, jsonify, session, send_file
import requests
import json
import m3u8
from datetime import datetime
import logging
import secrets
import os
import io

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
            data = response.json()
            # Add expiration date processing
            if 'user_info' in data:
                data['user_info']['exp_date'] = datetime.fromtimestamp(
                    int(data['user_info'].get('exp_date', 0))
                ).strftime('%Y-%m-%d %H:%M:%S')
            return data
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

    def get_live_streams(self, category_id=None, search_term=None):
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
            streams = response.json()

            # Process streams and add URLs
            if isinstance(streams, list):
                # Apply search filter if provided
                if search_term:
                    search_term = search_term.lower()
                    streams = [s for s in streams if search_term in s.get('name', '').lower()]

                for stream in streams:
                    stream_id = stream.get('stream_id')
                    if stream_id:
                        stream['stream_url'] = f"{self.server}/live/{self.username}/{self.password}/{stream_id}"
                        stream['direct_source'] = f"{self.server}/live/{self.username}/{self.password}/{stream_id}"
                        stream['m3u8_url'] = f"{self.server}/live/{self.username}/{self.password}/{stream_id}.m3u8"

            return streams
        except requests.exceptions.RequestException as e:
            logger.error(f"Streams error: {str(e)}")
            return {'error': str(e)}

    def export_playlist(self):
        try:
            streams = self.get_live_streams()
            if isinstance(streams, list):
                playlist_content = "#EXTM3U\n"
                for stream in streams:
                    playlist_content += f'#EXTINF:-1 tvg-id="{stream.get("stream_id")}" tvg-name="{stream.get("name")}" tvg-logo="{stream.get("stream_icon")}",{stream.get("name")}\n'
                    playlist_content += f'{stream.get("m3u8_url")}\n'
                return playlist_content
            return None
        except Exception as e:
            logger.error(f"Export playlist error: {str(e)}")
            return None

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
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/categories')
def categories():
    if 'username' not in session:
        return jsonify({'error': 'Not authorized'})

    client = XtreamClient(session['server'], session['username'], session['password'])
    return jsonify(client.get_live_categories())

@app.route('/streams')
def streams():
    if 'username' not in session:
        return jsonify({'error': 'Not authorized'})

    category_id = request.args.get('category_id')
    search_term = request.args.get('search')
    client = XtreamClient(session['server'], session['username'], session['password'])
    return jsonify(client.get_live_streams(category_id, search_term))

@app.route('/export_playlist')
def export_playlist():
    if 'username' not in session:
        return jsonify({'error': 'Not authorized'})

    client = XtreamClient(session['server'], session['username'], session['password'])
    playlist_content = client.export_playlist()
    
    if playlist_content:
        buffer = io.BytesIO()
        buffer.write(playlist_content.encode('utf-8'))
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype='text/plain',
            as_attachment=True,
            download_name='playlist.m3u'
        )
    
    return jsonify({'error': 'Failed to generate playlist'})

@app.route('/logout')
def logout():
    session.clear()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
