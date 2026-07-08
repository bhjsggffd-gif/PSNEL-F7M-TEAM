import os
import subprocess
import venv
import shutil
import sys
from threading import Lock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVERS_DIR = os.path.join(BASE_DIR, 'servers')

venv_locks = {}

def get_venv_lock(username, server_name):
    key = f"{username}_{server_name}"
    if key not in venv_locks:
        venv_locks[key] = Lock()
    return venv_locks[key]

def create_venv(username, server_name):
    lock = get_venv_lock(username, server_name)
    with lock:
        server_dir = os.path.join(SERVERS_DIR, username, server_name)
        venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
        if os.path.exists(venv_dir):
            return True, venv_dir
        try:
            builder = venv.EnvBuilder(
                with_pip=True,
                upgrade_deps=False,
                clear=False,
                symlinks=False
            )
            builder.create(venv_dir)
            pip_path = os.path.join(venv_dir, 'bin', 'pip') if os.name != 'nt' else os.path.join(venv_dir, 'Scripts', 'pip.exe')
            subprocess.run(
                [pip_path, 'install', '--upgrade', 'pip', 'setuptools', 'wheel'],
                capture_output=True,
                text=True,
                timeout=60
            )
            return True, venv_dir
        except Exception as e:
            try:
                shutil.rmtree(venv_dir, ignore_errors=True)
            except:
                pass
            return False, str(e)

def remove_venv(username, server_name):
    lock = get_venv_lock(username, server_name)
    with lock:
        server_dir = os.path.join(SERVERS_DIR, username, server_name)
        venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
        if os.path.exists(venv_dir):
            try:
                shutil.rmtree(venv_dir, ignore_errors=True)
                return True, venv_dir
            except Exception as e:
                return False, str(e)
        return True, venv_dir

def install_requirements(username, server_name):
    lock = get_venv_lock(username, server_name)
    with lock:
        server_dir = os.path.join(SERVERS_DIR, username, server_name)
        requirements_file = os.path.join(server_dir, 'requirements.txt')
        venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
        if not os.path.exists(venv_dir):
            success, msg = create_venv(username, server_name)
            if not success:
                return False, msg
        if not os.path.exists(requirements_file):
            return True, 'No requirements file'
        pip_path = os.path.join(venv_dir, 'bin', 'pip') if os.name != 'nt' else os.path.join(venv_dir, 'Scripts', 'pip.exe')
        if not os.path.exists(pip_path):
            return False, 'pip not found'
        try:
            result = subprocess.run(
                [pip_path, 'install', '-r', requirements_file],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=server_dir
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout
        except subprocess.TimeoutExpired:
            return False, 'Installation timed out'
        except Exception as e:
            return False, str(e)

def install_package(username, server_name, package_name):
    lock = get_venv_lock(username, server_name)
    with lock:
        server_dir = os.path.join(SERVERS_DIR, username, server_name)
        venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
        if not os.path.exists(venv_dir):
            success, msg = create_venv(username, server_name)
            if not success:
                return False, msg
        pip_path = os.path.join(venv_dir, 'bin', 'pip') if os.name != 'nt' else os.path.join(venv_dir, 'Scripts', 'pip.exe')
        if not os.path.exists(pip_path):
            return False, 'pip not found'
        safe_package_name = package_name.strip()
        if ';' in safe_package_name or '&&' in safe_package_name or '|' in safe_package_name:
            return False, 'Invalid package name'
        if len(safe_package_name) > 100:
            return False, 'Package name too long'
        try:
            result = subprocess.run(
                [pip_path, 'install', safe_package_name],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=server_dir
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout
        except subprocess.TimeoutExpired:
            return False, 'Installation timed out'
        except Exception as e:
            return False, str(e)

def uninstall_package(username, server_name, package_name):
    lock = get_venv_lock(username, server_name)
    with lock:
        server_dir = os.path.join(SERVERS_DIR, username, server_name)
        venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
        if not os.path.exists(venv_dir):
            return False, 'Virtual environment not found'
        pip_path = os.path.join(venv_dir, 'bin', 'pip') if os.name != 'nt' else os.path.join(venv_dir, 'Scripts', 'pip.exe')
        if not os.path.exists(pip_path):
            return False, 'pip not found'
        safe_package_name = package_name.strip()
        try:
            result = subprocess.run(
                [pip_path, 'uninstall', '-y', safe_package_name],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=server_dir
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr or result.stdout
        except subprocess.TimeoutExpired:
            return False, 'Uninstallation timed out'
        except Exception as e:
            return False, str(e)

def list_installed_packages(username, server_name):
    lock = get_venv_lock(username, server_name)
    with lock:
        server_dir = os.path.join(SERVERS_DIR, username, server_name)
        venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
        if not os.path.exists(venv_dir):
            return []
        pip_path = os.path.join(venv_dir, 'bin', 'pip') if os.name != 'nt' else os.path.join(venv_dir, 'Scripts', 'pip.exe')
        if not os.path.exists(pip_path):
            return []
        try:
            result = subprocess.run(
                [pip_path, 'list', '--format=json'],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=server_dir
            )
            if result.returncode == 0:
                import json
                return json.loads(result.stdout)
            return []
        except:
            return []

def get_venv_python_path(username, server_name):
    server_dir = os.path.join(SERVERS_DIR, username, server_name)
    venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
    if os.name == 'nt':
        python_path = os.path.join(venv_dir, 'Scripts', 'python.exe')
    else:
        python_path = os.path.join(venv_dir, 'bin', 'python')
    if os.path.exists(python_path):
        return python_path
    return sys.executable

def activate_venv(username, server_name):
    server_dir = os.path.join(SERVERS_DIR, username, server_name)
    venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
    if not os.path.exists(venv_dir):
        return False, 'Virtual environment not found'
    activate_script = os.path.join(venv_dir, 'bin', 'activate_this.py')
    if os.name == 'nt':
        activate_script = os.path.join(venv_dir, 'Scripts', 'activate_this.py')
    if os.path.exists(activate_script):
        try:
            with open(activate_script) as f:
                exec(f.read(), {'__file__': activate_script})
            return True, 'Activated'
        except Exception as e:
            return False, str(e)
    return True, 'Virtual environment ready'

def deactivate_venv():
    if 'VIRTUAL_ENV' in os.environ:
        del os.environ['VIRTUAL_ENV']
    return True

def freeze_requirements(username, server_name):
    lock = get_venv_lock(username, server_name)
    with lock:
        server_dir = os.path.join(SERVERS_DIR, username, server_name)
        venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
        requirements_file = os.path.join(server_dir, 'requirements.txt')
        if not os.path.exists(venv_dir):
            return False, 'Virtual environment not found'
        pip_path = os.path.join(venv_dir, 'bin', 'pip') if os.name != 'nt' else os.path.join(venv_dir, 'Scripts', 'pip.exe')
        if not os.path.exists(pip_path):
            return False, 'pip not found'
        try:
            result = subprocess.run(
                [pip_path, 'freeze'],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=server_dir
            )
            if result.returncode == 0:
                with open(requirements_file, 'w') as f:
                    f.write(result.stdout)
                return True, requirements_file
            return False, result.stderr
        except Exception as e:
            return False, str(e)

def cleanup_orphaned_venvs():
    cleaned = 0
    if not os.path.exists(SERVERS_DIR):
        return cleaned
    for username in os.listdir(SERVERS_DIR):
        user_dir = os.path.join(SERVERS_DIR, username)
        if not os.path.isdir(user_dir):
            continue
        for server_name in os.listdir(user_dir):
            server_dir = os.path.join(user_dir, server_name)
            if not os.path.isdir(server_dir):
                continue
            for item in os.listdir(server_dir):
                if item.startswith('.venv_'):
                    main_file = os.path.join(server_dir, 'main.py')
                    if not os.path.exists(main_file):
                        venv_path = os.path.join(server_dir, item)
                        try:
                            shutil.rmtree(venv_path)
                            cleaned += 1
                        except:
                            pass
    return cleaned

def get_venv_size(username, server_name):
    server_dir = os.path.join(SERVERS_DIR, username, server_name)
    venv_dir = os.path.join(server_dir, f'.venv_{server_name}')
    if not os.path.exists(venv_dir):
        return 0
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(venv_dir):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total_size += os.path.getsize(fp)
            except:
                pass
    return total_size