[`English`](https://github.com/xszyou/Fay/blob/main/README_EN.md) 

<div align="center">
    <br>
    <img src="readme/icon.png" alt="Fay">
    <h1>FAY</h1>
	<h3>Fay数字人框架 助理版 </h3>
</div>



助理版是Fay 数字人框架最常用的版本。它提供了灵活的模块化设计，使开发人员能够定制和组合各种功能模块，包括情绪分析、NLP处理、语音合成和语音输出等。助理版构建的是一问（远程或本地，移动或PC，语音或文字）一答（数字人或机器，移动或PC，语音或文字或RPA）的标准模式。<span style="color:red;">助理版提供了更完善的接口，可以方便您把自己的产品接入数字人</span>



如果你需要是一个线上线下的销售员，请移步[`带货完整版`](https://github.com/xszyou/Fay/tree/fay-sales-edition)  

如果你需要是一个可以自主决策、主动联系主人的agent，请移步[`agent版`](https://github.com/xszyou/Fay/tree/fay-agent-edition)                      

## **Fay数字人助理版**



![](readme/controller.png)

https://github.com/TheRamU/Fay/blob/main/WebSocket.md)


## **源码启动**


### **环境** 
- Python 3.9、3.10、3.11、3.12
- Windows、macos、linux

### **安装依赖**

```shell
pip install -r requirements.txt
```

### **配置**
+ 修改 `./system.conf` 文件

### **启动**
启动Fay控制器
```shell
python main.py
```

## **docker 启动**
1. 下载助理版
https://github.com/xszyou/Fay/tree/fay-assistant-edition
2.  修改 `./system.conf` 文件
3. 删除requirements.txt下pyqt5~=5.15.6

build （修改配置文件后，需要重新build）
```shell
docker build  -t fay ./fay-assistant-edition
```
run
```shell
docker run -it --rm -p 5000:5000 -p 10001:10001 -p 10002:10002 -p 10003:10003 fay
```
### **启动数字人（非必须）**

ue: https://github.com/xszyou/fay-ue5

xuniren（2d）：https://qqk9ntwbcit.feishu.cn/wiki/BYn0w7OTKikGGqkRXoLche6Rnob

unity：https://qqk9ntwbcit.feishu.cn/wiki/Se9xw04hUiss00kb2Lmci1BVnM9

metahuman-stream：https://qqk9ntwbcit.feishu.cn/wiki/Ik1kwO9X5iilnGkFwRhcnmtvn3e

duix（android、ios)：https://qqk9ntwbcit.feishu.cn/wiki/Ik1kwO9X5iilnGkFwRhcnmtvn3e

### **启动android 连接器（非必须）**
代码地址：https://github.com/xszyou/fay-android



### **联系**

**商务QQ: 467665317**

**交流群及资料教程**关注公众号 **fay数字人**（**请先star本仓库**）

![](readme/gzh.jpg)
