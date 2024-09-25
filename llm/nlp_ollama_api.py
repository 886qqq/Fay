import json
import requests
import time 
from utils import config_util as cfg
from utils import util
from core import content_db
def question(cont, uid=0):

    contentdb = content_db.new_instance()
    if uid == 0:
        communication_history = contentdb.get_list('all','desc', 11)
    else:
        communication_history = contentdb.get_list('all','desc', 11, uid)
    #历史记录处理
    message=[]
    i = len(communication_history) - 1
    
    if len(communication_history)>1:
        while i >= 0:
            answer_info = dict()
            if communication_history[i][0] == "member":
                answer_info["role"] = "user"
                answer_info["content"] = communication_history[i][2]
            elif communication_history[i][0] == "fay":
                answer_info["role"] = "assistant"
                answer_info["content"] = communication_history[i][2]
            message.append(answer_info)
            i -= 1
    else:
         answer_info = dict()
         answer_info["role"] = "user"
         answer_info["content"] = cont
         message.append(answer_info)
    url=f"http://{cfg.ollama_ip}:11434/api/chat"
    req = json.dumps({
        "model": cfg.ollama_model,
        "messages": message, 
        "stream": False
        })
    headers = {'content-type': 'application/json'}
    session = requests.Session()    
    starttime = time.time()
     
    try:
        response = session.post(url, data=req, headers=headers)
        response.raise_for_status()  # 检查响应状态码是否为200

        result = json.loads(response.text)
        response_text = result["message"]["content"]
        
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        response_text = "抱歉，我现在太忙了，休息一会，请稍后再试。"
    util.log(1, "接口调用耗时 :" + str(time.time() - starttime))
    return response_text.strip()

if __name__ == "__main__":
    for i in range(3):
        query = "爱情是什么"
        response = question(query)        
        print("\n The result is ", response)    