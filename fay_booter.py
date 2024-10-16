#核心启动模块
import time
import re
import pyaudio
import socket
import psutil
import sys
from core.interact import Interact
from core.recorder import Recorder
from core.fay_core import FeiFei
from scheduler.thread_manager import MyThread
from utils import util, config_util, stream_util
from core.wsa_server import MyServer
from scheduler.thread_manager import MyThread
from core import wsa_server

feiFei: FeiFei = None
recorderListener: Recorder = None
__running = False
deviceSocketServer = None
DeviceInputListenerDict = {}
ngrok = None

#启动状态
def is_running():
    return __running

#录制麦克风音频输入并传给aliyun
class RecorderListener(Recorder):

    def __init__(self, device, fei):
        self.__device = device
        self.__RATE = 16000
        self.__FORMAT = pyaudio.paInt16
        self.__running = False
        self.username = 'User'

        super().__init__(fei)

    def on_speaking(self, text):
        if len(text) > 1:
            interact = Interact("mic", 1, {'user': 'User', 'msg': text})
            util.printInfo(3, "语音", '{}'.format(interact.data["msg"]), time.time())
            feiFei.on_interact(interact)

    def get_stream(self):
        self.paudio = pyaudio.PyAudio()
        device_id = 0
        self.stream = self.paudio.open(input_device_index=device_id, rate=self.__RATE, format=self.__FORMAT, channels=1, input=True)
        self.__running = True
        MyThread(target=self.__pyaudio_clear).start()
        return self.stream

    def __pyaudio_clear(self):
        while self.__running:
            time.sleep(30)
            

    def __findInternalRecordingDevice(self, p):
        for i in range(p.get_device_count()):
            devInfo = p.get_device_info_by_index(i)
            if devInfo['name'].find(self.__device) >= 0 and devInfo['hostApi'] == 0:
                config_util.config['source']['record']['channels'] = devInfo['maxInputChannels']
                config_util.save_config(config_util.config)
                return i, devInfo
        util.log(1, '[!] 无法找到内录设备!')
        return -1, None
    
    def stop(self):
        super().stop()
        self.__running = False
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.paudio.terminate()
        except Exception as e:
                print(e)
                util.log(1, "请检查设备是否有误，再重新启动!")

    def is_remote(self):
        return False
                    
        


#Edit by xszyou on 20230113:录制远程设备音频输入并传给aliyun
class DeviceInputListener(Recorder):
    def __init__(self, deviceConnector, fei):
        super().__init__(fei)
        self.__running = True
        self.streamCache = None
        self.thread = MyThread(target=self.run)
        self.thread.start()  #启动远程音频输入设备监听线程
        self.username = 'User'
        self.isOutput = True
        self.deviceConnector = deviceConnector

    def run(self):
        #启动ngork
        self.streamCache = stream_util.StreamCache(1024*1024*20)
        addr = None
        while self.__running:
            try:
                
                data = b""
                while self.deviceConnector:
                    data = self.deviceConnector.recv(2048)
                    if b"<username>" in data:
                        data_str = data.decode("utf-8")
                        match = re.search(r"<username>(.*?)</username>", data_str)
                        if match:
                            self.username = match.group(1)
                        else:
                            self.streamCache.write(data)
                    if b"<output>" in data:
                        data_str = data.decode("utf-8")
                        match = re.search(r"<output>(.*?)<output>", data_str)
                        if match:
                            self.isOutput = (match.group(1) == "True")
                        else:
                            self.streamCache.write(data)
                    if not b"<username>" in data and not b"<output>" in data:
                        self.streamCache.write(data)
                    time.sleep(0.005)
                self.streamCache.clear()
         
            except Exception as err:
                pass
            time.sleep(1)

    def on_speaking(self, text):
        global feiFei
        if len(text) > 1:
            interact = Interact("socket", 1, {"user": self.username, "msg": text, "socket": self.deviceConnector})
            util.printInfo(3, "(" + self.username + ")远程音频输入", '{}'.format(interact.data["msg"]), time.time())
            feiFei.on_interact(interact)

    #recorder会等待stream不为空才开始录音
    def get_stream(self):
        while not self.deviceConnector:
            time.sleep(1)
            pass
        return self.streamCache

    def stop(self):
        super().stop()
        self.__running = False

    def is_remote(self):
        return True

#检查远程音频连接状态
def device_socket_keep_alive():
    global DeviceInputListenerDict
    while __running:
        delkey = None
        for key, value in DeviceInputListenerDict.items():
            try:
                value.deviceConnector.send(b'\xf0\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8')#发送心跳包
                wsa_server.get_web_instance().add_cmd({"remote_audio_connect": True, "Username" : value.username}) 
            except Exception as serr:
                util.printInfo(3, value.username, "远程音频输入输出设备已经断开：{}".format(key))
                value.stop()
                delkey = key
                break
        if delkey:
             value =  DeviceInputListenerDict.pop(delkey)
             wsa_server.get_web_instance().add_cmd({"remote_audio_connect": False, "Username" : value.username})
        if len(DeviceInputListenerDict.items()) == 0:
            wsa_server.get_web_instance().add_cmd({"remote_audio_connect": False})
        time.sleep(1)

#远程音频连接
def accept_audio_device_output_connect():
    global deviceSocketServer
    global __running
    global DeviceInputListenerDict
    deviceSocketServer = socket.socket(socket.AF_INET,socket.SOCK_STREAM) 
    deviceSocketServer.bind(("0.0.0.0",10001))   
    deviceSocketServer.listen(1)
    MyThread(target = device_socket_keep_alive).start() # 开启心跳包检测
    addr = None        
    
    while __running:
        try:
            deviceConnector,addr = deviceSocketServer.accept()   #接受TCP连接，并返回新的套接字与IP地址
            deviceInputListener = DeviceInputListener(deviceConnector, feiFei)  # 设备音频输入输出麦克风
            deviceInputListener.start()

            #把DeviceInputListenner对象记录下来
            peername = str(deviceConnector.getpeername()[0]) + ":" + str(deviceConnector.getpeername()[1])
            DeviceInputListenerDict[peername] = deviceInputListener
            util.log(1,"远程音频输入输出设备连接上：{}".format(addr))
        except Exception as e:
            pass

def kill_process_by_port(port):
    for proc in psutil.process_iter(['pid', 'name','cmdline']):
        try:
            for conn in proc.connections(kind='inet'):
                if conn.laddr.port == port:
                    proc.terminate()
                    proc.wait()
        except(psutil.NosuchProcess, psutil.AccessDenied):
            pass

#控制台输入监听
def console_listener():
    global feiFei
    while __running:
        try:
            text = input()
        except EOFError:
            util.log(1, "控制台已经关闭")
            break
        
        args = text.split(' ')

        if len(args) == 0 or len(args[0]) == 0:
            continue

        if args[0] == 'help':
            util.log(1, 'in <msg> \t通过控制台交互')
            util.log(1, 'restart \t重启服务')
            util.log(1, 'stop \t\t关闭服务')
            util.log(1, 'exit \t\t结束程序')

        elif args[0] == 'stop':
            stop()
            break

        elif args[0] == 'restart':
            stop()
            time.sleep(0.1)
            start()

        elif args[0] == 'in':
            if len(args) == 1:
                util.log(1, '错误的参数！')
            msg = text[3:len(text)]
            util.printInfo(3, "控制台", '{}: {}'.format('控制台', msg))
            feiFei.last_quest_time = time.time()
            interact = Interact("console", 1, {'user': 'User', 'msg': msg})
            thr = MyThread(target=feiFei.on_interact, args=[interact])
            thr.start()

        elif args[0]=='exit':
            stop()
            time.sleep(0.1)
            util.log(1,'程序正在退出..')
            ports =[10001,10002,10003,5000]
            for port in ports:
                kill_process_by_port(port)
            sys.exit(0)
        else:
            util.log(1, '未知命令！使用 \'help\' 获取帮助.')

#停止服务
def stop():
    global feiFei
    global recorderListener
    global __running
    global DeviceInputListenerDict
    global ngrok

    util.log(1, '正在关闭服务...')
    __running = False
    if recorderListener is not None:
        util.log(1, '正在关闭录音服务...')
        recorderListener.stop()
        time.sleep(0.1)
    util.log(1, '正在关闭远程音频输入输出服务...')
    if len(DeviceInputListenerDict) > 0:
        for key in list(DeviceInputListenerDict.keys()):
            value = DeviceInputListenerDict.pop(key)
            value.stop()
    deviceSocketServer.close()
    util.log(1, '正在关闭核心服务...')
    feiFei.stop()
    util.log(1, '服务已关闭！')


#开启服务
def start():
    global feiFei
    global recorderListener
    global __running
    util.log(1, '开启服务...')
    __running = True

    #读取配置
    util.log(1, '读取配置...')
    config_util.load_config()

    #开启核心服务
    util.log(1, '开启核心服务...')
    feiFei = FeiFei()
    feiFei.start()

    #加载本地知识库
    if config_util.key_chat_module == 'langchain':
        from llm import nlp_langchain
        nlp_langchain.save_all()
    if config_util.key_chat_module == 'privategpt':    
        from llm import nlp_privategpt
        nlp_privategpt.save_all()

    #开启录音服务
    record = config_util.config['source']['record']
    if record['enabled']:
        util.log(1, '开启录音服务...')
        recorderListener = RecorderListener(record['device'], feiFei)  # 监听麦克风
        recorderListener.start()

    #启动远程音频连接服务
    util.log(1,'启动远程音频连接服务...')
    deviceSocketThread = MyThread(target=accept_audio_device_output_connect)
    deviceSocketThread.start()
            
    #监听控制台
    util.log(1, '注册命令...')
    MyThread(target=console_listener).start()  # 监听控制台

    util.log(1, '完成!')
    util.log(1, '使用 \'help\' 获取帮助.')

    

if __name__ == '__main__':
    ws_server: MyServer = None
    feiFei: FeiFei = None
    recorderListener: Recorder = None
    start()
