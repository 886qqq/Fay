from asyncio import AbstractEventLoop

import websockets
import asyncio
import json
import threading
from abc import abstractmethod
from websockets.legacy.server import Serve

from scheduler.thread_manager import MyThread
from utils import util
class LL:
    def acquire(self):
        pass
    def release(self):
        pass
class MyServer:
    def __init__(self, host='0.0.0.0', port=10000):
        self.lock = LL()#threading.Lock()
        self.__host = host  # ip
        self.__port = port  # 端口号
        self.__listCmd = []  # 要发送的信息的列表
        self.__clients = list() 
        self.__server: Serve = None
        self.__event_loop: AbstractEventLoop = None
        self.__running = True
        self.__pending = None
        self.isConnect = False

    def __del__(self):
        self.stop_server()

    # 接收处理
    async def __consumer_handler(self, websocket, path):
        username = None
        try:
            async for message in websocket:
                await asyncio.sleep(0.01)
                username = json.loads(message).get("Username")
                if username:
                    remote_address = websocket.remote_address
                    unique_id = f"{remote_address[0]}:{remote_address[1]}"
                    self.lock.acquire()
                    for i in range(len(self.__clients)): 
                        if self.__clients[i]["id"] == unique_id:
                            self.__clients[i]["username"] = username
                    self.lock.release()
                await self.__consumer(message)
        except websockets.exceptions.ConnectionClosedError as e:
            util.printInfo(1, "User" if username is None else username, f"WebSocket 连接关闭: {e}")
            self.lock.acquire()
            if len(self.__clients) == 0:
                self.isConnect = False
            self.lock.release()
            remote_address = websocket.remote_address
            unique_id = f"{remote_address[0]}:{remote_address[1]}"
            self.lock.acquire()
            delid = None
            for i in range(len(self.__clients)):
                if self.__clients[i]["id"] == unique_id:
                    delid = i
                    break
            if delid is not None:
                del self.__clients[delid]
            self.lock.release()
            self.on_close_handler()
            
    async def __producer_handler(self, websocket, path):
        message = None
        username = None
        try:
            while self.__running:
                await asyncio.sleep(0.01)
                if len(self.__listCmd) > 0:
                    message = await self.__producer()
                    if message:
                        username = json.loads(message).get("Username")
                        if username is None: #cmd没有指定username就群发
                            wsclients = list()
                            self.lock.acquire()
                            for c in self.__clients:
                                wsclients.append(c["websocket"])
                            self.lock.release()
                            tasks = [asyncio.create_task(client.send(message)) for client in wsclients]
                            await asyncio.wait(tasks)
                            self.lock.release()
                        else:#指定用户发送
                            self.lock.acquire()
                            for c in self.__clients:
                                if c.get("username") == username:
                                   await c["websocket"].send(message)
                            self.lock.release()
        except Exception as e:
            util.printInfo(1, "User" if  username is None else username, f"WebSocket 连接关闭: {e}")
            self.lock.acquire()
            if len(self.__clients) == 0:
                self.isConnect = False
            self.lock.release()
            remote_address = websocket.remote_address
            unique_id = f"{remote_address[0]}:{remote_address[1]}"
            self.lock.acquire()
            delid = None
            for i in range(len(self.__clients)):
                if self.__clients[i]["id"] == unique_id:
                    delid  = i
                    break
            if delid:
                del self.__clients[delid]        
            self.lock.release()
            self.on_close_handler()

    
    async def __handler(self, websocket, path):
        self.isConnect = True
        util.log(1,"websocket连接上:{}".format(self.__port))
        self.on_connect_handler()
        remote_address = websocket.remote_address
        unique_id = f"{remote_address[0]}:{remote_address[1]}"
        self.lock.acquire()
        self.__clients.append({"id" : unique_id, "websocket" : websocket, "username" : "User"})
        self.lock.release()
        consumer_task = asyncio.ensure_future(self.__consumer_handler(websocket, path)) # 接收
        producer_task = asyncio.ensure_future(self.__producer_handler(websocket, path)) # 发送
        done, self.__pending = await asyncio.wait([consumer_task, producer_task], return_when=asyncio.FIRST_COMPLETED)
        for task in self.__pending:
            task.cancel()
        self.lock.acquire()
        delid = None
        for i in range(len(self.__clients)):
            if self.__clients[i]["id"] == unique_id:
                delid = i
                break
        if delid:
            del self.__clients[delid]
        self.lock.release()
        if len(self.__clients) == 0:
                self.isConnect = False
        util.log(1, "websocket连接断开:{}".format(unique_id))
        self.on_close_handler()
                
    async def __consumer(self, message):
        self.on_revice_handler(message)
    
    async def __producer(self):
        if len(self.__listCmd) > 0:
            message = self.on_send_handler(self.__listCmd.pop(0))
            return message
        else:
            return None

    #Edit by xszyou on 20230113:通过继承此类来实现服务端的接收后处理逻辑
    @abstractmethod
    def on_revice_handler(self, message):
        pass

    #Edit by xszyou on 20230114:通过继承此类来实现服务端的连接处理逻辑
    @abstractmethod
    def on_connect_handler(self):
        pass
    
    #Edit by xszyou on 20230804:通过继承此类来实现服务端的发送前的处理逻辑
    @abstractmethod
    def on_send_handler(self, message):
        return message

    #Edit by xszyou on 20230816:通过继承此类来实现服务端的断开后的处理逻辑
    @abstractmethod
    def on_close_handler(self):
        pass

    # 创建server
    def __connect(self):
        self.__event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.__event_loop)
        self.__isExecute = True
        if self.__server:
            util.log(1, 'server already exist')
            return
        self.__server = websockets.serve(self.__handler, self.__host, self.__port)
        asyncio.get_event_loop().run_until_complete(self.__server)
        asyncio.get_event_loop().run_forever()

    # 往要发送的命令列表中，添加命令
    def add_cmd(self, content):
        if not self.__running:
            return
        jsonStr = json.dumps(content)
        self.__listCmd.append(jsonStr)
        # util.log('命令 {}'.format(content))

    # 开启服务
    def start_server(self):
        MyThread(target=self.__connect).start()

    # 关闭服务
    def stop_server(self):
        self.__running = False
        self.isConnect = False
        if self.__server is None:
            return
        self.__server.ws_server.close()
        self.__server = None
        try:
            all_tasks = asyncio.all_tasks(self.__event_loop)
            for task in all_tasks:
                while not task.cancel():
                    util.log(1, "无法关闭！")
            self.__event_loop.stop()
            self.__event_loop.close()
            self.__clients = list()
        except BaseException as e:
            util.log(1, "Error: {}".format(e))

#ui端server
class WebServer(MyServer):
    def __init__(self, host='0.0.0.0', port=10003):
        super().__init__(host, port)

    def on_revice_handler(self, message):
        pass
    
    def on_connect_handler(self):
        self.add_cmd({"panelMsg": "使用提示：Fay可以独立使用，启动数字人将自动对接。"})

    def on_send_handler(self, message):
        return message

    def on_close_handler(self):
        pass

#数字人端server
class HumanServer(MyServer):
    def __init__(self, host='0.0.0.0', port=10002):
        super().__init__(host, port)

    def on_revice_handler(self, message):
       pass

    def on_connect_handler(self):
        web_server_instance = get_web_instance()  
        web_server_instance.add_cmd({"is_connect": self.isConnect}) 
        

    def on_send_handler(self, message):
        # util.log(1, '向human发送 {}'.format(message))
        if not self.isConnect:
            return None
        return message

    def on_close_handler(self):
        web_server_instance = get_web_instance()  
        web_server_instance.add_cmd({"is_connect": self.isConnect}) 

        

#测试
class TestServer(MyServer):
    def __init__(self, host='0.0.0.0', port=10000):
        super().__init__(host, port)

    def on_revice_handler(self, message):
        print(message)
    
    def on_connect_handler(self):
        print("连接上了")
    
    def on_send_handler(self, message):
        return message
    
    def on_close_handler(self):
        pass



#单例

__instance: MyServer = None
__web_instance: MyServer = None


def new_instance(host='0.0.0.0', port=10002) -> MyServer:
    global __instance
    if __instance is None:
        __instance = HumanServer(host, port)
    return __instance


def new_web_instance(host='0.0.0.0', port=10003) -> MyServer:
    global __web_instance
    if __web_instance is None:
        __web_instance = WebServer(host, port)
    return __web_instance


def get_instance() -> MyServer:
    return __instance


def get_web_instance() -> MyServer:
    return __web_instance

if __name__ == '__main__':
    testServer = TestServer(host='0.0.0.0', port=10000)
    testServer.start_server()