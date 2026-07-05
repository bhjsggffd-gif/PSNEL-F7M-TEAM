import json, os, asyncio, aiohttp, random, secrets, hashlib
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from threading import Thread
import requests

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# ==================== CONSTANTS ====================
VIP_ACCOUNTS = {}
VIP_LOCK = asyncio.Lock()
_loop = None

# ==================== LOAD HTML FILES ====================
def load_html(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()

LOGIN_HTML = load_html('login.html')
INDEX_HTML = load_html('index.html')
ADMIN_HTML = load_html('admin.html')

# ==================== AUTH SYSTEM ====================
def load_users():
    try:
        with open('users.json', 'r') as f:
            return json.load(f)
    except:
        default = {"admin": {"password": "Admin@2099#Necro", "role": "admin", "created": datetime.now().isoformat()}}
        with open('users.json', 'w') as f:
            json.dump(default, f, indent=4)
        return default

def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(users, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session or session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

def log_user_action(username, action, detail=""):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{username}_{datetime.now().strftime('%Y-%m-%d')}.log"
    with open(log_file, 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] {action}: {detail}\n")

# ==================== ASYNC HELPERS ====================
def run_async(coro):
    """تشغيل دالة غير متزامنة في الـ loop الرئيسي"""
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=30)

# ==================== ROUTES ====================
@app.route('/login')
def login_page():
    if 'username' in session:
        return redirect(url_for('index'))
    return render_template_string(LOGIN_HTML)

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    users = load_users()
    if username in users and users[username]['password'] == password:
        session.permanent = True
        session['username'] = username
        session['role'] = users[username]['role']
        return jsonify({'status': 'success', 'role': session['role']})
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    username = session.get('username')
    if username in VIP_ACCOUNTS:
        for v in VIP_ACCOUNTS[username]:
            if 'task' in v and not v['task'].done():
                v['task'].cancel()
        VIP_ACCOUNTS.pop(username, None)
    session.clear()
    return jsonify({'status': 'logged out'})

@app.route('/')
@login_required
def index():
    return render_template_string(INDEX_HTML, 
                                  username=session['username'], 
                                  role=session['role'])

# ==================== SPAM API ====================
@app.route('/api/spam/start', methods=['POST'])
@login_required
def spam_start():
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id or not user_id.isdigit():
        return jsonify({'error': 'Invalid user_id'}), 400
    
    username = session['username']
    url = f"https://rooom-production.up.railway.app/spam?user_id={user_id}"
    
    try:
        response = requests.get(url, timeout=10)
        log_user_action(username, "SPAM_START", f"user_id:{user_id} | status:{response.status_code}")
        return jsonify({
            'status': 'success' if response.status_code == 200 else 'error',
            'user_id': user_id,
            'message': '✅ تم بدء السبام بنجاح' if response.status_code == 200 else f'⚠️ فشل: {response.status_code}'
        })
    except Exception as e:
        log_user_action(username, "SPAM_START_ERROR", f"user_id:{user_id} | error:{str(e)[:50]}")
        return jsonify({'error': f'Connection error: {str(e)}'}), 500

@app.route('/api/spam/stop', methods=['POST'])
@login_required
def spam_stop():
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id or not user_id.isdigit():
        return jsonify({'error': 'Invalid user_id'}), 400
    
    username = session['username']
    url = f"https://rooom-production.up.railway.app/stop?user_id={user_id}"
    
    try:
        response = requests.get(url, timeout=10)
        log_user_action(username, "SPAM_STOP", f"user_id:{user_id} | status:{response.status_code}")
        return jsonify({
            'status': 'success' if response.status_code == 200 else 'error',
            'user_id': user_id,
            'message': '⏹ تم إيقاف السبام' if response.status_code == 200 else f'⚠️ فشل: {response.status_code}'
        })
    except Exception as e:
        log_user_action(username, "SPAM_STOP_ERROR", f"user_id:{user_id} | error:{str(e)[:50]}")
        return jsonify({'error': f'Connection error: {str(e)}'}), 500

# ==================== VIP BOT API ====================
async def async_vip_add(username, uid, password, player_id):
    """الدالة غير المتزامنة لإضافة VIP"""
    url = f"https://jagwar-api-add-rem.vercel.app/add_friend?uid={uid}&password={password}&player_id={player_id}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    # جدولة الحذف التلقائي بعد ساعتين
                    async def schedule_remove():
                        await asyncio.sleep(7200)
                        try:
                            remove_url = f"https://jagwar-api-add-rem.vercel.app/remove_friend?uid={uid}&password={password}&player_id={player_id}"
                            async with aiohttp.ClientSession() as sess:
                                async with sess.get(remove_url) as resp:
                                    log_user_action(username, "VIP_AUTO_REMOVE", f"player_id:{player_id} | status:{resp.status}")
                        except Exception as e:
                            log_user_action(username, "VIP_AUTO_REMOVE_ERROR", f"player_id:{player_id} | error:{str(e)[:50]}")
                        finally:
                            async with VIP_LOCK:
                                if username in VIP_ACCOUNTS:
                                    VIP_ACCOUNTS[username] = [v for v in VIP_ACCOUNTS[username] if v.get('player_id') != player_id]
                    
                    task = asyncio.create_task(schedule_remove())
                    
                    async with VIP_LOCK:
                        if username not in VIP_ACCOUNTS:
                            VIP_ACCOUNTS[username] = []
                        VIP_ACCOUNTS[username].append({
                            'uid': uid,
                            'pwd': password,
                            'player_id': player_id,
                            'added_at': datetime.now().isoformat(),
                            'task': task
                        })
                    
                    log_user_action(username, "VIP_ADD", f"player_id:{player_id}")
                    return {
                        'status': 'success',
                        'player_id': player_id,
                        'message': '✅ تم إضافة البوت VIP وسيتم حذفه تلقائياً بعد ساعتين'
                    }
                else:
                    return {
                        'status': 'error',
                        'player_id': player_id,
                        'message': f'⚠️ فشل الإضافة: {response.status}'
                    }
    except Exception as e:
        log_user_action(username, "VIP_ADD_ERROR", f"player_id:{player_id} | error:{str(e)[:50]}")
        return {'error': f'Connection error: {str(e)}'}

@app.route('/api/vip/add', methods=['POST'])
@login_required
def vip_add():
    data = request.get_json()
    uid = data.get('uid')
    password = data.get('password')
    player_id = data.get('player_id')
    
    if not uid or not password or not player_id:
        return jsonify({'error': 'uid, password and player_id required'}), 400
    
    username = session['username']
    result = run_async(async_vip_add(username, uid, password, player_id))
    
    if 'error' in result:
        return jsonify({'error': result['error']}), 500
    return jsonify(result)

async def async_vip_remove(username, uid, password, player_id):
    """الدالة غير المتزامنة لحذف VIP"""
    url = f"https://jagwar-api-add-rem.vercel.app/remove_friend?uid={uid}&password={password}&player_id={player_id}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as response:
                async with VIP_LOCK:
                    if username in VIP_ACCOUNTS:
                        for v in VIP_ACCOUNTS[username]:
                            if v.get('player_id') == player_id and 'task' in v and not v['task'].done():
                                v['task'].cancel()
                        VIP_ACCOUNTS[username] = [v for v in VIP_ACCOUNTS[username] if v.get('player_id') != player_id]
                
                log_user_action(username, "VIP_REMOVE", f"player_id:{player_id} | status:{response.status}")
                return {
                    'status': 'success' if response.status == 200 else 'error',
                    'player_id': player_id,
                    'message': '✅ تم حذف البوت' if response.status == 200 else f'⚠️ فشل: {response.status}'
                }
    except Exception as e:
        log_user_action(username, "VIP_REMOVE_ERROR", f"player_id:{player_id} | error:{str(e)[:50]}")
        return {'error': f'Connection error: {str(e)}'}

@app.route('/api/vip/remove', methods=['POST'])
@login_required
def vip_remove():
    data = request.get_json()
    uid = data.get('uid')
    password = data.get('password')
    player_id = data.get('player_id')
    
    if not uid or not password or not player_id:
        return jsonify({'error': 'uid, password and player_id required'}), 400
    
    username = session['username']
    result = run_async(async_vip_remove(username, uid, password, player_id))
    
    if 'error' in result:
        return jsonify({'error': result['error']}), 500
    return jsonify(result)

@app.route('/api/vip/list', methods=['GET'])
@login_required
def vip_list():
    username = session['username']
    vips = VIP_ACCOUNTS.get(username, [])
    return jsonify({
        'count': len(vips),
        'vips': [{
            'player_id': v.get('player_id'),
            'uid': v.get('uid'),
            'added_at': v.get('added_at')
        } for v in vips]
    })

# ==================== PLAYER INFO API ====================
@app.route('/api/info', methods=['GET'])
@login_required
def player_info():
    uid = request.args.get('uid')
    if not uid or not uid.isdigit():
        return jsonify({'error': 'Invalid uid'}), 400
    
    username = session['username']
    url = f"http://api-of-info-ob54-shappno.vercel.app/info?uid={uid}"
    
    try:
        response = requests.get(url, timeout=10)
        log_user_action(username, "PLAYER_INFO", f"uid:{uid} | status:{response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                return jsonify({'status': 'success', 'uid': uid, 'data': data})
            except:
                return jsonify({'status': 'success', 'uid': uid, 'data': response.text[:500]})
        else:
            return jsonify({'status': 'error', 'uid': uid, 'message': f'Error {response.status_code}'}), 400
    except Exception as e:
        log_user_action(username, "PLAYER_INFO_ERROR", f"uid:{uid} | error:{str(e)[:50]}")
        return jsonify({'error': f'Connection error: {str(e)}'}), 500

# ==================== ADMIN ROUTES ====================
@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    users = load_users()
    return render_template_string(ADMIN_HTML, 
                                  users=users, 
                                  current_user=session['username'])

@app.route('/api/admin/create_user', methods=['POST'])
@login_required
@admin_required
def admin_create_user():
    data = request.get_json()
    new_user = data.get('username')
    new_pass = data.get('password')
    
    if not new_user or not new_pass:
        return jsonify({'error': 'Username and password required'}), 400
    
    users = load_users()
    if new_user in users:
        return jsonify({'error': 'User already exists'}), 400
    
    users[new_user] = {
        'password': new_pass,
        'role': 'user',
        'created': datetime.now().isoformat()
    }
    save_users(users)
    log_user_action(session['username'], "CREATE_USER", f"Created user: {new_user}")
    return jsonify({'status': 'User created successfully'})

@app.route('/api/admin/delete_user_data', methods=['POST'])
@login_required
@admin_required
def admin_delete_user_data():
    data = request.get_json()
    username = data.get('username')
    if username == 'admin':
        return jsonify({'error': 'Cannot delete admin'}), 400
    
    users = load_users()
    if username in users:
        del users[username]
        save_users(users)
    
    if username in VIP_ACCOUNTS:
        for v in VIP_ACCOUNTS[username]:
            if 'task' in v and not v['task'].done():
                v['task'].cancel()
        VIP_ACCOUNTS.pop(username, None)
    
    return jsonify({'status': 'success', 'message': f'All data for {username} deleted'})

# ==================== USER LOGS ====================
@app.route('/api/user/logs', methods=['GET'])
@login_required
def user_get_logs():
    username = session['username']
    log_file = Path("logs") / f"{username}_{datetime.now().strftime('%Y-%m-%d')}.log"
    if not log_file.exists():
        return jsonify({'logs': []})
    with open(log_file, 'r') as f:
        lines = f.readlines()[-50:]
    return jsonify({'logs': [l.strip() for l in lines]})

# ==================== MAIN ====================
if __name__ == '__main__':
    from threading import Thread
    
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    
    def run_flask():
        app.run(host='0.0.0.0', port=20165, threaded=True, use_reloader=False, debug=False)
    
    def run_loop():
        asyncio.set_event_loop(_loop)
        _loop.run_forever()
    
    Thread(target=run_loop, daemon=True).start()
    print("[*] AMINE BOT MANAGER v.ω.16")
    print("[*] All files in single folder")
    print("[*] Flask running on http://0.0.0.0:20165")
    run_flask()