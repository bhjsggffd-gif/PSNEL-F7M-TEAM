import os
import sys
import resource
import signal
import subprocess
import tempfile
import threading
import time
from config import SANDBOX_TIMEOUT, SANDBOX_MAX_MEMORY, MAX_CPU_PERCENT

class SandboxError(Exception):
    pass

class SandboxTimeout(Exception):
    pass

class SandboxMemoryError(Exception):
    pass

class SandboxSecurityError(Exception):
    pass

def set_resource_limits():
    try:
        resource.setrlimit(resource.RLIMIT_AS, (SANDBOX_MAX_MEMORY, SANDBOX_MAX_MEMORY))
    except:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (SANDBOX_TIMEOUT, SANDBOX_TIMEOUT))
    except:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))
    except:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (50, 50))
    except:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
    except:
        pass

def restrict_imports():
    allowed_modules = {
        'math', 'random', 'datetime', 'time', 'collections',
        'itertools', 'functools', 'json', 'csv', 're', 'string',
        'typing', 'decimal', 'fractions', 'statistics', 'hashlib',
        'base64', 'binascii', 'hmac', 'uuid', 'copy', 'pprint',
        'textwrap', 'enum', 'dataclasses', 'operator', 'logging',
        'pathlib', 'os.path', 'tempfile', 'io', 'contextlib',
        'abc', 'atexit', 'argparse', 'configparser', 'shlex'
    }
    import builtins
    original_import = builtins.__import__
    def restricted_import(name, *args, **kwargs):
        if name not in allowed_modules:
            if not any(name.startswith(f'{mod}.') for mod in allowed_modules):
                raise ImportError(f'Import of {name} is not allowed in sandbox')
        return original_import(name, *args, **kwargs)
    builtins.__import__ = restricted_import
    try:
        import os as os_module
        os_module.system = lambda *a, **kw: (_ for _ in ()).throw(PermissionError('os.system is disabled'))
        os_module.popen = lambda *a, **kw: (_ for _ in ()).throw(PermissionError('os.popen is disabled'))
        os_module.execv = lambda *a, **kw: (_ for _ in ()).throw(PermissionError('os.execv is disabled'))
        os_module.execve = lambda *a, **kw: (_ for _ in ()).throw(PermissionError('os.execve is disabled'))
        os_module.spawnv = lambda *a, **kw: (_ for _ in ()).throw(PermissionError('os.spawnv is disabled'))
        os_module.spawnve = lambda *a, **kw: (_ for _ in ()).throw(PermissionError('os.spawnve is disabled'))
        os_module.kill = lambda *a, **kw: (_ for _ in ()).throw(PermissionError('os.kill is disabled'))
    except:
        pass

def secure_environment():
    env = {}
    safe_vars = ['PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'TZ']
    for var in safe_vars:
        if var in os.environ:
            env[var] = os.environ[var]
    env['PATH'] = '/usr/local/bin:/usr/bin:/bin'
    env['HOME'] = tempfile.mkdtemp(prefix='sandbox_home_')
    env['TMPDIR'] = tempfile.mkdtemp(prefix='sandbox_tmp_')
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    return env

def execute_in_sandbox(code, globals_dict=None, locals_dict=None):
    if globals_dict is None:
        globals_dict = {'__builtins__': __builtins__}
    if locals_dict is None:
        locals_dict = {}
    try:
        compiled = compile(code, '<sandbox>', 'exec')
        exec(compiled, globals_dict, locals_dict)
        return locals_dict
    except SandboxError:
        raise
    except Exception as e:
        raise SandboxError(f'Sandbox execution failed: {str(e)}')

def create_sandbox_env(server_dir):
    restricted_dirs = []
    home_dir = os.path.join(server_dir, '.sandbox_home')
    tmp_dir = os.path.join(server_dir, '.sandbox_tmp')
    os.makedirs(home_dir, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)
    os.chmod(home_dir, 0o700)
    os.chmod(tmp_dir, 0o700)
    restricted_dirs.append(home_dir)
    restricted_dirs.append(tmp_dir)
    allowed_write_dirs = [server_dir, home_dir, tmp_dir]
    return {
        'home': home_dir,
        'tmp': tmp_dir,
        'restricted': restricted_dirs,
        'allowed_write': allowed_write_dirs
    }

def destroy_sandbox(sandbox_env):
    import shutil
    for d in sandbox_env.get('restricted', []):
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
            except:
                pass

def get_sandbox_status(sandbox_env):
    status = {
        'home_exists': os.path.exists(sandbox_env.get('home', '')),
        'tmp_exists': os.path.exists(sandbox_env.get('tmp', '')),
        'active': bool(sandbox_env)
    }
    if status['home_exists']:
        home_size = 0
        for dirpath, dirnames, filenames in os.walk(sandbox_env['home']):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    home_size += os.path.getsize(fp)
                except:
                    pass
        status['home_size_bytes'] = home_size
    return status

def timeout_handler(signum, frame):
    raise SandboxTimeout('Execution timed out')

def memory_handler():
    raise SandboxMemoryError('Memory limit exceeded')

def run_with_limits(func, args=(), kwargs=None, timeout=SANDBOX_TIMEOUT):
    if kwargs is None:
        kwargs = {}
    result = [None]
    error = [None]
    def target():
        try:
            set_resource_limits()
            signal.signal(signal.SIGXCPU, timeout_handler)
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            result[0] = func(*args, **kwargs)
        except Exception as e:
            error[0] = e
        finally:
            signal.alarm(0)
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout + 5)
    if thread.is_alive():
        raise SandboxTimeout(f'Execution exceeded timeout of {timeout} seconds')
    if error[0]:
        raise error[0]
    return result[0]

def validate_python_syntax(code):
    try:
        compile(code, '<validation>', 'exec')
        return True, 'Syntax is valid'
    except SyntaxError as e:
        return False, f'Syntax error: {str(e)}'
    except Exception as e:
        return False, f'Validation error: {str(e)}'

def clean_temp_files(sandbox_env):
    tmp_dir = sandbox_env.get('tmp', '')
    if os.path.exists(tmp_dir):
        for item in os.listdir(tmp_dir):
            item_path = os.path.join(tmp_dir, item)
            try:
                if os.path.isfile(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    import shutil
                    shutil.rmtree(item_path)
            except:
                pass

def isolate_network():
    os.environ.pop('http_proxy', None)
    os.environ.pop('https_proxy', None)
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)
    os.environ.pop('no_proxy', None)
    os.environ.pop('NO_PROXY', None)
    try:
        import socket
        socket.setdefaulttimeout(1)
        original_create_connection = socket.create_connection
        def blocked_connection(*args, **kwargs):
            raise PermissionError('Network connections are not allowed in sandbox')
        socket.create_connection = blocked_connection
    except:
        pass

def enforce_permissions(sandbox_env, filepath):
    allowed_dirs = sandbox_env.get('allowed_write', [])
    real_path = os.path.realpath(filepath)
    is_allowed = False
    for allowed_dir in allowed_dirs:
        allowed_real = os.path.realpath(allowed_dir)
        if real_path.startswith(allowed_real):
            is_allowed = True
            break
    if not is_allowed:
        raise SandboxSecurityError(f'Access denied to {filepath}')
    return True