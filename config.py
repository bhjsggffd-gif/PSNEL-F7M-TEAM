import os
import secrets

# ============================================
# الأمان المتقدم - هذه المعلومات تعرفها أنت فقط
# يجب تعيين هذه المتغيرات في البيئة
# ============================================

# إقرأ من متغيرات البيئة أو استخدم القيم الافتراضية الآمنة
SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))

MAX_FILE_SIZE = 50
MAX_USER_STORAGE = 2048
MAX_RAM_MB = 512
MAX_CPU_PERCENT = 50

# ⚠️ مهم جدا - هذه البيانات يجب أن تكون في متغيرات البيئة فقط
# لا تضعها مباشرة هنا في الإنتاج!
ADMIN_USERNAME = os.environ.get('JAGWAR_ADMIN_USER', 'JAGWARGG')
ADMIN_PASSWORD = os.environ.get('JAGWAR_ADMIN_PASS', 'JAGWAR12345')

SESSION_LIFETIME = 86400
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True  # تشغيل HTTPS فقط
SESSION_COOKIE_SAMESITE = 'Strict'

RATE_LIMIT_MAX = 30
RATE_LIMIT_WINDOW = 60

ALLOWED_EXTENSIONS = {
    '.py', '.txt', '.json', '.yaml', '.yml', '.md', '.cfg', '.ini',
    '.env', '.html', '.css', '.js', '.csv', '.log', '.xml', '.toml',
    '.req', '.requirements'
}

BLOCKED_PATTERNS = [
    'rm -rf', 'rm -r', 'os.system', 'subprocess.call', 'subprocess.Popen',
    'eval(', 'exec(', '__import__', 'open(', 'file(', 'input(',
    'raw_input', 'compile(', 'execfile(', 'os.remove', 'os.rmdir',
    'os.unlink', 'shutil.rmtree', 'shutil.remove', 'sys.exit',
    'os.chmod', 'os.chown', 'os.kill', 'os.popen', 'commands.',
    'pty.spawn', 'pexpect', 'socket.', 'http.server', 'BaseHTTP',
    'SimpleHTTP', 'CGIHTTP', 'urllib.request.urlopen', 'requests.get',
    'requests.post', 'requests.put', 'requests.delete', 'requests.patch',
    'wget', 'curl', 'scapy', 'nmap', 'import os', 'from os import',
    'import subprocess', 'from subprocess import', 'import shutil',
    'from shutil import', 'import sys', 'from sys import',
    'os.path.join', 'os.walk', 'os.listdir', 'glob.glob',
    'pathlib.Path', 'open(', 'file.write', 'pickle.', 'marshal.',
    'ctypes.', 'multiprocessing.', 'threading.Thread', 'signal.',
    'setuid', 'setgid', 'seteuid', 'setegid', 'setreuid', 'setregid',
    'ptrace', 'process_vm_writev', 'process_vm_readv',
    'syscall', '__builtins__', 'builtins', 'getattr(', 'setattr(',
    'delattr(', 'hasattr(', 'vars(', 'dir(', 'type(', 'issubclass(',
    'isinstance(', 'super(', 'classmethod', 'staticmethod',
    'property(', '__dict__', '__class__', '__bases__', '__mro__',
    '__subclasses__', '__globals__', '__code__', '__closure__'
]

SENSITIVE_KEYWORDS = [
    'password', 'secret', 'token', 'api_key', 'private_key',
    'ssh', 'credential', 'auth', 'database_url', 'connection_string'
]

LOGIN_LOG_MAX = 1000
EVENT_LOG_MAX = 5000

SANDBOX_TIMEOUT = 300
SANDBOX_MAX_MEMORY = 512 * 1024 * 1024

WEBSOCKET_PING_INTERVAL = 25
WEBSOCKET_PING_TIMEOUT = 10

SERVER_NAME = 'JAGWAR HOST'
SERVER_VERSION = '1.0.0'
COPYRIGHT_YEAR = 2026