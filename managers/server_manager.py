import json
import os
import shutil
from datetime import datetime
from threading import Lock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
SERVERS_FILE = os.path.join(DATA_DIR, 'servers.json')
SERVERS_DIR = os.path.join(BASE_DIR, 'servers')

servers_lock = Lock()

def load_servers():
    if not os.path.exists(SERVERS_FILE):
        return []
    try:
        with open(SERVERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, list):
                return []
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_servers(servers):
    os.makedirs(DATA_DIR, exist_ok=True)
    with servers_lock:
        try:
            with open(SERVERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(servers, f, indent=2, ensure_ascii=False)
        except:
            pass

def create_server(server_data):
    servers = load_servers()
    servers.append(server_data)
    save_servers(servers)
    return True, server_data

def get_server(server_id):
    servers = load_servers()
    for server in servers:
        if server.get('id') == server_id:
            return server
    return None

def get_all_servers():
    return load_servers()

def update_server(server_id, updates):
    servers = load_servers()
    for i, server in enumerate(servers):
        if server.get('id') == server_id:
            for key, value in updates.items():
                if key not in ['id', 'owner', 'created_at']:
                    servers[i][key] = value
            save_servers(servers)
            return True, servers[i]
    return False, None

def delete_server(server_id):
    servers = load_servers()
    server = None
    for s in servers:
        if s.get('id') == server_id:
            server = s
            break
    if server:
        servers = [s for s in servers if s.get('id') != server_id]
        save_servers(servers)
        server_dir = os.path.join(SERVERS_DIR, server.get('owner', ''), server.get('name', ''))
        if os.path.exists(server_dir):
            try:
                shutil.rmtree(server_dir)
            except:
                pass
        return True
    return False

def update_server_status(server_id, status, stats=None):
    updates = {
        'status': status,
        'last_status_change': datetime.now().isoformat()
    }
    if status == 'running':
        updates['last_start'] = datetime.now().isoformat()
    elif status == 'stopped':
        updates['last_stop'] = datetime.now().isoformat()
    if stats:
        updates.update(stats)
    return update_server(server_id, updates)

def get_server_stats(server_id):
    server = get_server(server_id)
    if not server:
        return None
    owner = server.get('owner', '')
    name = server.get('name', '')
    server_dir = os.path.join(SERVERS_DIR, owner, name)
    file_count = 0
    total_size = 0
    if os.path.exists(server_dir):
        for dirpath, dirnames, filenames in os.walk(server_dir):
            for f in filenames:
                if '.sandbox_' not in dirpath and '.venv_' not in dirpath:
                    file_count += 1
                    fp = os.path.join(dirpath, f)
                    try:
                        total_size += os.path.getsize(fp)
                    except:
                        pass
    server['file_count'] = file_count
    server['total_size_mb'] = round(total_size / (1024 * 1024), 2)
    return server

def get_user_servers_list(username):
    servers = load_servers()
    return [s for s in servers if s.get('owner') == username]

def get_running_servers():
    servers = load_servers()
    return [s for s in servers if s.get('status') == 'running']

def get_stopped_servers():
    servers = load_servers()
    return [s for s in servers if s.get('status') == 'stopped']

def get_crashed_servers():
    servers = load_servers()
    return [s for s in servers if s.get('status') == 'crashed']

def get_total_servers_count():
    return len(load_servers())

def get_running_servers_count():
    return len(get_running_servers())

def is_port_available(port):
    servers = load_servers()
    for server in servers:
        if server.get('port') == port:
            return False
    return True

def get_server_by_port(port):
    servers = load_servers()
    for server in servers:
        if server.get('port') == port:
            return server
    return None

def get_next_available_port(start=5001, end=60000):
    used_ports = {s.get('port') for s in load_servers()}
    for port in range(start, end + 1):
        if port not in used_ports:
            return port
    return None

def update_server_resources(server_id, cpu_usage, ram_usage):
    return update_server(server_id, {
        'cpu_usage': cpu_usage,
        'ram_usage': ram_usage,
        'last_stats_update': datetime.now().isoformat()
    })

def get_server_logs(server_id, limit=100):
    server = get_server(server_id)
    if not server:
        return []
    owner = server.get('owner', '')
    name = server.get('name', '')
    log_file = os.path.join(SERVERS_DIR, owner, name, '.server.log')
    if not os.path.exists(log_file):
        return []
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return [line.strip() for line in lines[-limit:]]
    except:
        return []

def write_server_log(server_id, message):
    server = get_server(server_id)
    if not server:
        return
    owner = server.get('owner', '')
    name = server.get('name', '')
    server_dir = os.path.join(SERVERS_DIR, owner, name)
    os.makedirs(server_dir, exist_ok=True)
    log_file = os.path.join(server_dir, '.server.log')
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().isoformat()
            f.write(f'[{timestamp}] {message}\n')
    except:
        pass

def search_servers(query):
    servers = load_servers()
    query_lower = query.lower()
    results = []
    for server in servers:
        if (query_lower in server.get('name', '').lower() or
            query_lower in server.get('owner', '').lower() or
            query_lower in server.get('id', '').lower()):
            results.append(server)
    return results

def get_servers_by_status(status):
    servers = load_servers()
    return [s for s in servers if s.get('status') == status]

def cleanup_crashed_servers():
    servers = load_servers()
    cleaned = 0
    for server in servers:
        if server.get('status') == 'crashed':
            last_change = server.get('last_status_change')
            if last_change:
                try:
                    change_time = datetime.fromisoformat(last_change)
                    if (datetime.now() - change_time).total_seconds() > 86400:
                        update_server_status(server['id'], 'stopped')
                        cleaned += 1
                except:
                    pass
    return cleaned

def get_server_uptime(server_id):
    server = get_server(server_id)
    if not server:
        return 'N/A'
    if server.get('status') != 'running':
        return '0s'
    last_start = server.get('last_start')
    if not last_start:
        return '0s'
    try:
        start_time = datetime.fromisoformat(last_start)
        delta = datetime.now() - start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f'{hours}h {minutes}m {seconds}s'
        elif minutes > 0:
            return f'{minutes}m {seconds}s'
        else:
            return f'{seconds}s'
    except:
        return '0s'