import re
from config import BLOCKED_PATTERNS

DANGEROUS_IMPORTS = {
    'os', 'subprocess', 'sys', 'shutil', 'socket', 'requests',
    'urllib', 'http.server', 'BaseHTTPServer', 'SimpleHTTPServer',
    'CGIHTTPServer', 'ftplib', 'telnetlib', 'smtplib', 'poplib',
    'imaplib', 'paramiko', 'fabric', 'ansible', 'pexpect', 'pty',
    'ctypes', 'multiprocessing', 'threading', 'signal', 'resource',
    'pickle', 'marshal', 'shelve', 'dbm', 'sqlite3', 'psycopg2',
    'mysql', 'pymongo', 'redis', 'memcache', 'kafka', 'celery',
    'scapy', 'nmap', 'impacket', 'pwn', 'pwntools', 'angr'
}

DANGEROUS_FUNCTIONS = [
    'eval', 'exec', 'compile', 'execfile', 'open', 'file',
    'input', 'raw_input', '__import__', 'reload', 'getattr',
    'setattr', 'delattr', 'hasattr', 'vars', 'dir', 'type',
    'globals', 'locals', 'callable', 'issubclass', 'isinstance',
    'super', 'classmethod', 'staticmethod', 'property'
]

NETWORK_PATTERNS = [
    r'socket\.', r'urllib', r'requests\.', r'http\.',
    r'httplib', r'ftplib', r'telnetlib', r'smtplib',
    r'poplib', r'imaplib', r'\.connect\(', r'\.bind\(',
    r'\.listen\(', r'\.accept\(', r'\.send\(', r'\.recv\(',
    r'urlopen', r'urlretrieve', r'HTTPConnection',
    r'HTTPSConnection', r'ProxyHandler', r'build_opener'
]

FILESYSTEM_PATTERNS = [
    r'os\.remove', r'os\.rmdir', r'os\.unlink', r'os\.chmod',
    r'os\.chown', r'os\.chdir', r'os\.mkdir', r'os\.makedirs',
    r'os\.symlink', r'os\.link', r'os\.rename', r'os\.renames',
    r'os\.replace', r'os\.truncate', r'os\.stat', r'os\.lstat',
    r'os\.access', r'os\.listdir', r'os\.walk', r'os\.scandir',
    r'shutil\.', r'glob\.', r'fnmatch\.', r'pathlib\.',
    r'\.read\(\)', r'\.write\(', r'\.seek\(', r'\.truncate\('
]

PROCESS_PATTERNS = [
    r'os\.system', r'os\.popen', r'os\.exec', r'os\.spawn',
    r'os\.fork', r'os\.kill', r'os\.wait', r'os\.waitpid',
    r'subprocess\.', r'commands\.', r'popen2', r'pexpect',
    r'pty\.', r'signal\.', r'\.kill\(', r'\.terminate\(',
    r'\.send_signal\(', r'process', r'Popen', r'CREATE_NEW'
]

SECURITY_BYPASS_PATTERNS = [
    r'__builtins__', r'__builtin__', r'builtins', r'builtin',
    r'__class__', r'__bases__', r'__mro__', r'__subclasses__',
    r'__globals__', r'__code__', r'__closure__', r'__dict__',
    r'__func__', r'__self__', r'__module__', r'__name__',
    r'__qualname__', r'__annotations__', r'__kwdefaults__',
    r'__defaults__', r'__doc__', r'__init__', r'__new__',
    r'__del__', r'__call__', r'__getattribute__', r'__getattr__',
    r'__setattr__', r'__delattr__', r'__getitem__', r'__setitem__',
    r'__delitem__', r'__iter__', r'__next__', r'__enter__',
    r'__exit__', r'__len__', r'__str__', r'__repr__',
    r'chr\(', r'ord\(', r'hex\(', r'oct\(', r'bin\(',
    r'base64', r'codecs', r'encode\(', r'decode\(', r'unicode',
    r'utf-8', r'ascii', r'latin', r'escape', r'unescape'
]

def scan_content(content):
    if not content:
        return True, ''
    if len(content) > 10 * 1024 * 1024:
        return False, 'Content exceeds maximum allowed size of 10MB'
    detected = []
    for pattern in BLOCKED_PATTERNS:
        if pattern.lower() in content.lower():
            detected.append(pattern)
    if detected:
        return False, f'Blocked patterns detected: {", ".join(detected[:5])}'
    return True, ''

def block_dangerous_imports(code):
    if not code:
        return True, ''
    lines = code.split('\n')
    dangerous_found = []
    for line in lines:
        line = line.strip()
        if line.startswith('import ') or line.startswith('from '):
            tokens = line.replace('import', ' ').replace('from', ' ').replace(',', ' ').split()
            for token in tokens:
                token = token.strip()
                if token in DANGEROUS_IMPORTS:
                    dangerous_found.append(token)
        if 'as ' in line:
            parts = line.split(' as ')
            if len(parts) == 2:
                alias = parts[1].strip()
                if alias in DANGEROUS_IMPORTS:
                    dangerous_found.append(f'alias:{alias}')
    if dangerous_found:
        return False, f'Blocked imports: {", ".join(dangerous_found)}'
    return True, ''

def is_command_safe(content):
    if not content:
        return True
    safe, msg = scan_content(content)
    if not safe:
        return False
    safe, msg = block_dangerous_imports(content)
    if not safe:
        return False
    for pattern in NETWORK_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return False
    for pattern in FILESYSTEM_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return False
    for pattern in PROCESS_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return False
    for pattern in SECURITY_BYPASS_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            return False
    shell_command_patterns = [
        r'rm\s+', r'rmdir\s+', r'del\s+', r'format\s+',
        r'mkfs\.', r'dd\s+', r'wget\s+', r'curl\s+',
        r'nc\s+', r'netcat\s+', r'telnet\s+', r'ssh\s+',
        r'scp\s+', r'rsync\s+', r'chmod\s+', r'chown\s+',
        r'mount\s+', r'umount\s+', r'fdisk\s+', r'parted\s+',
        r'mkfs\s+', r'mkswap\s+', r'swapon\s+', r'swapoff\s+'
    ]
    for pattern in shell_command_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return False
    obfuscation_patterns = [
        r'exec\s*\(', r'eval\s*\(', r'compile\s*\(',
        r'__import__\s*\(', r'getattr\s*\(', r'setattr\s*\(',
        r'base64\.b64decode', r'codecs\.decode',
        r'\\x[0-9a-fA-F]{2}', r'\\u[0-9a-fA-F]{4}',
        r'\\U[0-9a-fA-F]{8}', r'\\[0-7]{3}'
    ]
    for pattern in obfuscation_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return False
    return True

def deep_scan_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return is_command_safe(content)
    except:
        return False

def scan_binary_file(filepath):
    try:
        with open(filepath, 'rb') as f:
            header = f.read(1024)
        executable_signatures = [
            b'MZ', b'\x7fELF', b'\xca\xfe\xba\xbe',
            b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf',
            b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe',
            b'#!', b'\x00\x00\x00\x00'
        ]
        for sig in executable_signatures:
            if header.startswith(sig):
                return False
        return True
    except:
        return False

def sanitize_code_for_storage(code):
    if not code:
        return code
    code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'""".*?"""', '""', code, flags=re.DOTALL)
    code = re.sub(r"'''.*?'''", "''", code, flags=re.DOTALL)
    return code