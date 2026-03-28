"""
Responses API -> Chat Completions API 协议转换代理（完整工具调用支持）
支持：流式SSE、tool_call转换、developer角色映射
用法：python proxy.py
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import httpx, uvicorn, json, time, uuid

# ===================== 配置区 =====================
BACKEND_URL   = "http://ds.scc.com.cn/v1/chat/completions"
BACKEND_KEY   = "0"
LISTEN_HOST   = "0.0.0.0"
LISTEN_PORT   = 4000
DEFAULT_MODEL = "ds-v3"
TIMEOUT       = 120
# =================================================

app = FastAPI(title="Responses->Chat Proxy")
ROLE_MAP = {"developer": "system"}


# ──────────────── 消息提取 ────────────────

def extract_messages(body: dict) -> list:
    messages = []
    if body.get("instructions"):
        messages.append({"role": "system", "content": body["instructions"]})

    raw_input = body.get("input", "")
    if isinstance(raw_input, str):
        messages.append({"role": "user", "content": raw_input})
        return messages

    if isinstance(raw_input, list):
        for item in raw_input:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
                continue
            if not isinstance(item, dict):
                continue

            role = ROLE_MAP.get(item.get("role", "user"), item.get("role", "user"))
            content = item.get("content", "")

            # tool_result → 转为 tool role
            if item.get("type") == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id", "call_0"),
                    "content": str(item.get("output", ""))
                })
                continue

            if isinstance(content, str):
                messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                parts = []
                for p in content:
                    if not isinstance(p, dict):
                        continue
                    t = p.get("type", "")
                    if t in ("input_text", "text", "output_text"):
                        parts.append(p.get("text", ""))
                messages.append({"role": role, "content": " ".join(parts)})

    return messages


# ──────────────── Tools 转换：Responses API → OpenAI functions ────────────────

def convert_tools(resp_tools: list) -> list:
    """把 Responses API tools 格式转成 Chat Completions functions 格式"""
    functions = []
    for t in resp_tools:
        if t.get("type") == "function":
            functions.append({
                "type": "function",
                "function": {
                    "name":        t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters":  t.get("parameters", {"type": "object", "properties": {}}),
                }
            })
        # Codex 内置工具（shell / computer 等）直接透传
        else:
            functions.append({
                "type": "function",
                "function": {
                    "name":        t.get("name", t.get("type", "tool")),
                    "description": t.get("description", ""),
                    "parameters":  t.get("parameters", {"type": "object", "properties": {}}),
                }
            })
    return functions


# ──────────────── SSE 工具 ────────────────

def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ──────────────── 流式生成器 ────────────────

async def stream_response(body: dict):
    model      = body.get("model", DEFAULT_MODEL)
    messages   = extract_messages(body)
    resp_id    = f"resp-{uuid.uuid4().hex[:12]}"
    msg_id     = f"msg-{uuid.uuid4().hex[:12]}"
    created_at = int(time.time())

    chat_body = {
        "model":       model,
        "messages":    messages,
        "temperature": body.get("temperature", 1.0),
        "top_p":       body.get("top_p", 1.0),
        "stream":      True,
        "stream_options": {"include_usage": True},
    }
    if body.get("max_output_tokens"):
        chat_body["max_tokens"] = body["max_output_tokens"]

    # 透传 tools
    resp_tools = body.get("tools", [])
    if resp_tools:
        chat_body["tools"]       = convert_tools(resp_tools)
        chat_body["tool_choice"] = "auto"

    headers = {"Authorization": f"Bearer {BACKEND_KEY}", "Content-Type": "application/json"}

    # ── 事件序列 ──
    yield sse("response.created", {
        "type": "response.created",
        "response": {
            "id": resp_id, "object": "response", "created_at": created_at,
            "status": "in_progress", "model": model, "output": [],
            "usage": None, "error": None, "incomplete_details": None,
            "instructions": None, "metadata": {}, "tools": resp_tools,
            "tool_choice": "auto", "parallel_tool_calls": True,
            "store": False,
            "temperature": chat_body["temperature"], "top_p": chat_body["top_p"],
        }
    })
    yield sse("response.in_progress", {
        "type": "response.in_progress",
        "response": {"id": resp_id, "object": "response", "status": "in_progress"}
    })

    full_text       = ""
    input_tokens    = 0
    output_tokens   = 0
    # tool call 聚合
    tc_map: dict    = {}   # index -> {id, name, arguments_buf}
    finish_reason   = "stop"

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

                    # ── 文本 delta ──
                    text_piece = delta.get("content", "")
                    if text_piece:
                        if not full_text:
                            # 第一个文本 delta，先发 item added + part added
                            yield sse("response.output_item.added", {
                                "type": "response.output_item.added",
                                "output_index": 0,
                                "item": {"id": msg_id, "object": "realtime.item",
                                         "type": "message", "role": "assistant",
                                         "status": "in_progress", "content": []}
                            })
                            yield sse("response.content_part.added", {
                                "type": "response.content_part.added",
                                "item_id": msg_id, "output_index": 0, "content_index": 0,
                                "part": {"type": "output_text", "text": "", "annotations": []}
                            })
                        full_text += text_piece
                        yield sse("response.output_text.delta", {
                            "type": "response.output_text.delta",
                            "item_id": msg_id, "output_index": 0, "content_index": 0,
                            "delta": text_piece
                        })

                    # ── tool_calls delta ──
                    for tc in delta.get("tool_calls", []):
                        idx = tc.get("index", 0)
                        if idx not in tc_map:
                            tc_id   = tc.get("id", f"call_{uuid.uuid4().hex[:8]}")
                            tc_name = tc.get("function", {}).get("name", "")
                            tc_map[idx] = {"id": tc_id, "name": tc_name, "arguments_buf": ""}
                            # 通知 Codex 有新 function call
                            fc_item_id = f"fc-{uuid.uuid4().hex[:8]}"
                            tc_map[idx]["item_id"] = fc_item_id
                            yield sse("response.output_item.added", {
                                "type": "response.output_item.added",
                                "output_index": idx,
                                "item": {
                                    "id": fc_item_id, "type": "function_call",
                                    "call_id": tc_id,
                                    "name": tc_name, "arguments": "",
                                    "status": "in_progress"
                                }
                            })
                        tc_map[idx]["arguments_buf"] += tc.get("function", {}).get("arguments", "")

                    usage = chunk.get("usage", {})
                    if usage:
                        input_tokens  = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)

    except Exception as e:
        yield sse("error", {"type": "error", "message": str(e)})
        return

    # ── 收尾：文本消息 ──
    output_items = []
    if full_text:
        yield sse("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": msg_id, "output_index": 0, "content_index": 0,
            "text": full_text
        })
        yield sse("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": msg_id, "output_index": 0, "content_index": 0,
            "part": {"type": "output_text", "text": full_text, "annotations": []}
        })
        yield sse("response.output_item.done", {
            "type": "response.output_item.done", "output_index": 0,
            "item": {
                "id": msg_id, "object": "realtime.item", "type": "message",
                "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": full_text, "annotations": []}]
            }
        })
        output_items.append({
            "id": msg_id, "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": full_text, "annotations": []}]
        })

    # ── 收尾：tool calls ──
    for idx, tc in tc_map.items():
        yield sse("response.output_item.done", {
            "type": "response.output_item.done", "output_index": idx,
            "item": {
                "id": tc["item_id"], "type": "function_call",
                "call_id": tc["id"], "name": tc["name"],
                "arguments": tc["arguments_buf"], "status": "completed"
            }
        })
        output_items.append({
            "id": tc["item_id"], "type": "function_call",
            "call_id": tc["id"], "name": tc["name"],
            "arguments": tc["arguments_buf"], "status": "completed"
        })

    # 9. response.completed
    yield sse("response.completed", {
        "type": "response.completed",
        "response": {
            "id": resp_id, "object": "response", "created_at": created_at,
            "status": "completed", "model": model,
            "output": output_items,
            "usage": {
                "input_tokens":  input_tokens,
                "output_tokens": output_tokens,
                "total_tokens":  input_tokens + output_tokens,
            },
            "error": None, "incomplete_details": None, "instructions": None,
            "metadata": {}, "tools": resp_tools, "tool_choice": "auto",
            "parallel_tool_calls": True, "store": False,
            "temperature": chat_body["temperature"], "top_p": chat_body["top_p"],
        }
    })


# ──────────────── 路由 ────────────────

@app.post("/v1/responses")
async def responses_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    messages = extract_messages(body)
    if not messages:
        return JSONResponse({"error": "No valid input messages"}, status_code=400)

    return StreamingResponse(
        stream_response(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/v1/models")
async def list_models():
    return JSONResponse({
        "object": "list",
        "data": [{"id": DEFAULT_MODEL, "object": "model",
                  "created": int(time.time()), "owned_by": "local"}]
    })


@app.get("/health")
async def health():
    return {"status": "ok", "backend": BACKEND_URL}


if __name__ == "__main__":
    print(f"启动代理: http://{LISTEN_HOST}:{LISTEN_PORT}")
    print(f"后端地址: {BACKEND_URL}")
    uvicorn.run(app, host=LISTEN_HOST, port=LISTEN_PORT)