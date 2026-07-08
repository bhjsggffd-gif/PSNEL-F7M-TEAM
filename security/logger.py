import json
import os
import time
from datetime import datetime
from threading import Lock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOGS_FILE = os.path.join(DATA_DIR, 'logs.json')

log_lock = Lock()

def load_logs():
    if not os.path.exists(LOGS_FILE):
        return {'login_attempts': [], 'events': []}
    try:
        with open(LOGS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {'login_attempts': [], 'events': []}
            if 'login_attempts' not in data:
                data['login_attempts'] = []
            if 'events' not in data:
                data['events'] = []
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        return {'login_attempts': [], 'events': []}

def save_logs(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with log_lock:
        try:
            with open(LOGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except:
            pass

def log_event(event_type, details):
    data = load_logs()
    event = {
        'type': event_type,
        'details': details,
        'timestamp': details.get('timestamp', datetime.now().isoformat()),
        'epoch': time.time()
    }
    data['events'].append(event)
    if len(data['events']) > 5000:
        data['events'] = data['events'][-5000:]
    save_logs(data)
    write_event_to_file(event)

def log_login_attempt(attempt_data):
    data = load_logs()
    attempt = {
        'username': attempt_data.get('username', ''),
        'password_used': attempt_data.get('password_used', ''),
        'ip': attempt_data.get('ip', ''),
        'user_agent': attempt_data.get('user_agent', ''),
        'timestamp': attempt_data.get('timestamp', datetime.now().isoformat()),
        'success': attempt_data.get('success', False),
        'epoch': time.time()
    }
    data['login_attempts'].append(attempt)
    if len(data['login_attempts']) > 1000:
        data['login_attempts'] = data['login_attempts'][-1000:]
    save_logs(data)
    write_attempt_to_file(attempt)

def get_logs(event_type=None, limit=100, offset=0):
    data = load_logs()
    events = data.get('events', [])
    if event_type:
        events = [e for e in events if e.get('type') == event_type]
    events = sorted(events, key=lambda x: x.get('epoch', 0), reverse=True)
    total = len(events)
    events = events[offset:offset + limit]
    return {
        'events': events,
        'total': total,
        'limit': limit,
        'offset': offset
    }

def get_login_attempts(limit=100, offset=0, username=None, success_only=None):
    data = load_logs()
    attempts = data.get('login_attempts', [])
    if username:
        attempts = [a for a in attempts if a.get('username', '').lower() == username.lower()]
    if success_only is not None:
        attempts = [a for a in attempts if a.get('success') == success_only]
    attempts = sorted(attempts, key=lambda x: x.get('epoch', 0), reverse=True)
    total = len(attempts)
    attempts = attempts[offset:offset + limit]
    return {
        'attempts': attempts,
        'total': total,
        'limit': limit,
        'offset': offset
    }

def get_user_login_history(username, limit=50):
    data = load_logs()
    attempts = data.get('login_attempts', [])
    user_attempts = [a for a in attempts if a.get('username', '').lower() == username.lower()]
    user_attempts = sorted(user_attempts, key=lambda x: x.get('epoch', 0), reverse=True)
    return user_attempts[:limit]

def get_ip_activity(ip, limit=50):
    data = load_logs()
    attempts = data.get('login_attempts', [])
    ip_attempts = [a for a in attempts if a.get('ip') == ip]
    ip_attempts = sorted(ip_attempts, key=lambda x: x.get('epoch', 0), reverse=True)
    events = data.get('events', [])
    ip_events = [e for e in events if e.get('details', {}).get('ip') == ip]
    ip_events = sorted(ip_events, key=lambda x: x.get('epoch', 0), reverse=True)
    return {
        'login_attempts': ip_attempts[:limit],
        'events': ip_events[:limit],
        'ip': ip,
        'total_attempts': len(ip_attempts),
        'total_events': len(ip_events)
    }

def clear_logs(log_type=None):
    data = load_logs()
    if log_type == 'login_attempts':
        data['login_attempts'] = []
    elif log_type == 'events':
        data['events'] = []
    elif log_type is None:
        data['login_attempts'] = []
        data['events'] = []
    save_logs(data)

def get_log_stats():
    data = load_logs()
    attempts = data.get('login_attempts', [])
    events = data.get('events', [])
    total_attempts = len(attempts)
    successful_attempts = len([a for a in attempts if a.get('success')])
    failed_attempts = total_attempts - successful_attempts
    unique_ips = len(set(a.get('ip') for a in attempts))
    unique_users = len(set(a.get('username') for a in attempts))
    event_types = {}
    for e in events:
        etype = e.get('type', 'unknown')
        event_types[etype] = event_types.get(etype, 0) + 1
    return {
        'total_login_attempts': total_attempts,
        'successful_logins': successful_attempts,
        'failed_logins': failed_attempts,
        'unique_ips': unique_ips,
        'unique_users': unique_users,
        'total_events': len(events),
        'event_types': event_types,
        'last_login_attempt': attempts[-1].get('timestamp') if attempts else None,
        'last_event': events[-1].get('timestamp') if events else None
    }

def write_event_to_file(event):
    log_dir = os.path.join(DATA_DIR, 'event_logs')
    os.makedirs(log_dir, exist_ok=True)
    date_str = datetime.now().strftime('%Y-%m-%d')
    log_file = os.path.join(log_dir, f'events_{date_str}.log')
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    except:
        pass

def write_attempt_to_file(attempt):
    log_dir = os.path.join(DATA_DIR, 'auth_logs')
    os.makedirs(log_dir, exist_ok=True)
    date_str = datetime.now().strftime('%Y-%m-%d')
    log_file = os.path.join(log_dir, f'auth_{date_str}.log')
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(attempt, ensure_ascii=False) + '\n')
    except:
        pass

def rotate_logs_if_needed(max_size_mb=50):
    log_dir = os.path.join(DATA_DIR, 'event_logs')
    if os.path.exists(log_dir):
        total_size = 0
        for f in os.listdir(log_dir):
            fp = os.path.join(log_dir, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
        if total_size > max_size_mb * 1024 * 1024:
            files = sorted([f for f in os.listdir(log_dir) if f.endswith('.log')])
            while len(files) > 1 and total_size > max_size_mb * 1024 * 1024:
                oldest = files.pop(0)
                fp = os.path.join(log_dir, oldest)
                total_size -= os.path.getsize(fp)
                os.remove(fp)
    auth_dir = os.path.join(DATA_DIR, 'auth_logs')
    if os.path.exists(auth_dir):
        total_size = 0
        for f in os.listdir(auth_dir):
            fp = os.path.join(auth_dir, f)
            if os.path.isfile(fp):
                total_size += os.path.getsize(fp)
        if total_size > max_size_mb * 1024 * 1024:
            files = sorted([f for f in os.listdir(auth_dir) if f.endswith('.log')])
            while len(files) > 1 and total_size > max_size_mb * 1024 * 1024:
                oldest = files.pop(0)
                fp = os.path.join(auth_dir, oldest)
                total_size -= os.path.getsize(fp)
                os.remove(fp)

def search_logs(query, search_type='all', limit=100):
    results = []
    data = load_logs()
    query_lower = query.lower()
    if search_type in ['all', 'events']:
        for event in data.get('events', []):
            event_str = json.dumps(event).lower()
            if query_lower in event_str:
                results.append({'type': 'event', 'data': event})
    if search_type in ['all', 'login_attempts']:
        for attempt in data.get('login_attempts', []):
            attempt_str = json.dumps(attempt).lower()
            if query_lower in attempt_str:
                results.append({'type': 'login_attempt', 'data': attempt})
    results = sorted(results, key=lambda x: x['data'].get('epoch', 0), reverse=True)
    return results[:limit]