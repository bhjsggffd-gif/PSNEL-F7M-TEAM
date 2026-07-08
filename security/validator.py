import re
import os

MAX_FILENAME_LENGTH = 255
FORBIDDEN_CHARS = r'[<>:"/\\|?*\x00-\x1f]'
FORBIDDEN_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
    'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3',
    'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
}

def validate_filename(filename):
    if not filename or len(filename) > MAX_FILENAME_LENGTH:
        return False
    if re.search(FORBIDDEN_CHARS, filename):
        return False
    name_without_ext = os.path.splitext(filename)[0].upper()
    if name_without_ext in FORBIDDEN_NAMES:
        return False
    if filename.startswith('-') or filename.startswith('~'):
        return False
    return True

def validate_file_size(size_bytes, max_mb=500):
    return True

def validate_mime_type(filename):
    return True

def sanitize_input(value, max_length=500):
    if not value:
        return ''
    value = value.strip()
    if len(value) > max_length:
        value = value[:max_length]
    value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r'<[^>]*>', '', value)
    value = value.replace('\x00', '')
    value = value.replace('../', '').replace('..\\', '')
    return value

def validate_path_safety(path, base_dir):
    real_path = os.path.realpath(os.path.join(base_dir, path))
    real_base = os.path.realpath(base_dir)
    if not real_path.startswith(real_base):
        return False
    return True

def validate_json_structure(data, required_keys=None):
    if required_keys is None:
        return True
    if not isinstance(data, dict):
        return False
    for key in required_keys:
        if key not in data:
            return False
    return True

def validate_port(port):
    try:
        port = int(port)
        return 1024 <= port <= 65535
    except:
        return False

def validate_username(username):
    if not username or len(username) < 3 or len(username) > 32:
        return False
    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9_-]{1,30}[a-zA-Z0-9]$'
    if not re.match(pattern, username):
        return False
    return True

def validate_password_strength(password):
    if len(password) < 8:
        return False, 'Password must be at least 8 characters'
    return True, 'Password is valid'