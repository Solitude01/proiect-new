"""
Claude Code -> Chat Completions API 协议转换代理（完整版）
- 支持全部 Claude Code 内置工具双向转换
- 自动裁剪 max_tokens 防止超出上下文窗口
- 完整 SSE 流式事件序列
端口：4001
用法：
  python claude_code_proxy.py
  set ANTHROPIC_BASE_URL=http://localhost:4001
  set ANTHROPIC_AUTH_TOKEN=any-value
  claude
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import httpx, uvicorn, json, time, uuid

# ===================== 配置区 =====================
BACKEND_URL        = "http://ds.scc.com.cn/v1/chat/completions"
BACKEND_KEY        = "0"
LISTEN_HOST        = "0.0.0.0"
LISTEN_PORT        = 4001
DEFAULT_MODEL      = "ds-v3"
TIMEOUT            = 180
# 模型上下文窗口大小（token），用于动态计算 max_tokens 上限
MODEL_CONTEXT_SIZE = 32768000   # 保守值，避免超出后端限制
# 固定 max_tokens 上限（None = 动态计算）
MAX_TOKENS_CAP     = 4096
# =================================================

app = FastAPI(title="ClaudeCode->ChatCompletions Proxy")


# ─────────────────────── 工具定义注入 ───────────────────────
# Claude Code 发送的是 Anthropic 格式的工具，本地模型可能不支持工具调用
# 这里定义 fallback：当后端不支持工具调用时，用 system prompt 描述工具能力
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
        # 注入工具描述到 system prompt
        result.append({"role": "system", "content": system + "\n\n" + TOOLS_SYSTEM_ADDON})

    for msg in messages:
        role    = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        if isinstance(content, list):
            text_parts   = []
            tool_calls   = []
            tool_results = []

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")

                if btype == "text":
                    text_parts.append(block.get("text", ""))

                elif btype == "tool_use":
                    tool_calls.append({
                        "id":   block.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name":      block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                        }
                    })

                elif btype == "tool_result":
                    inner = block.get("content", "")
                    if isinstance(inner, list):
                        inner = "\n".join(
                            c.get("text", "") for c in inner
                            if isinstance(c, dict) and c.get("type") == "text"
                        )
                    tool_results.append({
                        "role":         "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content":      str(inner),
                    })

            if tool_calls:
                result.append({
                    "role":       "assistant",
                    "content":    " ".join(text_parts) or None,
                    "tool_calls": tool_calls,
                })
            elif text_parts:
                result.append({"role": role, "content": " ".join(text_parts)})

            for tr in tool_results:
                result.append(tr)

    return result


def convert_tools_to_openai(anthropic_tools: list) -> list:
    """Anthropic tools -> OpenAI functions"""
    result = []
    for t in anthropic_tools:
        result.append({
            "type": "function",
            "function": {
                "name":        t.get("name", ""),
                "description": t.get("description", ""),
                "parameters":  t.get("input_schema", {"type": "object", "properties": {}}),
            }
        })
    return result


def parse_system(body: dict) -> str | None:
    """兼容 string 和 list 两种 system 格式"""
    sys = body.get("system")
    if isinstance(sys, str):
        return sys
    if isinstance(sys, list):
        parts = [b.get("text", "") for b in sys if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(parts)
    return None


def safe_max_tokens(body: dict, input_token_estimate: int = 4000) -> int:
    """动态计算安全的 max_tokens，防止超出上下文窗口"""
    requested = body.get("max_tokens", MAX_TOKENS_CAP)
    available = MODEL_CONTEXT_SIZE - input_token_estimate - 256  # 留 256 余量
    return min(requested, MAX_TOKENS_CAP, max(available, 256))


# ─────────────────────── SSE ───────────────────────

def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ─────────────────────── 流式生成器 ───────────────────────

async def stream_anthropic(body: dict):
    model    = body.get("model", DEFAULT_MODEL)
    system   = parse_system(body)
    messages = anthropic_to_openai_messages(body.get("messages", []), system)
    msg_id   = f"msg_{uuid.uuid4().hex[:24]}"

    # 估算输入 token（粗略：4 字符 ≈ 1 token）
    input_text_len = sum(len(str(m.get("content", ""))) for m in messages)
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
        oai_tools = convert_tools_to_openai(anth_tools)
        if oai_tools:
            chat_body["tools"]       = oai_tools
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

    full_text        = ""
    text_started     = False
    text_block_index = 0
    next_block_index = 0
    input_tokens     = input_tokens_est
    output_tokens    = 0
    finish_reason    = "end_turn"
    tc_map: dict     = {}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream("POST", BACKEND_URL, json=chat_body, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except Exception:
                        continue

                    choice = chunk.get("choices", [{}])[0]
                    delta  = choice.get("delta", {})
                    finish_reason = choice.get("finish_reason") or finish_reason

                    # 文本 delta
                    text_piece = delta.get("content", "")
                    if text_piece:
                        if not text_started:
                            text_block_index = next_block_index
                            next_block_index += 1
                            yield sse("content_block_start", {
                                "type": "content_block_start", "index": text_block_index,
                                "content_block": {"type": "text", "text": ""}
                            })
                            text_started = True
                        full_text += text_piece
                        yield sse("content_block_delta", {
                            "type": "content_block_delta", "index": text_block_index,
                            "delta": {"type": "text_delta", "text": text_piece}
                        })

                    # tool_calls delta
                    for tc in delta.get("tool_calls", []):
                        idx = tc.get("index", 0)
                        if idx not in tc_map:
                            tc_id          = tc.get("id", f"toolu_{uuid.uuid4().hex[:20]}")
                            tc_name        = tc.get("function", {}).get("name", "")
                            tc_block_index = next_block_index
                            next_block_index += 1
                            tc_map[idx] = {
                                "id":            tc_id,
                                "name":          tc_name,
                                "arguments_buf": "",
                                "block_index":   tc_block_index,
                            }
                            yield sse("content_block_start", {
                                "type": "content_block_start", "index": tc_block_index,
                                "content_block": {
                                    "type":  "tool_use",
                                    "id":    tc_id,
                                    "name":  tc_name,
                                    "input": {}
                                }
                            })
                        args_piece = tc.get("function", {}).get("arguments", "")
                        if args_piece:
                            tc_map[idx]["arguments_buf"] += args_piece
                            yield sse("content_block_delta", {
                                "type": "content_block_delta",
                                "index": tc_map[idx]["block_index"],
                                "delta": {"type": "input_json_delta", "partial_json": args_piece}
                            })

                    usage = chunk.get("usage", {})
                    if usage:
                        input_tokens  = usage.get("prompt_tokens", input_tokens_est)
                        output_tokens = usage.get("completion_tokens", 0)

    except httpx.HTTPStatusError as e:
        err_text = e.response.text[:200]
        yield sse("error", {"type": "error",
                             "error": {"type": "api_error", "message": f"Backend {e.response.status_code}: {err_text}"}})
        return
    except Exception as e:
        yield sse("error", {"type": "error",
                             "error": {"type": "api_error", "message": str(e)}})
        return

    # 关闭所有 content_block
    if text_started:
        yield sse("content_block_stop", {"type": "content_block_stop", "index": text_block_index})
    for tc in tc_map.values():
        yield sse("content_block_stop", {"type": "content_block_stop", "index": tc["block_index"]})

    stop_reason = {"tool_calls": "tool_use", "length": "max_tokens"}.get(finish_reason, "end_turn")

    yield sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": output_tokens}
    })
    yield sse("message_stop", {"type": "message_stop"})


# ─────────────────────── 路由 ───────────────────────

@app.post("/v1/messages")
async def messages_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    if body.get("stream", False):
        return StreamingResponse(
            stream_anthropic(body),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── 非流式 ──
    model    = body.get("model", DEFAULT_MODEL)
    system   = parse_system(body)
    messages = anthropic_to_openai_messages(body.get("messages", []), system)
    input_text_len = sum(len(str(m.get("content", ""))) for m in messages)

    chat_body: dict = {
        "model":      model,
        "messages":   messages,
        "stream":     False,
        "max_tokens": safe_max_tokens(body, input_text_len // 4),
    }
    anth_tools = body.get("tools", [])
    if anth_tools:
        oai_tools = convert_tools_to_openai(anth_tools)
        if oai_tools:
            chat_body["tools"]       = oai_tools
            chat_body["tool_choice"] = "auto"

    headers = {"Authorization": f"Bearer {BACKEND_KEY}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(BACKEND_URL, json=chat_body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return JSONResponse({"error": e.response.text}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)

    choice  = data["choices"][0]
    message = choice["message"]
    usage   = data.get("usage", {})
    blocks  = []

    if message.get("content"):
        blocks.append({"type": "text", "text": message["content"]})
    for tc in message.get("tool_calls", []):
        try:
            inp = json.loads(tc["function"]["arguments"])
        except Exception:
            inp = {}
        blocks.append({
            "type":  "tool_use",
            "id":    tc.get("id", f"toolu_{uuid.uuid4().hex[:20]}"),
            "name":  tc["function"]["name"],
            "input": inp,
        })

    fr = choice.get("finish_reason", "stop")
    stop_reason = {"tool_calls": "tool_use", "length": "max_tokens"}.get(fr, "end_turn")

    return JSONResponse({
        "id":            data.get("id", f"msg_{uuid.uuid4().hex[:24]}"),
        "type":          "message",
        "role":          "assistant",
        "model":         data.get("model", model),
        "content":       blocks,
        "stop_reason":   stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens":  usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    })


@app.post("/v1/messages/count_tokens")
async def count_tokens(request: Request):
    try:
        body  = await request.json()
        msgs  = body.get("messages", [])
        total = sum(len(str(m.get("content", ""))) for m in msgs) // 4
    except Exception:
        total = 1024
    return JSONResponse({"input_tokens": total})


@app.get("/v1/models")
async def list_models():
    return JSONResponse({
        "object": "list",
        "data": [{"id": DEFAULT_MODEL, "object": "model",
                  "created": int(time.time()), "owned_by": "local"}]
    })


@app.get("/health")
async def health():
    return {"status": "ok", "backend": BACKEND_URL, "port": LISTEN_PORT}


if __name__ == "__main__":
    print(f"\n{'='*52}")
    print(f"  Claude Code 本地模型代理  v3")
    print(f"  监听地址 : http://{LISTEN_HOST}:{LISTEN_PORT}")
    print(f"  后端模型 : {BACKEND_URL}")
    print(f"  上下文窗口: {MODEL_CONTEXT_SIZE} tokens")
    print(f"  max_tokens 上限: {MAX_TOKENS_CAP}")
    print(f"{'='*52}")
    print(f"\n  启动 Claude Code 前设置环境变量：")
    print(f"  set ANTHROPIC_BASE_URL=http://localhost:{LISTEN_PORT}")
    print(f"  set ANTHROPIC_AUTH_TOKEN=any-value")
    print(f"  claude\n")
    uvicorn.run(app, host=LISTEN_HOST, port=LISTEN_PORT)