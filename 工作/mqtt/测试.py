import paho.mqtt.client as mqtt

BROKER = "10.20.3.106"
PORT   = 1883
USER   = "sedp"
PASS   = "Sdep@2025"
TOPIC  = "sedp-w9/#"   # 订阅所有 sedp-w9 子topic

def on_connect(client, userdata, flags, rc):
    rc_map = {
        0: "✅ 连接成功",
        1: "❌ 协议版本错误",
        2: "❌ 客户端ID无效",
        3: "❌ 服务器不可用",
        4: "❌ 用户名或密码错误",
        5: "❌ 未授权",
    }
    print(f"连接结果: {rc_map.get(rc, f'未知错误 rc={rc}')}")
    if rc == 0:
        client.subscribe(TOPIC)
        print(f"已订阅: {TOPIC}")
        # 连接后立即发一条测试消息
        client.publish("sedp-w9/test", "hello from python")

def on_message(client, userdata, msg):
    print(f"📨 收到消息  topic={msg.topic}  payload={msg.payload.decode()}")

def on_disconnect(client, userdata, rc):
    print(f"断开连接 rc={rc}")

client = mqtt.Client()
client.username_pw_set(USER, PASS)
client.on_connect    = on_connect
client.on_message    = on_message
client.on_disconnect = on_disconnect

print(f"正在连接 {BROKER}:{PORT} ...")
client.connect(BROKER, PORT, keepalive=60)
client.loop_forever()