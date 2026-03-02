import requests

# 定义模型的接口信息
models = [
     "qwen3-8b", "ds-v3", "deepseek-r1"
]

urls = [
    "http://ds.scc.com.cn/v1/chat/completions", 

]

# API 密钥
api_key = "0"  # 设置秘钥为 "0"

# 生成模型和接口的所有组合
combinations = []
for model in models:
    for url in urls:
        combinations.append((model, url))

# 测试每个模型与接口的组合
for model_name, model_url in combinations:
    try:
        # 向模型接口发送请求，示例请求体
        payload = {
            "model": model_name,
            "messages": [{"role": "system", "content": "Hello, test."}],
        }
        
        # 请求头，添加 Authorization 信息
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",  # 使用秘钥 "0"
        }
        
        # 发送 POST 请求
        response = requests.post(model_url, json=payload, headers=headers)

        # 检查返回状态
        if response.status_code == 200:
            print(f"模型 {model_name} 在接口 {model_url} 可用！6666666666666666666666666666666666666")
        else:
            print(f"模型 {model_name} 在接口 {model_url} 无法使用，状态码：{response.status_code}，错误信息：{response.text}")
    except requests.exceptions.RequestException as e:
        print(f"请求模型 {model_name} 在接口 {model_url} 时发生错误: {e}")
