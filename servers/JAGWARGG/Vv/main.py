import requests, os, json, binascii, time, urllib3, socket, threading, random, string, sys
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from concurrent.futures import ThreadPoolExecutor
from threading import Thread, Lock
from datetime import datetime
from flask import Flask, request, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

K0 = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
V0 = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])

LOGIN_URL   = 'https://loginbp.ggpolarbear.com/MajorLogin'
DATA_URL    = 'https://clientbp.ggpolarbear.com/GetLoginData'
GARENA_URL  = 'https://100067.connect.garena.com/oauth/guest/token/grant'
OB          = 'OB53'
UNITY_VER   = '2022.3.47f1'

flaskApp     = Flask(__name__)
cliLock      = Lock()
clients      = {}

def ldAccs():
    with open('accs.json') as f:
        return json.load(f)

def rClr():
    colors = ['FF9999','99FF99','99CCFF','FFD700','FFB6C1','FFA07A','98FB98',
              'E6E6FA','AFEEEE','F0E68C','FFE4B5','D8BFD8','FFFACD','87CEFA',
              'FFDEAD','B0E0E6','FFDAB9','E0FFFF','F5DEB3','FFC0CB','ADD8E6']
    return random.choice(colors)

def rDev():
    v = random.choice(['4.0.18P6','4.1.0P3','5.0.1B2','5.2.0B1','5.3.2P2'])
    m = random.choice(['SM-A125F','SM-A325M','Redmi 9A','POCO M3','CPH2239'])
    a = random.choice(['9','10','11','12','13'])
    l = random.choice(['en-US','pt-BR','id-ID'])
    c = random.choice(['USA','BRA','IDN'])
    return f'GarenaMSDK/{v}({m};Android {a};{l};{c};)'

def eAes(hx):
    return AES.new(K0, AES.MODE_CBC, V0).encrypt(pad(bytes.fromhex(hx), 16)).hex()

def ePkt(hx, k, v):
    return AES.new(k, AES.MODE_CBC, v).encrypt(pad(bytes.fromhex(hx), 16)).hex()

def eVr(n):
    h = []
    while True:
        b = n & 0x7F
        n >>= 7
        if n: 
            b |= 0x80
        h.append(b)
        if not n: 
            break
    return bytes(h)

def dHex(h):
    f = hex(h)[2:]
    return ('0' + f) if len(f) == 1 else f

def mkV(fn, v): 
    return eVr((fn << 3) | 0) + eVr(v)

def mkL(fn, v):
    ev = v.encode() if isinstance(v, str) else v
    return eVr((fn << 3) | 2) + eVr(len(ev)) + ev

def mkPb(flds):
    pk = bytearray()
    for f, v in flds.items():
        if isinstance(v, dict):           
            pk.extend(mkL(f, mkPb(v)))
        elif isinstance(v, int):          
            pk.extend(mkV(f, v))
        elif isinstance(v, (str, bytes)): 
            pk.extend(mkL(f, v))
    return pk

def _vI(b, i):
    x = s = 0
    while True:
        c = b[i]
        i += 1
        x |= (c & 0x7F) << s
        if c < 0x80: 
            break
        s += 7
    return x, i

def pRaw(data):
    b = data if isinstance(data, (bytes, bytearray)) else bytes.fromhex(data)
    i, r = 0, {}
    while i < len(b):
        try:
            H, i = _vI(b, i)
            F, T = H >> 3, H & 7
            if T == 0: 
                r[F], i = _vI(b, i)
            elif T == 2:
                L, i = _vI(b, i)
                r[F] = b[i:i+L]
                i += L
            elif T == 1: 
                r[F] = int.from_bytes(b[i:i+8], 'little')
                i += 8
            else: 
                break
        except: 
            break
    return r

def pStr(data):
    b = data if isinstance(data, (bytes, bytearray)) else bytes.fromhex(data)
    i, r = 0, {}
    while i < len(b):
        try:
            H, i = _vI(b, i)
            F, T = H >> 3, H & 7
            if T == 0: 
                r[str(F)], i = _vI(b, i)
            elif T == 2:
                L, i = _vI(b, i)
                c = b[i:i+L]
                i += L
                try: 
                    r[str(F)] = c.decode()
                except:
                    try: 
                        r[str(F)] = pStr(c)
                    except: 
                        r[str(F)] = c.hex()
            elif T == 1: 
                r[str(F)] = int.from_bytes(b[i:i+8], 'little')
                i += 8
            else: 
                break
        except: 
            break
    return r

def mkPkt(hx, hdr, k, v):
    enc = ePkt(hx, k, v)
    ln = dHex(len(enc) // 2)
    # Pad length to 6 characters
    ln = ln.zfill(6)
    return bytes.fromhex(hdr + ln + enc)

def eUid(h):
    x, e = int(h), []
    while x:
        e.append((x & 0x7F) | (0x80 if x > 0x7F else 0))
        x >>= 7
    return bytes(e).hex()

def mkAuth(uid, tok, ts, k, v):
    uh = hex(uid)[2:]
    ul = len(uh)
    padding = {9:'0000000', 8:'00000000', 10:'000000', 7:'000000000'}.get(ul, '0000000')
    ep = ePkt(tok.encode().hex(), k, v)
    return f'0115{padding}{uh}{dHex(ts)}00000{dHex(len(ep)//2)}{ep}'

def pJwt(tok):
    seg = tok.split('.')[1]
    seg += '=' * (-len(seg) % 4)
    import base64 as _b64
    return json.loads(_b64.urlsafe_b64decode(seg))

def gKIv(data):
    try:
        r = pRaw(data)
        return r.get(21, 0), r.get(22, b''), r.get(23, b'')
    except: 
        return None, None, None

def mkLoginPl(at, oid):
    dT = bytes.fromhex(
        '1a13323032352d31312d32362030313a35313a3238220966726565206669726528013a07'
        '312e3132332e384232416e64726f6964204f532039202f204150492d3238202850492f72'
        '656c2e636a772e32303232303531382e313134313333294a0848616e6468656c64520c4d'
        '544e2f537061636574656c5a045749464960800a68d00572033234307a2d7838362d3634'
        '205353453320535345342e3120535345342e32204156582041565832207c2032343030207c'
        '20348001e61e8a010f416472656e6f2028544d292036343092010d4f70656e474c205353'
        '20332e329a012b476f6f676c657c36323566373136662d393161372d343935622d396631'
        '362d303866653964336336353333a2010e3137362e32382e3133392e313835aa01026172'
        'b201203433303632343537393364653836646134323561353263616164663231656564ba01'
        '0134c2010848616e6468656c64ca010d4f6e65506c7573204135303130ea014063363961'
        '653230386661643732373338623637346232383437623530613361316466613235643161'
        '313966616537343566633736616334613065343134633934f00101ca020c4d544e2f5370'
        '61636574656cd2020457494649ca03203161633462383065636630343738613434323033'
        '626638666163363132306635e003b5ee02e8039a8002f003af13f80384078004a78f0288'
        '04b5ee029004a78f029804b5ee02b00404c80401d2043d2f646174612f6170702f636f6d'
        '2e6474732e667265656669726574682d66705843537068495636644b43376a4c2d574f79'
        '52413d3d2f6c69622f61726de00401ea045f65363261623933353464386662356662303831'
        '646233333861636233333439317c2f646174612f6170702f636f6d2e6474732e66726565'
        '6669726574682d66705843537068495636644b43376a4c2d574f7952413d3d2f62617365'
        '2e61706bf00406f804018a050233329a050a32303139313139303236a80503b205094f70'
        '656e474c455332b805ff01c00504e005be7eea05093372645f7061727479f205704b7173'
        '48543857393347646347335a6f7a454e6646775648746d377171316552554e6149444e67'
        '526f626f7a4942744c4f695943633459367a767670634943787a514632734f4534636279'
        '74774c7334785a62526e70524d706d5752514b6d654f35766373386e5159426877714837'
        '4bf805e7e4068806019006019a060134a2060134b2062213521146500e590349510e4609'
        '00115843395f005b510f685b560a6107576d0f0366'
    )
    dT = dT.replace(b'2025-11-26 01:51:28', str(datetime.now())[:-7].encode())
    dT = dT.replace(b'c69ae208fad72738b674b2847b50a3a1dfa25d1a19fae745fc76ac4a0e414c94', at.encode())
    dT = dT.replace(b'4306245793de86da425a52caadf21eed', oid.encode())
    return bytes.fromhex(eAes(dT.hex()))

def guestTok(uid, pw):
    h = {'Host':'100067.connect.garena.com','User-Agent':rDev(),
         'Content-Type':'application/x-www-form-urlencoded',
         'Accept-Encoding':'gzip, deflate','Connection':'close'}
    d = {'uid':uid,'password':pw,'response_type':'token','client_type':'2',
         'client_secret':'2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3',
         'client_id':'100067'}
    r = requests.post(GARENA_URL, headers=h, data=d).json()
    return r['access_token'], r['open_id']

def majLogin(at, oid):
    pl = mkLoginPl(at, oid)
    h = {'X-Unity-Version':UNITY_VER, 'ReleaseVersion':OB,
         'Content-Type':'application/x-www-form-urlencoded',
         'X-GA':'v1 1', 'Host':'loginbp.ggpolarbear.com',
         'Connection':'Keep-Alive', 'Accept-Encoding':'gzip'}
    r = requests.post(LOGIN_URL, headers=h, data=pl, verify=False)
    if r.status_code != 200 or len(r.text) < 10: 
        return None
    d = pStr(r.content)
    tok = d.get('8', {}).get('data', d.get('8', '')) if isinstance(d.get('8'), dict) else d.get('8', '')
    ts, k, v = gKIv(r.content)
    return tok, k, v, ts, pl

def dataLogin(tok, pl):
    h = {'Expect':'100-continue','Authorization':f'Bearer {tok}',
         'X-Unity-Version':UNITY_VER,'X-GA':'v1 1','ReleaseVersion':OB,
         'Content-Type':'application/x-www-form-urlencoded',
         'Host':'clientbp.ggpolarbear.com','Connection':'close','Accept-Encoding':'gzip'}
    r = requests.post(DATA_URL, headers=h, data=pl, verify=False)
    d = pStr(r.content)
    a1 = d.get('32', {}).get('data', d.get('32', '')) if isinstance(d.get('32'), dict) else d.get('32', '')
    a2 = d.get('14', {}).get('data', d.get('14', '')) if isinstance(d.get('14'), dict) else d.get('14', '')
    ip, pt = a1[:-6], a1[-5:]
    ip2, pt2 = a2[:-6], a2[-5:]
    return ip, pt, ip2, pt2

def pktJoin(tc, k, v):
    f = {1:4, 2:{4:bytes.fromhex('01090a0b121920'), 5:str(tc), 6:6, 8:1,
                 9:{2:800, 6:11, 8:'1.111.1', 9:5, 10:1}}}
    return mkPkt(mkPb(f).hex(), '0515', k, v)

def pktExit(k, v):
    f = {1:7, 2:{1:int(11037044965)}}
    return mkPkt(mkPb(f).hex(), '0515', k, v)

def pktOpen(tid, sq, k, v):
    f = {1:3, 2:{1:tid, 3:'fr', 4:sq}}
    return mkPkt(mkPb(f).hex(), '1215', k, v)

def pktMsg(msg, tid, k, v):
    f = {1:1, 2:{1:12404281032, 2:tid, 4:msg, 7:2, 10:'fr',
                 9:{1:'xBesTo', 2:902000306, 4:330, 5:909000014, 8:'xBesTo', 10:1, 11:1,
                    12:{1:2}, 14:{1:1158053040,2:8,3:'\u0010\u0015\b\n\u000b\u0015\f\u000f\u0011\u0004\u0007\u0002\u0003\r\u000e\u0012\u0001\u0005\u0006'}},
                 13:{1:2,2:1}, 14:{}}}
    return mkPkt(mkPb(f).hex(), '1215', k, v)


class Client:
    def __init__(self, uid, pw):
        self.uid = uid
        self.pw = pw
        self.key = None
        self.iv = None
        self.sock = None
        self.sock2 = None
        self.data_received = b''
        self.response_event = threading.Event()
        self.response_data = None
        with cliLock: 
            clients[uid] = self
        self._boot()

    def _boot(self):
        at, oid = guestTok(self.uid, self.pw)
        res = majLogin(at, oid)
        if not res: 
            return
        tok, k, v, ts, pl = res
        self.key = k
        self.iv = v
        ip, pt, ip2, pt2 = dataLogin(tok, pl)
        j = pJwt(tok)
        uid_int = j.get('account_id', 0)
        auth = mkAuth(uid_int, tok, ts, k, v)
        Thread(target=self._chat, args=(ip, pt, auth), daemon=True).start()
        Thread(target=self._online, args=(ip2, pt2, auth), daemon=True).start()

    def _chat(self, ip, pt, auth):
        while True:
            try:
                self.sock = socket.create_connection((ip, int(pt)))
                self.sock.send(bytes.fromhex(auth))
                self.sock.recv(1024)
                while True:
                    d = self.sock.recv(99999)
                    if not d: 
                        break
            except Exception as e:
                print(f"Chat error: {e}")
                time.sleep(2)

    def _online(self, ip, pt, auth):
        while True:
            try:
                self.sock2 = socket.create_connection((ip, int(pt)))
                self.sock2.send(bytes.fromhex(auth))
                
                # Set timeout for socket
                self.sock2.settimeout(0.5)
                
                while True:
                    try:
                        chunk = self.sock2.recv(99999)
                        if chunk:
                            self.data_received += chunk
                            # Check if we have a complete packet
                            hex_data = self.data_received.hex()
                            if len(hex_data) >= 10 and '0500' in hex_data[:10]:
                                # Signal that we received a response
                                self.response_data = self.data_received
                                self.response_event.set()
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"Online recv error: {e}")
                        break
            except Exception as e:
                print(f"Online connection error: {e}")
                time.sleep(2)

    def sqInfo(self, tc):
        """جلب معلومات السكواد مع انتظار الاستجابة"""
        try:
            if not self.sock2:
                return {"success": False, "reason": "No secondary connection"}
            
            # Clear previous data
            self.data_received = b''
            self.response_event.clear()
            self.response_data = None
            
            # Send join request
            self.sock2.send(pktJoin(tc, self.key, self.iv))
            
            # Wait for response (max 5 seconds)
            start_time = time.time()
            while time.time() - start_time < 5:
                if self.response_event.wait(timeout=0.5):
                    hex_data = self.response_data.hex()
                    
                    # Check for valid response packet
                    if len(hex_data) >= 10 and '0500' in hex_data[:10]:
                        try:
                            # Parse the response
                            if len(hex_data) > 10:
                                decoded = pStr(self.response_data)
                                
                                # Navigate through the response structure
                                d5 = decoded.get('5', {})
                                if isinstance(d5, dict):
                                    d5_data = d5.get('data', d5)
                                    
                                    # Extract data - try multiple possible field numbers
                                    owner_uid = None
                                    chat_code = None
                                    squad_code = None
                                    
                                    # Try field 1 for owner UID
                                    if '1' in d5_data:
                                        field1 = d5_data['1']
                                        if isinstance(field1, dict):
                                            owner_uid = field1.get('data')
                                        else:
                                            owner_uid = field1
                                    
                                    # Try field 14 or 17 for chat code
                                    if '14' in d5_data:
                                        field14 = d5_data['14']
                                        if isinstance(field14, dict):
                                            chat_code = field14.get('data')
                                        else:
                                            chat_code = field14
                                    elif '17' in d5_data:
                                        field17 = d5_data['17']
                                        if isinstance(field17, dict):
                                            chat_code = field17.get('data')
                                        else:
                                            chat_code = field17
                                    
                                    # Try field 31 for squad code
                                    if '31' in d5_data:
                                        field31 = d5_data['31']
                                        if isinstance(field31, dict):
                                            squad_code = field31.get('data')
                                        else:
                                            squad_code = field31
                                    
                                    if owner_uid and chat_code:
                                        # Send exit packet
                                        self.sock2.send(pktExit(self.key, self.iv))
                                        return {
                                            "success": True,
                                            "owner_uid": owner_uid,
                                            "chat_code": chat_code,
                                            "squad_code": squad_code
                                        }
                                    else:
                                        return {
                                            "success": False,
                                            "reason": f"Missing data: owner={'found' if owner_uid else 'missing'}, chat={'found' if chat_code else 'missing'}"
                                        }
                        except Exception as e:
                            return {"success": False, "reason": f"Parse error: {str(e)}"}
                else:
                    # Continue waiting
                    continue
            
            return {"success": False, "reason": "Timeout waiting for response"}
            
        except Exception as e:
            return {"success": False, "reason": str(e)}

    def spamMsg(self, owner_uid, chat_code, msg):
        """إرسال رسائل spam"""
        try:
            targets = list(clients.values())[:3]
            
            def send_from_client(client):
                try:
                    if client.sock:
                        client.sock.send(pktOpen(owner_uid, chat_code, client.key, client.iv))
                        time.sleep(0.5)
                        for _ in range(100):
                            client.sock.send(pktMsg(f'[b][c][{rClr()}]{msg}', owner_uid, client.key, client.iv))
                            time.sleep(0.3)
                except Exception as e:
                    print(f"Send error from client {client.uid}: {e}")
            
            threads = [Thread(target=send_from_client, args=(c,)) for c in targets]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
            
            return True
        except Exception as e:
            print(f"Spam error: {e}")
            return False


def chkTc(tc):
    return bool(tc and len(tc) >= 6)

@flaskApp.route('/msg', methods=['GET', 'POST'])
def sendMsg():
    """نقطة نهاية API مع إرجاع أسباب الفشل"""
    if request.method == 'GET':
        tc = request.args.get('teamcode')
        msg = request.args.get('message')
    else:
        d = request.get_json()
        tc = d.get('teamcode')
        msg = d.get('message')
    
    if not tc or not msg:
        return jsonify({
            'success': False,
            'error': 'teamcode and message required'
        }), 400
    
    if not chkTc(tc):
        return jsonify({
            'success': False,
            'error': 'invalid teamcode',
            'reason': 'Team code must be at least 6 characters'
        }), 400
    
    with cliLock:
        if not clients:
            return jsonify({
                'success': False,
                'error': 'No connected clients',
                'reason': 'No accounts are currently connected to the server'
            }), 503
        
        # Get first available client
        client = list(clients.values())[0]
    
    # Get squad info
    result = client.sqInfo(tc)
    
    if not result.get("success"):
        return jsonify({
            'success': False,
            'error': 'Failed to get squad info',
            'reason': result.get('reason', 'Unknown error'),
            'teamcode': tc
        }), 400
    
    # Send spam messages
    success = client.spamMsg(result['owner_uid'], result['chat_code'], msg)
    
    if success:
        return jsonify({
            'success': True,
            'message': f'Messages sent successfully to squad: {tc}',
            'details': {
                'owner_uid': result['owner_uid'],
                'chat_code': result['chat_code'],
                'squad_code': result.get('squad_code', '')
            }
        }), 200
    else:
        return jsonify({
            'success': False,
            'error': 'Failed to send messages',
            'reason': 'Error occurred while sending spam messages'
        }), 500

@flaskApp.route('/status', methods=['GET'])
def getStatus():
    with cliLock:
        return jsonify({
            'success': True,
            'connected_accounts': len(clients),
            'accounts': list(clients.keys()),
            'status': 'running'
        }), 200

def bootClients():
    time.sleep(5)
    accs = ldAccs()
    for a in accs:
        Thread(target=lambda x=a: _startClient(x), daemon=True).start()
        time.sleep(5)

def _startClient(a):
    while True:
        try:
            Client(a['id'], a['password'])
            print(f"Started client: {a['id']}")
            break
        except Exception as e:
            print(f"Failed to start client {a['id']}: {e}")
            time.sleep(3)

if __name__ == '__main__':
    print("Starting bot...")
    Thread(target=bootClients, daemon=True).start()
    print("Starting Flask server on port 5000...")
    flaskApp.run(host='0.0.0.0', port=5000, debug=False)