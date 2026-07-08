from flask import Flask, render_template_string, request, redirect, url_for, jsonify, session, flash, send_file, Response
import os
import zipfile
import shutil
import threading
import subprocess
import psutil
import json
from datetime import datetime, timedelta
import time
import uuid
import signal
import sys
import socket
import hashlib
import secrets
import re
from functools import wraps
import base64
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import urllib.request
import urllib.error

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-this-in-production'

# Configuration
UPLOAD_FOLDER = 'uploads'
SERVERS_FOLDER = 'servers'
LOGS_FOLDER = 'logs'
USERS_FILE = 'users.json'
VIP_PLANS_FILE = 'vip_plans.json'
PROFILE_PICS_FOLDER = 'profile_pics'

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SERVERS_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)
os.makedirs(PROFILE_PICS_FOLDER, exist_ok=True)

# Global dictionary to track server processes
server_processes = {}

def get_available_port(start_port=5000, max_attempts=100):
    """Find an available port starting from start_port"""
    port = start_port
    attempts = 0
    
    while attempts < max_attempts:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            port += 1
            attempts += 1
    
    return start_port

_PROXY_HOP_BY_HOP_HEADERS = {
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailers', 'transfer-encoding', 'upgrade',
    'content-encoding', 'content-length', 'host'
}

def _is_known_hosted_port(port):
    """Only allow proxying to ports that belong to a server created in this panel."""
    try:
        for server in server_manager.servers.values():
            if server.get('port') == port:
                return True
    except Exception:
        pass
    return False


def _build_target_url(port, subpath):
    """Build the internal URL on the local machine that the request should be forwarded to."""
    target = f"http://127.0.0.1:{port}/{subpath}" if subpath else f"http://127.0.0.1:{port}/"
    query_string = request.query_string.decode('utf-8') if request.query_string else ''
    if query_string:
        target = f"{target}?{query_string}"
    return target


def proxy_request(port, subpath=''):
    """
    Forward the current Flask request to a local hosted server running on `port`,
    then relay the response back to the original client. Supports all HTTP methods,
    request/response headers, and binary or text bodies (websockets are not supported).
    """
    if not isinstance(port, int) or port <= 0 or port > 65535:
        return jsonify({'error': 'Invalid proxy port'}), 400

    if not _is_known_hosted_port(port):
        return jsonify({'error': 'No active hosted server is bound to this port'}), 404

    target_url = _build_target_url(port, subpath)

    forwarded_headers = {}
    for header_name, header_value in request.headers.items():
        if header_name.lower() in _PROXY_HOP_BY_HOP_HEADERS:
            continue
        forwarded_headers[header_name] = header_value
    forwarded_headers['Host'] = f'127.0.0.1:{port}'
    forwarded_headers['X-Forwarded-Host'] = request.host
    forwarded_headers['X-Forwarded-Proto'] = request.scheme
    forwarded_headers['X-Forwarded-For'] = request.remote_addr or ''
    forwarded_headers['X-Forwarded-Prefix'] = f'/proxy/{port}'

    body = request.get_data() or None

    req = urllib.request.Request(
        target_url,
        data=body,
        headers=forwarded_headers,
        method=request.method
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as upstream_response:
            response_body = upstream_response.read()
            status_code = upstream_response.status
            response_headers = upstream_response.getheaders()
    except urllib.error.HTTPError as e:
        response_body = e.read()
        status_code = e.code
        response_headers = e.headers.items() if e.headers else []
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError):
        return jsonify({
            'error': 'The hosted server on this port is not reachable. '
                     'Make sure it is running and listening on 0.0.0.0/127.0.0.1.'
        }), 502

    flask_response = Response(response_body, status=status_code)
    for header_name, header_value in response_headers:
        if header_name.lower() in _PROXY_HOP_BY_HOP_HEADERS:
            continue
        flask_response.headers[header_name] = header_value

    return flask_response

def generate_default_avatar(username, size=100):
    """Generate a default avatar with user's initials"""
    img = Image.new('RGB', (size, size), color=get_random_color())
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", size//2)
    except:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size//2)
        except:
            font = ImageFont.load_default()
    
    initials = ''.join([name[0].upper() for name in username.split()[:2]]) or username[0].upper()
    
    bbox = draw.textbbox((0, 0), initials, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) // 2
    y = (size - text_height) // 2
    
    draw.text((x, y), initials, fill=(255, 255, 255), font=font)
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()

def get_random_color():
    """Generate a random color for avatar background"""
    colors = [
        (41, 128, 185), (39, 174, 96), (142, 68, 173), (230, 126, 34),
        (231, 76, 60), (52, 152, 219), (155, 89, 182), (26, 188, 156),
    ]
    return secrets.choice(colors)

class AutoInstaller:
    """Automatic dependency installer for Python projects"""
    
    @staticmethod
    def install_dependencies(server_path, log_file_path=None):
        """
        Automatically install dependencies from requirements.txt
        Returns: (success, message, log_content)
        """
        requirements_file = os.path.join(server_path, 'requirements.txt')
        
        if not os.path.exists(requirements_file):
            return True, "No requirements.txt found. Skipping dependency installation.", ""
        
        try:
            log_content = []
            log_content.append(f"📦 Installing dependencies from requirements.txt")
            log_content.append(f"📄 Requirements file: {requirements_file}")
            
            with open(requirements_file, 'r') as f:
                requirements = f.read().strip()
            
            if not requirements:
                log_content.append("ℹ️ requirements.txt is empty. Skipping.")
                return True, "No dependencies to install.", "\n".join(log_content)
            
            log_content.append(f"📋 Dependencies to install:\n{requirements}")
            
            # Get Python command
            python_cmd = 'python3' if sys.platform != 'win32' else 'python'
            
            # Install using pip
            install_cmd = f"{python_cmd} -m pip install -r requirements.txt"
            
            log_content.append(f"🚀 Running: {install_cmd}")
            
            process = subprocess.Popen(
                install_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=server_path,
                text=True
            )
            
            stdout, stderr = process.communicate(timeout=300)
            
            log_content.append("=" * 50)
            log_content.append("STDOUT:")
            log_content.append(stdout)
            log_content.append("=" * 50)
            log_content.append("STDERR:")
            log_content.append(stderr)
            log_content.append("=" * 50)
            
            if process.returncode == 0:
                log_content.append("✅ Dependencies installed successfully!")
                success = True
                message = "Dependencies installed successfully."
            else:
                log_content.append(f"❌ Failed to install dependencies. Return code: {process.returncode}")
                success = False
                message = f"Failed to install dependencies. Error: {stderr[:200]}"
            
            if log_file_path:
                with open(log_file_path, 'w', encoding='utf-8') as f:
                    f.write("\n".join(log_content))
            
            return success, message, "\n".join(log_content)
            
        except subprocess.TimeoutExpired:
            error_msg = "❌ Dependency installation timed out after 5 minutes."
            if log_file_path:
                with open(log_file_path, 'w', encoding='utf-8') as f:
                    f.write(error_msg)
            return False, "Installation timed out.", error_msg
            
        except Exception as e:
            error_msg = f"❌ Error installing dependencies: {str(e)}"
            if log_file_path:
                with open(log_file_path, 'w', encoding='utf-8') as f:
                    f.write(error_msg)
            return False, f"Error: {str(e)}", error_msg
    
    @staticmethod
    def check_and_install_packages(server_path, packages, log_file_path=None):
        """Install specific packages"""
        if not packages:
            return True, "No packages specified.", ""
        
        try:
            log_content = []
            log_content.append(f"📦 Installing specific packages: {', '.join(packages)}")
            
            python_cmd = 'python3' if sys.platform != 'win32' else 'python'
            
            for package in packages:
                log_content.append(f"\n📥 Installing: {package}")
                
                install_cmd = f"{python_cmd} -m pip install {package}"
                log_content.append(f"🚀 Running: {install_cmd}")
                
                process = subprocess.Popen(
                    install_cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=server_path,
                    text=True
                )
                
                stdout, stderr = process.communicate(timeout=120)
                
                if process.returncode == 0:
                    log_content.append(f"✅ Successfully installed {package}")
                else:
                    log_content.append(f"❌ Failed to install {package}")
                    log_content.append(f"Error: {stderr[:200]}")
            
            if log_file_path:
                with open(log_file_path, 'a', encoding='utf-8') as f:
                    f.write("\n".join(log_content))
            
            return True, "Package installation completed.", "\n".join(log_content)
            
        except Exception as e:
            error_msg = f"❌ Error: {str(e)}"
            if log_file_path:
                with open(log_file_path, 'a', encoding='utf-8') as f:
                    f.write(error_msg)
            return False, f"Error: {str(e)}", error_msg

class VIPManager:
    def __init__(self):
        self.vip_plans_file = VIP_PLANS_FILE
        self.load_vip_plans()
    
    def load_vip_plans(self):
        default_plans = {
            'free': {
                'name': 'Free',
                'max_servers': 1,
                'price': 0,
                'features': ['1 Server', 'Basic Support', '30 Days Expiry', 'File Editor', 'Terminal Access']
            },
            'basic': {
                'name': 'Basic VIP',
                'max_servers': 10,
                'price': 5.99,
                'duration_days': 30,
                'features': ['10 Servers', 'Priority Support', '30 Days VIP', 'Auto Install System', 'Faster Support']
            },
            'pro': {
                'name': 'Pro VIP',
                'max_servers': 25,
                'price': 12.99,
                'duration_days': 30,
                'features': ['25 Servers', '24/7 Support', 'Auto Install System', '30 Days VIP', 'Priority Processing']
            },
            'enterprise': {
                'name': 'Enterprise VIP',
                'max_servers': 100,
                'price': 29.99,
                'duration_days': 30,
                'features': ['100 Servers', '24/7 Priority Support', 'Auto Install System', 'Backup System', '30 Days VIP']
            }
        }
        
        if os.path.exists(self.vip_plans_file):
            with open(self.vip_plans_file, 'r') as f:
                self.plans = json.load(f)
        else:
            self.plans = default_plans
            self.save_vip_plans()
    
    def save_vip_plans(self):
        with open(self.vip_plans_file, 'w') as f:
            json.dump(self.plans, f, indent=4)
    
    def get_plan(self, plan_id):
        return self.plans.get(plan_id)
    
    def get_all_plans(self):
        return self.plans
    
    def update_plan(self, plan_id, plan_data):
        if plan_id in self.plans:
            self.plans[plan_id].update(plan_data)
            self.save_vip_plans()
            return True
        return False
    
    def activate_vip(self, user, plan_id):
        plan = self.get_plan(plan_id)
        if not plan:
            return False, "Invalid VIP plan"
        
        user['is_vip'] = True
        user['vip_plan'] = plan_id
        user['max_servers'] = plan['max_servers']
        
        if plan_id != 'free':
            user['vip_expiry'] = (datetime.now() + timedelta(days=plan['duration_days'])).isoformat()
        else:
            user['vip_expiry'] = (datetime.now() + timedelta(days=30)).isoformat()
        
        return True, f"VIP {plan['name']} activated successfully"

class UserManager:
    def __init__(self):
        self.users_file = USERS_FILE
        self.vip_manager = VIPManager()
        self.load_users()
    
    def load_users(self):
        if os.path.exists(self.users_file):
            with open(self.users_file, 'r') as f:
                self.users = json.load(f)
        else:
            self.users = {}
    
    def save_users(self):
        with open(self.users_file, 'w') as f:
            json.dump(self.users, f, indent=4)
    
    def hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(self, username, password, email=None):
        user_id = str(uuid.uuid4())
        
        for existing_user in self.users.values():
            if existing_user['username'].lower() == username.lower():
                return False, "Username already exists"
        
        free_plan = self.vip_manager.get_plan('free')
        
        avatar_data = generate_default_avatar(username)
        avatar_filename = f"{user_id}.png"
        avatar_path = os.path.join(PROFILE_PICS_FOLDER, avatar_filename)
        
        with open(avatar_path, 'wb') as f:
            f.write(avatar_data)
        
        self.users[user_id] = {
            'id': user_id,
            'username': username,
            'password': self.hash_password(password),
            'email': email,
            'is_vip': False,
            'vip_plan': 'free',
            'vip_expiry': (datetime.now() + timedelta(days=30)).isoformat(),
            'max_servers': free_plan['max_servers'],
            'created_at': datetime.now().isoformat(),
            'last_login': datetime.now().isoformat(),
            'balance': 0.0,
            'total_servers_created': 0,
            'profile_pic': avatar_filename,
            'theme': 'light',
            'language': 'en',
            'timezone': 'UTC',
            'custom_css': '',
            'is_admin': False
        }
        
        self.save_users()
        return True, user_id
    
    def verify_user(self, username, password):
        for user_id, user in self.users.items():
            if user['username'].lower() == username.lower():
                if user['password'] == self.hash_password(password):
                    user['last_login'] = datetime.now().isoformat()
                    self.save_users()
                    return True, user_id
        return False, None
    
    def get_user(self, user_id):
        return self.users.get(user_id)
    
    def update_user(self, user_id, updates):
        if user_id in self.users:
            self.users[user_id].update(updates)
            self.save_users()
            return True
        return False
    
    def is_vip_expired(self, user_id):
        user = self.get_user(user_id)
        if not user or not user.get('vip_expiry'):
            return True
        
        try:
            expiry_date = datetime.fromisoformat(user['vip_expiry'])
            return datetime.now() > expiry_date
        except:
            return True
    
    def check_and_downgrade(self, user_id):
        user = self.get_user(user_id)
        if not user:
            return
        
        if self.is_vip_expired(user_id) and user.get('vip_plan') != 'free':
            free_plan = self.vip_manager.get_plan('free')
            user['is_vip'] = False
            user['vip_plan'] = 'free'
            user['max_servers'] = free_plan['max_servers']
            user['vip_expiry'] = (datetime.now() + timedelta(days=30)).isoformat()
            self.save_users()
    
    def get_all_users(self):
        return self.users
    
    def set_vip_plan(self, user_id, plan_id):
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        return self.vip_manager.activate_vip(user, plan_id)

user_manager = UserManager()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = user_manager.get_user(session['user_id'])
        if not user or not user.get('is_admin', False):
            return "Admin access required", 403
        return f(*args, **kwargs)
    return decorated_function

class ServerManager:
    def __init__(self):
        self.servers_file = 'servers.json'
        self.load_servers()
    
    def load_servers(self):
        if os.path.exists(self.servers_file):
            with open(self.servers_file, 'r') as f:
                self.servers = json.load(f)
        else:
            self.servers = {}
    
    def save_servers(self):
        with open(self.servers_file, 'w') as f:
            json.dump(self.servers, f, indent=4)
    
    def get_user_servers(self, user_id):
        user_servers = {}
        for server_id, server in self.servers.items():
            if server.get('user_id') == user_id:
                user_servers[server_id] = server
        return user_servers
    
    def get_user_server_count(self, user_id):
        return len(self.get_user_servers(user_id))
    
    def can_create_server(self, user_id):
        user_manager.check_and_downgrade(user_id)
        user = user_manager.get_user(user_id)
        if not user:
            return False
        
        current_count = self.get_user_server_count(user_id)
        max_servers = user.get('max_servers', 4)
        
        return current_count < max_servers
    
    def create_server(self, name, expiry_date, zip_file, user_id):
        if not self.can_create_server(user_id):
            user = user_manager.get_user(user_id)
            max_servers = user.get('max_servers', 4) if user else 4
            return None, f"Server limit reached. You can only create {max_servers} servers."
        
        server_id = str(uuid.uuid4())
        server_path = os.path.join(SERVERS_FOLDER, server_id)
        log_path = os.path.join(LOGS_FOLDER, server_id)
        os.makedirs(server_path, exist_ok=True)
        os.makedirs(log_path, exist_ok=True)
        
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            zip_ref.extractall(server_path)
        
        # Auto-install dependencies from requirements.txt
        install_log_path = os.path.join(log_path, 'install.log')
        install_success, install_message, install_log = AutoInstaller.install_dependencies(
            server_path, 
            install_log_path
        )
        
        main_file = self.find_main_file(server_path)
        
        self.servers[server_id] = {
            'id': server_id,
            'name': name,
            'user_id': user_id,
            'expiry_date': expiry_date,
            'path': server_path,
            'log_path': log_path,
            'main_file': main_file,
            'status': 'stopped',
            'port': self.get_available_port(),
            'created_at': datetime.now().isoformat(),
            'install_success': install_success,
            'install_message': install_message,
            'install_log_path': install_log_path
        }
        
        user = user_manager.get_user(user_id)
        if user:
            user['total_servers_created'] = user.get('total_servers_created', 0) + 1
            user_manager.save_users()
        
        self.save_servers()
        return server_id, "Server created successfully"
    
    def find_main_file(self, server_path):
        possible_files = ['app.py', 'main.py', 'server.py', 'run.py', 'application.py', 'index.py', 'wsgi.py']
        
        for file in possible_files:
            if os.path.exists(os.path.join(server_path, file)):
                return file
        
        for root, dirs, files in os.walk(server_path):
            for file in files:
                if file.endswith('.py') and not file.startswith('.'):
                    return file
        
        return None
    
    def get_available_port(self):
        port = 50010
        while True:
            if not any(server.get('port') == port for server in self.servers.values()):
                return port
            port += 1
    
    def is_server_expired(self, server_id):
        if server_id not in self.servers:
            return True
        
        server = self.servers[server_id]
        try:
            expiry_date = datetime.fromisoformat(server['expiry_date'])
            return datetime.now() > expiry_date
        except:
            return True
    
    def get_python_command(self):
        if sys.platform.startswith('win'):
            return 'python'
        else:
            try:
                subprocess.check_call(['python3', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return 'python3'
            except:
                return 'python'
    
    def start_server(self, server_id):
        if server_id not in self.servers:
            return False, "Server not found"
        
        if self.is_server_expired(server_id):
            return False, "Server has expired. Please update the expiry date."
        
        server = self.servers[server_id]
        
        self.stop_server(server_id)
        
        server_path = server['path']
        main_file = server['main_file']
        
        if not main_file:
            return False, "No main Python file found in the server package."
        
        try:
            python_cmd = self.get_python_command()
            
            log_file = open(os.path.join(server['log_path'], 'server.log'), 'w')
            
            process = subprocess.Popen(
                [python_cmd, main_file],
                stdout=log_file,
                stderr=log_file,
                cwd=server_path,
                shell=False,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            server_processes[server_id] = {
                'process': process,
                'log_file': log_file
            }
            
            server['status'] = 'running'
            server['started_at'] = datetime.now().isoformat()
            self.save_servers()
            
            time.sleep(3)
            if process.poll() is not None:
                log_file.close()
                server['status'] = 'stopped'
                self.save_servers()
                
                with open(os.path.join(server['log_path'], 'server.log'), 'r') as f:
                    error_log = f.read()
                
                return False, f"Server failed to start. Check server logs for details."
            
            return True, "Server started successfully"
            
        except Exception as e:
            print(f"Error starting server: {e}")
            return False, f"Error starting server: {str(e)}"
    
    def stop_server(self, server_id):
        if server_id in server_processes:
            process_info = server_processes[server_id]
            process = process_info['process']
            log_file = process_info['log_file']
            
            try:
                if os.name == 'nt':
                    process.terminate()
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        process.kill()
                    else:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    process.wait()
            except Exception as e:
                print(f"Error stopping server: {e}")
            finally:
                if log_file:
                    log_file.close()
            
            del server_processes[server_id]
        
        if server_id in self.servers:
            self.servers[server_id]['status'] = 'stopped'
            if 'started_at' in self.servers[server_id]:
                del self.servers[server_id]['started_at']
            self.save_servers()
        
        return True
    
    def restart_server(self, server_id):
        self.stop_server(server_id)
        time.sleep(2)
        return self.start_server(server_id)
    
    def update_expiry_date(self, server_id, new_date):
        if server_id in self.servers:
            self.servers[server_id]['expiry_date'] = new_date
            self.save_servers()
            return True
        return False
    
    def delete_server(self, server_id):
        if server_id in self.servers:
            self.stop_server(server_id)
            
            server_path = self.servers[server_id]['path']
            log_path = self.servers[server_id]['log_path']
            
            if os.path.exists(server_path):
                shutil.rmtree(server_path)
            if os.path.exists(log_path):
                shutil.rmtree(log_path)
            
            del self.servers[server_id]
            self.save_servers()
            
            return True
        return False
    
    def get_server_logs(self, server_id, lines=50):
        if server_id not in self.servers:
            return "Server not found"
        
        log_file_path = os.path.join(self.servers[server_id]['log_path'], 'server.log')
        
        if not os.path.exists(log_file_path):
            return "No logs available"
        
        try:
            with open(log_file_path, 'r') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except Exception as e:
            return f"Error reading logs: {str(e)}"
    
    def get_install_logs(self, server_id):
        """Get dependency installation logs"""
        if server_id not in self.servers:
            return "Server not found"
        
        install_log_path = self.servers[server_id].get('install_log_path')
        if not install_log_path or not os.path.exists(install_log_path):
            return "No installation logs available"
        
        try:
            with open(install_log_path, 'r') as f:
                return f.read()
        except Exception as e:
            return f"Error reading installation logs: {str(e)}"
    
    def install_dependencies_now(self, server_id):
        """Manually install dependencies"""
        if server_id not in self.servers:
            return False, "Server not found", ""
        
        server_path = self.servers[server_id]['path']
        install_log_path = os.path.join(self.servers[server_id]['log_path'], 'install_manual.log')
        
        success, message, log_content = AutoInstaller.install_dependencies(
            server_path,
            install_log_path
        )
        
        self.servers[server_id]['install_success'] = success
        self.servers[server_id]['install_message'] = message
        self.servers[server_id]['install_log_path'] = install_log_path
        self.save_servers()
        
        return success, message, log_content
    
    def install_specific_package(self, server_id, package_name):
        """Install a specific package"""
        if server_id not in self.servers:
            return False, "Server not found", ""
        
        server_path = self.servers[server_id]['path']
        install_log_path = os.path.join(self.servers[server_id]['log_path'], 'install_manual.log')
        
        success, message, log_content = AutoInstaller.check_and_install_packages(
            server_path,
            [package_name],
            install_log_path
        )
        
        return success, message, log_content
    
    def get_server_files(self, server_id):
        if server_id not in self.servers:
            return []
        
        server_path = self.servers[server_id]['path']
        files = []
        
        for root, dirs, filenames in os.walk(server_path):
            dirs[:] = [d for d in dirs if d != '__pycache__' and not d.startswith('.')]
            for filename in filenames:
                if not filename.startswith('.'):
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, server_path)
                    files.append(relative_path)
        
        return files
    
    def get_file_content(self, server_id, file_path):
        if server_id not in self.servers:
            return None
        
        server_path = self.servers[server_id]['path']
        full_path = os.path.join(server_path, file_path)
        
        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                try:
                    with open(full_path, 'r', encoding='latin-1') as f:
                        return f.read()
                except:
                    return "Unable to read file content"
        
        return None
    
    def save_file_content(self, server_id, file_path, content):
        if server_id not in self.servers:
            return False
        
        server_path = self.servers[server_id]['path']
        full_path = os.path.join(server_path, file_path)
        
        if os.path.exists(full_path) and os.path.isfile(full_path):
            try:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                if self.servers[server_id]['status'] == 'running':
                    self.restart_server(server_id)
                
                return True
            except Exception as e:
                print(f"Error saving file: {e}")
                return False
        
        return False
    
    def execute_command(self, server_id, command):
        if server_id not in self.servers:
            return False, "Server not found"
        
        server_path = self.servers[server_id]['path']
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=server_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return True, {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, f"Error executing command: {str(e)}"

server_manager = ServerManager()

def check_expired_servers_and_vip():
    while True:
        try:
            for server_id, server in server_manager.servers.items():
                if server_manager.is_server_expired(server_id) and server['status'] == 'running':
                    print(f"Stopping expired server: {server['name']}")
                    server_manager.stop_server(server_id)
            
            for user_id, user in user_manager.users.items():
                user_manager.check_and_downgrade(user_id)
                
        except Exception as e:
            print(f"Error in expiry checker: {e}")
        
        time.sleep(30)

expiry_thread = threading.Thread(target=check_expired_servers_and_vip, daemon=True)
expiry_thread.start()


LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - AMINE HOSTING</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #212529;
            --border-color: #dee2e6;
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        [data-theme="dark"] {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --border-color: #343a40;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
        }
        .login-container {
            max-width: 400px;
            width: 100%;
            margin: 0 auto;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .btn-gradient {
            background: var(--primary-gradient);
            border: none;
            color: white;
        }
        .btn-gradient:hover {
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
            color: white;
        }
        .theme-toggle {
            background: none;
            border: none;
            color: var(--text-color);
            font-size: 1.2rem;
            cursor: pointer;
            position: absolute;
            top: 20px;
            right: 20px;
        }
    </style>
</head>
<body>
    <button class="theme-toggle" id="themeToggle">
        <i class="fas fa-moon"></i>
    </button>

    <div class="container">
        <div class="login-container">
            <div class="text-center mb-4">
                <h1 class="h3">
                    <i class="fas fa-server me-2"></i>
                    AMINE HOSTING 
                </h1>
                <p class="text-muted">Sign in to your account</p>
            </div>

            <div class="card">
                <div class="card-body p-4">
                    {% with messages = get_flashed_messages(with_categories=true) %}
                        {% if messages %}
                            {% for category, message in messages %}
                                <div class="alert alert-{{ 'danger' if category == 'error' else 'success' }} alert-dismissible fade show">
                                    {{ message }}
                                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                                </div>
                            {% endfor %}
                        {% endif %}
                    {% endwith %}

                    <form method="POST">
                        <div class="mb-3">
                            <label for="username" class="form-label">Username</label>
                            <input type="text" class="form-control" id="username" name="username" required 
                                   placeholder="Enter your username">
                        </div>
                        
                        <div class="mb-3">
                            <label for="password" class="form-label">Password</label>
                            <input type="password" class="form-control" id="password" name="password" required 
                                   placeholder="Enter your password">
                        </div>
                        
                        <div class="d-grid gap-2">
                            <button type="submit" class="btn btn-gradient btn-lg">
                                <i class="fas fa-sign-in-alt me-2"></i>Sign In
                            </button>
                        </div>
                    </form>

                    <div class="text-center mt-3">
                        <p class="mb-0">
                            Don't have an account? 
                            <a href="{{ url_for('register') }}" class="text-decoration-none">Create one</a>
                        </p>
                    </div>
                </div>
            </div>

            <div class="text-center mt-3">
                <small class="text-muted">
                    <i class="fas fa-info-circle me-1"></i>
                    Free users get 1 server
                </small>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        const themeToggle = document.getElementById('themeToggle');
        const currentTheme = localStorage.getItem('theme') || 'light';
        
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateThemeIcon(currentTheme);

        themeToggle.addEventListener('click', () => {
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });

        function updateThemeIcon(theme) {
            const icon = themeToggle.querySelector('i');
            icon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }
    </script>
</body>
</html>
'''

REGISTER_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Register - AMINE HOSTING</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #212529;
            --border-color: #dee2e6;
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        [data-theme="dark"] {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --border-color: #343a40;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
        }
        .register-container {
            max-width: 500px;
            width: 100%;
            margin: 0 auto;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .btn-gradient {
            background: var(--primary-gradient);
            border: none;
            color: white;
        }
        .btn-gradient:hover {
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
            color: white;
        }
        .theme-toggle {
            background: none;
            border: none;
            color: var(--text-color);
            font-size: 1.2rem;
            cursor: pointer;
            position: absolute;
            top: 20px;
            right: 20px;
        }
    </style>
</head>
<body>
    <button class="theme-toggle" id="themeToggle">
        <i class="fas fa-moon"></i>
    </button>

    <div class="container">
        <div class="register-container">
            <div class="text-center mb-4">
                <h1 class="h3">
                    <i class="fas fa-user-plus me-2"></i>
                    Create Account
                </h1>
                <p class="text-muted">Join our AMINE HOSTING platform</p>
            </div>

            <div class="card">
                <div class="card-body p-4">
                    {% with messages = get_flashed_messages(with_categories=true) %}
                        {% if messages %}
                            {% for category, message in messages %}
                                <div class="alert alert-{{ 'danger' if category == 'error' else 'success' }} alert-dismissible fade show">
                                    {{ message }}
                                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                                </div>
                            {% endfor %}
                        {% endif %}
                    {% endwith %}

                    <form method="POST" id="registerForm">
                        <div class="mb-3">
                            <label for="username" class="form-label">Username</label>
                            <input type="text" class="form-control" id="username" name="username" required 
                                   placeholder="Choose a username" minlength="3" maxlength="20">
                            <div class="form-text">3-20 characters, letters and numbers only</div>
                        </div>
                        
                        <div class="mb-3">
                            <label for="password" class="form-label">Password</label>
                            <input type="password" class="form-control" id="password" name="password" required 
                                   placeholder="Create a strong password" minlength="6">
                            <div class="form-text">Minimum 6 characters</div>
                        </div>

                        <div class="mb-3">
                            <label for="confirm_password" class="form-label">Confirm Password</label>
                            <input type="password" class="form-control" id="confirm_password" name="confirm_password" required 
                                   placeholder="Confirm your password">
                        </div>
                        
                        <div class="mb-3">
                            <label for="email" class="form-label">Email (Optional)</label>
                            <input type="email" class="form-control" id="email" name="email" 
                                   placeholder="your@email.com">
                        </div>
                        
                        <div class="alert alert-info">
                            <h6><i class="fas fa-info-circle me-2"></i>Account Features:</h6>
                            <ul class="mb-0 small">
                                <li><strong>Free accounts get 1 server</strong></li>
                                <li>30 days server expiry</li>
                                <li>Full server management</li>
                                <li>File editor & terminal access</li>
                                <li>Auto dependency installer</li>
                                <li>VIP upgrades available</li>
                            </ul>
                        </div>
                        
                        <div class="d-grid gap-2">
                            <button type="submit" class="btn btn-gradient btn-lg" id="submitBtn">
                                <i class="fas fa-user-plus me-2"></i>Create Account
                            </button>
                            <a href="{{ url_for('login') }}" class="btn btn-outline-secondary">Back to Login</a>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        const themeToggle = document.getElementById('themeToggle');
        const currentTheme = localStorage.getItem('theme') || 'light';
        
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateThemeIcon(currentTheme);

        themeToggle.addEventListener('click', () => {
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });

        function updateThemeIcon(theme) {
            const icon = themeToggle.querySelector('i');
            icon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }

        document.getElementById('registerForm').addEventListener('submit', function(e) {
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirm_password').value;
            
            if (password !== confirmPassword) {
                e.preventDefault();
                alert('Passwords do not match');
                return;
            }
        });
    </script>
</body>
</html>
'''

INDEX_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AMINE HOSTING Control Panel</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #212529;
            --border-color: #dee2e6;
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --secondary-gradient: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            --success-gradient: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            --warning-gradient: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
            --danger-gradient: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        }

        [data-theme="dark"] {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --border-color: #343a40;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            transition: all 0.3s ease;
        }

        .navbar {
            background: var(--primary-gradient);
        }

        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease;
            margin-bottom: 20px;
        }

        .card:hover {
            transform: translateY(-5px);
        }

        .server-card {
            border-left: 5px solid #667eea;
        }

        .status-running {
            border-left-color: #28a745 !important;
        }

        .status-stopped {
            border-left-color: #dc3545 !important;
        }

        .status-expired {
            border-left-color: #ffc107 !important;
        }

        .stats-card {
            background: var(--primary-gradient);
            color: white;
        }

        .btn-gradient {
            background: var(--primary-gradient);
            border: none;
            color: white;
        }

        .btn-gradient:hover {
            background: var(--secondary-gradient);
            color: white;
        }

        .user-info {
            background: var(--primary-gradient);
            color: white;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }

        .theme-toggle {
            background: none;
            border: none;
            color: white;
            font-size: 1.2rem;
            cursor: pointer;
        }

        .terminal {
            background-color: #1e1e1e;
            color: #00ff00;
            font-family: 'Courier New', monospace;
            padding: 15px;
            border-radius: 5px;
            height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
        }

        .file-editor {
            height: 400px;
            border: 1px solid var(--border-color);
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            background-color: var(--card-bg);
            color: var(--text-color);
        }

        .progress {
            height: 10px;
            border-radius: 10px;
        }

        .file-list {
            max-height: 400px;
            overflow-y: auto;
        }

        .tab-content {
            border: 1px solid var(--border-color);
            border-top: none;
            border-radius: 0 0 5px 5px;
            padding: 15px;
            background-color: var(--card-bg);
        }

        .nav-tabs .nav-link {
            color: var(--text-color);
        }

        .nav-tabs .nav-link.active {
            background-color: var(--card-bg);
            border-color: var(--border-color) var(--border-color) var(--card-bg);
        }

        .search-replace-panel {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 15px;
        }

        .command-input {
            background-color: #1e1e1e;
            color: #00ff00;
            border: 1px solid #343a40;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
        }

        .three-dots {
            cursor: pointer;
            padding: 5px 10px;
            border-radius: 5px;
            transition: background-color 0.2s;
        }

        .three-dots:hover {
            background-color: var(--border-color);
        }
        .user-avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            object-fit: cover;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-server me-2"></i>
                AMINE HOSTING
            </a>
            <div class="navbar-nav ms-auto">
                <button class="theme-toggle nav-link" id="themeToggle">
                    <i class="fas fa-moon"></i>
                </button>
                <div class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
                        <img src="/profile_pic/{{ user.id }}" class="user-avatar me-1" alt="{{ user.username }}">
                        {{ user.username }}
                    </a>
                    <ul class="dropdown-menu">
                        <li><span class="dropdown-item-text small">
                            <i class="fas fa-server me-2"></i>{{ user_servers_count }}/{{ user.max_servers }} servers<br>
                            <i class="fas fa-crown me-2"></i>{{ user.vip_plan|title }} Plan
                            {% if user.is_vip %}
                            <span class="badge bg-warning ms-1">VIP</span>
                            {% endif %}
                        </span></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item" href="/profile"><i class="fas fa-user me-2"></i>Profile Settings</a></li>
                        <li><a class="dropdown-item" href="/vip"><i class="fas fa-crown me-2"></i>VIP Plans</a></li>
                        {% if user.is_admin %}
                        <li><a class="dropdown-item" href="/admin"><i class="fas fa-shield-alt me-2"></i>Admin Panel</a></li>
                        {% endif %}
                        <li><a class="dropdown-item" href="/logout"><i class="fas fa-sign-out-alt me-2"></i>Logout</a></li>
                    </ul>
                </div>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <!-- User Info Card - تم إصلاح مشكلة created_at -->
        <div class="user-info">
            <div class="row">
                <div class="col-md-6">
                    <h5 class="mb-1"><i class="fas fa-user me-2"></i>{{ user.username }}</h5>
                    <small>
                        <i class="fas fa-calendar me-1"></i>
                        Joined: {% if user.created_at %}{{ user.created_at[:10] }}{% else %}N/A{% endif %}
                        {% if user.email %}
                        <br><i class="fas fa-envelope me-1"></i>{{ user.email }}
                        {% endif %}
                    </small>
                </div>
                <div class="col-md-6 text-end">
                    <h5 class="mb-1">{{ user_servers_count }}/{{ user.max_servers }} Servers</h5>
                    <small>
                        {% if user.is_vip %}
                        <span class="badge bg-warning"><i class="fas fa-crown me-1"></i>{{ user.vip_plan|title }} VIP</span>
                        {% else %}
                        <span class="badge bg-secondary"><i class="fas fa-user me-1"></i>Free</span>
                        {% endif %}
                        <br>
                        <small>Total Created: {{ user.total_servers_created or 0 }}</small>
                    </small>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body text-center">
                        <i class="fas fa-microchip fa-2x mb-2"></i>
                        <h5 id="cpu-usage">0%</h5>
                        <p class="mb-0">CPU Usage</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body text-center">
                        <i class="fas fa-memory fa-2x mb-2"></i>
                        <h5 id="ram-usage">0%</h5>
                        <p class="mb-0">RAM Usage</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body text-center">
                        <i class="fas fa-play-circle fa-2x mb-2"></i>
                        <h5>{{ running_servers }}</h5>
                        <p class="mb-0">Running Servers</p>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card stats-card">
                    <div class="card-body text-center">
                        <i class="fas fa-stop-circle fa-2x mb-2"></i>
                        <h5>{{ total_servers }}</h5>
                        <p class="mb-0">Total Servers</p>
                    </div>
                </div>
            </div>
        </div>

        <div class="row mt-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h4 class="mb-0"><i class="fas fa-list me-2"></i>Your Servers</h4>
                        <div>
                            <a href="/vip" class="btn btn-warning me-2">
                                <i class="fas fa-crown me-1"></i>VIP Plans
                            </a>
                            <a href="/create" class="btn btn-gradient">
                                <i class="fas fa-plus me-1"></i>Create New Server
                            </a>
                        </div>
                    </div>
                    <div class="card-body">
                        {% if servers %}
                            <div class="row">
                                {% for server_id, server in servers.items() %}
                                    {% set is_expired = server_manager.is_server_expired(server_id) %}
                                    <div class="col-md-6 col-lg-4">
                                        <div class="card server-card 
                                            {% if server.status == 'running' %}status-running
                                            {% elif is_expired %}status-expired
                                            {% else %}status-stopped{% endif %}">
                                            <div class="card-body">
                                                <div class="d-flex justify-content-between align-items-start">
                                                    <h5 class="card-title">
                                                        <i class="fas fa-server me-2"></i>{{ server.name }}
                                                        {% if is_expired %}
                                                            <i class="fas fa-exclamation-triangle text-warning ms-1" title="Expired"></i>
                                                        {% endif %}
                                                    </h5>
                                                    <div class="dropdown">
                                                        <span class="three-dots" data-bs-toggle="dropdown">
                                                            <i class="fas fa-ellipsis-v"></i>
                                                        </span>
                                                        <ul class="dropdown-menu">
                                                            <li><a class="dropdown-item" href="/server/{{ server.id }}"><i class="fas fa-cog me-2"></i>Manage</a></li>
                                                            <li><a class="dropdown-item" href="/server/{{ server.id }}/dependencies"><i class="fas fa-boxes me-2"></i>Dependencies</a></li>
                                                            <li><a class="dropdown-item" href="#" onclick="showServerTerminal('{{ server.id }}')"><i class="fas fa-terminal me-2"></i>Terminal</a></li>
                                                            <li><a class="dropdown-item" href="#" onclick="showFileEditor('{{ server.id }}')"><i class="fas fa-code me-2"></i>File Editor</a></li>
                                                            <li><hr class="dropdown-divider"></li>
                                                            <li><a class="dropdown-item text-danger" href="#" onclick="deleteServer('{{ server.id }}')"><i class="fas fa-trash me-2"></i>Delete</a></li>
                                                        </ul>
                                                    </div>
                                                </div>
                                                <p class="card-text">
                                                    <small class="text-muted">
                                                        <i class="fas fa-calendar me-1"></i>
                                                        Expires: {{ server.expiry_date }}
                                                    </small>
                                                    <br>
                                                    <small class="text-muted">
                                                        <i class="fas fa-network-wired me-1"></i>
                                                        Port: {{ server.port }}
                                                    </small>
                                                    <br>
                                                    <span class="badge 
                                                        {% if server.status == 'running' %}bg-success
                                                        {% elif is_expired %}bg-warning
                                                        {% else %}bg-danger{% endif %}">
                                                        {% if server.status == 'running' %}Running
                                                        {% elif is_expired %}Expired
                                                        {% else %}Stopped{% endif %}
                                                    </span>
                                                </p>
                                                <div class="btn-group w-100">
                                                    <a href="/server/{{ server.id }}" class="btn btn-outline-primary btn-sm">
                                                        <i class="fas fa-cog"></i>
                                                    </a>
                                                    {% if server.status == 'running' %}
                                                        <button onclick="stopServer('{{ server.id }}')" class="btn btn-outline-danger btn-sm">
                                                            <i class="fas fa-stop"></i>
                                                        </button>
                                                        <button onclick="restartServer('{{ server.id }}')" class="btn btn-outline-warning btn-sm">
                                                            <i class="fas fa-redo"></i>
                                                        </button>
                                                    {% else %}
                                                        {% if is_expired %}
                                                            <button onclick="showExpiryModal('{{ server.id }}')" class="btn btn-outline-warning btn-sm">
                                                                <i class="fas fa-calendar-plus"></i>
                                                            </button>
                                                        {% else %}
                                                            <button onclick="startServer('{{ server.id }}')" class="btn btn-outline-success btn-sm">
                                                                <i class="fas fa-play"></i>
                                                            </button>
                                                        {% endif %}
                                                    {% endif %}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                {% endfor %}
                            </div>
                        {% else %}
                            <div class="text-center py-5">
                                <i class="fas fa-server fa-4x text-muted mb-3"></i>
                                <h4 class="text-muted">No servers yet</h4>
                                <p class="text-muted">Create your first server to get started</p>
                                <a href="/create" class="btn btn-gradient">
                                    <i class="fas fa-plus me-1"></i>Create Your First Server
                                </a>
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Expiry Modal -->
    <div class="modal fade" id="expiryModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Update Expiry Date</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <p>This server has expired. Please update the expiry date to start it.</p>
                    <div class="mb-3">
                        <label for="modal-expiry-date" class="form-label">New Expiry Date:</label>
                        <input type="date" id="modal-expiry-date" class="form-control">
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" onclick="updateExpiryFromModal()">Update & Start</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Server Terminal Modal -->
    <div class="modal fade" id="serverTerminalModal" tabindex="-1">
        <div class="modal-dialog modal-xl">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Server Terminal - <span id="terminal-server-name"></span></h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="terminal" id="terminal-output" style="height: 400px;"></div>
                    <div class="input-group mt-3">
                        <input type="text" class="form-control command-input" id="terminal-command" placeholder="Enter command...">
                        <button class="btn btn-gradient" onclick="executeTerminalCommand()">
                            <i class="fas fa-play"></i> Execute
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- File Editor Modal -->
    <div class="modal fade" id="fileEditorModal" tabindex="-1">
        <div class="modal-dialog modal-xl">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">File Editor - <span id="editor-server-name"></span></h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="row">
                        <div class="col-md-3">
                            <div class="card">
                                <div class="card-header">
                                    <h6 class="mb-0">Files</h6>
                                </div>
                                <div class="card-body file-list" id="modal-file-tree"></div>
                            </div>
                        </div>
                        <div class="col-md-9">
                            <div class="search-replace-panel" id="search-replace-panel" style="display: none;">
                                <div class="row">
                                    <div class="col-md-5">
                                        <label class="form-label">Search:</label>
                                        <input type="text" class="form-control" id="search-text">
                                    </div>
                                    <div class="col-md-5">
                                        <label class="form-label">Replace with:</label>
                                        <input type="text" class="form-control" id="replace-text">
                                    </div>
                                    <div class="col-md-2 d-flex align-items-end">
                                        <div class="btn-group w-100">
                                            <button class="btn btn-sm btn-primary" onclick="replaceAll()">Replace All</button>
                                            <button class="btn btn-sm btn-success" onclick="replaceAndFind()">Replace & Find</button>
                                            <button class="btn btn-sm btn-secondary" onclick="findNext()">Find Next</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="mb-3">
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <label class="form-label mb-0">File: <span id="modal-current-file">None</span></label>
                                    <div class="btn-group">
                                        <button class="btn btn-sm btn-outline-primary" onclick="toggleSearchPanel()">
                                            <i class="fas fa-search me-1"></i>Search & Replace
                                        </button>
                                        <button class="btn btn-sm btn-outline-success" onclick="saveModalFile()">
                                            <i class="fas fa-save me-1"></i>Save
                                        </button>
                                    </div>
                                </div>
                                <textarea id="modal-file-content" class="form-control file-editor" placeholder="Select a file to edit"></textarea>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let currentServerId = null;
        let currentTerminalServerId = null;
        let currentEditorServerId = null;
        let currentSearchIndex = -1;

        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        const currentTheme = localStorage.getItem('theme') || 'light';
        
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateThemeIcon(currentTheme);

        themeToggle.addEventListener('click', () => {
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });

        function updateThemeIcon(theme) {
            const icon = themeToggle.querySelector('i');
            icon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }

        function startServer(serverId) {
            fetch(`/server/${serverId}/start`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert('Failed to start server: ' + data.message);
                    }
                });
        }

        function stopServer(serverId) {
            fetch(`/server/${serverId}/stop`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    }
                });
        }

        function restartServer(serverId) {
            fetch(`/server/${serverId}/restart`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert('Failed to restart server: ' + data.message);
                    }
                });
        }

        function deleteServer(serverId) {
            if (confirm('Are you sure you want to delete this server? This action cannot be undone.')) {
                fetch(`/server/${serverId}/delete`, { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            location.reload();
                        }
                    });
            }
        }

        function showExpiryModal(serverId) {
            currentServerId = serverId;
            // Set default date to tomorrow
            const tomorrow = new Date();
            tomorrow.setDate(tomorrow.getDate() + 1);
            document.getElementById('modal-expiry-date').value = tomorrow.toISOString().split('T')[0];
            
            const modal = new bootstrap.Modal(document.getElementById('expiryModal'));
            modal.show();
        }

        function updateExpiryFromModal() {
            if (!currentServerId) return;
            
            const newDate = document.getElementById('modal-expiry-date').value;
            const formData = new FormData();
            formData.append('new_date', newDate);

            fetch(`/server/${currentServerId}/update_expiry`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Close modal and start server
                    const modal = bootstrap.Modal.getInstance(document.getElementById('expiryModal'));
                    modal.hide();
                    startServer(currentServerId);
                } else {
                    alert('Failed to update expiry date');
                }
            });
        }

        function showServerTerminal(serverId) {
            currentTerminalServerId = serverId;
            const serverName = document.querySelector(`[href="/server/${serverId}"]`).closest('.card').querySelector('.card-title').textContent.trim();
            document.getElementById('terminal-server-name').textContent = serverName;
            
            loadTerminalLogs();
            const modal = new bootstrap.Modal(document.getElementById('serverTerminalModal'));
            modal.show();
        }

        function showFileEditor(serverId) {
            currentEditorServerId = serverId;
            const serverName = document.querySelector(`[href="/server/${serverId}"]`).closest('.card').querySelector('.card-title').textContent.trim();
            document.getElementById('editor-server-name').textContent = serverName;
            
            loadModalFiles();
            const modal = new bootstrap.Modal(document.getElementById('fileEditorModal'));
            modal.show();
        }

        function loadTerminalLogs() {
            if (!currentTerminalServerId) return;
            
            fetch(`/server/${currentTerminalServerId}/logs`)
                .then(response => response.json())
                .then(data => {
                    const terminal = document.getElementById('terminal-output');
                    if (data.logs) {
                        terminal.textContent = data.logs;
                        terminal.scrollTop = terminal.scrollHeight;
                    } else {
                        terminal.textContent = 'No logs available';
                    }
                });
        }

        function executeTerminalCommand() {
            if (!currentTerminalServerId) return;
            
            const command = document.getElementById('terminal-command').value;
            if (!command.trim()) return;

            fetch(`/server/${currentTerminalServerId}/execute`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ command: command })
            })
            .then(response => response.json())
            .then(data => {
                const terminal = document.getElementById('terminal-output');
                terminal.textContent += `\\n$ ${command}\\n`;
                if (data.success) {
                    terminal.textContent += data.result.stdout || '';
                    if (data.result.stderr) {
                        terminal.textContent += `\\nError: ${data.result.stderr}`;
                    }
                } else {
                    terminal.textContent += `Error: ${data.message}`;
                }
                terminal.scrollTop = terminal.scrollHeight;
                document.getElementById('terminal-command').value = '';
            });
        }

        function loadModalFiles() {
            if (!currentEditorServerId) return;
            
            fetch(`/server/${currentEditorServerId}/files`)
                .then(response => response.json())
                .then(data => {
                    const fileTree = document.getElementById('modal-file-tree');
                    fileTree.innerHTML = '';
                    
                    if (data.files && data.files.length > 0) {
                        data.files.forEach(file => {
                            const fileElement = document.createElement('div');
                            fileElement.className = 'file-item mb-1';
                            const escapedFile = file.replace(/'/g, "\\\\'");
                            fileElement.innerHTML = `
                                <button class="btn btn-sm btn-outline-primary w-100 text-start" onclick="loadModalFile('${escapedFile}')">
                                    <i class="fas fa-file me-1"></i>${file}
                                </button>
                            `;
                            fileTree.appendChild(fileElement);
                        });
                    } else {
                        fileTree.innerHTML = '<p class="text-muted">No files found</p>';
                    }
                });
        }

        function loadModalFile(filePath) {
            if (!currentEditorServerId) return;
            
            fetch(`/server/${currentEditorServerId}/file/${encodeURIComponent(filePath)}`)
                .then(response => response.json())
                .then(data => {
                    document.getElementById('modal-current-file').textContent = filePath;
                    if (data.content) {
                        document.getElementById('modal-file-content').value = data.content;
                    } else {
                        document.getElementById('modal-file-content').value = 'Error loading file content';
                    }
                    currentSearchIndex = -1;
                });
        }

        function saveModalFile() {
            if (!currentEditorServerId) return;
            
            const filePath = document.getElementById('modal-current-file').textContent;
            if (filePath === 'None') return;
            
            const content = document.getElementById('modal-file-content').value;
            const formData = new FormData();
            formData.append('content', content);

            fetch(`/server/${currentEditorServerId}/file/${encodeURIComponent(filePath)}`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showNotification('File saved successfully!', 'success');
                } else {
                    showNotification('Failed to save file', 'error');
                }
            });
        }

        function toggleSearchPanel() {
            const panel = document.getElementById('search-replace-panel');
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        }

        function findNext() {
            const searchText = document.getElementById('search-text').value;
            if (!searchText) return;
            
            const content = document.getElementById('modal-file-content');
            const text = content.value;
            const index = text.toLowerCase().indexOf(searchText.toLowerCase(), currentSearchIndex + 1);
            
            if (index !== -1) {
                content.focus();
                content.setSelectionRange(index, index + searchText.length);
                currentSearchIndex = index;
            } else {
                showNotification('No more matches found', 'warning');
                currentSearchIndex = -1;
            }
        }

        function replaceAll() {
            const searchText = document.getElementById('search-text').value;
            const replaceText = document.getElementById('replace-text').value;
            if (!searchText) return;
            
            const content = document.getElementById('modal-file-content');
            const newContent = content.value.replace(new RegExp(searchText, 'gi'), replaceText);
            content.value = newContent;
            showNotification('All occurrences replaced', 'success');
        }

        function replaceAndFind() {
            const searchText = document.getElementById('search-text').value;
            const replaceText = document.getElementById('replace-text').value;
            if (!searchText) return;
            
            const content = document.getElementById('modal-file-content');
            const text = content.value;
            
            if (currentSearchIndex !== -1) {
                const before = text.substring(0, currentSearchIndex);
                const after = text.substring(currentSearchIndex + searchText.length);
                content.value = before + replaceText + after;
                content.setSelectionRange(currentSearchIndex, currentSearchIndex + replaceText.length);
            }
            
            findNext();
        }

        function showNotification(message, type) {
            // Create notification element
            const notification = document.createElement('div');
            notification.className = `alert alert-${type === 'success' ? 'success' : type === 'error' ? 'danger' : 'warning'} alert-dismissible fade show`;
            notification.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            
            // Add to page
            document.body.appendChild(notification);
            
            // Auto remove after 3 seconds
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 3000);
        }

        // Update system stats
        function updateStats() {
            fetch('/system_stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('cpu-usage').textContent = data.cpu_percent + '%';
                    document.getElementById('ram-usage').textContent = data.ram_usage + '%';
                });
        }

        // Update stats every 5 seconds
        setInterval(updateStats, 5000);
        updateStats();

        // Terminal command input handler
        document.getElementById('terminal-command').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                executeTerminalCommand();
            }
        });
    </script>
</body>
</html>
'''

CREATE_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create Server - AMINE HOSTING</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #212529;
            --border-color: #dee2e6;
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        [data-theme="dark"] {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --border-color: #343a40;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: var(--primary-gradient);
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .btn-gradient {
            background: var(--primary-gradient);
            border: none;
            color: white;
        }
        .btn-gradient:hover {
            background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
            color: white;
        }
        .theme-toggle {
            background: none;
            border: none;
            color: white;
            font-size: 1.2rem;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-server me-2"></i>
                AMINE HOSTING
            </a>
            <div class="navbar-nav ms-auto">
                <button class="theme-toggle nav-link" id="themeToggle">
                    <i class="fas fa-moon"></i>
                </button>
                <a class="nav-link" href="/">
                    <i class="fas fa-arrow-left me-1"></i>Back to Dashboard
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row justify-content-center">
            <div class="col-md-8">
                <div class="card">
                    <div class="card-header">
                        <h4 class="mb-0"><i class="fas fa-plus-circle me-2"></i>Create New Server</h4>
                    </div>
                    <div class="card-body">
                        <form method="POST" enctype="multipart/form-data">
                            <div class="mb-3">
                                <label for="name" class="form-label">Server Name</label>
                                <input type="text" class="form-control" id="name" name="name" required 
                                       placeholder="Enter a unique name for your server">
                            </div>
                            
                            <div class="mb-3">
                                <label for="expiry_date" class="form-label">Expiry Date</label>
                                <input type="date" class="form-control" id="expiry_date" name="expiry_date" 
                                       value="{{ default_expiry }}" required>
                                <div class="form-text">
                                    The server will automatically stop when this date is reached.
                                </div>
                            </div>
                            
                            <div class="mb-3">
                                <label for="zip_file" class="form-label">ZIP File</label>
                                <input type="file" class="form-control" id="zip_file" name="zip_file" 
                                       accept=".zip" required>
                                <div class="form-text">
                                    Upload a ZIP file containing your Python application. The main file should be named 
                                    app.py, main.py, server.py, or similar.
                                    <br><strong>Auto-install:</strong> If you include a requirements.txt file, 
                                    dependencies will be automatically installed.
                                </div>
                            </div>
                            
                            <div class="alert alert-info">
                                <h6><i class="fas fa-info-circle me-2"></i>Requirements:</h6>
                                <ul class="mb-0">
                                    <li>ZIP file must contain your Python application</li>
                                    <li>Main file should be named app.py, main.py, etc.</li>
                                    <li>Include requirements.txt for auto dependency installation</li>
                                    <li>Application should run on the specified port</li>
                                    <li>Server will automatically stop when expired</li>
                                </ul>
                            </div>
                            
                            <div class="d-grid gap-2">
                                <button type="submit" class="btn btn-gradient btn-lg">
                                    <i class="fas fa-plus me-2"></i>Create Server
                                </button>
                                <a href="/" class="btn btn-outline-secondary">Cancel</a>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        const currentTheme = localStorage.getItem('theme') || 'light';
        
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateThemeIcon(currentTheme);

        themeToggle.addEventListener('click', () => {
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });

        function updateThemeIcon(theme) {
            const icon = themeToggle.querySelector('i');
            icon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }
    </script>
</body>
</html>
'''

SERVER_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ server.name }} - AMINE HOSTING</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #212529;
            --border-color: #dee2e6;
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            --secondary-gradient: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            --success-gradient: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            --warning-gradient: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);
            --danger-gradient: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
        }

        [data-theme="dark"] {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --border-color: #343a40;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            transition: all 0.3s ease;
        }
        .navbar {
            background: var(--primary-gradient);
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
        }
        .btn-gradient {
            background: var(--primary-gradient);
            border: none;
            color: white;
        }
        .btn-gradient:hover {
            background: var(--secondary-gradient);
            color: white;
        }
        .file-editor {
            height: 400px;
            border: 1px solid var(--border-color);
            border-radius: 5px;
            font-family: 'Courier New', monospace;
            background-color: var(--card-bg);
            color: var(--text-color);
        }
        .file-list {
            max-height: 400px;
            overflow-y: auto;
        }
        .progress {
            height: 10px;
            border-radius: 10px;
        }
        .file-item {
            margin-bottom: 5px;
        }
        .terminal {
            background-color: #1e1e1e;
            color: #00ff00;
            font-family: 'Courier New', monospace;
            padding: 15px;
            border-radius: 5px;
            height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
            font-size: 12px;
            line-height: 1.4;
        }
        .tab-content {
            border: 1px solid var(--border-color);
            border-top: none;
            border-radius: 0 0 5px 5px;
            padding: 15px;
            background-color: var(--card-bg);
        }
        .nav-tabs .nav-link {
            color: var(--text-color);
        }
        .nav-tabs .nav-link.active {
            background-color: var(--card-bg);
            border-color: var(--border-color) var(--border-color) var(--card-bg);
        }
        .search-replace-panel {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .command-input {
            background-color: #1e1e1e;
            color: #00ff00;
            border: 1px solid #343a40;
            border-radius: 5px;
            font-family: 'Courier New', monospace;
        }
        .theme-toggle {
            background: none;
            border: none;
            color: white;
            font-size: 1.2rem;
            cursor: pointer;
        }
        .user-avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            object-fit: cover;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-server me-2"></i>
                AMINE HOSTING
            </a>
            <div class="navbar-nav ms-auto">
                <button class="theme-toggle nav-link" id="themeToggle">
                    <i class="fas fa-moon"></i>
                </button>
                <div class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
                        <img src="/profile_pic/{{ session.user_id }}" class="user-avatar me-1" alt="User">
                        {{ user.username if user else 'User' }}
                    </a>
                    <ul class="dropdown-menu">
                        <li><a class="dropdown-item" href="/profile"><i class="fas fa-user me-2"></i>Profile Settings</a></li>
                        <li><a class="dropdown-item" href="/vip"><i class="fas fa-crown me-2"></i>VIP Plans</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item" href="/logout"><i class="fas fa-sign-out-alt me-2"></i>Logout</a></li>
                    </ul>
                </div>
                <a class="nav-link" href="/">
                    <i class="fas fa-arrow-left me-1"></i>Back to Dashboard
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <div class="col-md-8">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h4 class="mb-0">
                            <i class="fas fa-server me-2"></i>{{ server.name }}
                            {% if is_expired %}
                                <span class="badge bg-warning ms-2">Expired</span>
                            {% endif %}
                        </h4>
                        <span class="badge 
                            {% if server.status == 'running' %}bg-success
                            {% elif is_expired %}bg-warning
                            {% else %}bg-danger{% endif %}">
                            {% if server.status == 'running' %}Running
                            {% elif is_expired %}Expired
                            {% else %}Stopped{% endif %}
                        </span>
                    </div>
                    <div class="card-body">
                        <div class="row mb-3">
                            <div class="col-md-6">
                                <strong><i class="fas fa-calendar me-2"></i>Expiry Date:</strong>
                                <span id="expiry-display">{{ server.expiry_date }}</span>
                                <button class="btn btn-sm btn-outline-primary ms-2" onclick="showExpiryEditor()">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <div id="expiry-editor" class="input-group mt-2" style="display: none;">
                                    <input type="date" id="new-expiry" class="form-control" value="{{ server.expiry_date }}">
                                    <button class="btn btn-success" onclick="updateExpiry()">
                                        <i class="fas fa-check"></i>
                                    </button>
                                    <button class="btn btn-secondary" onclick="hideExpiryEditor()">
                                        <i class="fas fa-times"></i>
                                    </button>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <strong><i class="fas fa-network-wired me-2"></i>Port:</strong> {{ server.port }}
                            </div>
                        </div>

                        <!-- Dependency Status -->
                        <div class="row mb-3">
                            <div class="col-md-12">
                                {% if server.install_success %}
                                    <div class="alert alert-success">
                                        <i class="fas fa-check-circle me-2"></i>
                                        <strong>Dependencies:</strong> {{ server.install_message }}
                                        <a href="/server/{{ server.id }}/dependencies" class="btn btn-sm btn-outline-success float-end">
                                            <i class="fas fa-boxes me-1"></i>Manage Dependencies
                                        </a>
                                    </div>
                                {% else %}
                                    <div class="alert alert-danger">
                                        <i class="fas fa-exclamation-circle me-2"></i>
                                        <strong>Dependencies Failed:</strong> {{ server.install_message }}
                                        <a href="/server/{{ server.id }}/dependencies" class="btn btn-sm btn-outline-danger float-end">
                                            <i class="fas fa-redo me-1"></i>Fix Dependencies
                                        </a>
                                    </div>
                                {% endif %}
                            </div>
                        </div>

                        <div class="btn-group w-100 mb-4">
                            {% if server.status == 'running' %}
                                <button onclick="stopServer()" class="btn btn-danger">
                                    <i class="fas fa-stop me-2"></i>Stop Server
                                </button>
                                <button onclick="restartServer()" class="btn btn-warning">
                                    <i class="fas fa-redo me-2"></i>Restart Server
                                </button>
                            {% else %}
                                {% if is_expired %}
                                    <button onclick="updateAndStart()" class="btn btn-warning">
                                        <i class="fas fa-calendar-plus me-2"></i>Update Expiry & Start
                                    </button>
                                {% else %}
                                    <button onclick="startServer()" class="btn btn-success">
                                        <i class="fas fa-play me-2"></i>Start Server
                                    </button>
                                {% endif %}
                            {% endif %}
                            <button onclick="deleteServer()" class="btn btn-outline-danger">
                                <i class="fas fa-trash me-2"></i>Delete Server
                            </button>
                        </div>

                        <div class="row">
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-header">
                                        <h6 class="mb-0"><i class="fas fa-tachometer-alt me-2"></i>CPU Usage</h6>
                                    </div>
                                    <div class="card-body">
                                        <h3 id="server-cpu">0%</h3>
                                        <div class="progress">
                                            <div id="server-cpu-bar" class="progress-bar" role="progressbar" style="width: 0%"></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-header">
                                        <h6 class="mb-0"><i class="fas fa-memory me-2"></i>RAM Usage</h6>
                                    </div>
                                    <div class="card-body">
                                        <h3 id="server-ram">0%</h3>
                                        <div class="progress">
                                            <div id="server-ram-bar" class="progress-bar" role="progressbar" style="width: 0%"></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Tabs for Terminal and File Editor -->
                <div class="card">
                    <div class="card-header">
                        <ul class="nav nav-tabs card-header-tabs" id="serverTabs" role="tablist">
                            <li class="nav-item" role="presentation">
                                <button class="nav-link active" id="terminal-tab" data-bs-toggle="tab" data-bs-target="#terminal" type="button" role="tab">
                                    <i class="fas fa-terminal me-2"></i>Terminal
                                </button>
                            </li>
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" id="logs-tab" data-bs-toggle="tab" data-bs-target="#logs" type="button" role="tab">
                                    <i class="fas fa-scroll me-2"></i>Logs
                                </button>
                            </li>
                            <li class="nav-item" role="presentation">
                                <button class="nav-link" id="files-tab" data-bs-toggle="tab" data-bs-target="#files" type="button" role="tab">
                                    <i class="fas fa-code me-2"></i>File Editor
                                </button>
                            </li>
                        </ul>
                    </div>
                    <div class="tab-content">
                        <div class="tab-pane fade show active" id="terminal" role="tabpanel">
                            <div class="terminal" id="terminal-output" style="height: 400px;">Loading terminal...</div>
                            <div class="input-group mt-3">
                                <input type="text" class="form-control command-input" id="terminal-command" placeholder="Enter command...">
                                <button class="btn btn-gradient" onclick="executeTerminalCommand()">
                                    <i class="fas fa-play"></i> Execute
                                </button>
                            </div>
                        </div>
                        <div class="tab-pane fade" id="logs" role="tabpanel">
                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <h6 class="mb-0">Server Logs</h6>
                                <button onclick="refreshLogs()" class="btn btn-sm btn-outline-primary">
                                    <i class="fas fa-sync-alt me-1"></i>Refresh
                                </button>
                            </div>
                            <div class="terminal" id="logs-output">
                                Loading logs...
                            </div>
                        </div>
                        <div class="tab-pane fade" id="files" role="tabpanel">
                            <div class="search-replace-panel" id="search-replace-panel" style="display: none;">
                                <div class="row">
                                    <div class="col-md-5">
                                        <label class="form-label">Search:</label>
                                        <input type="text" class="form-control" id="search-text">
                                    </div>
                                    <div class="col-md-5">
                                        <label class="form-label">Replace with:</label>
                                        <input type="text" class="form-control" id="replace-text">
                                    </div>
                                    <div class="col-md-2 d-flex align-items-end">
                                        <div class="btn-group w-100">
                                            <button class="btn btn-sm btn-primary" onclick="replaceAll()">Replace All</button>
                                            <button class="btn btn-sm btn-success" onclick="replaceAndFind()">Replace & Find</button>
                                            <button class="btn btn-sm btn-secondary" onclick="findNext()">Find Next</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="row">
                                <div class="col-md-4">
                                    <div class="file-list card">
                                        <div class="card-header">
                                            <h6 class="mb-0">Files</h6>
                                        </div>
                                        <div class="card-body">
                                            <div id="file-tree"></div>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-8">
                                    <div class="mb-3">
                                        <div class="d-flex justify-content-between align-items-center mb-2">
                                            <label class="form-label mb-0">Selected File: <span id="current-file">None</span></label>
                                            <div class="btn-group">
                                                <button class="btn btn-sm btn-outline-primary" onclick="toggleSearchPanel()">
                                                    <i class="fas fa-search me-1"></i>Search & Replace
                                                </button>
                                                <button class="btn btn-sm btn-outline-success" onclick="saveFile()" id="save-btn" disabled>
                                                    <i class="fas fa-save me-1"></i>Save Changes
                                                </button>
                                            </div>
                                        </div>
                                        <textarea id="file-content" class="form-control file-editor" placeholder="Select a file to edit"></textarea>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-md-4">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0"><i class="fas fa-info-circle me-2"></i>Server Information</h5>
                    </div>
                    <div class="card-body">
                        <p><strong>ID:</strong> {{ server.id }}</p>
                        <p><strong>Created:</strong> {{ server.created_at[:10] }}</p>
                        <p><strong>Main File:</strong> {{ server.main_file or 'Not found' }}</p>
                        <p><strong>Path:</strong> {{ server.path }}</p>
                        
                        {% if is_expired %}
                        <div class="alert alert-warning">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            This server has expired. Update the expiry date to start it.
                        </div>
                        {% elif server.status == 'running' %}
                        <div class="alert alert-success">
                            <i class="fas fa-check-circle me-2"></i>
                            Server is currently running and accessible.
                        </div>
                        {% else %}
                        <div class="alert alert-danger">
                            <i class="fas fa-stop-circle me-2"></i>
                            Server is stopped. Click start to run it.
                        </div>
                        {% endif %}
                        
                        <div class="d-grid gap-2 mt-3">
                            <a href="/server/{{ server.id }}/dependencies" class="btn btn-info">
                                <i class="fas fa-boxes me-2"></i>Manage Dependencies
                            </a>
                            <a href="/server/{{ server.id }}/install_logs" class="btn btn-outline-info" target="_blank">
                                <i class="fas fa-scroll me-2"></i>View Installation Logs
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        const serverId = '{{ server.id }}';
        let currentFile = null;
        let currentSearchIndex = -1;

        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        const currentTheme = localStorage.getItem('theme') || 'light';
        
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateThemeIcon(currentTheme);

        themeToggle.addEventListener('click', () => {
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });

        function updateThemeIcon(theme) {
            const icon = themeToggle.querySelector('i');
            icon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }

        function startServer() {
            fetch(`/server/${serverId}/start`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert('Failed to start server: ' + data.message);
                    }
                });
        }

        function stopServer() {
            fetch(`/server/${serverId}/stop`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    }
                });
        }

        function restartServer() {
            fetch(`/server/${serverId}/restart`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        location.reload();
                    } else {
                        alert('Failed to restart server: ' + data.message);
                    }
                });
        }

        function deleteServer() {
            if (confirm('Are you sure you want to delete this server? This action cannot be undone.')) {
                fetch(`/server/${serverId}/delete`, { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            window.location.href = '/';
                        }
                    });
            }
        }

        function updateAndStart() {
            // Set tomorrow as default
            const tomorrow = new Date();
            tomorrow.setDate(tomorrow.getDate() + 1);
            const newDate = tomorrow.toISOString().split('T')[0];
            
            const formData = new FormData();
            formData.append('new_date', newDate);

            fetch(`/server/${serverId}/update_expiry`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    startServer();
                } else {
                    alert('Failed to update expiry date');
                }
            });
        }

        function showExpiryEditor() {
            document.getElementById('expiry-display').style.display = 'none';
            document.getElementById('expiry-editor').style.display = 'flex';
        }

        function hideExpiryEditor() {
            document.getElementById('expiry-display').style.display = 'block';
            document.getElementById('expiry-editor').style.display = 'none';
        }

        function updateExpiry() {
            const newDate = document.getElementById('new-expiry').value;
            const formData = new FormData();
            formData.append('new_date', newDate);

            fetch(`/server/${serverId}/update_expiry`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('expiry-display').textContent = newDate;
                    hideExpiryEditor();
                    location.reload();
                } else {
                    alert('Failed to update expiry date');
                }
            });
        }

        // Terminal functions
        function executeTerminalCommand() {
            const command = document.getElementById('terminal-command').value;
            if (!command.trim()) return;

            fetch(`/server/${serverId}/execute`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ command: command })
            })
            .then(response => response.json())
            .then(data => {
                const terminal = document.getElementById('terminal-output');
                terminal.textContent += `\\n$ ${command}\\n`;
                if (data.success) {
                    terminal.textContent += data.result.stdout || '';
                    if (data.result.stderr) {
                        terminal.textContent += `\\nError: ${data.result.stderr}`;
                    }
                } else {
                    terminal.textContent += `Error: ${data.message}`;
                }
                terminal.scrollTop = terminal.scrollHeight;
                document.getElementById('terminal-command').value = '';
            });
        }

        // Load terminal logs
        function loadLogs() {
            fetch(`/server/${serverId}/logs`)
                .then(response => response.json())
                .then(data => {
                    const logsOutput = document.getElementById('logs-output');
                    if (data.logs) {
                        logsOutput.textContent = data.logs;
                        logsOutput.scrollTop = logsOutput.scrollHeight;
                    } else {
                        logsOutput.textContent = 'No logs available';
                    }
                })
                .catch(error => {
                    console.error('Error loading logs:', error);
                    document.getElementById('logs-output').textContent = 'Error loading logs';
                });
        }

        function refreshLogs() {
            loadLogs();
        }

        // Load files
        function loadFiles() {
            fetch(`/server/${serverId}/files`)
                .then(response => response.json())
                .then(data => {
                    const fileTree = document.getElementById('file-tree');
                    fileTree.innerHTML = '';
                    
                    if (data.files && data.files.length > 0) {
                        data.files.forEach(file => {
                            const fileElement = document.createElement('div');
                            fileElement.className = 'file-item mb-1';
                            // Escape file path for JavaScript
                            const escapedFile = file.replace(/'/g, "\\\\'");
                            fileElement.innerHTML = `
                                <button class="btn btn-sm btn-outline-primary w-100 text-start" onclick="loadFile('${escapedFile}')">
                                    <i class="fas fa-file me-1"></i>${file}
                                </button>
                            `;
                            fileTree.appendChild(fileElement);
                        });
                    } else {
                        fileTree.innerHTML = '<p class="text-muted">No files found</p>';
                    }
                })
                .catch(error => {
                    console.error('Error loading files:', error);
                    document.getElementById('file-tree').innerHTML = '<p class="text-danger">Error loading files</p>';
                });
        }

        function loadFile(filePath) {
            currentFile = filePath;
            document.getElementById('current-file').textContent = filePath;
            document.getElementById('save-btn').disabled = false;

            fetch(`/server/${serverId}/file/${encodeURIComponent(filePath)}`)
                .then(response => response.json())
                .then(data => {
                    if (data.content) {
                        document.getElementById('file-content').value = data.content;
                    } else {
                        document.getElementById('file-content').value = 'Error loading file content';
                    }
                    currentSearchIndex = -1;
                })
                .catch(error => {
                    console.error('Error loading file:', error);
                    document.getElementById('file-content').value = 'Error loading file';
                });
        }

        function saveFile() {
            if (!currentFile) return;

            const content = document.getElementById('file-content').value;
            const formData = new FormData();
            formData.append('content', content);

            fetch(`/server/${serverId}/file/${encodeURIComponent(currentFile)}`, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showNotification('File saved successfully!', 'success');
                } else {
                    showNotification('Failed to save file', 'error');
                }
            })
            .catch(error => {
                console.error('Error saving file:', error);
                showNotification('Error saving file', 'error');
            });
        }

        function toggleSearchPanel() {
            const panel = document.getElementById('search-replace-panel');
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        }

        function findNext() {
            const searchText = document.getElementById('search-text').value;
            if (!searchText) return;
            
            const content = document.getElementById('file-content');
            const text = content.value;
            const index = text.toLowerCase().indexOf(searchText.toLowerCase(), currentSearchIndex + 1);
            
            if (index !== -1) {
                content.focus();
                content.setSelectionRange(index, index + searchText.length);
                currentSearchIndex = index;
            } else {
                showNotification('No more matches found', 'warning');
                currentSearchIndex = -1;
            }
        }

        function replaceAll() {
            const searchText = document.getElementById('search-text').value;
            const replaceText = document.getElementById('replace-text').value;
            if (!searchText) return;
            
            const content = document.getElementById('file-content');
            const newContent = content.value.replace(new RegExp(searchText, 'gi'), replaceText);
            content.value = newContent;
            showNotification('All occurrences replaced', 'success');
        }

        function replaceAndFind() {
            const searchText = document.getElementById('search-text').value;
            const replaceText = document.getElementById('replace-text').value;
            if (!searchText) return;
            
            const content = document.getElementById('file-content');
            const text = content.value;
            
            if (currentSearchIndex !== -1) {
                const before = text.substring(0, currentSearchIndex);
                const after = text.substring(currentSearchIndex + searchText.length);
                content.value = before + replaceText + after;
                content.setSelectionRange(currentSearchIndex, currentSearchIndex + replaceText.length);
            }
            
            findNext();
        }

        function showNotification(message, type) {
            // Create notification element
            const notification = document.createElement('div');
            notification.className = `alert alert-${type === 'success' ? 'success' : type === 'error' ? 'danger' : 'warning'} alert-dismissible fade show`;
            notification.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            
            // Add to page
            document.body.appendChild(notification);
            
            // Auto remove after 3 seconds
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 3000);
        }

        // Update server stats
        function updateServerStats() {
            fetch('/system_stats')
                .then(response => response.json())
                .then(data => {
                    if (data.cpu_percent !== undefined) {
                        document.getElementById('server-cpu').textContent = data.cpu_percent + '%';
                        document.getElementById('server-ram').textContent = data.ram_usage + '%';
                        
                        document.getElementById('server-cpu-bar').style.width = data.cpu_percent + '%';
                        document.getElementById('server-ram-bar').style.width = data.ram_usage + '%';
                        
                        // Color coding
                        document.getElementById('server-cpu-bar').className = 
                            `progress-bar ${data.cpu_percent > 80 ? 'bg-danger' : data.cpu_percent > 60 ? 'bg-warning' : 'bg-success'}`;
                        document.getElementById('server-ram-bar').className = 
                            `progress-bar ${data.ram_usage > 80 ? 'bg-danger' : data.ram_usage > 60 ? 'bg-warning' : 'bg-success'}`;
                    }
                })
                .catch(error => {
                    console.error('Error updating stats:', error);
                });
        }

        // Initialize
        loadLogs();
        loadFiles();
        updateServerStats();
        setInterval(updateServerStats, 3000);
        
        // Auto-refresh logs every 5 seconds if server is running
        {% if server.status == 'running' %}
        setInterval(loadLogs, 5000);
        {% endif %}

        // Terminal command input handler
        document.getElementById('terminal-command').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                executeTerminalCommand();
            }
        });
    </script>
</body>
</html>
'''

VIP_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VIP Plans - AMINE HOSTING</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #212529;
            --border-color: #dee2e6;
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        [data-theme="dark"] {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --border-color: #343a40;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: var(--primary-gradient);
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease;
            margin-bottom: 20px;
        }
        .card:hover {
            transform: translateY(-5px);
        }
        .vip-card {
            border: 2px solid transparent;
        }
        .vip-card.basic {
            border-color: #17a2b8;
        }
        .vip-card.pro {
            border-color: #ffc107;
        }
        .vip-card.enterprise {
            border-color: #dc3545;
        }
        .btn-telegram {
            background: #0088cc;
            border: none;
            color: white;
            padding: 12px 20px;
            font-size: 16px;
            font-weight: 600;
        }
        .btn-telegram:hover {
            background: #0077b3;
            color: white;
            transform: translateY(-2px);
        }
        .theme-toggle {
            background: none;
            border: none;
            color: white;
            font-size: 1.2rem;
            cursor: pointer;
        }
        .price {
            font-size: 2.5rem;
            font-weight: bold;
        }
        .feature-list {
            list-style: none;
            padding: 0;
        }
        .feature-list li {
            padding: 8px 0;
            border-bottom: 1px solid var(--border-color);
        }
        .feature-list li:last-child {
            border-bottom: none;
        }
        .feature-list li i {
            width: 20px;
            margin-right: 10px;
        }
        .popular-badge {
            position: absolute;
            top: -10px;
            right: 20px;
            background: #ffc107;
            color: #000;
            padding: 5px 15px;
            border-radius: 15px;
            font-weight: bold;
            font-size: 0.8rem;
        }
        .telegram-button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .plan-header {
            background: var(--primary-gradient);
            color: white;
            padding: 15px;
            border-radius: 10px 10px 0 0;
            margin: -20px -20px 20px -20px;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-server me-2"></i>
                AMINE HOSTING
            </a>
            <div class="navbar-nav ms-auto">
                <button class="theme-toggle nav-link" id="themeToggle">
                    <i class="fas fa-moon"></i>
                </button>
                <a class="nav-link" href="/">
                    <i class="fas fa-arrow-left me-1"></i>Back to Dashboard
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <div class="col-12 text-center mb-4">
                <h1><i class="fas fa-crown me-2"></i>VIP Plans</h1>
                <p class="lead">Upgrade your account for more servers and premium features</p>
            </div>
        </div>

        <!-- Quick Payment Info -->
        <div class="row mb-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-body text-center">
                        <h4><i class="fab fa-telegram me-2 text-primary"></i>Instant VIP Activation</h4>
                        <p class="mb-0">Click "Buy Now" to open Telegram and complete your payment. VIP activated immediately after payment.</p>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            {% for plan_id, plan in vip_plans.items() %}
            <div class="col-md-6 col-lg-3 mb-4">
                <div class="card vip-card {{ plan_id }} position-relative h-100">
                    {% if plan_id == 'pro' %}
                    <div class="popular-badge">MOST POPULAR</div>
                    {% endif %}
                    
                    <div class="plan-header text-center">
                        <h4 class="mb-0">{{ plan.name }}</h4>
                    </div>
                    
                    <div class="card-body d-flex flex-column">
                        <div class="text-center mb-3">
                            <div class="price text-primary">
                                {% if plan.price == 0 %}
                                FREE
                                {% else %}
                                ${{ plan.price }}
                                {% endif %}
                            </div>
                            <p class="text-muted mb-0">
                                {% if plan_id != 'free' %}
                                per 30 days
                                {% else %}
                                forever
                                {% endif %}
                            </p>
                        </div>
                        
                        <ul class="feature-list flex-grow-1">
                            {% for feature in plan.features %}
                            <li><i class="fas fa-check text-success"></i> {{ feature }}</li>
                            {% endfor %}
                        </ul>
                        
                        <div class="mt-auto">
                            {% if user.vip_plan == plan_id %}
                            <button class="btn btn-outline-primary w-100" disabled>
                                <i class="fas fa-check me-2"></i>Current Plan
                            </button>
                            {% elif plan_id == 'free' %}
                            <button class="btn btn-outline-secondary w-100" onclick="activatePlan('free')">
                                <i class="fas fa-sync me-2"></i>Downgrade to Free
                            </button>
                            {% else %}
                            <button class="btn btn-telegram w-100 telegram-button" 
                                    onclick="buyWithTelegram('{{ plan_id }}', '{{ plan.name }}', {{ plan.price }})">
                                <i class="fab fa-telegram me-2"></i>
                                Buy Now - ${{ plan.price }}
                            </button>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>

        <!-- Payment Instructions -->
        <div class="row mt-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h4 class="mb-0"><i class="fas fa-info-circle me-2"></i>How to Buy VIP</h4>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-4">
                                <div class="text-center">
                                    <div class="bg-primary text-white rounded-circle d-inline-flex align-items-center justify-content-center mb-3" style="width: 60px; height: 60px;">
                                        <i class="fas fa-mouse-pointer fa-lg"></i>
                                    </div>
                                    <h5>1. Click Buy Now</h5>
                                    <p>Choose your plan and click the Buy Now button</p>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="text-center">
                                    <div class="bg-success text-white rounded-circle d-inline-flex align-items-center justify-content-center mb-3" style="width: 60px; height: 60px;">
                                        <i class="fab fa-telegram fa-lg"></i>
                                    </div>
                                    <h5>2. Open Telegram</h5>
                                    <p>Automatically opens Telegram with pre-filled message</p>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <div class="text-center">
                                    <div class="bg-warning text-white rounded-circle d-inline-flex align-items-center justify-content-center mb-3" style="width: 60px; height: 60px;">
                                        <i class="fas fa-bolt fa-lg"></i>
                                    </div>
                                    <h5>3. Instant Activation</h5>
                                    <p>Send payment and get VIP activated immediately</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Contact Info -->
        <div class="row mt-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-body text-center">
                        <h5><i class="fas fa-headset me-2"></i>Need Help?</h5>
                        <p>Contact us directly on Telegram for instant support</p>
                        <a href="https://t.me/MC_8G" class="btn btn-telegram" target="_blank">
                            <i class="fab fa-telegram me-2"></i>Message @MC_8G
                        </a>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        const currentTheme = localStorage.getItem('theme') || 'light';
        
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateThemeIcon(currentTheme);

        themeToggle.addEventListener('click', () => {
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });

        function updateThemeIcon(theme) {
            const icon = themeToggle.querySelector('i');
            icon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }

        function buyWithTelegram(planId, planName, price) {
            // Create a unique payment ID
            const paymentId = 'PY' + Date.now() + Math.random().toString(36).substr(2, 5);
            
            // Create pre-filled Telegram message
            const username = '{{ user.username }}';
            const message = `🚀 **VIP Plan Purchase Request**\\n\\n` +
                           `📦 Plan: ${planName}\\n` +
                           `💰 Price: $${price}\\n` +
                           `👤 Username: ${username}\\n` +
                           `🆔 Payment ID: ${paymentId}\\n\\n` +
                           `Please send payment details and transaction ID.`;
            
            // Encode message for URL
            const encodedMessage = encodeURIComponent(message);
            
            // Create Telegram URL
            const telegramUrl = `https://t.me/MC_8G?text=${encodedMessage}`;
            
            // Save payment info to local storage (for tracking)
            const paymentInfo = {
                planId: planId,
                planName: planName,
                price: price,
                paymentId: paymentId,
                timestamp: new Date().toISOString(),
                username: username
            };
            localStorage.setItem('lastPayment', JSON.stringify(paymentInfo));
            
            // Open Telegram in new tab
            window.open(telegramUrl, '_blank');
            
            // Show confirmation message
            alert(`🚀 Opening Telegram...\\n\\nPlease send this payment ID to @MC_8G:\\n${paymentId}\\n\\nWe'll activate your VIP immediately after payment!`);
        }

        function activatePlan(planId) {
            if (confirm('Are you sure you want to change to Free plan? You will lose VIP benefits.')) {
                fetch('/activate_vip', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ plan_id: planId })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Plan changed successfully!');
                        window.location.href = '/';
                    } else {
                        alert('Error: ' + data.message);
                    }
                })
                .catch(error => {
                    alert('Error changing plan');
                });
            }
        }

        // Check if user just returned from payment
        window.addEventListener('load', function() {
            const lastPayment = localStorage.getItem('lastPayment');
            if (lastPayment) {
                const payment = JSON.parse(lastPayment);
                const timeDiff = Date.now() - new Date(payment.timestamp).getTime();
                const minutesDiff = timeDiff / (1000 * 60);
                
                // If returned within 10 minutes, show message
                if (minutesDiff < 10) {
                    console.log('User returned from payment attempt:', payment);
                }
            }
        });
    </script>
</body>
</html>
'''

ADMIN_DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard - AMINE ADMIN PANEL</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #212529;
            --border-color: #dee2e6;
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        [data-theme="dark"] {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --border-color: #343a40;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: var(--primary-gradient);
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
        }
        .btn-gradient {
            background: var(--primary-gradient);
            border: none;
            color: white;
        }
        .theme-toggle {
            background: none;
            border: none;
            color: white;
            font-size: 1.2rem;
            cursor: pointer;
        }
        .user-avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            object-fit: cover;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-server me-2"></i>
                AMINE HOSTING - Admin
            </a>
            <div class="navbar-nav ms-auto">
                <button class="theme-toggle nav-link" id="themeToggle">
                    <i class="fas fa-moon"></i>
                </button>
                <a class="nav-link" href="/">
                    <i class="fas fa-arrow-left me-1"></i>User Dashboard
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h4 class="mb-0"><i class="fas fa-users me-2"></i>User Management</h4>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped">
                                <thead>
                                    <tr>
                                        <th>Avatar</th>
                                        <th>Username</th>
                                        <th>Email</th>
                                        <th>VIP Plan</th>
                                        <th>Servers</th>
                                        <th>Status</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for user_id, user in all_users.items() %}
                                    <tr>
                                        <td>
                                            <img src="/profile_pic/{{ user_id }}" class="user-avatar" alt="{{ user.username }}">
                                        </td>
                                        <td>{{ user.username }}{% if user.is_admin %} <span class="badge bg-danger">Admin</span>{% endif %}</td>
                                        <td>{{ user.email or 'N/A' }}</td>
                                        <td>
                                            <span class="badge {% if user.vip_plan == 'enterprise' %}bg-danger{% elif user.vip_plan == 'pro' %}bg-warning{% elif user.vip_plan == 'basic' %}bg-info{% else %}bg-secondary{% endif %}">
                                                {{ user.vip_plan|title }}
                                            </span>
                                        </td>
                                        <td>{{ server_counts[user_id] }}/{{ user.max_servers }}</td>
                                        <td>
                                            {% if user_manager.is_vip_expired(user_id) %}
                                                <span class="badge bg-warning">Expired</span>
                                            {% else %}
                                                <span class="badge bg-success">Active</span>
                                            {% endif %}
                                        </td>
                                        <td>
                                            <div class="btn-group">
                                                <button class="btn btn-sm btn-outline-primary" onclick="editUserVIP('{{ user_id }}')">
                                                    <i class="fas fa-crown"></i> VIP
                                                </button>
                                                {% if not user.is_admin %}
                                                <button class="btn btn-sm btn-outline-danger" onclick="deleteUser('{{ user_id }}')">
                                                    <i class="fas fa-trash"></i>
                                                </button>
                                                {% endif %}
                                            </div>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0"><i class="fas fa-crown me-2"></i>VIP Plan Management</h5>
                    </div>
                    <div class="card-body">
                        {% for plan_id, plan in vip_plans.items() %}
                        <div class="mb-3 p-3 border rounded">
                            <h6>{{ plan.name }}</h6>
                            <form onsubmit="updateVIPPlan('{{ plan_id }}'); return false;">
                                <div class="row">
                                    <div class="col-md-6">
                                        <label>Max Servers:</label>
                                        <input type="number" class="form-control mb-2" id="max_servers_{{ plan_id }}" value="{{ plan.max_servers }}">
                                    </div>
                                    <div class="col-md-6">
                                        <label>Price ($):</label>
                                        <input type="number" step="0.01" class="form-control mb-2" id="price_{{ plan_id }}" value="{{ plan.price }}">
                                    </div>
                                </div>
                                <button type="submit" class="btn btn-sm btn-success">Update</button>
                            </form>
                        </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0"><i class="fas fa-chart-bar me-2"></i>System Statistics</h5>
                    </div>
                    <div class="card-body">
                        <p><strong>Total Users:</strong> {{ total_users }}</p>
                        <p><strong>Total Servers:</strong> {{ total_servers }}</p>
                        <p><strong>Running Servers:</strong> {{ running_servers }}</p>
                        <p><strong>Free Users:</strong> {{ free_users }}</p>
                        <p><strong>VIP Users:</strong> {{ vip_users }}</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- VIP Edit Modal -->
    <div class="modal fade" id="vipModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">Edit User VIP Plan</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <p>User: <strong id="modal-username"></strong></p>
                    <div class="mb-3">
                        <label class="form-label">VIP Plan:</label>
                        <select class="form-select" id="vip-plan-select">
                            {% for plan_id, plan in vip_plans.items() %}
                            <option value="{{ plan_id }}">{{ plan.name }} ({{ plan.max_servers }} servers)</option>
                            {% endfor %}
                        </select>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                    <button type="button" class="btn btn-primary" onclick="saveVIPChanges()">Save Changes</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        let currentEditUserId = null;

        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        const currentTheme = localStorage.getItem('theme') || 'light';
        
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateThemeIcon(currentTheme);

        themeToggle.addEventListener('click', () => {
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });

        function updateThemeIcon(theme) {
            const icon = themeToggle.querySelector('i');
            icon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }

        function editUserVIP(userId) {
            currentEditUserId = userId;
            const userRow = document.querySelector(`[onclick="editUserVIP('${userId}')"]`).closest('tr');
            const username = userRow.querySelector('td:nth-child(2)').textContent.trim();
            
            document.getElementById('modal-username').textContent = username;
            
            const modal = new bootstrap.Modal(document.getElementById('vipModal'));
            modal.show();
        }

        function saveVIPChanges() {
            if (!currentEditUserId) return;
            
            const planId = document.getElementById('vip-plan-select').value;
            
            fetch('/admin/set_user_vip', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: currentEditUserId,
                    plan_id: planId
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('VIP plan updated successfully');
                    location.reload();
                } else {
                    alert('Error: ' + data.message);
                }
            });
        }

        function updateVIPPlan(planId) {
            const maxServers = document.getElementById(`max_servers_${planId}`).value;
            const price = document.getElementById(`price_${planId}`).value;
            
            fetch('/admin/update_vip_plan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    plan_id: planId,
                    max_servers: parseInt(maxServers),
                    price: parseFloat(price)
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('VIP plan updated successfully');
                    location.reload();
                } else {
                    alert('Error: ' + data.message);
                }
            });
        }

        function deleteUser(userId) {
            if (confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
                fetch('/admin/delete_user', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ user_id: userId })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('User deleted successfully');
                        location.reload();
                    } else {
                        alert('Error: ' + data.message);
                    }
                });
            }
        }
    </script>
</body>
</html>
'''

PROFILE_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Profile Settings - AMINE HOSTING</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --text-color: #212529;
            --border-color: #dee2e6;
            --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        [data-theme="dark"] {
            --bg-color: #121212;
            --card-bg: #1e1e1e;
            --text-color: #e9ecef;
            --border-color: #343a40;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: var(--primary-gradient);
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
        }
        .btn-gradient {
            background: var(--primary-gradient);
            border: none;
            color: white;
        }
        .theme-toggle {
            background: none;
            border: none;
            color: white;
            font-size: 1.2rem;
            cursor: pointer;
        }
        .profile-avatar {
            width: 150px;
            height: 150px;
            border-radius: 50%;
            object-fit: cover;
            border: 5px solid var(--border-color);
        }
        .avatar-upload {
            position: relative;
            display: inline-block;
        }
        .avatar-upload input {
            position: absolute;
            left: 0;
            top: 0;
            opacity: 0;
            width: 100%;
            height: 100%;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark">
        <div class="container">
            <a class="navbar-brand" href="/">
                <i class="fas fa-server me-2"></i>
                AMINE HOSTING 
            </a>
            <div class="navbar-nav ms-auto">
                <button class="theme-toggle nav-link" id="themeToggle">
                    <i class="fas fa-moon"></i>
                </button>
                <a class="nav-link" href="/">
                    <i class="fas fa-arrow-left me-1"></i>Back to Dashboard
                </a>
            </div>
        </div>
    </nav>

    <div class="container mt-4">
        <div class="row">
            <div class="col-md-4">
                <div class="card text-center">
                    <div class="card-body">
                        <div class="avatar-upload mb-3">
                            <img src="/profile_pic/{{ user.id }}" class="profile-avatar" id="avatar-preview" alt="{{ user.username }}">
                            <input type="file" id="avatar-input" accept="image/*">
                        </div>
                        <h4>{{ user.username }}</h4>
                        <p class="text-muted">{{ user.email or 'No email' }}</p>
                        <span class="badge {% if user.vip_plan == 'enterprise' %}bg-danger{% elif user.vip_plan == 'pro' %}bg-warning{% elif user.vip_plan == 'basic' %}bg-info{% else %}bg-secondary{% endif %}">
                            {{ user.vip_plan|title }} Plan
                        </span>
                        <div class="mt-3">
                            <button class="btn btn-sm btn-outline-primary" onclick="document.getElementById('avatar-input').click()">
                                <i class="fas fa-camera me-1"></i>Change Avatar
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-8">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0"><i class="fas fa-user-cog me-2"></i>Profile Settings</h5>
                    </div>
                    <div class="card-body">
                        <form id="profile-form">
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">Username</label>
                                        <input type="text" class="form-control" name="username" value="{{ user.username }}" required>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">Email</label>
                                        <input type="email" class="form-control" name="email" value="{{ user.email or '' }}">
                                    </div>
                                </div>
                            </div>
                            
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">Theme</label>
                                        <select class="form-select" name="theme">
                                            <option value="light" {% if user.theme == 'light' %}selected{% endif %}>Light</option>
                                            <option value="dark" {% if user.theme == 'dark' %}selected{% endif %}>Dark</option>
                                        </select>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">Language</label>
                                        <select class="form-select" name="language">
                                            <option value="en" {% if user.language == 'en' %}selected{% endif %}>English</option>
                                            <option value="es" {% if user.language == 'es' %}selected{% endif %}>Spanish</option>
                                            <option value="fr" {% if user.language == 'fr' %}selected{% endif %}>French</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Custom CSS</label>
                                <textarea class="form-control" name="custom_css" rows="4" placeholder="Enter custom CSS code">{{ user.custom_css or '' }}</textarea>
                                <div class="form-text">Add your own CSS to customize the appearance</div>
                            </div>
                            
                            <button type="submit" class="btn btn-gradient">
                                <i class="fas fa-save me-2"></i>Save Changes
                            </button>
                        </form>
                    </div>
                </div>
                
                <div class="card mt-4">
                    <div class="card-header">
                        <h5 class="mb-0"><i class="fas fa-key me-2"></i>Change Password</h5>
                    </div>
                    <div class="card-body">
                        <form id="password-form">
                            <div class="mb-3">
                                <label class="form-label">Current Password</label>
                                <input type="password" class="form-control" name="current_password" required>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">New Password</label>
                                <input type="password" class="form-control" name="new_password" required minlength="6">
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Confirm New Password</label>
                                <input type="password" class="form-control" name="confirm_password" required>
                            </div>
                            <button type="submit" class="btn btn-gradient">
                                <i class="fas fa-key me-2"></i>Change Password
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        const currentTheme = localStorage.getItem('theme') || 'light';
        
        document.documentElement.setAttribute('data-theme', currentTheme);
        updateThemeIcon(currentTheme);

        themeToggle.addEventListener('click', () => {
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });

        function updateThemeIcon(theme) {
            const icon = themeToggle.querySelector('i');
            icon.className = theme === 'light' ? 'fas fa-moon' : 'fas fa-sun';
        }

        // Avatar upload
        document.getElementById('avatar-input').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const formData = new FormData();
                formData.append('avatar', file);
                
                fetch('/upload_avatar', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('avatar-preview').src = '/profile_pic/{{ user.id }}?t=' + new Date().getTime();
                        alert('Avatar updated successfully!');
                    } else {
                        alert('Error: ' + data.message);
                    }
                });
            }
        });

        // Profile form
        document.getElementById('profile-form').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            
            fetch('/update_profile', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Profile updated successfully!');
                    localStorage.setItem('theme', formData.get('theme'));
                    document.documentElement.setAttribute('data-theme', formData.get('theme'));
                    updateThemeIcon(formData.get('theme'));
                } else {
                    alert('Error: ' + data.message);
                }
            });
        });

        // Password form
        document.getElementById('password-form').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(this);
            const newPassword = formData.get('new_password');
            const confirmPassword = formData.get('confirm_password');
            
            if (newPassword !== confirmPassword) {
                alert('New passwords do not match!');
                return;
            }
            
            fetch('/change_password', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Password changed successfully!');
                    this.reset();
                } else {
                    alert('Error: ' + data.message);
                }
            });
        });
    </script>
</body>
</html>
'''


@app.route('/')
@login_required
def index():
    user_id = session['user_id']
    user = user_manager.get_user(user_id)
    
    if user and 'created_at' not in user:
        user['created_at'] = datetime.now().isoformat()
        user_manager.save_users()
    
    user_servers = server_manager.get_user_servers(user_id)
    
    running_servers = sum(1 for server in user_servers.values() if server['status'] == 'running')
    total_servers = len(user_servers)
    
    return render_template_string(
        INDEX_HTML, 
        servers=user_servers,
        running_servers=running_servers,
        total_servers=total_servers,
        user=user,
        user_servers_count=total_servers,
        now=datetime.now(),
        datetime=datetime,
        server_manager=server_manager
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        success, user_id = user_manager.verify_user(username, password)
        if success:
            session['user_id'] = user_id
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template_string(LOGIN_HTML)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template_string(REGISTER_HTML)
        
        success, result = user_manager.create_user(username, password, email)
        if success:
            session['user_id'] = result
            return redirect(url_for('index'))
        else:
            flash(result, 'error')
    
    return render_template_string(REGISTER_HTML)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/vip')
@login_required
def vip_plans():
    user_id = session['user_id']
    user = user_manager.get_user(user_id)
    vip_plans = user_manager.vip_manager.get_all_plans()
    return render_template_string(VIP_HTML, vip_plans=vip_plans, user=user)

@app.route('/activate_vip', methods=['POST'])
@login_required
def activate_vip():
    data = request.get_json()
    plan_id = data.get('plan_id')
    
    user_id = session['user_id']
    user = user_manager.get_user(user_id)
    
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    success, message = user_manager.vip_manager.activate_vip(user, plan_id)
    if success:
        user_manager.save_users()
    
    return jsonify({'success': success, 'message': message})

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_server():
    user_id = session['user_id']
    
    if not server_manager.can_create_server(user_id):
        user = user_manager.get_user(user_id)
        max_servers = user.get('max_servers', 4) if user else 4
        flash(f"Server limit reached. You can only create {max_servers} servers.", 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        expiry_date = request.form.get('expiry_date')
        zip_file = request.files.get('zip_file')
        
        if name and expiry_date and zip_file:
            zip_path = os.path.join(UPLOAD_FOLDER, zip_file.filename)
            zip_file.save(zip_path)
            
            server_id, message = server_manager.create_server(name, expiry_date, zip_path, user_id)
            
            if os.path.exists(zip_path):
                os.remove(zip_path)
            
            if server_id:
                return redirect(url_for('server_details', server_id=server_id))
            else:
                flash(message, 'error')
        else:
            flash("Please fill all fields", 'error')
    
    default_expiry = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    return render_template_string(CREATE_HTML, default_expiry=default_expiry)

@app.route('/server/<server_id>')
@login_required
def server_details(server_id):
    if server_id not in server_manager.servers:
        return redirect(url_for('index'))
    
    server = server_manager.servers[server_id]
    
    if server.get('user_id') != session['user_id']:
        return "Access denied", 403
    
    is_expired = server_manager.is_server_expired(server_id)
    user = user_manager.get_user(session['user_id'])
    
    return render_template_string(
        SERVER_HTML, 
        server=server, 
        is_expired=is_expired,
        user=user,
        now=datetime.now(),
        datetime=datetime
    )

@app.route('/server/<server_id>/start')
@login_required
def start_server(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    success, message = server_manager.start_server(server_id)
    return jsonify({'success': success, 'message': message})

@app.route('/server/<server_id>/stop')
@login_required
def stop_server(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    success = server_manager.stop_server(server_id)
    return jsonify({'success': success})

@app.route('/server/<server_id>/restart')
@login_required
def restart_server(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    success, message = server_manager.restart_server(server_id)
    return jsonify({'success': success, 'message': message})

@app.route('/server/<server_id>/update_expiry', methods=['POST'])
@login_required
def update_expiry(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    new_date = request.form.get('new_date')
    success = server_manager.update_expiry_date(server_id, new_date)
    return jsonify({'success': success})

@app.route('/server/<server_id>/delete', methods=['POST'])
@login_required
def delete_server(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    success = server_manager.delete_server(server_id)
    return jsonify({'success': success})

@app.route('/server/<server_id>/logs')
@login_required
def server_logs(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'error': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'error': 'Access denied'})
    
    logs = server_manager.get_server_logs(server_id, lines=100)
    return jsonify({'logs': logs})

@app.route('/server/<server_id>/files')
@login_required
def server_files(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'error': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'error': 'Access denied'})
    
    files = server_manager.get_server_files(server_id)
    return jsonify({'files': files})

@app.route('/server/<server_id>/file/<path:file_path>')
@login_required
def get_file(server_id, file_path):
    if server_id not in server_manager.servers:
        return jsonify({'error': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'error': 'Access denied'})
    
    content = server_manager.get_file_content(server_id, file_path)
    if content is not None:
        return jsonify({'content': content})
    else:
        return jsonify({'error': 'File not found'}), 404

@app.route('/server/<server_id>/file/<path:file_path>', methods=['POST'])
@login_required
def save_file(server_id, file_path):
    if server_id not in server_manager.servers:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    content = request.form.get('content')
    success = server_manager.save_file_content(server_id, file_path, content)
    return jsonify({'success': success})

@app.route('/server/<server_id>/execute', methods=['POST'])
@login_required
def execute_server_command(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    data = request.get_json()
    command = data.get('command')
    
    if not command:
        return jsonify({'success': False, 'message': 'No command provided'})
    
    success, result = server_manager.execute_command(server_id, command)
    return jsonify({'success': success, 'result': result, 'message': result if not success else None})

# Dependency management routes
@app.route('/server/<server_id>/dependencies')
@login_required
def dependency_management(server_id):
    if server_id not in server_manager.servers:
        return redirect(url_for('index'))
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return "Access denied", 403
    
    server = server_manager.servers[server_id]
    
    DEPENDENCY_HTML = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dependency Management - {{ server.name }}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <style>
            :root {
                --bg-color: #f8f9fa;
                --card-bg: #ffffff;
                --text-color: #212529;
                --border-color: #dee2e6;
                --primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }

            [data-theme="dark"] {
                --bg-color: #121212;
                --card-bg: #1e1e1e;
                --text-color: #e9ecef;
                --border-color: #343a40;
            }

            body {
                background-color: var(--bg-color);
                color: var(--text-color);
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            .navbar {
                background: var(--primary-gradient);
            }
            .card {
                background-color: var(--card-bg);
                border: 1px solid var(--border-color);
                border-radius: 15px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            .terminal {
                background-color: #1e1e1e;
                color: #00ff00;
                font-family: 'Courier New', monospace;
                padding: 15px;
                border-radius: 5px;
                height: 400px;
                overflow-y: auto;
                white-space: pre-wrap;
                font-size: 12px;
            }
            .btn-gradient {
                background: var(--primary-gradient);
                border: none;
                color: white;
            }
        </style>
    </head>
    <body>
        <nav class="navbar navbar-expand-lg navbar-dark">
            <div class="container">
                <a class="navbar-brand" href="/">
                    <i class="fas fa-server me-2"></i>
                    AMINE HOSTING
                </a>
                <div class="navbar-nav ms-auto">
                    <a class="nav-link" href="/server/{{ server.id }}">
                        <i class="fas fa-arrow-left me-1"></i>Back to Server
                    </a>
                </div>
            </div>
        </nav>

        <div class="container mt-4">
            <div class="row">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-header">
                            <h4 class="mb-0"><i class="fas fa-boxes me-2"></i>Dependency Management - {{ server.name }}</h4>
                        </div>
                        <div class="card-body">
                            <div class="alert alert-info">
                                <h6><i class="fas fa-info-circle me-2"></i>Auto Dependency Installer</h6>
                                <p class="mb-0">
                                    The system automatically checks for <code>requirements.txt</code> and installs 
                                    dependencies when the server is created. You can also manually install dependencies here.
                                </p>
                            </div>

                            <div class="row mb-4">
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-header">
                                            <h6 class="mb-0">Installation Status</h6>
                                        </div>
                                        <div class="card-body">
                                            {% if server.install_success %}
                                                <div class="alert alert-success">
                                                    <i class="fas fa-check-circle me-2"></i>
                                                    <strong>Success:</strong> {{ server.install_message }}
                                                </div>
                                            {% else %}
                                                <div class="alert alert-danger">
                                                    <i class="fas fa-exclamation-circle me-2"></i>
                                                    <strong>Failed:</strong> {{ server.install_message }}
                                                </div>
                                            {% endif %}
                                            
                                            <div class="d-grid gap-2">
                                                <button class="btn btn-primary" onclick="installDependencies()">
                                                    <i class="fas fa-redo me-2"></i>Re-install Dependencies
                                                </button>
                                                <a href="/server/{{ server.id }}/install_logs" class="btn btn-outline-info" target="_blank">
                                                    <i class="fas fa-scroll me-2"></i>View Installation Logs
                                                </a>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="card">
                                        <div class="card-header">
                                            <h6 class="mb-0">Install Specific Package</h6>
                                        </div>
                                        <div class="card-body">
                                            <div class="input-group mb-3">
                                                <input type="text" class="form-control" id="packageName" placeholder="Package name (e.g., flask, django)">
                                                <button class="btn btn-success" onclick="installPackage()">
                                                    <i class="fas fa-download me-2"></i>Install
                                                </button>
                                            </div>
                                            <small class="text-muted">
                                                Example: flask, django, requests, numpy, pandas, etc.
                                            </small>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div class="card">
                                <div class="card-header">
                                    <h6 class="mb-0"><i class="fas fa-terminal me-2"></i>Installation Output</h6>
                                </div>
                                <div class="card-body">
                                    <div class="terminal" id="install-output">
                                        Click "Re-install Dependencies" or "Install" button to see output here.
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card">
                        <div class="card-header">
                            <h6 class="mb-0"><i class="fas fa-lightbulb me-2"></i>Tips & Information</h6>
                        </div>
                        <div class="card-body">
                            <h6>How it works:</h6>
                            <ul>
                                <li>Automatically detects <code>requirements.txt</code></li>
                                <li>Installs packages using <code>pip install -r requirements.txt</code></li>
                                <li>Logs all installation output</li>
                                <li>Supports manual package installation</li>
                            </ul>
                            
                            <h6>Common requirements.txt format:</h6>
                            <pre class="bg-dark text-light p-2 rounded">flask==2.3.3
django==4.2.7
requests>=2.31.0
numpy
pandas</pre>
                            
                            <div class="alert alert-warning mt-3">
                                <i class="fas fa-exclamation-triangle me-2"></i>
                                <strong>Note:</strong> Installation may fail if:
                                <ul class="mb-0 mt-2">
                                    <li>Internet connection is unavailable</li>
                                    <li>Package name is incorrect</li>
                                    <li>Version conflicts exist</li>
                                    <li>System permissions are insufficient</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            const serverId = '{{ server.id }}';
            
            function installDependencies() {
                const output = document.getElementById('install-output');
                output.textContent = '📦 Installing dependencies... Please wait...\\n';
                
                fetch(`/server/${serverId}/install_dependencies`, {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    output.textContent += '\\n' + (data.log_content || data.message);
                    
                    if (data.success) {
                        output.textContent += '\\n✅ Installation completed successfully!';
                    } else {
                        output.textContent += '\\n❌ Installation failed!';
                    }
                    
                    setTimeout(() => {
                        location.reload();
                    }, 3000);
                })
                .catch(error => {
                    output.textContent += '\\n❌ Error: ' + error.message;
                });
            }
            
            function installPackage() {
                const packageName = document.getElementById('packageName').value.trim();
                if (!packageName) {
                    alert('Please enter a package name');
                    return;
                }
                
                const output = document.getElementById('install-output');
                output.textContent = `📦 Installing ${packageName}... Please wait...\\n`;
                
                fetch(`/server/${serverId}/install_package`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ package: packageName })
                })
                .then(response => response.json())
                .then(data => {
                    output.textContent += '\\n' + (data.log_content || data.message);
                    
                    if (data.success) {
                        output.textContent += `\\n✅ ${packageName} installed successfully!`;
                    } else {
                        output.textContent += `\\n❌ Failed to install ${packageName}!`;
                    }
                    
                    document.getElementById('packageName').value = '';
                })
                .catch(error => {
                    output.textContent += '\\n❌ Error: ' + error.message;
                });
            }
        </script>
    </body>
    </html>
    '''
    
    return render_template_string(DEPENDENCY_HTML, server=server)

@app.route('/server/<server_id>/install_dependencies', methods=['POST'])
@login_required
def install_dependencies(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    success, message, log_content = server_manager.install_dependencies_now(server_id)
    return jsonify({
        'success': success,
        'message': message,
        'log_content': log_content
    })

@app.route('/server/<server_id>/install_package', methods=['POST'])
@login_required
def install_package(server_id):
    if server_id not in server_manager.servers:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'})
    
    data = request.get_json()
    package_name = data.get('package')
    
    if not package_name:
        return jsonify({'success': False, 'message': 'No package name provided'})
    
    success, message, log_content = server_manager.install_specific_package(server_id, package_name)
    return jsonify({
        'success': success,
        'message': message,
        'log_content': log_content
    })

@app.route('/server/<server_id>/install_logs')
@login_required
def get_install_logs(server_id):
    if server_id not in server_manager.servers:
        return "Server not found"
    
    if server_manager.servers[server_id].get('user_id') != session['user_id']:
        return "Access denied"
    
    logs = server_manager.get_install_logs(server_id)
    return f'<pre>{logs}</pre>'

@app.route('/system_stats')
def system_stats():
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        ram_usage = memory.percent
        ram_total = round(memory.total / (1024 ** 3), 2)
        ram_used = round(memory.used / (1024 ** 3), 2)
        
        disk_usage = disk.percent
        disk_total = round(disk.total / (1024 ** 3), 2)
        disk_used = round(disk.used / (1024 ** 3), 2)
        
        uptime_seconds = time.time() - psutil.boot_time()
        uptime_days = int(uptime_seconds // (24 * 3600))
        uptime_hours = int((uptime_seconds % (24 * 3600)) // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        uptime = f"{uptime_days}d {uptime_hours}h {uptime_minutes}m"
        
        return jsonify({
            'cpu_percent': cpu_percent,
            'ram_usage': ram_usage,
            'ram_total': ram_total,
            'ram_used': ram_used,
            'disk_usage': disk_usage,
            'disk_total': disk_total,
            'disk_used': disk_used,
            'uptime': uptime
        })
    except Exception as e:
        return jsonify({
            'cpu_percent': 0,
            'ram_usage': 0,
            'ram_total': 0,
            'ram_used': 0,
            'disk_usage': 0,
            'disk_total': 0,
            'disk_used': 0,
            'uptime': 'Unknown',
            'error': str(e)
        })

@app.route('/admin')
@admin_required
def admin_dashboard():
    all_users = user_manager.get_all_users()
    vip_plans = user_manager.vip_manager.get_all_plans()
    
    total_users = len(all_users)
    total_servers = len(server_manager.servers)
    running_servers = sum(1 for server in server_manager.servers.values() if server['status'] == 'running')
    free_users = sum(1 for user in all_users.values() if user['vip_plan'] == 'free')
    vip_users = total_users - free_users
    
    server_counts = {}
    for user_id in all_users:
        server_counts[user_id] = server_manager.get_user_server_count(user_id)
    
    return render_template_string(
        ADMIN_DASHBOARD_HTML,
        all_users=all_users,
        vip_plans=vip_plans,
        total_users=total_users,
        total_servers=total_servers,
        running_servers=running_servers,
        free_users=free_users,
        vip_users=vip_users,
        server_counts=server_counts,
        user_manager=user_manager
    )

@app.route('/admin/set_user_vip', methods=['POST'])
@admin_required
def admin_set_user_vip():
    data = request.get_json()
    user_id = data.get('user_id')
    plan_id = data.get('plan_id')
    
    success, message = user_manager.set_vip_plan(user_id, plan_id)
    if success:
        user_manager.save_users()
    
    return jsonify({'success': success, 'message': message})

@app.route('/admin/update_vip_plan', methods=['POST'])
@admin_required
def admin_update_vip_plan():
    data = request.get_json()
    plan_id = data.get('plan_id')
    max_servers = data.get('max_servers')
    price = data.get('price')
    
    success = user_manager.vip_manager.update_plan(plan_id, {
        'max_servers': max_servers,
        'price': price
    })
    
    return jsonify({'success': success, 'message': 'VIP plan updated' if success else 'Failed to update VIP plan'})

@app.route('/admin/delete_user', methods=['POST'])
@admin_required
def admin_delete_user():
    data = request.get_json()
    user_id = data.get('user_id')
    
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': 'Cannot delete your own account'})
    
    user = user_manager.get_user(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    if user.get('is_admin'):
        return jsonify({'success': False, 'message': 'Cannot delete admin user'})
    
    user_servers = server_manager.get_user_servers(user_id)
    for server_id in user_servers:
        server_manager.delete_server(server_id)
    
    if user.get('profile_pic'):
        profile_pic_path = os.path.join(PROFILE_PICS_FOLDER, user['profile_pic'])
        if os.path.exists(profile_pic_path):
            os.remove(profile_pic_path)
    
    del user_manager.users[user_id]
    user_manager.save_users()
    
    return jsonify({'success': True, 'message': 'User deleted successfully'})

@app.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    user = user_manager.get_user(user_id)
    return render_template_string(PROFILE_HTML, user=user)

@app.route('/upload_avatar', methods=['POST'])
@login_required
def upload_avatar():
    user_id = session['user_id']
    user = user_manager.get_user(user_id)
    
    if 'avatar' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'})
    
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})
    
    if file and allowed_file(file.filename):
        try:
            img = Image.open(file.stream)
            img = img.resize((150, 150))
            
            avatar_filename = f"{user_id}.png"
            avatar_path = os.path.join(PROFILE_PICS_FOLDER, avatar_filename)
            img.save(avatar_path, 'PNG')
            
            user['profile_pic'] = avatar_filename
            user_manager.save_users()
            
            return jsonify({'success': True, 'message': 'Avatar updated successfully'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Error processing image: {str(e)}'})
    
    return jsonify({'success': False, 'message': 'Invalid file type'})

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@app.route('/profile_pic/<user_id>')
def get_profile_pic(user_id):
    user = user_manager.get_user(user_id)
    if not user or not user.get('profile_pic'):
        avatar_data = generate_default_avatar(user['username'] if user else 'User')
        return send_file(BytesIO(avatar_data), mimetype='image/png')
    
    avatar_path = os.path.join(PROFILE_PICS_FOLDER, user['profile_pic'])
    if os.path.exists(avatar_path):
        return send_file(avatar_path, mimetype='image/png')
    else:
        avatar_data = generate_default_avatar(user['username'])
        return send_file(BytesIO(avatar_data), mimetype='image/png')

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    user_id = session['user_id']
    user = user_manager.get_user(user_id)
    
    username = request.form.get('username')
    email = request.form.get('email')
    theme = request.form.get('theme')
    language = request.form.get('language')
    custom_css = request.form.get('custom_css')
    
    if username != user['username']:
        for existing_user in user_manager.users.values():
            if existing_user['username'].lower() == username.lower() and existing_user['id'] != user_id:
                return jsonify({'success': False, 'message': 'Username already taken'})
    
    updates = {
        'username': username,
        'email': email,
        'theme': theme,
        'language': language,
        'custom_css': custom_css
    }
    
    if user_manager.update_user(user_id, updates):
        return jsonify({'success': True, 'message': 'Profile updated successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to update profile'})

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    user_id = session['user_id']
    user = user_manager.get_user(user_id)
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    
    if user_manager.hash_password(current_password) != user['password']:
        return jsonify({'success': False, 'message': 'Current password is incorrect'})
    
    updates = {
        'password': user_manager.hash_password(new_password)
    }
    
    if user_manager.update_user(user_id, updates):
        return jsonify({'success': True, 'message': 'Password changed successfully'})
    else:
        return jsonify({'success': False, 'message': 'Failed to change password'})

@app.route('/proxy/<int:port>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
@app.route('/proxy/<int:port>/', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def proxy_root(port):
    return proxy_request(port, '')

@app.route('/proxy/<int:port>/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'])
def proxy_subpath(port, subpath):
    return proxy_request(port, subpath)

if __name__ == '__main__':
    for user_id, user in user_manager.users.items():
        if 'created_at' not in user:
            user['created_at'] = datetime.now().isoformat()
            user_manager.save_users()
    
    if not any(user.get('is_admin') for user in user_manager.users.values()):
        # Create admin user
        user_manager.create_user('admin', 'admin123', 'admin@example.com')
        admin_user_id = list(user_manager.users.keys())[0]
        user_manager.update_user(admin_user_id, {
            'is_admin': True, 
            'max_servers': 100,
            'is_vip': True,
            'vip_plan': 'enterprise'
        })
        print("🔧 Created admin user: admin / admin123")
    
    PORT = get_available_port(50005)
    print(f"🚀 Starting AMINE HOSTING Control Panel on port {PORT}...")
    print(f"📊 Access the application at: http://localhost:{PORT}")
    print(f"🔐 Login system enabled")
    print(f"🆓 Free users: 1 server")
    print(f"👑 VIP system with admin management")
    print(f"📦 AUTO DEPENDENCY INSTALLER ENABLED!")
    print(f"   ✓ Automatic requirements.txt installation")
    print(f"   ✓ Manual package installation")
    print(f"   ✓ Installation logging and monitoring")
    print(f"👤 User profiles with avatars and customization")
    print(f"⚡ All features: File Editor, Terminal, Server Management, VIP System")
    print(f"🔧 Admin panel for user and VIP management")
    
    try:
        app.run(debug=True, host='0.0.0.0', port=PORT, use_reloader=False)
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"❌ Port {PORT} is busy. Trying next available port...")
            PORT = get_available_port(PORT + 1)
            print(f"🔄 Switching to port: {PORT}")
            app.run(debug=True, host='0.0.0.0', port=PORT, use_reloader=False)
        else:
            raise e