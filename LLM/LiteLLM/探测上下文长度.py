import asyncio
import httpx
import re
import json

CONFIG = {
    "model_name": "glm-4.7-flash",
    "api_url": "http://ds.scc.com.cn/v1/chat/completions",
    "api_key": "1",
    "timeout": 15.0
}

async def probe_context_size():
    print(f"🚀 开始探测模型 [{CONFIG['model_name']}] 的上下文窗口...")
    
    payload = {
        "model": CONFIG["model_name"],
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1000000, # 触发报错
    }
    
    headers = {
        "Authorization": f"Bearer {CONFIG['api_key']}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=CONFIG["timeout"]) as client:
            resp = await client.post(CONFIG["api_url"], headers=headers, json=payload)
            
            # 无论返回 400 还是 500，都尝试解析内容
            content = resp.text
            
            # 核心正则表达式：匹配数字
            patterns = [
                r"maximum context length is (\d+)",
                r"context length of (\d+)",
                r"limit is (\d+) tokens",
                r"max_model_len=(\d+)"
            ]
            
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    size = int(match.group(1))
                    print(f"\n✅ 探测成功！")
                    print(f"HTTP 状态码: {resp.status_code}")
                    print(f"解析结果: {size} tokens")
                    return size

            print(f"❌ 解析失败。收到状态码 {resp.status_code}，但未找到上下文长度信息。")
            print(f"原始响应: {content}")

    except Exception as e:
        print(f"❌ 请求发生异常: {e}")

    return None

if __name__ == "__main__":
    asyncio.run(probe_context_size())