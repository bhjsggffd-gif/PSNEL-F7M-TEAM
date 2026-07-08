import hashlib
import secrets
import time
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from config import SESSION_LIFETIME, ADMIN_USERNAME

def hash_password(password):
    salt = secrets.token_hex(16)
    iterations = 200000
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
    return f"pbkdf2:sha256:{iterations}${salt}${dk.hex()}"

def verify_password(password, password_hash):
    try:
        parts = password_hash.split('$')
        if len(parts) != 3:
            return False
        algorithm_iterations = parts[0].split(':')
        if len(algorithm_iterations) != 3 or algorithm_iterations[0] != 'pbkdf2' or algorithm_iterations[1] != 'sha256':
            return False
        iterations = int(algorithm_iterations[2])
        salt = parts[1]
        stored_hash = parts[2]
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations)
        return secrets.compare_digest(dk.hex(), stored_hash)
    except:
        return False

def generate_session_token():
    return secrets.token_hex(32)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Authentication required'}), 401
            return redirect(url_for('login'))
        if 'token' not in session:
            session.clear()
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Invalid session token'}), 401
            return redirect(url_for('login'))
        if 'login_time' in session:
            elapsed = time.time() - session['login_time']
            if elapsed > SESSION_LIFETIME:
                session.clear()
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': 'Session expired'}), 401
                return redirect(url_for('login'))
        session['login_time'] = time.time()
        user_agent = request.headers.get('User-Agent', '')
        if 'user_agent' in session and session['user_agent'] != user_agent:
            session.clear()
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'Session hijacking detected'}), 401
            return redirect(url_for('login'))
        session['user_agent'] = user_agent
        ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
        if 'ip_address' in session and session['ip_address'] != ip_address:
            session.clear()
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'error': 'IP mismatch detected'}), 401
            return redirect(url_for('login'))
        session['ip_address'] = ip_address
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin', False) and session.get('user') != ADMIN_USERNAME:
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def csrf_protect(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
            if not token or token != session.get('token'):
                return jsonify({'error': 'CSRF validation failed'}), 403
        return f(*args, **kwargs)
    return decorated_function

def sanitize_session():
    sensitive_keys = ['password', 'secret', 'token_raw']
    for key in list(session.keys()):
        if key not in ['user', 'is_admin', 'token', 'login_time', 'user_agent', 'ip_address']:
            session.pop(key, None)