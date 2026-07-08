import json
import os
import shutil
from datetime import datetime
from threading import Lock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
SERVERS_DIR = os.path.join(BASE_DIR, 'servers')

users_lock = Lock()

def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_users(users):
    os.makedirs(DATA_DIR, exist_ok=True)
    with users_lock:
        try:
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(users, f, indent=2, ensure_ascii=False)
        except:
            pass

def create_user(username, password_hash, is_premium=False):
    users = load_users()
    for user in users:
        if user.get('username') == username:
            return False, 'User already exists'
    new_user = {
        'username': username,
        'password': password_hash,
        'is_premium': is_premium,
        'created_at': datetime.now().isoformat(),
        'last_login': None,
        'total_servers_created': 0,
        'total_logins': 0,
        'status': 'active',
        'storage_used_mb': 0,
        'bandwidth_used_mb': 0
    }
    users.append(new_user)
    save_users(users)
    user_dir = os.path.join(SERVERS_DIR, username)
    os.makedirs(user_dir, exist_ok=True)
    return True, new_user

def get_user(username):
    users = load_users()
    for user in users:
        if user.get('username') == username:
            return user
    return None

def get_all_users():
    return load_users()

def update_user(username, updates):
    users = load_users()
    for i, user in enumerate(users):
        if user.get('username') == username:
            for key, value in updates.items():
                if key not in ['username', 'created_at']:
                    users[i][key] = value
            save_users(users)
            return True, users[i]
    return False, None

def delete_user(username):
    users = load_users()
    users = [u for u in users if u.get('username') != username]
    save_users(users)
    user_dir = os.path.join(SERVERS_DIR, username)
    if os.path.exists(user_dir):
        try:
            shutil.rmtree(user_dir)
        except:
            pass
    return True

def change_password(username, new_password_hash):
    return update_user(username, {'password': new_password_hash})

def make_premium(username):
    return update_user(username, {'is_premium': True})

def remove_premium(username):
    return update_user(username, {'is_premium': False})

def record_login(username):
    update_user(username, {
        'last_login': datetime.now().isoformat(),
        'total_logins': (get_user(username) or {}).get('total_logins', 0) + 1
    })

def get_user_servers(username):
    from managers.server_manager import load_servers
    servers = load_servers()
    return [s for s in servers if s.get('owner') == username]

def get_user_server_count(username):
    servers = get_user_servers(username)
    return len(servers)

def can_create_server(username):
    user = get_user(username)
    if not user:
        return False, 'User not found'
    limit = 5 if user.get('is_premium', False) else 1
    current = get_user_server_count(username)
    if current >= limit:
        return False, f'Server limit reached ({limit} max)'
    return True, 'OK'

def get_user_storage_usage(username):
    user_dir = os.path.join(SERVERS_DIR, username)
    if not os.path.exists(user_dir):
        return 0
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(user_dir):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total_size += os.path.getsize(fp)
            except:
                pass
    return round(total_size / (1024 * 1024), 2)

def update_storage_usage(username):
    usage_mb = get_user_storage_usage(username)
    update_user(username, {'storage_used_mb': usage_mb})
    return usage_mb

def get_user_stats(username):
    user = get_user(username)
    servers = get_user_servers(username)
    running = len([s for s in servers if s.get('status') == 'running'])
    stopped = len([s for s in servers if s.get('status') == 'stopped'])
    crashed = len([s for s in servers if s.get('status') == 'crashed'])
    return {
        'username': username,
        'is_premium': user.get('is_premium', False) if user else False,
        'total_servers': len(servers),
        'running_servers': running,
        'stopped_servers': stopped,
        'crashed_servers': crashed,
        'server_limit': 5 if (user.get('is_premium', False) if user else False) else 1,
        'storage_used_mb': get_user_storage_usage(username),
        'created_at': user.get('created_at') if user else None,
        'last_login': user.get('last_login') if user else None
    }

def search_users(query):
    users = load_users()
    query_lower = query.lower()
    results = []
    for user in users:
        if query_lower in user.get('username', '').lower():
            results.append(user)
    return results

def ban_user(username):
    return update_user(username, {'status': 'banned'})

def unban_user(username):
    return update_user(username, {'status': 'active'})

def is_user_banned(username):
    user = get_user(username)
    return user.get('status') == 'banned' if user else False

def get_total_users_count():
    return len(load_users())

def get_premium_users_count():
    users = load_users()
    return len([u for u in users if u.get('is_premium', False)])

def get_active_users_count():
    users = load_users()
    now = datetime.now()
    active = 0
    for user in users:
        last_login = user.get('last_login')
        if last_login:
            try:
                login_time = datetime.fromisoformat(last_login)
                if (now - login_time).days < 7:
                    active += 1
            except:
                pass
    return active