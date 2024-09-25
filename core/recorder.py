#作用是音频录制，对于aliyun asr来说，边录制边stt，但对于其他来说，是先保存成文件再推送给asr模型，通过实现子类的方式（fay_booter.py 上有实现）来管理音频流的来源
import audioop
import math
import time
import threading
from abc import abstractmethod

from asr.ali_nls import ALiNls
from asr.funasr import FunASR
from core import wsa_server
from scheduler.thread_manager import MyThread
from utils import util
from utils import config_util as cfg
import numpy as np
import tempfile
import wave
# 启动时间 (秒)
_ATTACK = 0.2

# 释放时间 (秒)
_RELEASE = 0.75


class Recorder:

    def __init__(self, fay):
        self.__fay = fay
        self.__running = True
        self.__processing = False
        self.__history_level = []
        self.__history_data = []
        self.__dynamic_threshold = 0.5 # 声音识别的音量阈值

        self.__MAX_LEVEL = 25000
        self.__MAX_BLOCK = 100
        
        #Edit by xszyou in 20230516:增加本地asr
        self.ASRMode = cfg.ASR_mode
        self.__aLiNls = None
        self.is_awake = False
        self.wakeup_matched = False
        if cfg.config['source']['wake_word_enabled']:
            self.timer = threading.Timer(60, self.reset_wakeup_status)  # 60秒后执行reset_wakeup_status方法
        self.username = 'User' #默认用户，子类实现时会重写


    def asrclient(self):
        if self.ASRMode == "ali":
            asrcli = ALiNls(self.username)
        elif self.ASRMode == "funasr" or self.ASRMode == "sensevoice":
            asrcli = FunASR(self.username)
        return asrcli

    def save_buffer_to_file(self, buffer):
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav", dir="cache_data")
        wf = wave.open(temp_file.name, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(2)  
        wf.setframerate(16000)
        wf.writeframes(buffer)
        wf.close()
        return temp_file.name

    def __get_history_average(self, number):
        total = 0
        num = 0
        for i in range(len(self.__history_level) - 1, -1, -1):
            level = self.__history_level[i]
            total += level
            num += 1
            if num >= number:
                break
        return total / num

    def __get_history_percentage(self, number):
        return (self.__get_history_average(number) / self.__MAX_LEVEL) * 1.05 + 0.02

    def reset_wakeup_status(self):
        self.wakeup_matched = False        

    def __waitingResult(self, iat: asrclient, audio_data):
        self.processing = True
        t = time.time()
        tm = time.time()
        if self.ASRMode == "funasr"  or self.ASRMode == "sensevoice":
            file_url = self.save_buffer_to_file(audio_data)
            self.__aLiNls.send_url(file_url)
        
        # return
        # 等待结果返回
        while not iat.done and time.time() - t < 1:
            time.sleep(0.01)
        text = iat.finalResults
        util.printInfo(1, self.username, "语音处理完成！ 耗时: {} ms".format(math.floor((time.time() - tm) * 1000)))
        if len(text) > 0:
            if cfg.config['source']['wake_word_enabled']:
                #普通唤醒模式
                if cfg.config['source']['wake_word_type'] == 'common':

                    if not self.wakeup_matched:
                        #唤醒词判断
                        wake_word =  cfg.config['source']['wake_word']
                        wake_word_list = wake_word.split(',')
                        wake_up = False
                        for word in wake_word_list:
                            if word in text:
                                    wake_up = True
                        if wake_up:
                            self.wakeup_matched = True  # 唤醒成功
                            util.printInfo(3, self.username, "唤醒成功！")
                            self.on_speaking(text)
                            self.processing = False
                            self.timer.cancel()  # 取消之前的计时器任务
                        else:
                            util.printInfo(3, self.username, "[!] 待唤醒！")
                            wsa_server.get_web_instance().add_cmd({"panelMsg": "", "Username" : self.username})
                    else:
                        self.on_speaking(text)
                        self.processing = False
                        self.timer.cancel()  # 取消之前的计时器任务
                        self.timer = threading.Timer(60, self.reset_wakeup_status)  # 重设计时器为60秒
                        self.timer.start()
                
                #前置唤醒词模式
                elif  cfg.config['source']['wake_word_type'] == 'front':
                    wake_word =  cfg.config['source']['wake_word']
                    wake_word_list = wake_word.split(',')
                    wake_up = False
                    for word in wake_word_list:
                        if text.startswith(word):
                            wake_up_word = word
                            wake_up = True
                            break
                    if wake_up:
                        util.printInfo(3, self.username, "唤醒成功！")
                        #去除唤醒词后语句
                        question = text[len(wake_up_word):].lstrip()
                        self.on_speaking(question)
                        self.processing = False
                    else:
                        util.printInfo(3, self.username, "[!] 待唤醒！")
                        wsa_server.get_web_instance().add_cmd({"panelMsg": "", 'Username' : self.username})

            #非唤醒模式
            else:
                 self.on_speaking(text)
                 self.processing = False
        else:
            if self.wakeup_matched:
                self.wakeup_matched = False
            util.printInfo(1, self.username, "[!] 语音未检测到内容！")
            self.processing = False
            self.dynamic_threshold = self.__get_history_percentage(30)
            wsa_server.get_web_instance().add_cmd({"panelMsg": "", 'Username' : self.username})
            if not cfg.config["interact"]["playSound"]: # 非展板播放
                content = {'Topic': 'Unreal', 'Data': {'Key': 'log', 'Value': ""}, 'Username' : self.username}
                wsa_server.get_instance().add_cmd(content)

    def __record(self):   
        try:
            stream = self.get_stream() #此方法会阻塞
        except Exception as e:
                print(e)
                util.printInfo(1, self.username, "请检查设备是否有误，再重新启动!")
                return
        isSpeaking = False
        last_mute_time = time.time()
        last_speaking_time = time.time()
        data = None
        concatenated_audio = bytearray()
        while self.__running:
            try:
                data = stream.read(2048, exception_on_overflow=False)
            except Exception as e:
                data = None
                print(e)
                util.log(1, "请检查设备是否有误，再重新启动!")
                return
            if not data:
                continue
            

            if  cfg.config['source']['record']['enabled'] and not self.is_remote():
                if len(cfg.config['source']['record'])<3:
                    channels = 1
                else:
                    channels = int(cfg.config['source']['record']['channels'])
                #只获取第一声道
                data = np.frombuffer(data, dtype=np.int16)
                data = np.reshape(data, (-1, channels))  # reshaping the array to split the channels
                mono = data[:, 0]  # taking the first channel
                data = mono.tobytes()  

            #计算音量是否满足激活拾音
            level = audioop.rms(data, 2)
            if len(self.__history_data) >= 5:#保存激活前的音频，以免信息掉失
                self.__history_data.pop(0)
            if len(self.__history_level) >= 500:
                self.__history_level.pop(0)
            self.__history_data.append(data)
            self.__history_level.append(level)
            percentage = level / self.__MAX_LEVEL
            history_percentage = self.__get_history_percentage(30)
            if history_percentage > self.__dynamic_threshold:
                self.__dynamic_threshold += (history_percentage - self.__dynamic_threshold) * 0.0025
            elif history_percentage < self.__dynamic_threshold:
                self.__dynamic_threshold += (history_percentage - self.__dynamic_threshold) * 1

            #是否可以拾音:fay_core没有在播放，或者开启了唤醒（可以打断）时可以拾音
            can_listen = False
            if cfg.config['source']['wake_word_enabled']:    
                can_listen = True
            else:
                if not self.__fay.speaking:
                     can_listen = True
                else:
                     can_listen = False
            
            #激活拾音
            if percentage > self.__dynamic_threshold and can_listen:
                last_speaking_time = time.time()
                if not self.__processing and not isSpeaking and time.time() - last_mute_time > _ATTACK:
                    isSpeaking = True  #用户正在说话
                    util.printInfo(3, self.username,"聆听中...")
                    concatenated_audio.clear()
                    self.__aLiNls = self.asrclient()
                    try:
                        self.__aLiNls.start()
                    except Exception as e:
                        print(e)
                        util.printInfo(1, self.username, "aliyun asr 连接受限")
                    for i in range(len(self.__history_data) - 1): #当前data在下面会做发送，这里是发送激活前的音频数据，以免漏掉信息
                        buf = self.__history_data[i]
                        if self.ASRMode == "ali":
                            self.__aLiNls.send(buf)
                        else:
                            concatenated_audio.extend(buf)
                    self.__history_data.clear()
            else:#结束拾音
                last_mute_time = time.time()
                if isSpeaking:
                    if time.time() - last_speaking_time > _RELEASE:
                        isSpeaking = False
                        util.printInfo(1, self.username, "语音处理中...")
                        self.__aLiNls.end()
                        self.__fay.last_quest_time = time.time()
                        self.__waitingResult(self.__aLiNls, concatenated_audio)
            
            #向asr server传输数据
            if isSpeaking:
                if self.ASRMode == "ali":
                    self.__aLiNls.send(data)
                else:
                    concatenated_audio.extend(data)
     
    def set_processing(self, processing):
        self.__processing = processing

    def start(self):
        MyThread(target=self.__record).start()

    def stop(self):
        self.__running = False

    @abstractmethod
    def on_speaking(self, text):
        pass

    #TODO Edit by xszyou on 20230113:把流的获取方式封装出来方便实现麦克风录制及网络流等不同的流录制子类
    @abstractmethod
    def get_stream(self):
        pass

    @abstractmethod
    def is_remote(self):
        pass
