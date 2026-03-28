"""
Claude Code -> Chat Completions API 协议转换代理（完整版 v4）
新增功能：
  - /dashboard  实时监控面板（Token消耗、请求统计、错误率、用户隔离）
  - 按 IP / API-Key 隔离统计
  - 请求历史日志（最近200条）
  - 自动裁剪 max_tokens 防止超出上下文
端口：4001  监控面板：http://localhost:4001/dashboard
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
import httpx, uvicorn, json, time, uuid
from collections import defaultdict, deque
from datetime import datetime
import threading

# ===================== 配置区 =====================
BACKEND_URL        = "http://ds.scc.com.cn/v1/chat/completions"
BACKEND_KEY        = "0"
LISTEN_HOST        = "0.0.0.0"
LISTEN_PORT        = 4001
DEFAULT_MODEL      = "ds-v3"
TIMEOUT            = 180
MODEL_CONTEXT_SIZE = 40960
MAX_TOKENS_CAP     = 4096
# =================================================

app = FastAPI(title="ClaudeCode->ChatCompletions Proxy")

# ─────────────────────── 统计存储 ───────────────────────

class Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.start_time   = time.time()
        self.total_reqs   = 0
        self.total_ok     = 0
        self.total_err    = 0
        self.total_in_tok = 0
        self.total_out_tok= 0
        self.total_latency= 0.0   # 秒
        # 按用户（IP 或 API-Key 前8位）
        self.user_stats   = defaultdict(lambda: {
            "reqs":0,"ok":0,"err":0,"in_tok":0,"out_tok":0,"last_seen":""
        })
        # 最近200条请求日志
        self.log = deque(maxlen=200)
        # 每分钟请求数（最近60分钟）
        self.rpm_buckets  = defaultdict(int)   # minute_ts -> count

    def record(self, user_id: str, ok: bool, in_tok: int, out_tok: int, latency: float, error: str = ""):
        ts = datetime.now()
        minute_key = ts.strftime("%H:%M")
        with self._lock:
            self.total_reqs   += 1
            self.total_in_tok += in_tok
            self.total_out_tok+= out_tok
            self.total_latency+= latency
            self.rpm_buckets[minute_key] += 1
            if ok:
                self.total_ok += 1
            else:
                self.total_err += 1
            u = self.user_stats[user_id]
            u["reqs"]    += 1
            u["in_tok"]  += in_tok
            u["out_tok"] += out_tok
            u["last_seen"]= ts.strftime("%H:%M:%S")
            if ok: u["ok"] += 1
            else:  u["err"]+= 1
            self.log.append({
                "time":    ts.strftime("%H:%M:%S"),
                "user":    user_id,
                "ok":      ok,
                "in_tok":  in_tok,
                "out_tok": out_tok,
                "latency": round(latency, 2),
                "error":   error[:120] if error else "",
            })

    def snapshot(self):
        with self._lock:
            uptime = int(time.time() - self.start_time)
            avg_lat = (self.total_latency / self.total_ok) if self.total_ok else 0
            # 最近10分钟 RPM
            now_min = datetime.now().strftime("%H:%M")
            recent_rpm = list(self.rpm_buckets.items())[-10:]
            return {
                "uptime_s":    uptime,
                "total_reqs":  self.total_reqs,
                "total_ok":    self.total_ok,
                "total_err":   self.total_err,
                "total_in_tok":self.total_in_tok,
                "total_out_tok":self.total_out_tok,
                "avg_latency": round(avg_lat, 2),
                "users":       dict(self.user_stats),
                "recent_log":  list(reversed(self.log)),
                "rpm_chart":   recent_rpm,
            }

stats = Stats()


def get_user_id(request: Request) -> str:
    """从请求头提取用户标识（API Key 前8位，或 IP）"""
    auth = request.headers.get("x-api-key") or request.headers.get("authorization", "")
    if auth and auth != "Bearer any-value" and len(auth) > 8:
        key = auth.replace("Bearer ", "")[:8]
        return f"key:{key}"
    # fallback 到 IP
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    return f"ip:{ip.split(',')[0].strip()}"


# ─────────────────────── 工具定义注入 ───────────────────────

TOOLS_SYSTEM_ADDON = """
You are Claude Code, an AI coding assistant. You have access to the following tools.
When you want to use a tool, respond with a JSON block in this EXACT format:
<tool_call>
{"name": "TOOL_NAME", "input": {PARAMETERS}}
</tool_call>

Available tools:
- Bash: {"command": "shell command", "description": "why"}
- Read: {"file_path": "/abs/path"}
- Write: {"file_path": "/abs/path", "content": "file content"}
- Edit: {"file_path": "/abs/path", "old_string": "...", "new_string": "..."}
- Glob: {"pattern": "**/*.py", "path": "/optional/base"}
- Grep: {"pattern": "search term", "path": "/dir", "include": "*.py"}
- WebFetch: {"url": "https://...", "prompt": "what to extract"}
- WebSearch: {"query": "search terms"}
- TodoWrite: {"todos": [{"id":"1","content":"task","status":"pending","priority":"high"}]}
- Task: {"description": "task desc", "prompt": "detailed instructions", "subagent_type": "general-purpose"}

IMPORTANT: Only use <tool_call> blocks for actual tool invocations. Always explain what you are doing.
"""


# ─────────────────────── 消息转换 ───────────────────────

def anthropic_to_openai_messages(messages: list, system: str | None) -> list:
    result = []
    if system:
        result.append({"role": "system", "content": system + "\n\n" + TOOLS_SYSTEM_ADDON})

    for msg in messages:
        role    = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        if isinstance(content, list):
            text_parts = []
            tool_calls = []
            tool_results = []

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    tool_calls.append({
                        "id": block.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                        }
                    })
                elif btype == "tool_result":
                    inner = block.get("content", "")
                    if isinstance(inner, list):
                        inner = "\n".join(c.get("text","") for c in inner if isinstance(c,dict) and c.get("type")=="text")
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": str(inner),
                    })

            if tool_calls:
                result.append({"role":"assistant","content":" ".join(text_parts) or None,"tool_calls":tool_calls})
            elif text_parts:
                result.append({"role": role, "content": " ".join(text_parts)})
            for tr in tool_results:
                result.append(tr)

    return result


def convert_tools_to_openai(anthropic_tools: list) -> list:
    return [{"type":"function","function":{"name":t.get("name",""),"description":t.get("description",""),"parameters":t.get("input_schema",{"type":"object","properties":{}})}} for t in anthropic_tools]


def parse_system(body: dict) -> str | None:
    sys = body.get("system")
    if isinstance(sys, str): return sys
    if isinstance(sys, list): return "\n".join(b.get("text","") for b in sys if isinstance(b,dict) and b.get("type")=="text")
    return None


def safe_max_tokens(body: dict, input_token_estimate: int = 4000) -> int:
    requested = body.get("max_tokens", MAX_TOKENS_CAP)
    adjusted  = int(input_token_estimate * 1.5)
    available = MODEL_CONTEXT_SIZE - adjusted - 512
    return min(requested, MAX_TOKENS_CAP, max(available, 256))


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ─────────────────────── 流式生成器 ───────────────────────

async def stream_anthropic(body: dict, user_id: str):
    t0       = time.time()
    model    = body.get("model", DEFAULT_MODEL)
    system   = parse_system(body)
    messages = anthropic_to_openai_messages(body.get("messages", []), system)
    msg_id   = f"msg_{uuid.uuid4().hex[:24]}"

    input_text_len   = sum(len(str(m.get("content",""))) for m in messages)
    input_tokens_est = input_text_len // 4

    chat_body: dict = {
        "model":          model,
        "messages":       messages,
        "stream":         True,
        "stream_options": {"include_usage": True},
        "temperature":    body.get("temperature", 1.0),
        "top_p":          body.get("top_p", 1.0),
        "max_tokens":     safe_max_tokens(body, input_tokens_est),
    }
    anth_tools = body.get("tools", [])
    if anth_tools:
        oai = convert_tools_to_openai(anth_tools)
        if oai:
            chat_body["tools"]       = oai
            chat_body["tool_choice"] = "auto"

    headers = {"Authorization": f"Bearer {BACKEND_KEY}", "Content-Type": "application/json"}

    yield sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id, "type": "message", "role": "assistant",
            "model": model, "content": [], "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": input_tokens_est, "output_tokens": 0},
        }
    })
    yield sse("ping", {"type": "ping"})

    full_text = ""
    text_started = False
    text_block_index = next_block_index = 0
    input_tokens = input_tokens_est
    output_tokens = 0
    finish_reason = "end_turn"
    tc_map: dict  = {}
    error_msg = ""

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream("POST", BACKEND_URL, json=chat_body, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"): continue
                    raw = line[5:].strip()
                    if raw == "[DONE]": break
                    try: chunk = json.loads(raw)
                    except: continue

                    choice = chunk.get("choices",[{}])[0]
                    delta  = choice.get("delta",{})
                    finish_reason = choice.get("finish_reason") or finish_reason

                    text_piece = delta.get("content","")
                    if text_piece:
                        if not text_started:
                            text_block_index = next_block_index
                            next_block_index += 1
                            yield sse("content_block_start",{"type":"content_block_start","index":text_block_index,"content_block":{"type":"text","text":""}})
                            text_started = True
                        full_text += text_piece
                        yield sse("content_block_delta",{"type":"content_block_delta","index":text_block_index,"delta":{"type":"text_delta","text":text_piece}})

                    for tc in delta.get("tool_calls",[]):
                        idx = tc.get("index",0)
                        if idx not in tc_map:
                            tc_id = tc.get("id",f"toolu_{uuid.uuid4().hex[:20]}")
                            tc_name = tc.get("function",{}).get("name","")
                            bi = next_block_index; next_block_index += 1
                            tc_map[idx] = {"id":tc_id,"name":tc_name,"arguments_buf":"","block_index":bi}
                            yield sse("content_block_start",{"type":"content_block_start","index":bi,"content_block":{"type":"tool_use","id":tc_id,"name":tc_name,"input":{}}})
                        ap = tc.get("function",{}).get("arguments","")
                        if ap:
                            tc_map[idx]["arguments_buf"] += ap
                            yield sse("content_block_delta",{"type":"content_block_delta","index":tc_map[idx]["block_index"],"delta":{"type":"input_json_delta","partial_json":ap}})

                    usage = chunk.get("usage",{})
                    if usage:
                        input_tokens  = usage.get("prompt_tokens", input_tokens_est)
                        output_tokens = usage.get("completion_tokens", 0)

        stats.record(user_id, True, input_tokens, output_tokens, time.time()-t0)

    except httpx.HTTPStatusError as e:
        error_msg = f"Backend {e.response.status_code}: {e.response.text[:200]}"
        stats.record(user_id, False, input_tokens_est, 0, time.time()-t0, error_msg)
        yield sse("error",{"type":"error","error":{"type":"api_error","message":error_msg}})
        return
    except Exception as e:
        error_msg = str(e)
        stats.record(user_id, False, input_tokens_est, 0, time.time()-t0, error_msg)
        yield sse("error",{"type":"error","error":{"type":"api_error","message":error_msg}})
        return

    if text_started:
        yield sse("content_block_stop",{"type":"content_block_stop","index":text_block_index})
    for tc in tc_map.values():
        yield sse("content_block_stop",{"type":"content_block_stop","index":tc["block_index"]})

    stop_reason = {"tool_calls":"tool_use","length":"max_tokens"}.get(finish_reason,"end_turn")
    yield sse("message_delta",{"type":"message_delta","delta":{"stop_reason":stop_reason,"stop_sequence":None},"usage":{"output_tokens":output_tokens}})
    yield sse("message_stop",{"type":"message_stop"})


# ─────────────────────── 路由 ───────────────────────

@app.post("/v1/messages")
async def messages_endpoint(request: Request):
    user_id = get_user_id(request)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error":"Invalid JSON"}, status_code=400)

    if body.get("stream", False):
        return StreamingResponse(
            stream_anthropic(body, user_id),
            media_type="text/event-stream",
            headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"},
        )

    t0 = time.time()
    model    = body.get("model", DEFAULT_MODEL)
    system   = parse_system(body)
    messages = anthropic_to_openai_messages(body.get("messages",[]), system)
    input_text_len = sum(len(str(m.get("content",""))) for m in messages)
    chat_body: dict = {"model":model,"messages":messages,"stream":False,"max_tokens":safe_max_tokens(body, input_text_len//4)}
    anth_tools = body.get("tools",[])
    if anth_tools:
        oai = convert_tools_to_openai(anth_tools)
        if oai: chat_body["tools"]=oai; chat_body["tool_choice"]="auto"

    headers = {"Authorization":f"Bearer {BACKEND_KEY}","Content-Type":"application/json"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(BACKEND_URL, json=chat_body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        stats.record(user_id, False, input_text_len//4, 0, time.time()-t0, e.response.text[:120])
        return JSONResponse({"error":e.response.text}, status_code=502)
    except Exception as e:
        stats.record(user_id, False, input_text_len//4, 0, time.time()-t0, str(e))
        return JSONResponse({"error":str(e)}, status_code=502)

    choice  = data["choices"][0]
    message = choice["message"]
    usage   = data.get("usage",{})
    blocks  = []
    if message.get("content"):
        blocks.append({"type":"text","text":message["content"]})
    for tc in message.get("tool_calls",[]):
        try: inp = json.loads(tc["function"]["arguments"])
        except: inp = {}
        blocks.append({"type":"tool_use","id":tc.get("id",f"toolu_{uuid.uuid4().hex[:20]}"),"name":tc["function"]["name"],"input":inp})

    fr = choice.get("finish_reason","stop")
    stop_reason = {"tool_calls":"tool_use","length":"max_tokens"}.get(fr,"end_turn")
    in_tok  = usage.get("prompt_tokens",0)
    out_tok = usage.get("completion_tokens",0)
    stats.record(user_id, True, in_tok, out_tok, time.time()-t0)

    return JSONResponse({
        "id": data.get("id",f"msg_{uuid.uuid4().hex[:24]}"),
        "type":"message","role":"assistant","model":data.get("model",model),
        "content":blocks,"stop_reason":stop_reason,"stop_sequence":None,
        "usage":{"input_tokens":in_tok,"output_tokens":out_tok},
    })


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    try:
        body  = await request.json()
        total = sum(len(str(m.get("content",""))) for m in body.get("messages",[])) // 4
    except: total = 1024
    return JSONResponse({"input_tokens": total})


@app.get("/v1/models")
async def list_models():
    return JSONResponse({"object":"list","data":[{"id":DEFAULT_MODEL,"object":"model","created":int(time.time()),"owned_by":"local"}]})


@app.get("/health")
async def health():
    return {"status":"ok","backend":BACKEND_URL,"port":LISTEN_PORT}


# ─────────────────────── 监控面板 ───────────────────────

@app.get("/stats")
async def get_stats():
    return JSONResponse(stats.snapshot())


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(DASHBOARD_HTML)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude Code Proxy 监控</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh}
.header{background:linear-gradient(135deg,#1a1f2e,#252b3b);padding:20px 32px;border-bottom:1px solid #2d3748;display:flex;align-items:center;gap:16px}
.header h1{font-size:1.4rem;font-weight:600;color:#a78bfa}
.header .sub{font-size:.85rem;color:#64748b;margin-top:2px}
.badge{background:#a78bfa22;color:#a78bfa;padding:3px 10px;border-radius:99px;font-size:.78rem;border:1px solid #a78bfa44}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;padding:24px 32px 0}
.card{background:#1a1f2e;border:1px solid #2d3748;border-radius:12px;padding:20px}
.card .label{font-size:.78rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px}
.card .value{font-size:2rem;font-weight:700;color:#e2e8f0}
.card .value.green{color:#34d399}
.card .value.red{color:#f87171}
.card .value.blue{color:#60a5fa}
.card .value.purple{color:#a78bfa}
.card .sub{font-size:.8rem;color:#64748b;margin-top:4px}
.section{padding:24px 32px}
.section h2{font-size:1rem;font-weight:600;color:#94a3b8;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.section h2::before{content:'';display:inline-block;width:3px;height:1em;background:#a78bfa;border-radius:2px}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:8px 12px;color:#64748b;font-weight:500;border-bottom:1px solid #2d3748;font-size:.78rem;text-transform:uppercase}
td{padding:9px 12px;border-bottom:1px solid #1e2433;color:#cbd5e1}
tr:hover td{background:#1e2433}
.ok{color:#34d399}.err{color:#f87171}.warn{color:#fbbf24}
.bar-wrap{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.bar-label{width:48px;font-size:.78rem;color:#64748b;text-align:right;flex-shrink:0}
.bar-bg{flex:1;height:18px;background:#1e2433;border-radius:4px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,#6366f1,#a78bfa);border-radius:4px;transition:width .5s}
.bar-val{width:48px;font-size:.78rem;color:#94a3b8;flex-shrink:0}
.refresh{font-size:.78rem;color:#475569;padding:0 32px 16px;display:flex;align-items:center;gap:8px}
.dot{width:7px;height:7px;background:#34d399;border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:500}
.tag.ok{background:#34d39922;color:#34d399}.tag.err{background:#f8717122;color:#f87171}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🔮 Claude Code Proxy 监控面板</h1>
    <div class="sub">实时 API 使用统计 · 本地模型代理</div>
  </div>
  <div class="badge" id="backend-url">加载中...</div>
</div>
<div class="refresh"><span class="dot"></span>每 5 秒自动刷新 · 最后更新: <span id="last-update">-</span></div>

<div class="grid" id="cards"></div>

<div class="section">
  <h2>最近10分钟 请求量趋势</h2>
  <div id="rpm-chart"></div>
</div>

<div class="section">
  <h2>用户统计（按 IP / API Key）</h2>
  <table><thead><tr>
    <th>用户标识</th><th>请求数</th><th>成功</th><th>失败</th>
    <th>输入 Tokens</th><th>输出 Tokens</th><th>最后活跃</th>
  </tr></thead><tbody id="user-table"></tbody></table>
</div>

<div class="section">
  <h2>最近请求日志</h2>
  <table><thead><tr>
    <th>时间</th><th>用户</th><th>状态</th>
    <th>输入 Token</th><th>输出 Token</th><th>耗时(s)</th><th>错误</th>
  </tr></thead><tbody id="log-table"></tbody></table>
</div>

<script>
async function refresh(){
  try{
    const r=await fetch('/stats');
    const d=await r.json();
    document.getElementById('last-update').textContent=new Date().toLocaleTimeString();
    document.getElementById('backend-url').textContent='后端: '+location.host;

    const upH=Math.floor(d.uptime_s/3600),upM=Math.floor((d.uptime_s%3600)/60);
    const errRate=d.total_reqs?((d.total_err/d.total_reqs)*100).toFixed(1):0;
    document.getElementById('cards').innerHTML=`
      <div class="card"><div class="label">总请求数</div><div class="value blue">${d.total_reqs.toLocaleString()}</div><div class="sub">成功 ${d.total_ok} / 失败 ${d.total_err}</div></div>
      <div class="card"><div class="label">输入 Tokens</div><div class="value purple">${d.total_in_tok.toLocaleString()}</div><div class="sub">累计消耗</div></div>
      <div class="card"><div class="label">输出 Tokens</div><div class="value purple">${d.total_out_tok.toLocaleString()}</div><div class="sub">累计生成</div></div>
      <div class="card"><div class="label">总 Tokens</div><div class="value">${(d.total_in_tok+d.total_out_tok).toLocaleString()}</div><div class="sub">输入+输出</div></div>
      <div class="card"><div class="label">平均延迟</div><div class="value ${d.avg_latency>30?'red':d.avg_latency>10?'warn':'green'}">${d.avg_latency}s</div><div class="sub">成功请求</div></div>
      <div class="card"><div class="label">错误率</div><div class="value ${errRate>10?'red':errRate>5?'warn':'green'}">${errRate}%</div><div class="sub">共 ${d.total_err} 次错误</div></div>
      <div class="card"><div class="label">活跃用户</div><div class="value green">${Object.keys(d.users).length}</div><div class="sub">累计接入</div></div>
      <div class="card"><div class="label">运行时长</div><div class="value">${upH}h ${upM}m</div><div class="sub">启动后持续运行</div></div>
    `;

    // RPM 图表
    const maxRPM=Math.max(...d.rpm_chart.map(x=>x[1]),1);
    document.getElementById('rpm-chart').innerHTML=d.rpm_chart.map(([t,v])=>`
      <div class="bar-wrap">
        <div class="bar-label">${t}</div>
        <div class="bar-bg"><div class="bar-fill" style="width:${(v/maxRPM*100).toFixed(1)}%"></div></div>
        <div class="bar-val">${v}次</div>
      </div>`).join('');

    // 用户表
    document.getElementById('user-table').innerHTML=Object.entries(d.users).sort((a,b)=>b[1].reqs-a[1].reqs).map(([uid,u])=>`
      <tr>
        <td>${uid}</td><td>${u.reqs}</td>
        <td class="ok">${u.ok}</td><td class="err">${u.err}</td>
        <td>${u.in_tok.toLocaleString()}</td><td>${u.out_tok.toLocaleString()}</td>
        <td>${u.last_seen}</td>
      </tr>`).join('');

    // 日志表
    document.getElementById('log-table').innerHTML=d.recent_log.slice(0,50).map(l=>`
      <tr>
        <td>${l.time}</td><td>${l.user}</td>
        <td><span class="tag ${l.ok?'ok':'err'}">${l.ok?'OK':'ERR'}</span></td>
        <td>${l.in_tok}</td><td>${l.out_tok}</td>
        <td>${l.latency}</td>
        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;color:#f87171">${l.error||''}</td>
      </tr>`).join('');
  }catch(e){console.error(e)}
}
refresh();
setInterval(refresh,5000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    print(f"\n{'='*52}")
    print(f"  Claude Code 本地模型代理  v4")
    print(f"  监听地址   : http://{LISTEN_HOST}:{LISTEN_PORT}")
    print(f"  后端模型   : {BACKEND_URL}")
    print(f"  监控面板   : http://localhost:{LISTEN_PORT}/dashboard")
    print(f"  上下文窗口 : {MODEL_CONTEXT_SIZE} tokens")
    print(f"  max_tokens : {MAX_TOKENS_CAP}")
    print(f"{'='*52}")
    print(f"\n  启动 Claude Code 前设置环境变量：")
    print(f"  set ANTHROPIC_BASE_URL=http://localhost:{LISTEN_PORT}")
    print(f"  set ANTHROPIC_AUTH_TOKEN=any-value")
    print(f"  claude\n")
    uvicorn.run(app, host=LISTEN_HOST, port=LISTEN_PORT)