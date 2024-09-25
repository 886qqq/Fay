from langchain.chat_models import ChatOpenAI

# 初始化 ChatOpenAI 实例，设置 base_url
chat = ChatOpenAI(api_key="YOUR_API_KEY", model="gpt-3.5-turbo", base_url="http://127.0.0.1:5000/v1")

# 定义一个函数与 GPT 进行交互
def test_gpt(prompt):
    response = chat.predict(prompt)
    return response

# 测试脚本
if __name__ == "__main__":
    user_input = "你好"
    result = test_gpt(user_input)
    print("GPT 的回复:", result)
