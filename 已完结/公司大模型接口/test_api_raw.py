import requests
import json

# --- 配置区域 ---
# 注意：原生请求必须写全路径
FULL_URL = "http://ds.scc.com.cn/v1/chat/completions" 
API_KEY = "0"
MODEL_ID = "qwen3-8b" #"ds-v3"
# ----------------

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

data = {
    "model": MODEL_ID,
    "messages": [{"role": "user", "content": "测试连接"}],
    "max_tokens": 50
}

print(f"正在发送原生 POST 请求到: {FULL_URL}")

try:
    response = requests.post(FULL_URL, headers=headers, json=data, timeout=10)
    
    print(f"\n状态码: {response.status_code}")
    
    # 打印服务器信息，帮你判断后端框架
    server_header = response.headers.get('Server', '未知')
    print(f"🔍 服务器标识 (Server Header): [{server_header}]")
    
    if response.status_code == 200:
        res_json = response.json()
        content = res_json['choices'][0]['message']['content']
        print(f"✅ 回复: {content}")
    else:
        print(f"❌ 请求失败: {response.text}")

except Exception as e:
    print(f"❌ 连接错误: {e}")