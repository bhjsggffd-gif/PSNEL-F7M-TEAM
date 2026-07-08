import os
import sys
import subprocess
import signal
import psutil
import time
import threading
import socket

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVERS_DIR = os.path.join(BASE_DIR, 'servers')
MAX_RAM_MB = 512
MAX_CPU_PERCENT = 50

active_processes = {}
process_output_threads = {}

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return '127.0.0.1'

LOCAL_IP = get_local_ip()

def start_server_process(username, server_name, port, server_id, app_type='python', output_callback=None):
    """
    تشغيل عملية السيرفر وإرجاع المخرجات الحقيقية 100% من stdout/stderr
    """
    server_dir = os.path.join(SERVERS_DIR, username, server_name)
    venv_dir = os.path.join(server_dir, '.venv_' + server_name)
    
    if not os.path.exists(server_dir):
        if output_callback:
            output_callback(f"Error: Server directory not found: {server_dir}", True)
        return None
    
    # تحديد ملف الإدخال الرئيسي
    main_file = os.path.join(server_dir, 'main.py')
    app_file = os.path.join(server_dir, 'app.py')
    
    target_file = None
    if os.path.exists(app_file):
        target_file = app_file
    elif os.path.exists(main_file):
        target_file = main_file
    else:
        if output_callback:
            output_callback(f"Error: No main.py or app.py found in {server_dir}", True)
        return None
    
    # إيقاف العملية القديمة إذا وجدت
    if server_id in active_processes:
        try:
            stop_server_process(server_id)
        except:
            pass
    
    # إعداد البيئة
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['SERVER_PORT'] = str(port)
    env['PORT'] = str(port)
    env['FLASK_RUN_PORT'] = str(port)
    env['FLASK_RUN_HOST'] = '0.0.0.0'
    
    # تحديد مسار Python (استخدام البيئة الافتراضية إذا وجدت)
    python_exe = sys.executable
    
    if os.path.exists(venv_dir):
        if os.name == 'nt':
            venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')
        else:
            venv_python = os.path.join(venv_dir, 'bin', 'python')
            if not os.path.exists(venv_python):
                venv_python = os.path.join(venv_dir, 'bin', 'python3')
        if os.path.exists(venv_python):
            python_exe = venv_python
    
    # تثبيت المتطلبات إذا وجدت
    req_path = os.path.join(server_dir, 'requirements.txt')
    if os.path.exists(req_path):
        if output_callback:
            output_callback(f"Installing requirements from {req_path}...")
        try:
            pip_process = subprocess.Popen(
                [python_exe, '-m', 'pip', 'install', '-r', 'requirements.txt', '--quiet'],
                cwd=server_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            
            # قراءة مخرجات pip وإرسالها حقيقية
            for line in iter(pip_process.stdout.readline, ''):
                if line.strip() and output_callback:
                    output_callback(line.strip())
            
            pip_process.wait(timeout=120)
            
            if pip_process.returncode == 0:
                if output_callback:
                    output_callback("Requirements installed successfully")
            else:
                if output_callback:
                    output_callback(f"Warning: Some requirements failed to install", True)
                    
        except subprocess.TimeoutExpired:
            if output_callback:
                output_callback("Error: Requirements installation timed out", True)
        except Exception as e:
            if output_callback:
                output_callback(f"Error installing requirements: {str(e)}", True)
    
    # تشغيل العملية الرئيسية
    try:
        if output_callback:
            output_callback(f"Starting: {os.path.basename(target_file)}")
            output_callback(f"Working directory: {server_dir}")
            output_callback(f"Python: {python_exe}")
            output_callback(f"Port: {port}")
        
        # إعداد preexec_fn لإنشاء مجموعة عمليات جديدة (لأنظمة Unix)
        preexec_fn = None
        if os.name != 'nt':
            preexec_fn = os.setsid
        
        process = subprocess.Popen(
            [python_exe, '-u', target_file],
            cwd=server_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            preexec_fn=preexec_fn
        )
        
        active_processes[server_id] = process
        
        # دالة لقراءة المخرجات من stdout (مخرجات حقيقية 100%)
        def read_stdout(pipe):
            try:
                for line in iter(pipe.readline, ''):
                    if line and output_callback:
                        line = line.rstrip('\n\r')
                        if line:
                            output_callback(line)
            except Exception as e:
                if output_callback:
                    output_callback(f"Error reading stdout: {str(e)}", True)
        
        # دالة لقراءة المخرجات من stderr (أخطاء حقيقية 100%)
        def read_stderr(pipe):
            try:
                for line in iter(pipe.readline, ''):
                    if line and output_callback:
                        line = line.rstrip('\n\r')
                        if line:
                            output_callback(line, True)  # تمرير is_error=True
            except Exception as e:
                if output_callback:
                    output_callback(f"Error reading stderr: {str(e)}", True)
        
        stdout_thread = threading.Thread(target=read_stdout, args=(process.stdout,), daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, args=(process.stderr,), daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        
        process_output_threads[server_id] = (stdout_thread, stderr_thread)
        
        return process
        
    except Exception as e:
        if output_callback:
            output_callback(f"Error starting process: {str(e)}", True)
        return None

def stop_server_process(server_id):
    """إيقاف عملية السيرفر"""
    if server_id not in active_processes:
        return False
    
    process = active_processes[server_id]
    try:
        pid = process.pid
        
        # محاولة إنهاء العملية بلطف أولاً
        if os.name != 'nt':
            # Unix/Linux: إنهاء مجموعة العمليات بأكملها
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except:
                process.terminate()
        else:
            # Windows
            process.terminate()
        
        # انتظار انتهاء العملية
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # إذا لم تنتهِ، قتلها
            if os.name != 'nt':
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except:
                    process.kill()
            else:
                process.kill()
            process.wait(timeout=3)
            
    except Exception as e:
        try:
            process.kill()
        except:
            pass
    
    # تنظيف
    active_processes.pop(server_id, None)
    process_output_threads.pop(server_id, None)
    
    return True

def read_process_output(server_id):
    """قراءة مخرجات العملية المخزنة (للاستخدام في API)"""
    return []  # سنقوم بتنفيذ هذا لاحقًا إذا لزم الأمر

def is_process_running(server_id):
    """التحقق من أن العملية لا تزال قيد التشغيل"""
    if server_id not in active_processes:
        return False
    
    process = active_processes[server_id]
    return process.poll() is None

def get_process_pid(server_id):
    """الحصول على PID للعملية"""
    if server_id not in active_processes:
        return None
    
    process = active_processes[server_id]
    try:
        return process.pid
    except:
        return None