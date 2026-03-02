import requests

# 使用 requests 测试接口是否正常
url = "http://ds.scc.com.cn/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer 0"   # 使用给定秘钥
}

data = {
    "model": "deepseek-r1",
    "messages": [
        {"role": "user", "content": "你好，测试接口是否正常"}
    ]
}

# 发送请求
resp = requests.post(url, headers=headers, json=data)

# 打印结果
print(resp.status_code)   # 打印状态码
print(resp.text)          # 打印返回内容
