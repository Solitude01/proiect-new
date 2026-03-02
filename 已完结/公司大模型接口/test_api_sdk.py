import requests
import os

# --- 关键配置：强制禁用代理 ---
# 在公司内网访问内部服务时，必须绕过系统代理
os.environ['NO_PROXY'] = 'ds.scc.com.cn,localhost,127.0.0.1'
# 也可以显式设置 session 的 trust_env 为 False，见下文
# ---------------------------

# 定义模型和接口
models = ["ds-v3", "qwen3-8b"]
urls = ["http://ds.scc.com.cn/v1/chat/completions"]
api_key = "0"

# 生成组合
combinations = []
for model in models:
    for url in urls:
        combinations.append((model, url))

# 创建一个 Session 对象，比直接用 requests 更稳定
session = requests.Session()

# 【关键点 1】告诉 Session 不要读取系统的代理设置 (环境变量)
session.trust_env = False 

# 测试
print("开始测试连接...\n")

for model_name, model_url in combinations:
    try:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Hello, 1+1=?"}],
            "stream": False # 显式关闭流式输出，减少连接复杂性
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            # 【关键点 2】伪装成浏览器 User-Agent，防止被防火墙当做爬虫拦截
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        print(f"正在尝试: {model_name} -> {model_url}")
        
        # 使用配置好的 session 发送请求
        response = session.post(model_url, json=payload, headers=headers, timeout=10)

        if response.status_code == 200:
            print(f"✅ [成功] 模型 {model_name} 可用！")
            print(f"   回复内容: {response.json()['choices'][0]['message']['content'][:50]}...")
        else:
            print(f"❌ [失败] 状态码：{response.status_code}")
            print(f"   错误信息：{response.text}")
            
    except Exception as e:
        print(f"❌ [连接错误] 模型 {model_name}: {e}")

    print("-" * 30)