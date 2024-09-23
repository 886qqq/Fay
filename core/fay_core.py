#作用是处理交互逻辑，文字输入，语音、文字及情绪的发送、播放及展示输出
import math
import os
import time
import socket
import wave
import pygame

# 适应模型使用
import numpy as np
import fay_booter
from ai_module import baidu_emotion
from core import wsa_server, tts_voice
from core.interact import Interact
from core.tts_voice import EnumVoice
from scheduler.thread_manager import MyThread
from utils import util, config_util
from core import qa_service
from utils import config_util as cfg
from core import content_db
from ai_module import nlp_cemotion
from ai_module import nlp_rasa
from ai_module import nlp_gpt
from ai_module import yolov8
from ai_module import nlp_VisualGLM
from ai_module import nlp_lingju
from ai_module import nlp_xingchen
from ai_module import nlp_langchain
from ai_module import nlp_ollama_api
from ai_module import nlp_coze
from core import member_db
import threading
import functools

#线程同步注解
def synchronized(func):
  @functools.wraps(func)
  def wrapper(self, *args, **kwargs):
    with self.lock:
      return func(self, *args, **kwargs)
  return wrapper

#加载配置
cfg.load_config()
if cfg.tts_module =='ali':
    from ai_module.ali_tss import Speech
elif cfg.tts_module == 'gptsovits':
    from ai_module.gptsovits import Speech
elif cfg.tts_module == 'gptsovits_v3':
    from ai_module.gptsovits_v3 import Speech    
elif cfg.tts_module == 'volcano':
    from ai_module.volcano_tts import Speech
else:
    from ai_module.ms_tts_sdk import Speech

#windows运行推送唇形数据
import platform
if platform.system() == "Windows":
    import sys
    sys.path.append("test/ovr_lipsync")
    from test_olipsync import LipSyncGenerator
    
modules = {
    "nlp_gpt": nlp_gpt,
    "nlp_rasa": nlp_rasa,
    "nlp_VisualGLM": nlp_VisualGLM,
    "nlp_lingju": nlp_lingju,
    "nlp_xingchen": nlp_xingchen,
    "nlp_langchain": nlp_langchain,
    "nlp_ollama_api": nlp_ollama_api,
    "nlp_coze": nlp_coze

}

#大语言模型回复
def handle_chat_message(msg, username='User'):
    text = ''
    textlist = []
    try:
        util.log(1, '自然语言处理...')
        tm = time.time()
        cfg.load_config()
        module_name = "nlp_" + cfg.key_chat_module
        selected_module = modules.get(module_name)
        if selected_module is None:
            raise RuntimeError('请选择正确的nlp模型')   
        if cfg.key_chat_module == 'rasa':
            textlist = selected_module.question(msg)
            text = textlist[0]['text'] 
        else:
            uid = member_db.new_instance().find_user(username)
            text = selected_module.question(msg, uid)  
        util.log(1, '自然语言处理完成. 耗时: {} ms'.format(math.floor((time.time() - tm) * 1000)))
        if text == '哎呀，你这么说我也不懂，详细点呗' or text == '':
            util.log(1, '[!] 自然语言无语了！')
            text = '哎呀，你这么说我也不懂，详细点呗'  
    except BaseException as e:
        print(e)
        util.log(1, '自然语言处理错误！')
        text = '哎呀，你这么说我也不懂，详细点呗'   

    return text,textlist
    

class FeiFei:
    def __init__(self):
        self.lock = threading.Lock()
        pygame.mixer.init()
        self.q_msg = '你叫什么名字？'
        self.a_msg = 'hi,我叫菲菲，英文名是fay'
        self.mood = 0.0  # 情绪值
        self.old_mood = 0.0
        self.item_index = 0
        self.X = np.array([1, 0, 0, 0, 0, 0, 0, 0]).reshape(1, -1)  # 适应模型变量矩阵
        # self.W = np.array([0.01577594,1.16119452,0.75828,0.207746,1.25017864,0.1044121,0.4294899,0.2770932]).reshape(-1,1) #适应模型变量矩阵
        self.W = np.array([0.0, 0.6, 0.1, 0.7, 0.3, 0.0, 0.0, 0.0]).reshape(-1, 1)  # 适应模型变量矩阵

        self.wsParam = None
        self.wss = None
        self.sp = Speech()
        self.speaking = False
        self.__running = True
        self.sp.connect()  #TODO 预连接
        self.last_quest_time = time.time()
        self.cemotion = None

    #语音消息处理检查是否命中q&a
    def __get_answer(self, interleaver, text):
        answer = None
        # 全局问答
        answer = qa_service.question('qa',text)
        if answer is not None:
            return answer
        
        # 人设问答
        keyword = qa_service.question('Persona',text)
        if keyword is not None:
            return config_util.config["attribute"][keyword]
       
    #语音消息处理
    def __process_interact(self, interact: Interact):
        if self.__running:
            try:
                index = interact.interact_type
                if index == 1: #语音文字交互
                    #记录用户问题
                    self.q_msg = interact.data["msg"]
                    self.write_to_file("./logs", "asr_result.txt",  self.q_msg)

                    #同步用户问题到数字人
                    if wsa_server.get_instance().isConnect: 
                        content = {'Topic': 'Unreal', 'Data': {'Key': 'question', 'Value': interact.data["msg"]}, 'Username' : interact.data.get("user")}
                        wsa_server.get_instance().add_cmd(content)

                    #fay eyes启动时，进行mic交互时，看不到人不互动
                    if interact.interleaver == "mic":
                        fay_eyes = yolov8.new_instance()            
                        if fay_eyes.get_status():#YOLO正在运行
                            person_count, stand_count, sit_count = fay_eyes.get_counts()
                            if person_count < 1: #看不到人，不互动
                                wsa_server.get_web_instance().add_cmd({"panelMsg": "看不到人，不互动", "Username" : interact.data.get("user")})
                                if wsa_server.get_instance().isConnect:
                                    content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': "看不到人，不互动"}, 'Username' : interact.data.get("user")}
                                    wsa_server.get_instance().add_cmd(content)
                                return "看不到人，不互动"
                        
                    #确定是否命中q&a
                    answer = self.__get_answer(interact.interleaver, interact.data["msg"])

                    #记录用户
                    username = interact.data["user"]
                    if member_db.new_instance().is_username_exist(username)  == "notexists":
                        member_db.new_instance().add_user(username)
                    uid = member_db.new_instance().find_user(username)

                    #记录用户问题
                    content_db.new_instance().add_content('member','speak',interact.data["msg"], username, uid)
                    wsa_server.get_web_instance().add_cmd({"panelReply": {"type":"member","content":interact.data["msg"], "username":username, "uid":uid}, "Username" : username})
                    
                    #大语言模型回复    
                    text = ''
                    textlist = []
                    if answer is None:
                        wsa_server.get_web_instance().add_cmd({"panelMsg": "思考中...", "Username" : username})
                        if wsa_server.get_instance().isConnect:
                            content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': "思考中..."}, 'Username' : username}
                            wsa_server.get_instance().add_cmd(content)
                        text,textlist = handle_chat_message(interact.data["msg"], username)
                    else: 
                        text = answer

                    #记录回复    
                    self.a_msg = text
                    self.write_to_file("./logs", "answer_result.txt", text)
                    content_db.new_instance().add_content('fay','speak',text, username, uid)
                    wsa_server.get_web_instance().add_cmd({"panelReply": {"type":"fay","content":text, "username":username, "uid":uid}, "Username" : username})
                    if len(textlist) > 1:
                        i = 1
                        while i < len(textlist):
                            content_db.new_instance().add_content('fay','speak',textlist[i]['text'], username, uid)
                            wsa_server.get_web_instance().add_cmd({"panelReply": {"type":"fay","content":textlist[i]['text'], "username":username, "uid":uid}, "Username" : username})
                            i+= 1

                #同步回复到数字人            
                wsa_server.get_web_instance().add_cmd({"panelMsg": text, "Username" : username})
                if wsa_server.get_instance().isConnect:
                    content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': text}, "Username" : username}
                    wsa_server.get_instance().add_cmd(content)
                
                #声音输出
                MyThread(target=self.say, args=[interact, text]).start()

                return self.a_msg
                    
                        
            except BaseException as e:
                print(e)
                return e
        else:
            return "还没有开始运行"

    #记录问答到log
    def write_to_file(self, path, filename, content):
        if not os.path.exists(path):
            os.makedirs(path)
        full_path = os.path.join(path, filename)
        with open(full_path, 'w', encoding='utf-8') as file:
            file.write(content)
            file.flush()  
            os.fsync(file.fileno()) 

    #触发语音交互
    def on_interact(self, interact: Interact):
        MyThread(target=self.__update_mood, args=[interact.interact_type]).start()
        return self.__process_interact(interact)

    # 发送情绪
    def __send_mood(self):
         while self.__running:
            time.sleep(3)
            if wsa_server.get_instance().isConnect:
                if  self.old_mood != self.mood:
                    content = {'Topic': 'Unreal', 'Data': {'Key': 'mood', 'Value': self.mood}}
                    wsa_server.get_instance().add_cmd(content)
                    self.old_mood = self.mood
      
    # 更新情绪
    def __update_mood(self, typeIndex):
        perception = config_util.config["interact"]["perception"]
        if typeIndex == 1:
            try:
                if cfg.ltp_mode == "cemotion":
                    result = nlp_cemotion.get_sentiment(self.cemotion,self.q_msg)
                    chat_perception = perception["chat"]
                    if result >= 0.5 and result <= 1:
                       self.mood = self.mood + (chat_perception / 150.0)
                    elif result <= 0.2:
                       self.mood = self.mood - (chat_perception / 100.0)
                else:
                    if str(cfg.baidu_emotion_api_key) == '' or str(cfg.baidu_emotion_app_id) == '' or str(cfg.baidu_emotion_secret_key) == '':
                        self.mood = 0
                    else:
                        result = int(baidu_emotion.get_sentiment(self.q_msg))
                        chat_perception = perception["chat"]
                        if result >= 2:
                            self.mood = self.mood + (chat_perception / 150.0)
                        elif result == 0:
                            self.mood = self.mood - (chat_perception / 100.0)
            except BaseException as e:
                self.mood = 0
                print("[System] 情绪更新错误！")
                print(e)

        elif typeIndex == 2:
            self.mood = self.mood + (perception["join"] / 100.0)

        elif typeIndex == 3:
            self.mood = self.mood + (perception["gift"] / 100.0)

        elif typeIndex == 4:
            self.mood = self.mood + (perception["follow"] / 100.0)

        if self.mood >= 1:
            self.mood = 1
        if self.mood <= -1:
            self.mood = -1

    #获取不同情绪声音
    def __get_mood_voice(self):
        voice = tts_voice.get_voice_of(config_util.config["attribute"]["voice"])
        if voice is None:
            voice = EnumVoice.XIAO_XIAO
        styleList = voice.value["styleList"]
        sayType = styleList["calm"]
        if -1 <= self.mood < -0.5:
            sayType = styleList["angry"]
        if -0.5 <= self.mood < -0.1:
            sayType = styleList["lyrical"]
        if -0.1 <= self.mood < 0.1:
            sayType = styleList["calm"]
        if 0.1 <= self.mood < 0.5:
            sayType = styleList["assistant"]
        if 0.5 <= self.mood <= 1:
            sayType = styleList["cheerful"]
        return sayType

    # 合成声音
    def say(self, interact, text):
        try:
            if len(text) >= 1:
                util.printInfo(1, '菲菲', '({}) {}'.format(self.__get_mood_voice(), text))
                if wsa_server.get_instance().isConnect:
                    content = {'Topic': 'Unreal', 'Data': {'Key': 'text', 'Value': text}, 'Username' : interact.data.get('user')}
                    wsa_server.get_instance().add_cmd(content)
                if config_util.config["source"]["tts_enabled"]:#TODO 处理tts开关
                    util.log(1, '合成音频...')
                    tm = time.time()
                    result = self.sp.to_sample(text, self.__get_mood_voice())
                    util.log(1, '合成音频完成. 耗时: {} ms 文件:{}'.format(math.floor((time.time() - tm) * 1000), result))
                    if result is not None:            
                        MyThread(target=self.__process_output_audio, args=[result, interact, text]).start()
                        return result
                else:
                    util.log(1, '问答处理总时长：{} ms'.format(math.floor((time.time() - self.last_quest_time) * 1000)))
                    time.sleep(1)
                    wsa_server.get_web_instance().add_cmd({"panelMsg": "", 'Username' : interact.data.get('user')})
                    if wsa_server.get_instance().isConnect: 
                        content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': ''}, 'Username' : interact.data.get('user')}
                        wsa_server.get_instance().add_cmd(content)               
                
        except BaseException as e:
            print(e)
        return None

    #面板播放声音
    @synchronized
    def __play_sound(self, file_url, audio_length, interact):
        self.speaking = True
        util.log(1, '播放音频...')
        util.log(1, '问答处理总时长：{} ms'.format(math.floor((time.time() - self.last_quest_time) * 1000)))
        pygame.mixer.music.load(file_url)
        pygame.mixer.music.play()

        #等待音频播放完成，唤醒模式不用等待        
        length = 0
        while not cfg.config['source']['wake_word_enabled']:
            if audio_length + 0.01 > length:
                length = length + 0.01
                time.sleep(0.01)
            else:
                break
        self.speaking = False
        wsa_server.get_web_instance().add_cmd({"panelMsg": "", 'Username' : interact.data.get('user')})
    
    #推送远程音频
    def __send_remote_device_audio(self, file_url, interact):
        delkey = None    
        for key, value in fay_booter.DeviceInputListenerDict.items():
            if value.username == interact.data.get("user") and value.isOutput: #按username选择推送，booter.devicelistenerdice按用户名记录
                try:
                    value.deviceConnector.send(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08") # 发送音频开始标志，同时也检查设备是否在线
                    wavfile = open(os.path.abspath(file_url), "rb")
                    data = wavfile.read(102400)
                    total = 0
                    while data:
                        total += len(data)
                        value.deviceConnector.send(data)
                        data = wavfile.read(102400)
                        time.sleep(0.0001)
                    value.deviceConnector.send(b'\x08\x07\x06\x05\x04\x03\x02\x01\x00')# 发送音频结束标志
                    util.log(1, "远程音频发送完成：{}".format(total))
                except socket.error as serr:
                    util.log(1,"远程音频输入输出设备已经断开：{}".format(key)) 
                    value.stop()
                    delkey = key
        if delkey:            
             del fay_booter.DeviceInputListenerDict[key]
        if len(fay_booter.DeviceInputListenerDict.items()) == 0:
            wsa_server.get_web_instance().add_cmd({"remote_audio_connect": False, 'Username' : interact.data.get('user')})

    #输出音频处理
    def __process_output_audio(self, file_url, interact, text):
        try:
            try:
                with wave.open(file_url, 'rb') as wav_file: #wav音频长度
                    audio_length = wav_file.getnframes() / float(wav_file.getframerate())
            except Exception as e:
                audio_length = 3

            #推送远程音频
            MyThread(target=self.__send_remote_device_audio, args=[file_url, interact]).start()

            if config_util.config["interact"]["playSound"]:
                 self.__play_sound(file_url, audio_length, interact)

            #发送音频给数字人接口
            if wsa_server.get_instance().isConnect: 
                content = {'Topic': 'Unreal', 'Data': {'Key': 'audio', 'Value': 'http://127.0.0.1:5000/audio/' + os.path.basename(file_url), 'Text': text, 'Time': audio_length, 'Type': 'interact'}, 'Username' : interact.data.get('user')}
                #计算lips
                if platform.system() == "Windows":
                    try:
                        lip_sync_generator = LipSyncGenerator()
                        viseme_list = lip_sync_generator.generate_visemes(os.path.abspath(file_url))
                        consolidated_visemes = lip_sync_generator.consolidate_visemes(viseme_list)
                        content["Data"]["Lips"] = consolidated_visemes
                    except Exception as e:
                        print(e)
                        util.log(1, "唇型数据生成失败")
                wsa_server.get_instance().add_cmd(content)

            wsa_server.get_web_instance().add_cmd({"panelMsg": "", 'Username' : interact.data.get('user')})
            if wsa_server.get_instance().isConnect: 
                content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': ""}, 'Username' : interact.data.get('user')}
                wsa_server.get_instance().add_cmd(content)
            if config_util.config["interact"]["playSound"]:
                util.log(1, '结束播放！')
        except Exception as e:
            print(e)

    #启动核心服务
    def start(self):
        if cfg.ltp_mode == "cemotion":
            from cemotion import Cemotion
            self.cemotion = Cemotion()
        MyThread(target=self.__send_mood).start()

    #停止核心服务
    def stop(self):
        self.__running = False
        self.speaking = False
        self.sp.close()
        wsa_server.get_web_instance().add_cmd({"panelMsg": ""})
        if wsa_server.get_instance().isConnect:
            content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': ""}}
            wsa_server.get_instance().add_cmd(content)
