from pyexpat.model import XML_CQUANT_NONE
import requests , os , psutil , sys , jwt , pickle , json , binascii , time , urllib3 , _7aMa_Pb2 , base64 , datetime , re ,socket , threading , http.client , ssl , gzip , asyncio , gc
from io import BytesIO
from protobuf_decoder.protobuf_decoder import Parser
from xC4 import _7aMa_ChaT, _7aMa_InV, _7aMa_MsG, _7aMa_qChanneL, _7aMa_DeC
from xC4 import*
from datetime import datetime , timedelta
from google.protobuf.timestamp_pb2 import Timestamp
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from cfonts import render , say
from rich.console import Console
from rich.panel import Panel
from rich.align import Align
console = Console()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  

def G_AccEss(U , P):
    UrL = "https://100067.connect.garena.com/oauth/guest/token/grant"
    HE = {"Host": "100067.connect.garena.com","User-Agent": Ua(),"Content-Type": "application/x-www-form-urlencoded","Accept-Encoding": "gzip, deflate, br","Connection": "close",}
    dT = {"uid": f"{U}","password": f"{P}","response_type": "token","client_type": "2","client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3","client_id": "100067",}
    try:
        R = requests.post(UrL , headers = HE , data = dT)
        if R.status_code == 200: return R.json()['access_token'] , R.json()['open_id']
        else: 
            print(R.json())
    except Exception as e: 
        print(e) ; ResTarTinG()
                  
def MajorLoGin(PyL):
    context = ssl._create_unverified_context()
    conn = http.client.HTTPSConnection("loginbp.ggpolarbear.com", context=context)    
    headers = {
        'X-Unity-Version': '2018.4.11f1',
        'ReleaseVersion': 'OB52',
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-GA': 'v1 1',
        'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 7.1.2; ASUS_Z01QD Build/QKQ1.190825.002)',
        'Host': 'loginbp.ggpolarbear.com',
        'Connection': 'Keep-Alive',
        'Accept-Encoding': 'gzip'}
    try:
        conn.request("POST", "/MajorLogin", body=PyL, headers=headers)
        response = conn.getresponse()
        raw_data = response.read()
        if response.getheader('Content-Encoding') == 'gzip':
            with gzip.GzipFile(fileobj=BytesIO(raw_data)) as f:
                raw_data = f.read()                
        TexT = raw_data.decode(errors='ignore')
        if 'BR_PLATFORM_INVALID_OPENID' in TexT or 'BR_GOP_TOKEN_AUTH_FAILED' in TexT: sys.exit()
        return raw_data.hex() if response.status in [200,201] else None
    finally: conn.close() 
    
Thread(target = AuTo_ResTartinG , daemon = True).start()
      
class FF_CLient():

    def __init__(self , U , P):  
        self.empty_count = 0  
        self.reader = None ; self.writer = None          
        self.Get_FiNal_ToKen_0115(U , P)  
                    
    async def STarT(self , JwT_ToKen , AutH_ToKen , ip , port, ip2 , port2 , key, iv , bot_uid):
        R = asyncio.Event()
        task1 = asyncio.create_task(self.ChaT(self.JwT_ToKen , self.AutH_ToKen , ip , port , key , iv , bot_uid, R))  
        await R.wait()
        await asyncio.sleep(0.5)
        task2 = asyncio.create_task(self.OnLinE(self.JwT_ToKen , self.AutH_ToKen , ip2 , port2 , key , iv , bot_uid))
        await asyncio.gather(task1)
        
    async def sF(self):
        if self.writer:
            try: self.writer.close() ; await asyncio.sleep(0.2) ; await self.writer.wait_closed()
            except Exception as e: print(f' - Error CLose WriTer => {e}') ; ResTarTinG()
        self.reader = None ; self.writer = None
        gc.collect()

    async def OnLinE(self , Token , tok , host2 , port2 , key , iv , bot_uid):
        T = 'en'
        global writer , writer2 , TarGeT , sQ , Nm
        while True:  
            try: 
                self.reader2 , self.writer2 = await asyncio.open_connection(host2 , int(port2))
                await asyncio.sleep(0.5)
                self.writer2.write(bytes.fromhex(tok)) ; await self.writer2.drain() 
                await asyncio.sleep(0.4)   
                while True:  
                    try:  
                        self.DaTa = await self.reader2.read(9999)
                        if not self.DaTa: await asyncio.sleep(0.2) ; break
                        if self.DaTa.hex().startswith('0500') and len(self.DaTa.hex()) > 100:                            
                            Z = json.loads(DeCode_PackEt(self.DaTa.hex()[10:]))
                            SuQ = _7aMa_DeC(self.PaC)
                            if SuQ == None:
                                pass
                            else:
                                Uuu = Z["5"]["data"]["1"]["data"]
                                
                                self.writer2.write(ExiT(key , iv)) ; await self.writer2.drain()
                                self.writer2.write(Send_GhosTs(Uuu, "[b][c][FFFFFF]InsTa: [b][c]_7aMa_Pb2", SuQ, key, iv));await self.writer2.drain()

                    except (asyncio.TimeoutError , ConnectionResetError , ConnectionAbortedError , asyncio.IncompleteReadError , BrokenPipeError , OSError , Exception) as e: pass 
                          
            except (asyncio.TimeoutError , ConnectionRefusedError , ConnectionResetError , ConnectionAbortedError , asyncio.IncompleteReadError , BrokenPipeError , OSError , Exception) as e: pass 
            
    async def ChaT(self , Token , tok , host , port , key , iv ,bot_uid, R):
        T = 'en'
        print(f'ConNecTed ---->{bot_uid}')
        global writer , writer2 , TarGeT , sQ , Nm
        while True:  
            try: 
                self.reader, self.writer = await asyncio.open_connection(host , int(port))
                self.writer.write(bytes.fromhex(tok)) ; await self.writer.drain()  
                await asyncio.sleep(0.4)   
                self.writer.write(GLobaL(T , key , iv)) ; await self.writer.drain() 
                await asyncio.sleep(0.4)   
                R.set() 
                while True:  
                    try:  
                        self.DaTa = await self.reader.read(9999)
                        if not self.DaTa: await asyncio.sleep(0.2) ; break                        
                        if self.DaTa.hex().startswith("1200") and b"SecretCode" in self.DaTa:
                            U = json.loads(DeCode_PackEt(self.DaTa.hex()[10:]))
                            U2 = json.loads(DeCode_PackEt(self.DaTa.hex()[36:]))
                            Uu = json.loads(U["5"]["data"]["8"]["data"])
                            
                            Nm = U2['9']['data']['1']['data']
                            TarGeT = int(Uu['GroupID'])
                            sQ = Uu['SecretCode']
                            rQ = Uu['RecruitCode']

                            self.writer.write(_7aMa_ChaT(TarGeT , sQ, key , iv))
await self.writer.drain()

msg_text = (
    "[b][c] - [b][c][98F5F9]7aMa [b][c]is HeRe\n\n"
    "[b][c][E4080A]InsTa [b][c][FFFFFF]---> [b][c][EFC3CA]_7aMa_Pb2\n\n"
    "[b][c]FOLLOW ME OR I WILL "
    + xMsGFixinG("[b][c][FF0000]BAN") +
    " [b][c]YOU"
)

msg = xMsGFixinG(msg_text)

self.writer.write(_7aMa_MsG(msg , TarGeT, bot_uid , key , iv))
await self.writer.drain()
                            
                            await asyncio.sleep(1)
                            self.writer2.write(_7aMa_InV(bot_uid,TarGeT,key,iv)); await self.writer2.drain() 
                            self.writer.write(_7aMa_qChanneL(TarGeT ,key , iv)) ; await self.writer.drain() 
                            await asyncio.sleep(1)

                            print("With => {}".format(bot_uid) , "To => {}".format(TarGeT))
                            
                            self.writer2.write(Join_Sq(T , TarGeT , rQ , key , iv)) ; await self.writer2.drain()
                            self.writer2.write(ExiT(key , iv)) ; await self.writer2.drain()
                    except (asyncio.TimeoutError , ConnectionResetError , ConnectionAbortedError , asyncio.IncompleteReadError , BrokenPipeError , OSError , Exception) as e: pass
                          
            except (asyncio.TimeoutError , ConnectionRefusedError , ConnectionResetError , ConnectionAbortedError , asyncio.IncompleteReadError , BrokenPipeError , OSError , Exception) as e: pass
                
    def GeT_Key_Iv(self , serialized_data):
        my_message = _7aMa_Pb2.MyMessage()
        my_message.ParseFromString(serialized_data)
        timestamp , key , iv = my_message.field21 , my_message.field22 , my_message.field23
        timestamp_obj = Timestamp()
        timestamp_obj.FromNanoseconds(timestamp)
        timestamp_seconds = timestamp_obj.seconds
        timestamp_nanos = timestamp_obj.nanos
        combined_timestamp = timestamp_seconds * 1_000_000_000 + timestamp_nanos
        return combined_timestamp , key , iv  
                       
    def GeT_LoGin_PorTs(self , JwT_ToKen , PayLoad):
        self.UrL = 'https://clientbp.ggpolarbear.com/GetLoginData'
        self.HeadErs = {
            'Expect': '100-continue',
            'Authorization': f'Bearer {JwT_ToKen}',
            'X-Unity-Version': '2018.4.11f1',
            'X-GA': 'v1 1',
            'ReleaseVersion': 'OB52',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; G011A Build/PI)',
            'Host': 'clientbp.ggpolarbear.com',
            'Connection': 'close',
            'Accept-Encoding': 'gzip, deflate, br',}       
        try:
            self.Res = requests.post(self.UrL , headers=self.HeadErs , data=PayLoad , verify=False)
            self.BesTo_data = json.loads(DeCode_PackEt(self.Res.content.hex()))  
            address , address2 = self.BesTo_data['32']['data'] , self.BesTo_data['14']['data'] 
            ip , ip2 = address[:len(address) - 6] , address2[:len(address) - 6]
            port , port2 = address[len(address) - 5:] , address2[len(address2) - 5:]                        
            return ip , port , ip2 , port2
        except requests.RequestException as e:
                print(f" - Bad Requests !")
        print(" - Failed To GeT PorTs !")
        return None, None           
        
    def ToKen_GeneRaTe(self , U , P):
        try:
            if U and P: 
                self.PLaFTrom = 4
                self.A , self.O = G_AccEss(U , P)
                self.Version , self.V = '2019118695' , '1.118.8'      
                self.PyL = {
                    3: str(datetime.now())[:-7] ,
                    4: "free fire",
                    5: 1,
                    7: self.V ,
                    8: "Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)",
                    9: "Handheld",
                    10: "Verizon Wireless",
                    11: "WIFI",
                    12: 1280,
                    13: 960,
                    14: "240",
                    15: "x86-64 SSE3 SSE4.1 SSE4.2 AVX AVX2 | 2400 | 4",
                    16: 5951,
                    17: "Adreno (TM) 640",
                    18: "OpenGL ES 3.0",
                    19: "Google|0fc0e446-ca27-4faa-824a-d40d77767de9",
                    20: "20.171.73.202",
                    21: "fr",
                    22: self.O ,
                    23: self.PLaFTrom,
                    24: "Handheld",
                    25: "google G011A",
                    29: self.A ,
                    30: 1,
                    41: "Verizon Wireless",
                    42: "WIFI",
                    57: "1ac4b80ecf0478a44203bf8fac6120f5",
                    60: 32966,
                    61: 29779,
                    62: 2479,
                    63: 914,
                    64: 31176,
                    65: 32966,
                    66: 31176,
                    67: 32966,
                    70: 4,
                    73: 2,
                    74: "/data/app/com.dts.freefireth-g8eDE0T268FtFmnFZ2UpmA==/lib/arm",
                    76: 1,
                    77: "5b892aaabd688e571f688053118a162b|/data/app/com.dts.freefireth-g8eDE0T268FtFmnFZ2UpmA==/base.apk",
                    78: 6,
                    79: 1,
                    81: "32",
                    83: self.Version ,
                    86: "OpenGLES2",
                    87: 255,
                    88: self.PLaFTrom,
                    89: "J\u0003FD\u0004\r_UH\u0003\u000b\u0016_\u0003D^J>\u000fWT\u0000\\=\nQ_;\u0000\r;Z\u0005a",
                    90: "Phoenix",
                    91: "AZ",
                    92: 10214,
                    93: "3rd_party",
                    94: "KqsHT7gtKWkK0gY/HwmdwXIhSiz4fQldX3YjZeK86XBTthKAf1bW4Vsz6Di0S8vqr0Jc4HX3TMQ8KaUU3GeVvYzWF9I=",
                    95: 111207,
                    97: 1,
                    98: 1,
                    99: f"{self.PLaFTrom}" ,
                    100: f"{self.PLaFTrom}"}
            try:                  
                self.PyL = CrEaTe_ProTo(self.PyL).hex()        
                #print(self.PyL)
                self.PaYload = bytes.fromhex(EnC_AEs(self.PyL))
            except: ResTarTinG()
            self.ResPonse = MajorLoGin(self.PaYload)
            if self.ResPonse:
                self.BesTo_data = json.loads(DeCode_PackEt(self.ResPonse))
                #print(self.BesTo_data)
                self.bot_uid = self.BesTo_data['1']['data']
                self.JwT_ToKen = self.BesTo_data['8']['data']          
                self.combined_timestamp , self.key , self.iv = self.GeT_Key_Iv(bytes.fromhex(self.ResPonse))
                ip , port , ip2 , port2 = self.GeT_LoGin_PorTs(self.JwT_ToKen , self.PaYload)
                return self.JwT_ToKen , self.key , self.iv, self.combined_timestamp , ip , port , ip2 , port2,self.bot_uid
        except Exception as e:
            print('From Token Generate ' , e)
            ResTarTinG()
              
    def Get_FiNal_ToKen_0115(self , U , P):
        token , key , iv , Timestamp , ip , port , ip2 , port2 , bot_uid = self.ToKen_GeneRaTe(U , P)
        self.JwT_ToKen = token        
        try:
            self.AfTer_DeC_JwT = jwt.decode(token, options={"verify_signature": False})
            self.AccounT_Uid = self.AfTer_DeC_JwT.get('account_id')
            self.Nm = self.AfTer_DeC_JwT.get('nickname')
            self.H , self.M , self.S = GeT_Time(self.AfTer_DeC_JwT.get('exp'))
            self.Vr = self.AfTer_DeC_JwT.get('release_version')
            self.EncoDed_AccounT = hex(self.AccounT_Uid)[2:]
            self.HeX_VaLue = DecodE_HeX(Timestamp)
            self.TimE_HEx = self.HeX_VaLue
            self.JwT_ToKen_ = token.encode().hex()
        except Exception as e:
            print(f" - Error In ToKen : {e}")
            return
        try:
            self.Header = hex(len(EnC_PacKeT(self.JwT_ToKen_, key, iv)) // 2)[2:]
            length = len(self.EncoDed_AccounT)
            self.__ = '00000000'
            if length == 9: self.__ = '0000000'
            elif length == 8: self.__ = '00000000'
            elif length == 10: self.__ = '000000'
            elif length == 7: self.__ = '000000000'
            else:
                print('Unexpected length encountered')                
            self.Header = f'0115{self.__}{self.EncoDed_AccounT}{self.TimE_HEx}00000{self.Header}'
            self.FiNal_ToKen_0115 = self.Header + EnC_PacKeT(self.JwT_ToKen_, key, iv)
        except Exception as e:
            print(f" - Erorr In Final Token : {e}")            
        self.AutH_ToKen = self.FiNal_ToKen_0115
        #os.system('clear')
        asyncio.run(self.STarT(self.JwT_ToKen , self.AutH_ToKen , ip, port , ip2 , port2 , key,  iv, bot_uid))
        return self.AutH_ToKen , key , iv
  
def load_accounts(file_path="GuesTs.json"):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)        

def StarT_SerVer():
    print(render('Global', colors=['white', 'yellow'], align='center'))
    TexT = f'[TarGeT InFo] > BoTs arE OnLine\n[BoT sTaTus] > [bold green]ConEcTed SuccEssFuLy[/bold green]'
    panel = Panel(Align.center(TexT) , title="[bold yellow]FF - GLobaL[/bold yellow]", border_style="bright_yellow" , padding=(1, 2) , expand=False)
    console.print(panel)
    accounts = load_accounts()
    threads = []
    for uid, pwd in accounts.items():
        t = threading.Thread(target=FF_CLient, args=(uid, pwd))
        t.start()
        threads.append(t)    
    for t in threads:
        t.join()
if __name__ == "__main__":
    StarT_SerVer()
