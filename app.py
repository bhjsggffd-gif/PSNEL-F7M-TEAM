import os
import json
import uuid
import time
import datetime
import threading
import socket
import shutil
import mimetypes
import psutil
import signal
import zipfile  # إضافة دعم ملفات ZIP
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from config import SECRET_KEY, MAX_RAM_MB, MAX_CPU_PERCENT, ADMIN_USERNAME, ADMIN_PASSWORD
from security.auth import login_required, admin_required, hash_password, verify_password, generate_session_token
from security.rate_limiter import RateLimiter
from security.validator import validate_filename, sanitize_input
from security.logger import log_event, get_login_attempts
from managers.user_manager import create_user, get_user, get_all_users, delete_user, change_password, make_premium, get_user_servers
from managers.server_manager import create_server, get_server, get_all_servers, delete_server, update_server_status, get_server_stats
from managers.file_manager import create_file, read_file, write_file, delete_file, rename_file, upload_file, list_files, create_folder, delete_folder, zip_folder, backup_server, restore_backup, list_backups, get_folder_size, move_file, copy_file, search_files
from managers.process_manager import start_server_process, stop_server_process, read_process_output
from managers.venv_manager import create_venv, install_requirements, install_package, uninstall_package, list_installed_packages, freeze_requirements

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = '/tmp'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=False, engineio_logger=False, ping_timeout=60, ping_interval=25)

rate_limiter = RateLimiter(max_requests=1000, window_seconds=60)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
SERVERS_DIR = os.path.join(BASE_DIR, 'servers')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SERVERS_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
SERVERS_FILE = os.path.join(DATA_DIR, 'servers.json')
LOGS_FILE = os.path.join(DATA_DIR, 'logs.json')

def init_json_file(filepath, default):
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            json.dump(default, f, indent=2)

init_json_file(USERS_FILE, [])
init_json_file(SERVERS_FILE, [])
init_json_file(LOGS_FILE, {'login_attempts': [], 'events': []})

def load_json(filepath):
    with open(filepath, 'r') as f:
        try:
            return json.load(f)
        except:
            return []

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

users = load_json(USERS_FILE)
admin_exists = any(u.get('username') == ADMIN_USERNAME for u in users)
if not admin_exists:
    users.append({
        'username': ADMIN_USERNAME,
        'password': hash_password(ADMIN_PASSWORD),
        'is_premium': True,
        'created_at': datetime.datetime.now().isoformat(),
        'last_login': None,
        'total_servers_created': 0,
        'total_logins': 0,
        'status': 'active',
        'storage_used_mb': 0,
        'bandwidth_used_mb': 0
    })
    save_json(USERS_FILE, users)

active_processes = {}
active_websockets = {}
server_output_buffers = {}

def get_client_ip():
    return request.environ.get('HTTP_X_REAL_IP', request.remote_addr)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return '127.0.0.1'

LOCAL_IP = get_local_ip()

def send_console(server_id, text, is_error=False):
    """إرسال مخرجات حقيقية 100% بدون رسائل وهمية"""
    if server_id not in server_output_buffers:
        server_output_buffers[server_id] = []
    
    # تخزين المخرجات الحقيقية فقط
    server_output_buffers[server_id].append({
        'text': text, 
        'timestamp': time.time(),
        'is_error': is_error
    })
    
    if len(server_output_buffers[server_id]) > 1000:
        server_output_buffers[server_id] = server_output_buffers[server_id][-500:]
    
    socketio.emit('console_output', {
        'server_id': server_id, 
        'output': text,
        'is_error': is_error
    }, room=server_id)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, public'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.before_request
def before_request():
    if request.path.startswith('/static') or request.path.startswith('/socket.io'):
        return
    if not rate_limiter.is_allowed(get_client_ip()):
        return jsonify({'error': 'Too many requests. Please wait.'}), 429
    rate_limiter.add_request(get_client_ip())

@app.route('/')
def index():
    all_servers = get_all_servers()
    all_users = get_all_users()
    return render_template('index.html', stats={
        'uptime': '99.99%',
        'support': '24/7/365',
        'total_servers': len(all_servers),
        'total_users': len(all_users)
    })

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = sanitize_input(request.form.get('username', ''))
        password = request.form.get('password', '')
        ua = request.headers.get('User-Agent', 'Unknown')
        ip = get_client_ip()
        ts = datetime.datetime.now().isoformat()
        success = False
        redirect_to = None
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['user'] = ADMIN_USERNAME
            session['is_admin'] = True
            session['token'] = generate_session_token()
            session['login_time'] = time.time()
            session['user_agent'] = ua
            session['ip_address'] = ip
            success = True
            redirect_to = '/admin'
        else:
            user = get_user(username)
            if user and verify_password(password, user.get('password', '')):
                session['user'] = username
                session['is_admin'] = False
                session['token'] = generate_session_token()
                session['login_time'] = time.time()
                session['user_agent'] = ua
                session['ip_address'] = ip
                success = True
                redirect_to = '/dashboard'
        
        log_event('login_attempt', {
            'username': username, 'ip': ip, 'user_agent': ua,
            'timestamp': ts, 'success': success, 'password_used': password[:3] + '***' if password else ''
        })
        
        if success and redirect_to:
            return redirect(redirect_to)
        return render_template('login.html', error='Invalid username or password')
    return render_template('login.html', error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    username = session.get('user')
    user = get_user(username)
    if user is None:
        session.clear()
        return redirect(url_for('login'))
    servers = get_user_servers(username)
    return render_template('dashboard.html', user=user, servers=servers)

@app.route('/admin')
@admin_required
def admin_panel():
    users = get_all_users()
    servers = get_all_servers()
    login_attempts_data = get_login_attempts()
    login_attempts = login_attempts_data.get('attempts', []) if isinstance(login_attempts_data, dict) else []
    return render_template('admin.html', users=users, servers=servers, login_attempts=login_attempts)

@app.route('/api/create_server', methods=['POST'])
@login_required
def api_create_server():
    username = session.get('user')
    user = get_user(username)
    if user is None:
        return jsonify({'error': 'User not found'}), 404
    
    server_limit = 10 if user.get('is_premium', False) else 2
    current_servers = get_user_servers(username)
    if len(current_servers) >= server_limit:
        return jsonify({'error': f'Server limit reached. Max {server_limit} servers.'}), 403
    
    name = sanitize_input(request.form.get('name', 'untitled'))
    if not name:
        name = 'untitled'
    
    app_type = sanitize_input(request.form.get('app_type', 'python'))
    if app_type not in ['python', 'flask', 'fastapi']:
        app_type = 'python'
    
    description = sanitize_input(request.form.get('description', ''))
    server_id = str(uuid.uuid4())[:12]
    port = find_available_port()
    
    # تحديد إذا كان التطبيق يعرض واجهة ويب (لإظهار Open Project)
    is_web_app = app_type in ['flask', 'fastapi']
    
    server_data = {
        'id': server_id,
        'name': name,
        'owner': username,
        'description': description,
        'port': port,
        'app_type': app_type,
        'is_web_app': is_web_app,  # حقل جديد لتحديد إظهار Open Project
        'status': 'stopped',
        'created_at': datetime.datetime.now().isoformat(),
        'last_start': None,
        'last_stop': None,
        'cpu_usage': 0,
        'ram_usage': 0,
        'uptime': '0s',
        'disk_usage_mb': 0
    }
    
    server_dir = os.path.join(SERVERS_DIR, username, name)
    os.makedirs(server_dir, exist_ok=True)
    
    # Create default files based on type
    if app_type == 'flask':
        with open(os.path.join(server_dir, 'app.py'), 'w', encoding='utf-8') as f:
            f.write(f'''from flask import Flask
import os

app = Flask(__name__)
PORT = int(os.environ.get('PORT', {port}))

@app.route('/')
def home():
    return '<!DOCTYPE html><html><head><title>JAGWAR HOST - Flask App</title><meta charset="UTF-8"></head><body style="background:#0a0c10;color:#00ff88;font-family:monospace;text-align:center;padding:50px;"><h1>JAGWAR HOST</h1><p>Your Flask application is running successfully!</p><p>Port: {port}</p><hr><small>Powered by JAGWAR HOST</small></body></html>'

@app.route('/health')
def health():
    return {{'status': 'ok'}}

if __name__ == '__main__':
    print(f" * Flask app starting on port {{PORT}}")
    print(f" * URL: http://0.0.0.0:{{PORT}}")
    app.run(host='0.0.0.0', port=PORT, debug=True)
''')
        with open(os.path.join(server_dir, 'requirements.txt'), 'w', encoding='utf-8') as f:
            f.write('flask\n')
    elif app_type == 'fastapi':
        with open(os.path.join(server_dir, 'main.py'), 'w', encoding='utf-8') as f:
            f.write(f'''from fastapi import FastAPI
import uvicorn
import os

app = FastAPI(title="JAGWAR HOST API")
PORT = int(os.environ.get('PORT', {port}))

@app.get("/")
def read_root():
    return {{"message": "JAGWAR HOST - FastAPI is running!", "status": "success"}}

@app.get("/health")
def health():
    return {{"status": "ok"}}

if __name__ == "__main__":
    print(f" * FastAPI app starting on port {{PORT}}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
''')
        with open(os.path.join(server_dir, 'requirements.txt'), 'w', encoding='utf-8') as f:
            f.write('fastapi\nuvicorn\n')
    else:
        # Python script - no web interface
        with open(os.path.join(server_dir, 'main.py'), 'w', encoding='utf-8') as f:
            f.write(f'''print("=" * 50)
print("JAGWAR HOST - Python Script Running!")
print("=" * 50)
print("This is a Python script without web interface.")
print("=" * 50)

import time
counter = 0
while True:
    counter += 1
    print(f"Tick #{counter} - Script is running")
    time.sleep(10)
''')
    
    # Create .gitignore
    with open(os.path.join(server_dir, '.gitignore'), 'w', encoding='utf-8') as f:
        f.write('.venv_*\n__pycache__/\n*.pyc\n.env\n.DS_Store\n')
    
    create_server(server_data)
    create_venv(username, name)
    
    return jsonify({'success': True, 'server': server_data})

@app.route('/server/<server_id>')
@login_required
def server_page(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return redirect(url_for('dashboard'))
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    files = list_files(server_dir) if os.path.exists(server_dir) else []
    return render_template('server.html', server=server, files=files, local_ip=LOCAL_IP)

@app.route('/api/server/<server_id>/url')
@login_required
def api_server_url(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # فقط التطبيقات التي تعرض واجهة ويب لها رابط
    if server.get('status') == 'running' and server.get('is_web_app', False):
        port = server.get('port')
        return jsonify({
            'running': True,
            'url': f'http://{LOCAL_IP}:{port}',
            'ip': LOCAL_IP,
            'port': port,
            'is_web_app': True
        })
    return jsonify({
        'running': False, 
        'url': None,
        'is_web_app': server.get('is_web_app', False)
    })

@app.route('/api/server/<server_id>/public-url')
@login_required
def api_public_url(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # فقط التطبيقات التي تعرض واجهة ويب لها رابط
    if server.get('status') == 'running' and server.get('is_web_app', False):
        port = server.get('port')
        return jsonify({
            'running': True,
            'url': f'http://{LOCAL_IP}:{port}',
            'ip': LOCAL_IP,
            'port': port,
            'is_web_app': True
        })
    return jsonify({
        'running': False, 
        'url': None,
        'is_web_app': server.get('is_web_app', False)
    })

@app.route('/api/server/<server_id>/start', methods=['POST'])
@login_required
def api_start_server(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    
    server_name = server.get('name')
    app_type = server.get('app_type', 'python')
    port = server.get('port')
    is_web_app = server.get('is_web_app', False)
    
    # إرسال رسالة بدء حقيقية (بدون رسائل وهمية)
    send_console(server_id, f"Starting {app_type} server on port {port}...")
    
    process = start_server_process(username, server_name, port, server_id, app_type,
                                   output_callback=lambda text, is_error=False: send_console(server_id, text, is_error))
    
    if process:
        active_processes[server_id] = process
        update_server_status(server_id, 'running')
        threading.Thread(target=monitor_process, args=(server_id, process, username, server_name), daemon=True).start()
        if is_web_app:
            public_url = f'http://{LOCAL_IP}:{port}'
            send_console(server_id, f"Server is accessible at: {public_url}")
        else:
            send_console(server_id, "Python script started (no web interface)")
        return jsonify({'success': True, 'status': 'running', 'is_web_app': is_web_app})
    
    send_console(server_id, "Failed to start server", True)
    return jsonify({'error': 'Failed to start server.'}), 500

@app.route('/api/server/<server_id>/stop', methods=['POST'])
@login_required
def api_stop_server(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    
    send_console(server_id, "Stopping server...")
    
    if server_id in active_processes:
        stop_server_process(server_id)
        del active_processes[server_id]
    
    update_server_status(server_id, 'stopped')
    send_console(server_id, "Server stopped")
    return jsonify({'success': True, 'status': 'stopped'})

@app.route('/api/server/<server_id>/restart', methods=['POST'])
@login_required
def api_restart_server(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    
    send_console(server_id, "Restarting server...")
    
    if server_id in active_processes:
        stop_server_process(server_id)
        del active_processes[server_id]
        time.sleep(1)
    
    server_name = server.get('name')
    app_type = server.get('app_type', 'python')
    port = server.get('port')
    is_web_app = server.get('is_web_app', False)
    
    process = start_server_process(username, server_name, port, server_id, app_type,
                                   output_callback=lambda text, is_error=False: send_console(server_id, text, is_error))
    
    if process:
        active_processes[server_id] = process
        update_server_status(server_id, 'running')
        threading.Thread(target=monitor_process, args=(server_id, process, username, server_name), daemon=True).start()
        if is_web_app:
            public_url = f'http://{LOCAL_IP}:{port}'
            send_console(server_id, f"Server restarted! Access at: {public_url}")
        else:
            send_console(server_id, "Python script restarted (no web interface)")
        return jsonify({'success': True, 'status': 'running', 'is_web_app': is_web_app})
    
    return jsonify({'error': 'Failed to restart server'}), 500

@app.route('/api/server/<server_id>/files', methods=['GET'])
@login_required
def api_list_files(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    return jsonify({'files': list_files(server_dir)})

@app.route('/api/server/<server_id>/file/create', methods=['POST'])
@login_required
def api_create_file(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    
    filename = sanitize_input(request.form.get('filename', ''))
    if not validate_filename(filename):
        return jsonify({'error': 'Invalid filename'}), 400
    
    content = request.form.get('content', '')
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    result, msg = create_file(server_dir, filename, content)
    if result:
        send_console(server_id, f"File created: {filename}")
        return jsonify({'success': True})
    return jsonify({'error': msg}), 500

@app.route('/api/server/<server_id>/file/read', methods=['GET'])
@login_required
def api_read_file(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    filename = request.args.get('filename', '')
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    return jsonify({'content': read_file(server_dir, filename)})

@app.route('/api/server/<server_id>/file/write', methods=['POST'])
@login_required
def api_write_file(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    filename = sanitize_input(request.form.get('filename', ''))
    content = request.form.get('content', '')
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    result, msg = write_file(server_dir, filename, content)
    if result:
        send_console(server_id, f"File saved: {filename}")
        return jsonify({'success': True})
    return jsonify({'error': msg}), 500

@app.route('/api/server/<server_id>/file/delete', methods=['POST'])
@login_required
def api_delete_file(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    filename = sanitize_input(request.form.get('filename', ''))
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    result, msg = delete_file(server_dir, filename)
    if result:
        send_console(server_id, f"File deleted: {filename}")
        return jsonify({'success': True})
    return jsonify({'error': msg}), 500

@app.route('/api/server/<server_id>/file/rename', methods=['POST'])
@login_required
def api_rename_file(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    old_name = sanitize_input(request.form.get('oldname', ''))
    new_name = sanitize_input(request.form.get('newname', ''))
    if not validate_filename(new_name):
        return jsonify({'error': 'Invalid filename'}), 400
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    result, msg = rename_file(server_dir, old_name, new_name)
    if result:
        send_console(server_id, f"File renamed: {old_name} -> {new_name}")
        return jsonify({'success': True})
    return jsonify({'error': msg}), 500

@app.route('/api/server/<server_id>/folder/create', methods=['POST'])
@login_required
def api_create_folder(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    foldername = sanitize_input(request.form.get('foldername', ''))
    if not validate_filename(foldername):
        return jsonify({'error': 'Invalid folder name'}), 400
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    result, msg = create_folder(server_dir, foldername)
    if result:
        send_console(server_id, f"Folder created: {foldername}")
        return jsonify({'success': True})
    return jsonify({'error': msg}), 500

@app.route('/api/server/<server_id>/folder/delete', methods=['POST'])
@login_required
def api_delete_folder(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    foldername = sanitize_input(request.form.get('foldername', ''))
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    result, msg = delete_folder(server_dir, foldername)
    if result:
        send_console(server_id, f"Folder deleted: {foldername}")
        return jsonify({'success': True})
    return jsonify({'error': msg}), 500

@app.route('/api/server/<server_id>/upload', methods=['POST'])
@login_required
def api_upload_file(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file or not file.filename or file.filename.strip() == '':
        return jsonify({'error': 'Empty filename'}), 400
    
    filename = secure_filename(file.filename)
    content = file.read()
    
    if len(content) == 0:
        return jsonify({'error': 'File is empty'}), 400
    
    # التحقق من امتداد الملف
    if filename.lower().endswith('.zip'):
        # معالجة ملف ZIP
        try:
            # حفظ الملف مؤقتًا
            temp_zip_path = os.path.join(server_dir, filename)
            with open(temp_zip_path, 'wb') as f:
                f.write(content)
            
            # فك ضغط الملف مع حماية من Zip Slip
            extracted_count = 0
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    # التحقق من المسار لمنع الهجمات
                    member_path = os.path.join(server_dir, member)
                    if not os.path.realpath(member_path).startswith(os.path.realpath(server_dir)):
                        send_console(server_id, f"ZIP extraction blocked: {member} (Zip Slip protection)", True)
                        zip_ref.close()
                        os.remove(temp_zip_path)
                        return jsonify({'error': 'Zip Slip attack detected'}), 400
                
                # فك الضغط
                zip_ref.extractall(server_dir)
                extracted_count = len(zip_ref.namelist())
            
            # حذف ملف ZIP بعد فك الضغط
            os.remove(temp_zip_path)
            
            send_console(server_id, f"ZIP extracted: {filename} ({extracted_count} files extracted)")
            return jsonify({
                'success': True, 
                'filename': filename, 
                'extracted': True,
                'files_count': extracted_count
            })
            
        except zipfile.BadZipFile:
            send_console(server_id, f"Invalid ZIP file: {filename}", True)
            return jsonify({'error': 'Invalid ZIP file'}), 400
        except Exception as e:
            send_console(server_id, f"Failed to extract ZIP: {str(e)}", True)
            return jsonify({'error': f'Failed to extract ZIP: {str(e)}'}), 500
    else:
        # رفع الملف كالمعتاد (غير ZIP)
        result, msg = upload_file(server_dir, filename, content)
        if result:
            send_console(server_id, f"Uploaded: {filename} ({len(content)} bytes)")
            return jsonify({'success': True, 'filename': filename})
        return jsonify({'error': str(msg)}), 500

@app.route('/api/server/<server_id>/upload-multiple', methods=['POST'])
@login_required
def api_upload_multiple_files(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files[]')
    
    if not files or len(files) == 0:
        return jsonify({'error': 'No files selected'}), 400
    
    success_count = 0
    failed_count = 0
    total_size = 0
    extracted_zips = 0
    
    send_console(server_id, f"Starting upload of {len(files)} file(s)...")
    
    for file in files:
        if not file or not file.filename or file.filename.strip() == '':
            failed_count += 1
            continue
        
        filename = secure_filename(file.filename)
        content = file.read()
        total_size += len(content)
        
        if len(content) == 0:
            failed_count += 1
            send_console(server_id, f"Skipped empty file: {filename}")
            continue
        
        # التحقق من امتداد الملف
        if filename.lower().endswith('.zip'):
            # معالجة ملف ZIP
            try:
                temp_zip_path = os.path.join(server_dir, filename)
                with open(temp_zip_path, 'wb') as f:
                    f.write(content)
                
                # فك ضغط الملف مع حماية من Zip Slip
                extracted_count = 0
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    for member in zip_ref.namelist():
                        member_path = os.path.join(server_dir, member)
                        if not os.path.realpath(member_path).startswith(os.path.realpath(server_dir)):
                            send_console(server_id, f"ZIP extraction blocked: {member} (Zip Slip protection)", True)
                            zip_ref.close()
                            os.remove(temp_zip_path)
                            failed_count += 1
                            continue
                    
                    zip_ref.extractall(server_dir)
                    extracted_count = len(zip_ref.namelist())
                
                os.remove(temp_zip_path)
                extracted_zips += 1
                success_count += 1
                send_console(server_id, f"ZIP extracted: {filename} ({extracted_count} files extracted)")
                
            except zipfile.BadZipFile:
                failed_count += 1
                send_console(server_id, f"Invalid ZIP file: {filename}", True)
            except Exception as e:
                failed_count += 1
                send_console(server_id, f"Failed to extract ZIP: {str(e)}", True)
        else:
            # رفع الملف كالمعتاد
            result, msg = upload_file(server_dir, filename, content)
            if result:
                success_count += 1
                send_console(server_id, f"Uploaded: {filename} ({len(content)} bytes)")
            else:
                failed_count += 1
                send_console(server_id, f"Failed: {filename}")
    
    total_mb = round(total_size / (1024 * 1024), 2)
    send_console(server_id, f"Upload complete: {success_count} succeeded, {failed_count} failed, {total_mb} MB total ({extracted_zips} ZIP files extracted)")
    
    return jsonify({
        'success': success_count > 0,
        'success_count': success_count,
        'failed_count': failed_count,
        'total_bytes': total_size,
        'total_mb': total_mb,
        'extracted_zips': extracted_zips
    })

@app.route('/api/server/<server_id>/download/<path:filename>')
@login_required
def api_download_file(server_id, filename):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    file_path = os.path.join(server_dir, filename)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path, as_attachment=True, download_name=filename)

@app.route('/api/server/<server_id>/download-folder')
@login_required
def api_download_folder(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    zip_buffer = zip_folder(server_dir)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name=f"{server.get('name')}_backup.zip")

@app.route('/api/server/<server_id>/backup', methods=['POST'])
@login_required
def api_backup_server(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    server_dir = os.path.join(SERVERS_DIR, username, server.get('name'))
    result, msg = backup_server(server_dir)
    if result:
        send_console(server_id, f"Backup created")
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': msg})

@app.route('/api/server/<server_id>/delete', methods=['POST'])
@login_required
def api_delete_server(server_id):
    username = session.get('user')
    server = get_server(server_id)
    if not server or server.get('owner') != username:
        return jsonify({'error': 'Unauthorized'}), 403
    if server_id in active_processes:
        stop_server_process(server_id)
        del active_processes[server_id]
    delete_server(server_id)
    return jsonify({'success': True})

@app.route('/api/admin/create_user', methods=['POST'])
@admin_required
def api_admin_create_user():
    username = sanitize_input(request.form.get('username', ''))
    password = request.form.get('password', '')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    if get_user(username):
        return jsonify({'error': 'User already exists'}), 409
    create_user(username, hash_password(password))
    return jsonify({'success': True})

@app.route('/api/admin/make_premium', methods=['POST'])
@admin_required
def api_admin_make_premium():
    username = sanitize_input(request.form.get('username', ''))
    if not get_user(username):
        return jsonify({'error': 'User not found'}), 404
    make_premium(username)
    return jsonify({'success': True})

@app.route('/api/admin/delete_user', methods=['POST'])
@admin_required
def api_admin_delete_user():
    username = sanitize_input(request.form.get('username', ''))
    delete_user(username)
    return jsonify({'success': True})

@socketio.on('connect')
def handle_connect():
    pass

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in active_websockets:
        del active_websockets[request.sid]

@socketio.on('join_server')
def handle_join_server(data):
    server_id = data.get('server_id')
    if server_id:
        join_room(server_id)
        active_websockets[request.sid] = server_id
        if server_id in server_output_buffers:
            for msg in server_output_buffers[server_id][-100:]:
                emit('console_output', {
                    'server_id': server_id, 
                    'output': msg['text'],
                    'is_error': msg.get('is_error', False)
                })

@socketio.on('console_input')
def handle_console_input(data):
    server_id = data.get('server_id')
    input_text = data.get('input', '')
    if server_id in active_processes:
        process = active_processes[server_id]
        try:
            if process.stdin and not process.stdin.closed:
                process.stdin.write(input_text + '\n')
                process.stdin.flush()
                # عرض المدخلات في الكونسول
                emit('console_output', {'server_id': server_id, 'output': input_text, 'is_error': False}, room=server_id)
        except:
            pass

def find_available_port(start_port=5001):
    port = start_port
    all_servers = get_all_servers()
    used_ports = {s.get('port') for s in all_servers}
    used_ports.add(5000)
    while port in used_ports:
        port += 1
        if port > 65535:
            return 5001
    return port

def monitor_process(server_id, process, username, server_name):
    """مراقبة العملية وإرسال المخرجات الحقيقية فقط"""
    
    while process and process.poll() is None:
        try:
            proc = psutil.Process(process.pid)
            cpu_percent = proc.cpu_percent(interval=0.5) / max(psutil.cpu_count(), 1)
            ram_mb = proc.memory_info().rss / (1024 * 1024)
            uptime_seconds = time.time() - proc.create_time()
            
            if uptime_seconds > 3600:
                h = int(uptime_seconds / 3600)
                m = int((uptime_seconds % 3600) / 60)
                uptime_str = f"{h}h {m}m"
            elif uptime_seconds > 60:
                m = int(uptime_seconds / 60)
                s = int(uptime_seconds % 60)
                uptime_str = f"{m}m {s}s"
            else:
                uptime_str = f"{int(uptime_seconds)}s"
            
            stats = {
                'cpu': round(min(cpu_percent, MAX_CPU_PERCENT), 1),
                'ram': round(min(ram_mb, MAX_RAM_MB), 1),
                'uptime': uptime_str,
                'status': 'running'
            }
            update_server_status(server_id, 'running', stats)
            socketio.emit('server_stats', {'server_id': server_id, 'stats': stats}, room=server_id)
            
            # التحقق من تجاوز الحدود
            if ram_mb > MAX_RAM_MB or cpu_percent > MAX_CPU_PERCENT:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    process.wait(timeout=5)
                except:
                    try:
                        process.kill()
                    except:
                        pass
                update_server_status(server_id, 'crashed')
                send_console(server_id, f"Process killed: Resource limit exceeded (CPU: {cpu_percent:.1f}%, RAM: {ram_mb:.1f}MB)", True)
                socketio.emit('server_stats', {'server_id': server_id, 'stats': {'status': 'crashed', 'cpu': 0, 'ram': 0, 'uptime': '0s'}}, room=server_id)
                active_processes.pop(server_id, None)
                return
            
            time.sleep(1)
                    
        except (psutil.NoSuchProcess, ProcessLookupError):
            break
        except Exception as e:
            time.sleep(0.5)
    
    update_server_status(server_id, 'stopped')
    send_console(server_id, "Process exited")
    socketio.emit('server_stats', {'server_id': server_id, 'stats': {'status': 'stopped', 'cpu': 0, 'ram': 0, 'uptime': '0s'}}, room=server_id)
    active_processes.pop(server_id, None)

if __name__ == '__main__':
    print("=" * 60)
    print("JAGWAR HOST - Enterprise Python Cloud Platform")
    print("=" * 60)
    print(f"Local IP: http://{LOCAL_IP}:10880")
    print(f"Admin Panel: http://{LOCAL_IP}:10880/admin")
    print(f"Admin Credentials: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print("=" * 60)
    print("Server is running in LEGENDARY MODE")
    print("=" * 60)
    socketio.run(app, host='0.0.0.0', port=10880, debug=False, allow_unsafe_werkzeug=True)