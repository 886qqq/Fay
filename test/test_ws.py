import websocket
import datetime
import threading

def on_message(ws, message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    print(f"[{timestamp}] Received message: {message}")

def on_error(ws, error):
    print(f"[Error] {error}")

def on_close(ws, close_status_code, close_msg):
    print("### Connection closed ###")

def on_open(ws):
    print("### Connection opened ###")

if __name__ == "__main__":
    # 启用 WebSocket 调试信息（可选）
    # websocket.enableTrace(True)

    # 替换为您的 WebSocket 服务器地址
    ws_url = "ws://127.0.0.1:10002"

    ws = websocket.WebSocketApp(ws_url,
                                on_open=on_open,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close)

    # 运行 WebSocket 客户端
    wst = threading.Thread(target=ws.run_forever)
    wst.daemon = True
    wst.start()

    try:
        while True:
            pass  # 保持主线程运行
    except KeyboardInterrupt:
        ws.close()
        print("Exited")
