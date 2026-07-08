import os
import shutil
import zipfile
import io
import json
from datetime import datetime
from security.validator import validate_filename, validate_path_safety

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVERS_DIR = os.path.join(BASE_DIR, 'servers')
MAX_STORAGE_PER_USER = 2 * 1024 * 1024 * 1024

def get_server_dir(username, server_name):
    return os.path.join(SERVERS_DIR, username, server_name)

def list_files(server_dir):
    if not os.path.exists(server_dir):
        return []
    files = []
    try:
        for item in os.listdir(server_dir):
            if item.startswith('.sandbox_') or item.startswith('.venv_') or item == '.server.log':
                continue
            item_path = os.path.join(server_dir, item)
            is_dir = os.path.isdir(item_path)
            try:
                size = os.path.getsize(item_path) if not is_dir else 0
            except:
                size = 0
            try:
                modified = datetime.fromtimestamp(os.path.getmtime(item_path)).isoformat()
            except:
                modified = ''
            files.append({
                'name': item,
                'is_dir': is_dir,
                'size': size,
                'size_display': format_size(size),
                'modified': modified
            })
        files.sort(key=lambda x: (x['is_dir'], x['name']), reverse=True)
        files.sort(key=lambda x: x['is_dir'], reverse=True)
    except:
        pass
    return files

def create_file(server_dir, filename, content=''):
    if not validate_filename(filename):
        return False, 'Invalid filename'
    if not validate_path_safety(filename, server_dir):
        return False, 'Path traversal detected'
    filepath = os.path.join(server_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        os.chmod(filepath, 0o644)
        return True, filepath
    except Exception as e:
        return False, str(e)

def read_file(server_dir, filename):
    if not validate_filename(filename):
        return ''
    if not validate_path_safety(filename, server_dir):
        return ''
    filepath = os.path.join(server_dir, filename)
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        return ''
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except:
        return ''

def write_file(server_dir, filename, content):
    if not validate_filename(filename):
        return False, 'Invalid filename'
    if not validate_path_safety(filename, server_dir):
        return False, 'Path traversal detected'
    filepath = os.path.join(server_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, filepath
    except Exception as e:
        return False, str(e)

def delete_file(server_dir, filename):
    if not validate_filename(filename):
        return False, 'Invalid filename'
    if not validate_path_safety(filename, server_dir):
        return False, 'Path traversal detected'
    filepath = os.path.join(server_dir, filename)
    if not os.path.exists(filepath):
        return False, 'File not found'
    if os.path.isdir(filepath):
        return False, 'Use delete_folder for directories'
    try:
        os.remove(filepath)
        return True, filepath
    except Exception as e:
        return False, str(e)

def rename_file(server_dir, old_name, new_name):
    if not validate_filename(old_name) or not validate_filename(new_name):
        return False, 'Invalid filename'
    if not validate_path_safety(old_name, server_dir) or not validate_path_safety(new_name, server_dir):
        return False, 'Path traversal detected'
    old_path = os.path.join(server_dir, old_name)
    new_path = os.path.join(server_dir, new_name)
    if not os.path.exists(old_path):
        return False, 'File not found'
    if os.path.exists(new_path):
        return False, 'A file with this name already exists'
    try:
        os.rename(old_path, new_path)
        return True, new_path
    except Exception as e:
        return False, str(e)

def create_folder(server_dir, foldername):
    if not validate_filename(foldername):
        return False, 'Invalid folder name'
    if not validate_path_safety(foldername, server_dir):
        return False, 'Path traversal detected'
    folder_path = os.path.join(server_dir, foldername)
    if os.path.exists(folder_path):
        return False, 'Folder already exists'
    try:
        os.makedirs(folder_path, exist_ok=True)
        return True, folder_path
    except Exception as e:
        return False, str(e)

def delete_folder(server_dir, foldername):
    if not validate_filename(foldername):
        return False, 'Invalid folder name'
    if not validate_path_safety(foldername, server_dir):
        return False, 'Path traversal detected'
    folder_path = os.path.join(server_dir, foldername)
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return False, 'Folder not found'
    try:
        shutil.rmtree(folder_path)
        return True, folder_path
    except Exception as e:
        return False, str(e)

def upload_file(server_dir, filename, content):
    if not validate_filename(filename):
        return False, 'Invalid filename'
    if not validate_path_safety(filename, server_dir):
        return False, 'Path traversal detected'
    filepath = os.path.join(server_dir, filename)
    try:
        if isinstance(content, str):
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
        elif isinstance(content, bytes):
            with open(filepath, 'wb') as f:
                f.write(content)
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(str(content))
        os.chmod(filepath, 0o644)
        return True, filepath
    except Exception as e:
        return False, str(e)

def zip_folder(server_dir):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(server_dir):
            for file in files:
                if '.sandbox_' in root or '.venv_' in root:
                    continue
                if file == '.server.log':
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, server_dir)
                try:
                    zf.write(file_path, arcname)
                except:
                    pass
    zip_buffer.seek(0)
    return zip_buffer

def backup_server(server_dir):
    backup_dir = os.path.join(server_dir, '.backups')
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(backup_dir, f'backup_{timestamp}.zip')
    with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(server_dir):
            for file in files:
                if '.backups' in root or '.sandbox_' in root or '.venv_' in root:
                    continue
                if file == '.server.log':
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, server_dir)
                try:
                    zf.write(file_path, arcname)
                except:
                    pass
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith('.zip')],
        key=lambda x: os.path.getmtime(os.path.join(backup_dir, x)),
        reverse=True
    )
    while len(backups) > 5:
        oldest = backups.pop()
        try:
            os.remove(os.path.join(backup_dir, oldest))
        except:
            pass
    return True, backup_file

def restore_backup(server_dir, backup_filename):
    backup_dir = os.path.join(server_dir, '.backups')
    backup_path = os.path.join(backup_dir, backup_filename)
    if not os.path.exists(backup_path):
        return False, 'Backup file not found'
    try:
        with zipfile.ZipFile(backup_path, 'r') as zf:
            zf.extractall(server_dir)
        return True, server_dir
    except Exception as e:
        return False, str(e)

def list_backups(server_dir):
    backup_dir = os.path.join(server_dir, '.backups')
    if not os.path.exists(backup_dir):
        return []
    backups = []
    for f in os.listdir(backup_dir):
        if f.endswith('.zip'):
            fp = os.path.join(backup_dir, f)
            try:
                size = os.path.getsize(fp)
                modified = datetime.fromtimestamp(os.path.getmtime(fp)).isoformat()
                backups.append({
                    'name': f,
                    'size': format_size(size),
                    'modified': modified
                })
            except:
                pass
    return sorted(backups, key=lambda x: x['modified'], reverse=True)

def get_folder_size(server_dir):
    total = 0
    if not os.path.exists(server_dir):
        return 0
    for dirpath, dirnames, filenames in os.walk(server_dir):
        if '.sandbox_' in dirpath or '.venv_' in dirpath or '.backups' in dirpath:
            continue
        for f in filenames:
            if f == '.server.log':
                continue
            fp = os.path.join(dirpath, f)
            try:
                total += os.path.getsize(fp)
            except:
                pass
    return total

def check_storage_limit(server_dir, username=None):
    current_size = 0
    if username:
        user_dir = os.path.join(SERVERS_DIR, username)
        if os.path.exists(user_dir):
            current_size = get_folder_size(user_dir)
    else:
        current_size = get_folder_size(server_dir)
    if current_size > MAX_STORAGE_PER_USER:
        return False, current_size, MAX_STORAGE_PER_USER
    return True, current_size, MAX_STORAGE_PER_USER

def format_size(size_bytes):
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    elif size_bytes < 1024 * 1024 * 1024:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
    else:
        return f'{size_bytes / (1024 * 1024 * 1024):.2f} GB'

def move_file(server_dir, source, destination):
    if not validate_path_safety(source, server_dir) or not validate_path_safety(destination, server_dir):
        return False, 'Path traversal detected'
    source_path = os.path.join(server_dir, source)
    dest_path = os.path.join(server_dir, destination)
    if not os.path.exists(source_path):
        return False, 'Source file not found'
    if os.path.exists(dest_path):
        return False, 'Destination already exists'
    try:
        shutil.move(source_path, dest_path)
        return True, dest_path
    except Exception as e:
        return False, str(e)

def copy_file(server_dir, source, destination):
    if not validate_path_safety(source, server_dir) or not validate_path_safety(destination, server_dir):
        return False, 'Path traversal detected'
    source_path = os.path.join(server_dir, source)
    dest_path = os.path.join(server_dir, destination)
    if not os.path.exists(source_path):
        return False, 'Source file not found'
    if os.path.exists(dest_path):
        return False, 'Destination already exists'
    try:
        if os.path.isdir(source_path):
            shutil.copytree(source_path, dest_path)
        else:
            shutil.copy2(source_path, dest_path)
        return True, dest_path
    except Exception as e:
        return False, str(e)

def file_exists(server_dir, filename):
    filepath = os.path.join(server_dir, filename)
    return os.path.exists(filepath)

def search_files(server_dir, query):
    results = []
    if not os.path.exists(server_dir):
        return results
    query_lower = query.lower()
    for root, dirs, files in os.walk(server_dir):
        if '.sandbox_' in root or '.venv_' in root:
            continue
        for name in dirs + files:
            if query_lower in name.lower():
                full_path = os.path.join(root, name)
                rel_path = os.path.relpath(full_path, server_dir)
                results.append({
                    'name': name,
                    'path': rel_path,
                    'is_dir': os.path.isdir(full_path),
                    'size': format_size(os.path.getsize(full_path)) if os.path.isfile(full_path) else '-'
                })
    return results