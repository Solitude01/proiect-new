import os
import json
import requests

URL = "https://aiforge.scc.com.cn/api/ai_apaas/console/org_space/instance/debug"

COOKIE =  "idaas-project-id=843ea558d5ef41a1877584c62762632d; idaas-sessionid=ac4c4cbb08ff4ad0be21217a871f3f2a; idaas-csrftoken=24697afa309442abbe16f4a5eb5d640f; idaas-project-name=aiforge; idaas-default-url=\"\"; bce-sessionid=ac4c4cbb08ff4ad0be21217a871f3f2a; bce-auth-type=BCIA; bce-login-display-name=SN47118; PS_DEVICEFEATURES=width:1920 height:1080 pixelratio:1 touch:0 geolocation:1 websockets:1 webworkers:1 datepicker:1 dtpicker:1 timepicker:1 dnd:1 sessionstorage:1 localstorage:1 history:1 canvas:1 svg:1 postmessage:1 hc:0 maf:0; bce-user-info=\"2026-02-03T13:39:11Z|cfc5a9db30759184c643a575b6f4fcc2\"; LRToken=685baa181bca67b283d6d74cffd99dd5c8a512d9d0b04afd966e0d0ae3b7178ca8803acbe46ff95f8395175787ca2f1a03a392ac5202534904e78ff094706fe2b223f92e5563d77c75ab0d1e330259ec8020369983b4f936f0826f99dc62802ced041751df5491e9f6b37a26c147b49593ad77b9d6bcecfd5e3a87ddc45b1a51"         # 整段 Cookie
CSRF_TOKEN = "2026-02-03T13:39:11Z|cfc5a9db30759184c643a575b6f4fcc2"     # csrfToken 头

headers = {
    "content-type": "application/json",
    "origin": "https://aiforge.scc.com.cn",
    "referer": "https://aiforge.scc.com.cn/ai_apaas/personalSpace/app/debugger/assistant/0bfade1e-1e5e-4901-89c6-c1001503248d/831cec36-e8e1-464f-b802-38ea6dbc45b6",
    "csrfToken": CSRF_TOKEN,
    "cookie": COOKIE,
}

with open("payload.json", "r", encoding="utf-8") as f:
    payload = json.load(f)

# 先用 blocking 让你更容易看到返回（如果后端支持）
payload["response_mode"] = "blocking"
payload["query"] = "进行消息推送：消息主题：你好，推送人员：SN151157，消息内容：你好呀，消息类型：ewechat"

r = requests.post(URL, headers=headers, json=payload, timeout=60, allow_redirects=False)

print("status:", r.status_code)
print("content-type:", r.headers.get("content-type"))
print("location:", r.headers.get("location"))  # 如果 302 会有
print("body head:", r.text[:500])