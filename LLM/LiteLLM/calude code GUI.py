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
        self.tpm_buckets  = defaultdict(int)   # minute_ts -> total_tokens

    def record(self, user_id: str, ok: bool, in_tok: int, out_tok: int, latency: float, error: str = ""):
        ts = datetime.now()
        minute_key = ts.strftime("%H:%M")
        with self._lock:
            self.total_reqs   += 1
            self.total_in_tok += in_tok
            self.total_out_tok+= out_tok
            self.total_latency+= latency
            self.rpm_buckets[minute_key] += 1
            self.tpm_buckets[minute_key] += (in_tok + out_tok)
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
            uptime_min = max(uptime // 60, 1)
            avg_lat = (self.total_latency / self.total_ok) if self.total_ok else 0
            avg_rpm = self.total_reqs / uptime_min
            avg_tpm = (self.total_in_tok + self.total_out_tok) / uptime_min
            # 最近10分钟 RPM
            now_min = datetime.now().strftime("%H:%M")
            recent_rpm = list(self.rpm_buckets.items())[-10:]
            recent_tpm = list(self.tpm_buckets.items())[-10:]
            return {
                "uptime_s":    uptime,
                "total_reqs":  self.total_reqs,
                "total_ok":    self.total_ok,
                "total_err":   self.total_err,
                "total_in_tok":self.total_in_tok,
                "total_out_tok":self.total_out_tok,
                "avg_latency": round(avg_lat, 2),
                "avg_rpm":     round(avg_rpm, 2),
                "avg_tpm":     round(avg_tpm, 2),
                "users":       dict(self.user_stats),
                "recent_log":  list(reversed(self.log)),
                "rpm_chart":   recent_rpm,
                "tpm_chart":   recent_tpm,
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
        try:
            error_text = e.response.text
        except httpx.ResponseNotRead:
            try:
                e.response.read()
                error_text = e.response.text
            except Exception:
                error_text = f"<streaming response, status={e.response.status_code}>"
        except Exception:
            error_text = "<unable to read response>"
        error_msg = f"Backend {e.response.status_code}: {error_text[:200]}"
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


@app.get("/")
async def root():
    return {"status":"ok","service":"claude-code-proxy","version":"v4"}


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
:root{
--bg:#0f1117;--card-bg:#1a1f2e;--border:#2d3748;--text:#e2e8f0;
--text-dim:#64748b;--text-mid:#94a3b8;--purple:#a78bfa;--purple-dim:#a78bfa22;
--purple-border:#a78bfa44;--green:#34d399;--green-dim:#34d39922;
--red:#f87171;--red-dim:#f8717122;--blue:#60a5fa;--warn:#fbbf24;
--row-hover:#1e2433;--bar-bg:#1e2433;
}
body{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
.header{background:linear-gradient(135deg,#1a1f2e,#252b3b);padding:20px 32px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px}
.header h1{font-size:1.4rem;font-weight:600;color:var(--purple)}
.header .sub{font-size:.85rem;color:var(--text-dim);margin-top:2px}
.badge{background:var(--purple-dim);color:var(--purple);padding:3px 10px;border-radius:99px;font-size:.78rem;border:1px solid var(--purple-border)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;padding:24px 32px 0}
.card{background:var(--card-bg);border:1px solid var(--border);border-radius:12px;padding:20px}
.card .label{font-size:.78rem;color:var(--text-dim);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px}
.card .value{font-size:2rem;font-weight:700;color:var(--text)}
.card .value.green{color:var(--green)}
.card .value.red{color:var(--red)}
.card .value.blue{color:var(--blue)}
.card .value.purple{color:var(--purple)}
.card .sub{font-size:.8rem;color:var(--text-dim);margin-top:4px}
.section{padding:24px 32px}
.section h2{font-size:1rem;font-weight:600;color:var(--text-mid);margin-bottom:14px;display:flex;align-items:center;gap:8px}
.section h2::before{content:'';display:inline-block;width:3px;height:1em;background:var(--purple);border-radius:2px}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:8px 12px;color:var(--text-dim);font-weight:500;border-bottom:1px solid var(--border);font-size:.78rem;text-transform:uppercase}
td{padding:9px 12px;border-bottom:1px solid var(--row-hover);color:var(--text-mid)}
tr:hover td{background:var(--row-hover)}
.ok{color:var(--green)}.err{color:var(--red)}.warn{color:var(--warn)}
.bar-wrap{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.bar-label{width:48px;font-size:.78rem;color:var(--text-dim);text-align:right;flex-shrink:0}
.bar-bg{flex:1;height:18px;background:var(--bar-bg);border-radius:4px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,#6366f1,var(--purple));border-radius:4px;transition:width .5s}
.bar-wrap:hover .bar-fill{filter:brightness(1.2)}
.bar-val{width:48px;font-size:.78rem;color:var(--text-mid);flex-shrink:0}
@keyframes slideDown{from{transform:translateY(-100%)}to{transform:translateY(0)}}
.refresh{font-size:.78rem;color:#475569;padding:0 32px 16px;display:flex;align-items:center;gap:8px}
.dot{width:7px;height:7px;background:#34d399;border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:500}
.tag.ok{background:#34d39922;color:#34d399}.tag.err{background:#f8717122;color:#f87171}
@media(max-width:768px){
.header{padding:16px;flex-wrap:wrap;gap:12px}
.header h1{font-size:1.1rem;width:100%}
.grid{padding:16px;gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}
.card{padding:14px}
.card .value{font-size:1.4rem}
.section{padding:16px}
table{font-size:.75rem}
th,td{padding:6px 8px}
.bar-label{width:36px;font-size:.7rem}
.bar-val{width:36px;font-size:.7rem}
}
@media(max-width:480px){
.grid{grid-template-columns:1fr}
.header button{font-size:.75rem;padding:5px 10px}
}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🔮 Claude Code Proxy 监控面板</h1>
    <div class="sub">实时 API 使用统计 · 本地模型代理</div>
  </div>
  <div class="badge" id="backend-url">加载中...</div>
  <button onclick="refresh()" style="margin-left:auto;background:#a78bfa22;color:#a78bfa;border:1px solid #a78bfa44;padding:6px 16px;border-radius:6px;cursor:pointer;font-size:.85rem;display:flex;align-items:center;gap:6px;transition:all .2s" onmouseover="this.style.background='#a78bfa33'" onmouseout="this.style.background='#a78bfa22'">⟳ 刷新</button>
  <button onclick="exportData()" style="background:#34d39922;color:#34d399;border:1px solid #34d39944;padding:6px 16px;border-radius:6px;cursor:pointer;font-size:.85rem;display:flex;align-items:center;gap:6px;transition:all .2s" onmouseover="this.style.background='#34d39933'" onmouseout="this.style.background='#34d39922'">↓ 导出</button>
</div>
<div class="refresh"><span class="dot"></span>每 5 秒自动刷新 · 最后更新: <span id="last-update">-</span></div>

<div class="grid" id="cards"></div>

<div class="section">
  <h2>最近10分钟 请求量与Token趋势</h2>
  <div id="rpm-chart" role="img" aria-label="最近10分钟请求量与Token趋势图"></div>
</div>

<div class="section">
  <h2>Token 消耗分布</h2>
  <div id="token-pie-chart" role="img" aria-label="Token消耗分布饼图"></div>
</div>

<div class="section">
  <h2>用户活跃度排行</h2>
  <div id="user-rank-chart" role="img" aria-label="用户活跃度排行图"></div>
</div>

<div class="section">
  <h2>用户统计（按 IP / API Key）</h2>
  <table role="table" aria-label="用户统计数据"><thead><tr>
    <th>用户标识</th><th>请求数</th><th>成功</th><th>失败</th>
    <th>输入 Tokens</th><th>输出 Tokens</th><th>最后活跃</th>
  </tr></thead><tbody id="user-table"></tbody></table>
</div>

<div class="section">
  <h2>最近请求日志</h2>
  <table role="table" aria-label="最近请求日志"><thead><tr>
    <th>时间</th><th>用户</th><th>状态</th>
    <th>输入 Token</th><th>输出 Token</th><th>耗时(s)</th><th>错误</th>
  </tr></thead><tbody id="log-table"></tbody></table>
</div>

<script>
let refreshInProgress = false;

function esc(s){
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function exportData(){
  fetch('/stats').then(r=>r.json()).then(d=>{
    const ts = new Date().toISOString().replace(/[:.]/g,'-');
    // 导出 JSON
    const blob = new Blob([JSON.stringify(d,null,2)],{type:'application/json'});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'proxy-stats-' + ts + '.json';
    a.click();
    URL.revokeObjectURL(a.href);
  }).catch(e=>showError('导出失败: '+e.message));
}

function showError(msg){
  const existing = document.getElementById('error-banner');
  if(existing) existing.remove();
  const banner = document.createElement('div');
  banner.id = 'error-banner';
  banner.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#f87171;color:#fff;padding:12px 32px;text-align:center;font-size:.85rem;z-index:9999;animation:slideDown .3s ease';
  banner.textContent = '⚠ 数据加载失败: ' + msg;
  document.body.insertBefore(banner, document.body.firstChild);
  setTimeout(()=>{ if(banner.parentNode) banner.remove(); }, 5000);
}

async function refresh(){
  if(refreshInProgress) return;
  refreshInProgress = true;

  // 显示加载状态
  const refreshBtn = document.querySelector('.header button');
  if(refreshBtn){
    refreshBtn.disabled = true;
    refreshBtn.style.opacity = '0.5';
  }

  try{
    const response = await fetch('/stats');
    if(!response.ok) throw new Error('HTTP ' + response.status);
    const statsData = await response.json();
    document.getElementById('last-update').textContent=new Date().toLocaleTimeString();
    document.getElementById('backend-url').textContent='后端: '+location.host;

    const upH=Math.floor(statsData.uptime_s/3600),upM=Math.floor((statsData.uptime_s%3600)/60);
    const errRate=statsData.total_reqs?((statsData.total_err/statsData.total_reqs)*100).toFixed(1):0;
    document.getElementById('cards').innerHTML=`
      <div class="card"><div class="label">总请求数</div><div class="value blue">${statsData.total_reqs.toLocaleString()}</div><div class="sub">成功 ${statsData.total_ok} / 失败 ${statsData.total_err}</div></div>
      <div class="card"><div class="label">输入 Tokens</div><div class="value purple">${statsData.total_in_tok.toLocaleString()}</div><div class="sub">累计消耗</div></div>
      <div class="card"><div class="label">输出 Tokens</div><div class="value purple">${statsData.total_out_tok.toLocaleString()}</div><div class="sub">累计生成</div></div>
      <div class="card"><div class="label">总 Tokens</div><div class="value">${(statsData.total_in_tok+statsData.total_out_tok).toLocaleString()}</div><div class="sub">输入+输出</div></div>
      <div class="card"><div class="label">平均延迟</div><div class="value ${statsData.avg_latency>30?'red':statsData.avg_latency>10?'warn':'green'}">${statsData.avg_latency}s</div><div class="sub">成功请求</div></div>
      <div class="card"><div class="label">错误率</div><div class="value ${errRate>10?'red':errRate>5?'warn':'green'}">${errRate}%</div><div class="sub">共 ${statsData.total_err} 次错误</div></div>
      <div class="card"><div class="label">活跃用户</div><div class="value green">${Object.keys(statsData.users).length}</div><div class="sub">累计接入</div></div>
      <div class="card"><div class="label">运行时长</div><div class="value">${upH}h ${upM}m</div><div class="sub">启动后持续运行</div></div>
      <div class="card"><div class="label">平均 RPM</div><div class="value blue">${statsData.avg_rpm.toFixed(1)}</div><div class="sub">每分钟平均请求数</div></div>
      <div class="card"><div class="label">平均 TPM</div><div class="value purple">${statsData.avg_tpm.toFixed(1)}</div><div class="sub">每分钟平均 Token 数</div></div>
    `;

    // RPM + TPM 双指标图表
    const maxRPM=Math.max(...statsData.rpm_chart.map(x=>x[1]),1);
    const maxTPM=Math.max(...statsData.tpm_chart.map(x=>x[1]),1);
    const allTimes=new Set([...statsData.rpm_chart.map(x=>x[0]),...statsData.tpm_chart.map(x=>x[0])]);
    const sortedTimes=[...allTimes].sort();
    const rpmMap=new Map(statsData.rpm_chart);
    const tpmMap=new Map(statsData.tpm_chart);
    let chartHTML='<div style="margin-bottom:16px"><div style="font-size:.75rem;color:var(--text-dim);margin-bottom:6px">▸ RPM（每分钟请求数）</div>';
    sortedTimes.forEach(t=>{
      const rv=rpmMap.get(t)||0;
      chartHTML+=`<div class="bar-wrap" title="${t} · ${rv} 次请求" style="cursor:default"><div class="bar-label">${t}</div><div class="bar-bg"><div class="bar-fill" style="width:${(rv/maxRPM*100).toFixed(1)}%;background:linear-gradient(90deg,#60a5fa,#3b82f6)"></div></div><div class="bar-val">${rv}</div></div>`;
    });
    chartHTML+='</div><div><div style="font-size:.75rem;color:var(--text-dim);margin-bottom:6px">▸ TPM（每分钟Token数）</div>';
    sortedTimes.forEach(t=>{
      const tv=tpmMap.get(t)||0;
      chartHTML+=`<div class="bar-wrap" title="${t} · ${tv} Tokens" style="cursor:default"><div class="bar-label">${t}</div><div class="bar-bg"><div class="bar-fill" style="width:${(tv/maxTPM*100).toFixed(1)}%"></div></div><div class="bar-val">${tv}</div></div>`;
    });
    chartHTML+='</div>';
    document.getElementById('rpm-chart').innerHTML=chartHTML;

    // Token 消耗分布饼图
    const inT=statsData.total_in_tok||0, outT=statsData.total_out_tok||0, totalT=inT+outT;
    if(totalT>0){
      const inPct=(inT/totalT*100).toFixed(1), outPct=(outT/totalT*100).toFixed(1);
      const size=160, cx=size/2, cy=size/2, r=60;
      const circum=2*Math.PI*r;
      const inLen=(inT/totalT*circum).toFixed(2);
      const outLen=(outT/totalT*circum).toFixed(2);
      document.getElementById('token-pie-chart').innerHTML=`
        <div style="display:flex;align-items:center;gap:32px;flex-wrap:wrap">
          <div style="position:relative;width:${size}px;height:${size}px;flex-shrink:0">
            <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)">
              <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#2d3748" stroke-width="32"/>
              <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#6366f1" stroke-width="32" stroke-dasharray="${inLen} ${circum}" stroke-dashoffset="0"/>
              <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#a78bfa" stroke-width="32" stroke-dasharray="${outLen} ${circum}" stroke-dashoffset="-${inLen}"/>
            </svg>
            <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center">
              <div style="font-size:1.1rem;font-weight:700">${totalT>1000000?(totalT/1000000).toFixed(1)+'M':totalT>1000?(totalT/1000).toFixed(1)+'K':totalT}</div>
              <div style="font-size:.7rem;color:var(--text-dim)">总 Tokens</div>
            </div>
          </div>
          <div style="display:flex;flex-direction:column;gap:12px">
            <div style="display:flex;align-items:center;gap:8px"><div style="width:12px;height:12px;border-radius:3px;background:#6366f1"></div><span style="font-size:.85rem;color:var(--text-mid)">输入 Token <strong style="color:var(--text)">${inT.toLocaleString()}</strong> (${inPct}%)</span></div>
            <div style="display:flex;align-items:center;gap:8px"><div style="width:12px;height:12px;border-radius:3px;background:#a78bfa"></div><span style="font-size:.85rem;color:var(--text-mid)">输出 Token <strong style="color:var(--text)">${outT.toLocaleString()}</strong> (${outPct}%)</span></div>
          </div>
        </div>`;
    }

    // 用户活跃度排行
    const sortedUsers=Object.entries(statsData.users).sort((a,b)=>b[1].reqs-a[1].reqs).slice(0,10);
    if(sortedUsers.length>0){
      const maxReqs=Math.max(...sortedUsers.map(x=>x[1].reqs),1);
      document.getElementById('user-rank-chart').innerHTML=sortedUsers.map(([uid,u])=>`
        <div class="bar-wrap" title="${esc(uid)} · ${u.reqs} 次请求" style="cursor:default">
          <div class="bar-label" style="width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left" title="${esc(uid)}">${esc(uid)}</div>
          <div class="bar-bg"><div class="bar-fill" style="width:${(u.reqs/maxReqs*100).toFixed(1)}%;background:linear-gradient(90deg,#34d399,#10b981)"></div></div>
          <div class="bar-val">${u.reqs}次</div>
        </div>`).join('');
    } else {
      document.getElementById('user-rank-chart').innerHTML='<div style="color:var(--text-dim);font-size:.85rem;padding:16px 0">暂无用户数据</div>';
    }

    // 用户表
    document.getElementById('user-table').innerHTML=Object.entries(statsData.users).sort((a,b)=>b[1].reqs-a[1].reqs).map(([uid,u])=>`
      <tr>
        <td>${esc(uid)}</td><td>${u.reqs}</td>
        <td class="ok">${u.ok}</td><td class="err">${u.err}</td>
        <td>${u.in_tok.toLocaleString()}</td><td>${u.out_tok.toLocaleString()}</td>
        <td>${esc(u.last_seen)}</td>
      </tr>`).join('');

    // 日志表
    document.getElementById('log-table').innerHTML=statsData.recent_log.slice(0,50).map(l=>`
      <tr>
        <td>${esc(l.time)}</td><td>${esc(l.user)}</td>
        <td><span class="tag ${l.ok?'ok':'err'}">${l.ok?'OK':'ERR'}</span></td>
        <td>${l.in_tok}</td><td>${l.out_tok}</td>
        <td>${l.latency}</td>
        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;color:#f87171">${esc(l.error||'')}</td>
      </tr>`).join('');
  }catch(e){
    console.error(e);
    showError(e.message || '未知错误');
  }finally{
    refreshInProgress = false;
    if(refreshBtn){
      refreshBtn.disabled = false;
      refreshBtn.style.opacity = '1';
    }
  }
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