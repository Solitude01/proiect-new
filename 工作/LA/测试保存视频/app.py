#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask Web GUI — 海康 NVR 事件视频下载管理器
替代 n8n 工作流的独立 Web 应用。
"""

import argparse
import importlib.util
import json
import os
import queue
import re
import sqlite3
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from flask import Flask, Response, jsonify, request

# ---------------------------------------------------------------------------
# Import helpers from download_event.py (same directory, never modify it)
# ---------------------------------------------------------------------------
# PyInstaller 打包后: download_event.py 在 _MEIPASS 临时目录
# 用户数据文件 (Deepmind.json, config.json, db) 在 exe 同级目录
if getattr(sys, 'frozen', False):
    _BUNDLE_DIR = sys._MEIPASS
    _DATA_DIR = os.path.dirname(sys.executable)
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    _DATA_DIR = _BUNDLE_DIR

_spec = importlib.util.spec_from_file_location(
    "download_event", os.path.join(_BUNDLE_DIR, "download_event.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

to_hik_time = _mod.to_hik_time
load_deepmind_map = _mod.load_deepmind_map
build_download_url = _mod.build_download_url
build_download_by_name = _mod.build_download_by_name
search_recording = _mod.search_recording
download_hik_mp4 = _mod.download_hik_mp4
safe_mkdir = _mod.safe_mkdir

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DEEPMIND_JSON = os.path.join(_DATA_DIR, "Deepmind.json")
CONFIG_FILE = os.path.join(_DATA_DIR, "config.json")
DB_FILE = os.path.join(_DATA_DIR, "downloads.db")

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------
def _default_base_dir():
    if sys.platform == "win32":
        return os.path.join(os.environ.get("USERPROFILE", "C:\\"), "Downloads", "NVR")
    return "/vol1/1000/aa/LA"


DEFAULT_CONFIG = {
    "base_dir": _default_base_dir(),
    "pre_seconds": 5,
    "post_seconds": 5,
    "tail_seconds": 120,
    "tracks_suffix": "01",
    "download_timeout": 180,
    "max_workers": 4,
    "download_delay": 20,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# SQLite download history
# ---------------------------------------------------------------------------
def _get_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS download_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id    TEXT,
            deepmind    TEXT,
            channel     TEXT,
            begin_time  TEXT,
            end_time    TEXT,
            task_result TEXT DEFAULT '',
            status      TEXT DEFAULT 'pending',
            file_path   TEXT DEFAULT '',
            error_msg   TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now','localtime')),
            finished_at TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def db_insert(event_id, deepmind, channel, begin_time, end_time, task_result=""):
    conn = _get_db()
    cur = conn.execute(
        "INSERT INTO download_history (event_id, deepmind, channel, begin_time, end_time, task_result, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'downloading')",
        (event_id, deepmind, channel, begin_time, end_time, task_result),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def db_update_success(row_id, file_path):
    conn = _get_db()
    conn.execute(
        "UPDATE download_history SET status='success', file_path=?, finished_at=datetime('now','localtime') WHERE id=?",
        (file_path, row_id),
    )
    conn.commit()
    conn.close()


def db_update_error(row_id, error_msg):
    conn = _get_db()
    conn.execute(
        "UPDATE download_history SET status='error', error_msg=?, finished_at=datetime('now','localtime') WHERE id=?",
        (error_msg, row_id),
    )
    conn.commit()
    conn.close()


def db_get_history(page=1, per_page=20):
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) FROM download_history").fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM download_history ORDER BY id DESC LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def db_get_stats():
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) FROM download_history").fetchone()[0]
    success = conn.execute("SELECT COUNT(*) FROM download_history WHERE status='success'").fetchone()[0]
    error = conn.execute("SELECT COUNT(*) FROM download_history WHERE status='error'").fetchone()[0]
    downloading = conn.execute("SELECT COUNT(*) FROM download_history WHERE status='downloading'").fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = conn.execute(
        "SELECT COUNT(*) FROM download_history WHERE created_at LIKE ?", (today + "%",)
    ).fetchone()[0]
    conn.close()
    return {
        "total": total,
        "success": success,
        "error": error,
        "downloading": downloading,
        "today": today_count,
    }


# ---------------------------------------------------------------------------
# SSE Log Broadcaster
# ---------------------------------------------------------------------------
class LogBroadcaster:
    def __init__(self, max_history=500):
        self._lock = threading.Lock()
        self._subscribers = []
        self._history = []
        self._max = max_history

    def publish(self, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {"ts": ts, "msg": msg}
        with self._lock:
            self._history.append(entry)
            if len(self._history) > self._max:
                self._history = self._history[-self._max:]
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(entry)
                except Exception:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)

    def subscribe(self):
        q = queue.Queue(maxsize=256)
        with self._lock:
            for h in self._history:
                try:
                    q.put_nowait(h)
                except queue.Full:
                    break
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)


log_broadcaster = LogBroadcaster()


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    log_broadcaster.publish(msg)


# ---------------------------------------------------------------------------
# Time processing (ported from n8n Code node)
# ---------------------------------------------------------------------------
def process_event_times(begin_time_str, end_time_str, task_result, event_id, cfg):
    pre_seconds = cfg.get("pre_seconds", 5)
    post_seconds = cfg.get("post_seconds", 2)
    tail_seconds = cfg.get("tail_seconds", 120)

    fmt = "%Y-%m-%d %H:%M:%S"
    begin_dt = datetime.strptime(begin_time_str.split(".")[0], fmt)
    end_dt = datetime.strptime(end_time_str.split(".")[0], fmt)

    duration = (end_dt - begin_dt).total_seconds()

    if duration > tail_seconds:
        begin2 = end_dt - timedelta(seconds=tail_seconds)
    else:
        begin2 = begin_dt - timedelta(seconds=pre_seconds)

    end2 = end_dt + timedelta(seconds=post_seconds)

    sanitized = re.sub(r'[\\/:*?"<>|\s]+', "_", str(task_result).strip())
    event_id2 = f"{sanitized}_{event_id}" if sanitized else event_id

    begin2_str = begin2.strftime("%Y-%m-%d %H:%M:%S.000")
    end2_str = end2.strftime("%Y-%m-%d %H:%M:%S.000")

    return begin2_str, end2_str, event_id2


# ---------------------------------------------------------------------------
# Background download worker
# ---------------------------------------------------------------------------
executor = None


def init_executor(max_workers=4):
    global executor
    executor = ThreadPoolExecutor(max_workers=max_workers)


def do_download(row_id, event_id, begin_time, end_time, deepmind, channel, task_result, cfg):
    try:
        delay = cfg.get("download_delay", 20)
        if delay > 0:
            log(f"[下载] 事件={event_id} 等待 {delay}s 确保录像完整 ...")
            time.sleep(delay)

        begin2, end2, event_id2 = process_event_times(
            begin_time, end_time, task_result, event_id, cfg
        )
        log(f"[下载] 事件={event_id2} deepmind={deepmind} ch={channel} "
            f"开始={begin2} 结束={end2}")

        dm_map = load_deepmind_map(DEEPMIND_JSON)
        if deepmind not in dm_map:
            raise RuntimeError(f"Deepmind={deepmind} 在 Deepmind.json 中未找到")

        dev = dm_map[deepmind]
        base_dir = os.path.normpath(cfg.get("base_dir", DEFAULT_CONFIG["base_dir"]))
        tracks_suffix = cfg.get("tracks_suffix", "01")
        timeout = cfg.get("download_timeout", 180)

        event_dir = os.path.join(base_dir, event_id2)
        safe_mkdir(event_dir)

        b = to_hik_time(begin2)
        e = to_hik_time(end2)
        out_file = os.path.join(event_dir, f"ch{channel}_{b}_{e}.mp4")

        track_id = f"{channel}{tracks_suffix}"

        if dev.get("search_before_download", False):
            # 先搜索录像文件，获取 name/size，再用 POST+XML 下载
            log(f"[下载] 搜索录像 track={track_id} ...")
            rec = search_recording(
                nvr_ip=dev["ip"], scheme=dev["scheme"], http_port=dev["http_port"],
                username=dev["username"], password=dev["password"],
                track_id=track_id,
                start_time=begin2, end_time=end2,
                verify_tls=dev.get("verify_tls", False),
            )
            if not rec:
                raise RuntimeError(f"未搜索到录像 track={track_id} {begin2}~{end2}")
            log(f"[下载] 找到录像 name={rec.get('name','')} size={rec.get('size','')}")
            url, xml_body = build_download_by_name(
                nvr_ip=dev["ip"], scheme=dev["scheme"], http_port=dev["http_port"],
                search_playback_uri=rec["playbackURI"],
                begin_time=begin2, end_time=end2,
            )
        else:
            url, xml_body = build_download_url(
                nvr_ip=dev["ip"], scheme=dev["scheme"],
                http_port=dev["http_port"], rtsp_port=dev["rtsp_port"],
                channel=channel, begin_time=begin2, end_time=end2,
                tracks_suffix=tracks_suffix,
            )

        log(f"[下载] 正在下载 {out_file} ...")
        download_hik_mp4(
            url=url,
            username=dev["username"],
            password=dev["password"],
            out_file=out_file,
            timeout=timeout,
            verify_tls=dev.get("verify_tls", False),
            xml_body=xml_body,
        )

        db_update_success(row_id, out_file)
        log(f"[下载] 成功 事件={event_id2} -> {out_file}")

    except Exception as exc:
        err = str(exc)
        db_update_error(row_id, err)
        log(f"[下载] 失败 事件={event_id} -> {err}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Deepmind.json helpers
# ---------------------------------------------------------------------------
def _read_deepmind_list():
    if not os.path.isfile(DEEPMIND_JSON):
        return []
    with open(DEEPMIND_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_deepmind_list(data):
    with open(DEEPMIND_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.route("/")
def index():
    return Response(HTML_PAGE, content_type="text/html; charset=utf-8")


# --- Webhook (replaces n8n) ---
@app.route("/webhook/event", methods=["GET", "POST"])
def webhook_event():
    # 兼容 JSON / 表单 / URL 查询参数 三种方式
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = {}
        for src in (request.form, request.args):
            for k, v in src.items():
                if k not in data:
                    data[k] = v

    event_id = str(data.get("event_id", "")).strip()
    begin_time = str(data.get("beginTime", "")).strip()
    end_time = str(data.get("endTime", "")).strip()
    deepmind = str(data.get("Deepmind", "")).strip()
    channel = str(data.get("Channel", "")).strip()
    task_result = str(data.get("Task Result", data.get("Task_Result", ""))).strip()

    if not all([event_id, begin_time, end_time, deepmind, channel]):
        return jsonify({"ok": False, "error": "缺少必填字段",
                        "received": data}), 400

    cfg = load_config()
    row_id = db_insert(event_id, deepmind, channel, begin_time, end_time, task_result)
    log(f"[Webhook] 收到事件 event={event_id} deepmind={deepmind} ch={channel}")

    executor.submit(do_download, row_id, event_id, begin_time, end_time, deepmind, channel, task_result, cfg)
    return jsonify({"ok": True, "id": row_id, "event_id": event_id})


# --- SSE log stream ---
@app.route("/api/logs/stream")
def logs_stream():
    q = log_broadcaster.subscribe()

    def gen():
        try:
            while True:
                try:
                    entry = q.get(timeout=30)
                    yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            log_broadcaster.unsubscribe(q)

    return Response(gen(), content_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- Download history ---
@app.route("/api/downloads")
def api_downloads():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    rows, total = db_get_history(page, per_page)
    return jsonify({"rows": rows, "total": total, "page": page, "per_page": per_page})


# --- Stats ---
@app.route("/api/stats")
def api_stats():
    return jsonify(db_get_stats())


# --- Devices CRUD ---
@app.route("/api/devices", methods=["GET"])
def devices_list():
    return jsonify(_read_deepmind_list())


@app.route("/api/devices", methods=["POST"])
def devices_create():
    data = request.get_json(force=True) or {}
    devices = _read_deepmind_list()
    dm = str(data.get("Deepmind", "")).strip()
    if not dm:
        return jsonify({"error": "Deepmind 为必填项"}), 400
    for d in devices:
        if str(d.get("Deepmind")) == dm:
            return jsonify({"error": f"Deepmind {dm} 已存在"}), 409
    new_dev = {
        "Deepmind": dm,
        "IP": str(data.get("IP", "")).strip(),
        "Password": str(data.get("Password", "")).strip(),
        "HttpPort": int(data.get("HttpPort", 80)),
        "RtspPort": int(data.get("RtspPort", 554)),
        "Scheme": str(data.get("Scheme", "http")).strip().lower(),
        "SearchBeforeDownload": bool(data.get("SearchBeforeDownload", False)),
    }
    devices.append(new_dev)
    _write_deepmind_list(devices)
    log(f"[设备] 添加 Deepmind={dm} IP={new_dev['IP']}")
    return jsonify(new_dev), 201


@app.route("/api/devices/<dm_id>", methods=["PUT"])
def devices_update(dm_id):
    data = request.get_json(force=True) or {}
    devices = _read_deepmind_list()
    for i, d in enumerate(devices):
        if str(d.get("Deepmind")) == dm_id:
            devices[i] = {
                "Deepmind": dm_id,
                "IP": str(data.get("IP", d.get("IP", ""))).strip(),
                "Password": str(data.get("Password", d.get("Password", ""))).strip(),
                "HttpPort": int(data.get("HttpPort", d.get("HttpPort", 80))),
                "RtspPort": int(data.get("RtspPort", d.get("RtspPort", 554))),
                "Scheme": str(data.get("Scheme", d.get("Scheme", "http"))).strip().lower(),
                "SearchBeforeDownload": bool(data.get("SearchBeforeDownload", d.get("SearchBeforeDownload", False))),
            }
            _write_deepmind_list(devices)
            log(f"[设备] 更新 Deepmind={dm_id}")
            return jsonify(devices[i])
    return jsonify({"error": "Not found"}), 404


@app.route("/api/devices/<dm_id>", methods=["DELETE"])
def devices_delete(dm_id):
    devices = _read_deepmind_list()
    new_list = [d for d in devices if str(d.get("Deepmind")) != dm_id]
    if len(new_list) == len(devices):
        return jsonify({"error": "未找到"}), 404
    _write_deepmind_list(new_list)
    log(f"[设备] 删除 Deepmind={dm_id}")
    return jsonify({"ok": True})


# --- Config ---
@app.route("/api/config", methods=["GET"])
def api_config_get():
    return jsonify(load_config())


@app.route("/api/config", methods=["PUT"])
def api_config_put():
    data = request.get_json(force=True) or {}
    cfg = load_config()
    for k in DEFAULT_CONFIG:
        if k in data:
            cfg[k] = type(DEFAULT_CONFIG[k])(data[k])
    save_config(cfg)
    log(f"[配置] 已更新: {cfg}")
    return jsonify(cfg)


@app.route("/api/browse-folder", methods=["GET"])
def api_browse_folder():
    """弹出系统原生文件夹选择对话框。"""
    import threading as _thr
    result = [None]
    def _pick():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory(title="选择存储目录")
            root.destroy()
            result[0] = folder or ""
        except Exception:
            result[0] = ""
    # tkinter 必须在主线程或独立线程中运行，不能在 waitress 工作线程直接调
    t = _thr.Thread(target=_pick)
    t.start()
    t.join(timeout=120)
    return jsonify({"folder": result[0] or ""})


# --- Manual test download ---
@app.route("/api/test-download", methods=["POST"])
def api_test_download():
    data = request.get_json(force=True) or {}
    event_id = str(data.get("event_id", f"test_{uuid.uuid4().hex[:8]}")).strip()
    begin_time = str(data.get("beginTime", "")).strip()
    end_time = str(data.get("endTime", "")).strip()
    deepmind = str(data.get("Deepmind", "")).strip()
    channel = str(data.get("Channel", "")).strip()
    task_result = str(data.get("Task Result", "")).strip()

    if not all([begin_time, end_time, deepmind, channel]):
        return jsonify({"ok": False, "error": "缺少必填字段"}), 400

    cfg = load_config()
    row_id = db_insert(event_id, deepmind, channel, begin_time, end_time, task_result)
    log(f"[测试] 手动下载 事件={event_id} deepmind={deepmind} ch={channel}")

    executor.submit(do_download, row_id, event_id, begin_time, end_time, deepmind, channel, task_result, cfg)
    return jsonify({"ok": True, "id": row_id, "event_id": event_id})


# ---------------------------------------------------------------------------
# Embedded HTML frontend
# ---------------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NVR 下载管理器</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0f1117;--surface:#1a1d27;--surface2:#242836;--border:#2e3348;
  --text:#e0e0e0;--text2:#8b8fa3;--accent:#6c7cff;--accent2:#4c5ce0;
  --green:#34d399;--red:#f87171;--yellow:#fbbf24;--blue:#60a5fa;
}
body{font-family:'Segoe UI',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);line-height:1.5}
a{color:var(--accent);text-decoration:none}

/* Layout */
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;gap:16px}
.header h1{font-size:18px;font-weight:600;white-space:nowrap}
.tabs{display:flex;gap:4px;margin-left:32px}
.tab{padding:8px 20px;border-radius:6px;cursor:pointer;font-size:14px;color:var(--text2);transition:all .15s}
.tab:hover{color:var(--text);background:var(--surface2)}
.tab.active{color:#fff;background:var(--accent)}
.container{max-width:1280px;margin:0 auto;padding:20px 24px}
.page{display:none}.page.active{display:block}

/* Cards */
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px 20px}
.stat-card .label{font-size:12px;color:var(--text2);letter-spacing:.5px}
.stat-card .value{font-size:28px;font-weight:700;margin-top:4px}
.stat-card .value.green{color:var(--green)}.stat-card .value.red{color:var(--red)}
.stat-card .value.yellow{color:var(--yellow)}.stat-card .value.blue{color:var(--blue)}

/* Table */
.table-wrap{background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:20px}
table{width:100%;border-collapse:collapse}
th,td{padding:10px 14px;text-align:left;font-size:13px;border-bottom:1px solid var(--border)}
th{background:var(--surface2);color:var(--text2);font-weight:600;font-size:12px;letter-spacing:.5px;position:sticky;top:0}
tr:hover{background:var(--surface2)}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}
.badge.success{background:#065f4620;color:var(--green)}.badge.error{background:#7f1d1d20;color:var(--red)}
.badge.downloading{background:#78350f20;color:var(--yellow)}.badge.pending{background:#1e3a5f20;color:var(--blue)}
.pagination{display:flex;justify-content:center;gap:8px;margin-top:12px}
.pagination button{background:var(--surface2);color:var(--text);border:1px solid var(--border);padding:6px 14px;border-radius:4px;cursor:pointer;font-size:13px}
.pagination button:hover{background:var(--accent);color:#fff;border-color:var(--accent)}
.pagination button:disabled{opacity:.4;cursor:default;background:var(--surface2);color:var(--text);border-color:var(--border)}

/* Log panel */
.log-panel{background:#0a0c12;border:1px solid var(--border);border-radius:8px;padding:12px;height:300px;overflow-y:auto;font-family:'Cascadia Code','Fira Code',monospace;font-size:12px;line-height:1.7}
.log-entry{color:var(--text2)}.log-entry .ts{color:var(--accent);margin-right:8px}
.log-entry .msg{color:var(--text)}

/* Forms */
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.form-group{display:flex;flex-direction:column;gap:4px}
.form-group.full{grid-column:1/-1}
label{font-size:12px;color:var(--text2);font-weight:600;letter-spacing:.5px}
input,select{background:var(--surface2);color:var(--text);border:1px solid var(--border);padding:8px 12px;border-radius:6px;font-size:14px;outline:none}
input:focus,select:focus{border-color:var(--accent)}
.btn{display:inline-flex;align-items:center;justify-content:center;padding:8px 20px;border-radius:6px;border:none;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s}
.btn-primary{background:var(--accent);color:#fff}.btn-primary:hover{background:var(--accent2)}
.btn-danger{background:var(--red);color:#fff}.btn-danger:hover{background:#dc2626}
.btn-sm{padding:4px 12px;font-size:12px}
.btn-group{display:flex;gap:8px;margin-top:12px}

/* Section title */
.section-title{font-size:15px;font-weight:600;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px;margin-bottom:20px}

/* Modal */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;align-items:center;justify-content:center}
.modal-overlay.show{display:flex}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:24px;width:480px;max-width:90vw}
.modal h3{margin-bottom:16px;font-size:16px}

/* Scrollbar */
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:var(--surface)}::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
</head>
<body>

<div class="header">
  <h1>NVR 下载管理器</h1>
  <div class="tabs">
    <div class="tab active" onclick="switchTab('dashboard')">仪表盘</div>
    <div class="tab" onclick="switchTab('devices')">设备管理</div>
    <div class="tab" onclick="switchTab('settings')">系统设置</div>
  </div>
</div>

<div class="container">
  <!-- ========== 仪表盘 ========== -->
  <div id="page-dashboard" class="page active">
    <div class="stats-grid" id="stats-grid"></div>
    <div class="section-title">下载历史</div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>ID</th><th>事件 ID</th><th>Deepmind</th><th>通道</th>
          <th>开始时间</th><th>结束时间</th><th>状态</th><th>时间</th>
        </tr></thead>
        <tbody id="history-body"></tbody>
      </table>
    </div>
    <div class="pagination" id="pagination"></div>
    <div class="section-title" style="margin-top:20px">实时日志</div>
    <div class="log-panel" id="log-panel"></div>
  </div>

  <!-- ========== 设备管理 ========== -->
  <div id="page-devices" class="page">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div class="section-title" style="margin-bottom:0;border:none;padding:0">设备列表 (Deepmind.json)</div>
      <button class="btn btn-primary" onclick="showAddDevice()">+ 添加设备</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Deepmind</th><th>IP 地址</th><th>密码</th><th>HTTP 端口</th>
          <th>RTSP 端口</th><th>协议</th><th>搜索下载</th><th>操作</th>
        </tr></thead>
        <tbody id="devices-body"></tbody>
      </table>
    </div>
  </div>

  <!-- ========== 系统设置 ========== -->
  <div id="page-settings" class="page">
    <div class="panel">
      <div class="section-title">服务配置</div>
      <div class="form-grid" id="config-form">
        <div class="form-group">
          <label>存储根目录</label>
          <div style="display:flex;gap:6px">
            <input id="cfg-base_dir" type="text" style="flex:1" placeholder="Linux: /vol1/1000/aa/LA  Windows: D:\NVR\downloads">
            <button class="btn btn-primary btn-sm" onclick="browseFolder()" style="white-space:nowrap">选择文件夹</button>
          </div>
        </div>
        <div class="form-group">
          <label>前置秒数</label>
          <input id="cfg-pre_seconds" type="number">
        </div>
        <div class="form-group">
          <label>后置秒数</label>
          <input id="cfg-post_seconds" type="number">
        </div>
        <div class="form-group">
          <label>尾段秒数</label>
          <input id="cfg-tail_seconds" type="number">
        </div>
        <div class="form-group">
          <label>轨道后缀</label>
          <input id="cfg-tracks_suffix" type="text">
        </div>
        <div class="form-group">
          <label>下载超时 (秒)</label>
          <input id="cfg-download_timeout" type="number">
        </div>
        <div class="form-group">
          <label>最大并发数</label>
          <input id="cfg-max_workers" type="number">
        </div>
        <div class="form-group">
          <label>下载延迟 (秒)</label>
          <input id="cfg-download_delay" type="number" title="Webhook 到达后等待的秒数，确保 NVR 录像完整">
        </div>
      </div>
      <div class="btn-group">
        <button class="btn btn-primary" onclick="saveConfig()">保存配置</button>
      </div>
    </div>

    <div class="panel">
      <div class="section-title">手动测试下载</div>
      <div class="form-grid">
        <div class="form-group">
          <label>事件 ID（可选）</label>
          <input id="test-event_id" type="text" placeholder="留空则自动生成">
        </div>
        <div class="form-group">
          <label>Deepmind</label>
          <input id="test-deepmind" type="text" placeholder="例如 13">
        </div>
        <div class="form-group">
          <label>通道</label>
          <input id="test-channel" type="text" placeholder="例如 12">
        </div>
        <div class="form-group">
          <label>检测结果</label>
          <input id="test-task_result" type="text" placeholder="例如 NG">
        </div>
        <div class="form-group">
          <label>开始时间</label>
          <input id="test-beginTime" type="text" placeholder="2026-02-14 08:00:00.000">
        </div>
        <div class="form-group">
          <label>结束时间</label>
          <input id="test-endTime" type="text" placeholder="2026-02-14 08:02:00.000">
        </div>
      </div>
      <div class="btn-group">
        <button class="btn btn-primary" onclick="testDownload()">开始测试下载</button>
      </div>
    </div>

    <div class="panel">
      <div class="section-title">Webhook 地址</div>
      <div style="background:var(--surface2);padding:12px;border-radius:6px;font-family:monospace;font-size:13px;color:var(--accent);word-break:break-all" id="webhook-url"></div>
      <p style="margin-top:8px;font-size:12px;color:var(--text2)">POST JSON 字段: event_id, beginTime, endTime, Deepmind, Channel, Task Result</p>
    </div>
  </div>
</div>

<!-- 设备弹窗 -->
<div class="modal-overlay" id="device-modal">
  <div class="modal">
    <h3 id="modal-title">添加设备</h3>
    <div class="form-grid">
      <div class="form-group"><label>Deepmind</label><input id="dev-Deepmind" type="text"></div>
      <div class="form-group"><label>IP 地址</label><input id="dev-IP" type="text"></div>
      <div class="form-group"><label>密码</label><input id="dev-Password" type="text"></div>
      <div class="form-group"><label>HTTP 端口</label><input id="dev-HttpPort" type="number" value="80"></div>
      <div class="form-group"><label>RTSP 端口</label><input id="dev-RtspPort" type="number" value="554"></div>
      <div class="form-group"><label>协议</label>
        <select id="dev-Scheme"><option value="http">http</option><option value="https">https</option></select>
      </div>
      <div class="form-group"><label>搜索下载模式</label>
        <select id="dev-SearchBeforeDownload"><option value="false">否（直接按时间下载）</option><option value="true">是（先搜索再下载）</option></select>
      </div>
    </div>
    <div class="btn-group" style="justify-content:flex-end">
      <button class="btn" style="background:var(--surface2);color:var(--text)" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" id="modal-save-btn" onclick="saveDevice()">保存</button>
    </div>
  </div>
</div>

<script>
// ===== 状态 =====
let currentPage = 1, totalPages = 1, editingDm = null;

// ===== 文件夹浏览 =====
async function browseFolder() {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '选择中...';
  try {
    const r = await fetch('/api/browse-folder');
    const data = await r.json();
    if (data.folder) document.getElementById('cfg-base_dir').value = data.folder;
  } catch(e) { console.error(e); }
  btn.disabled = false;
  btn.textContent = '选择文件夹';
}

// ===== 标签页切换 =====
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelector(`.tab[onclick="switchTab('${name}')"]`).classList.add('active');
  document.getElementById('page-' + name).classList.add('active');
  if (name === 'dashboard') { loadStats(); loadHistory(); }
  if (name === 'devices') loadDevices();
  if (name === 'settings') loadConfig();
}

// ===== 仪表盘 =====
const STATUS_MAP = {success:'成功',error:'失败',downloading:'下载中',pending:'等待中'};
async function loadStats() {
  try {
    const r = await fetch('/api/stats');
    const d = await r.json();
    document.getElementById('stats-grid').innerHTML = `
      <div class="stat-card"><div class="label">总下载数</div><div class="value">${d.total}</div></div>
      <div class="stat-card"><div class="label">成功</div><div class="value green">${d.success}</div></div>
      <div class="stat-card"><div class="label">失败</div><div class="value red">${d.error}</div></div>
      <div class="stat-card"><div class="label">下载中</div><div class="value yellow">${d.downloading}</div></div>
      <div class="stat-card"><div class="label">今日</div><div class="value blue">${d.today}</div></div>`;
  } catch(e) { console.error(e); }
}

async function loadHistory(page) {
  page = page || currentPage;
  try {
    const r = await fetch(`/api/downloads?page=${page}&per_page=15`);
    const d = await r.json();
    currentPage = d.page;
    totalPages = Math.ceil(d.total / d.per_page) || 1;
    const tbody = document.getElementById('history-body');
    if (!d.rows.length) { tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text2)">暂无下载记录</td></tr>'; }
    else { tbody.innerHTML = d.rows.map(r => `<tr>
      <td>${r.id}</td><td title="${r.file_path||''}">${r.event_id}</td><td>${r.deepmind}</td><td>${r.channel}</td>
      <td>${r.begin_time}</td><td>${r.end_time}</td>
      <td><span class="badge ${r.status}">${STATUS_MAP[r.status]||r.status}</span></td>
      <td>${r.finished_at || r.created_at}</td>
    </tr>`).join(''); }
    renderPagination();
  } catch(e) { console.error(e); }
}

function renderPagination() {
  const el = document.getElementById('pagination');
  el.innerHTML = `
    <button ${currentPage<=1?'disabled':''} onclick="loadHistory(${currentPage-1})">上一页</button>
    <button disabled style="background:transparent;border:none;color:var(--text2)">${currentPage} / ${totalPages}</button>
    <button ${currentPage>=totalPages?'disabled':''} onclick="loadHistory(${currentPage+1})">下一页</button>`;
}

// ===== SSE 实时日志 =====
function initSSE() {
  const panel = document.getElementById('log-panel');
  const es = new EventSource('/api/logs/stream');
  es.onmessage = function(e) {
    try {
      const d = JSON.parse(e.data);
      const div = document.createElement('div');
      div.className = 'log-entry';
      div.innerHTML = `<span class="ts">${d.ts}</span><span class="msg">${escHtml(d.msg)}</span>`;
      panel.appendChild(div);
      if (panel.children.length > 500) panel.removeChild(panel.firstChild);
      panel.scrollTop = panel.scrollHeight;
    } catch(err) {}
  };
  es.onerror = function() { setTimeout(initSSE, 3000); es.close(); };
}
function escHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }

// ===== 设备管理 =====
async function loadDevices() {
  try {
    const r = await fetch('/api/devices');
    const d = await r.json();
    const tbody = document.getElementById('devices-body');
    if (!d.length) { tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text2)">暂无设备</td></tr>'; return; }
    tbody.innerHTML = d.map(dev => `<tr>
      <td>${dev.Deepmind}</td><td>${dev.IP}</td><td>${dev.Password ? '****' : ''}</td>
      <td>${dev.HttpPort||80}</td><td>${dev.RtspPort||554}</td><td>${dev.Scheme||'http'}</td>
      <td>${dev.SearchBeforeDownload ? '是' : '否'}</td>
      <td>
        <button class="btn btn-sm btn-primary" onclick="showEditDevice('${dev.Deepmind}')">编辑</button>
        <button class="btn btn-sm btn-danger" onclick="deleteDevice('${dev.Deepmind}')">删除</button>
      </td>
    </tr>`).join('');
  } catch(e) { console.error(e); }
}

function showAddDevice() {
  editingDm = null;
  document.getElementById('modal-title').textContent = '添加设备';
  document.getElementById('dev-Deepmind').value = '';
  document.getElementById('dev-Deepmind').disabled = false;
  document.getElementById('dev-IP').value = '';
  document.getElementById('dev-Password').value = '';
  document.getElementById('dev-HttpPort').value = '80';
  document.getElementById('dev-RtspPort').value = '554';
  document.getElementById('dev-Scheme').value = 'http';
  document.getElementById('dev-SearchBeforeDownload').value = 'false';
  document.getElementById('device-modal').classList.add('show');
}

async function showEditDevice(dm) {
  const r = await fetch('/api/devices');
  const devices = await r.json();
  const dev = devices.find(d => String(d.Deepmind) === dm);
  if (!dev) return;
  editingDm = dm;
  document.getElementById('modal-title').textContent = '编辑设备';
  document.getElementById('dev-Deepmind').value = dev.Deepmind;
  document.getElementById('dev-Deepmind').disabled = true;
  document.getElementById('dev-IP').value = dev.IP || '';
  document.getElementById('dev-Password').value = dev.Password || '';
  document.getElementById('dev-HttpPort').value = dev.HttpPort || 80;
  document.getElementById('dev-RtspPort').value = dev.RtspPort || 554;
  document.getElementById('dev-Scheme').value = dev.Scheme || 'http';
  document.getElementById('dev-SearchBeforeDownload').value = dev.SearchBeforeDownload ? 'true' : 'false';
  document.getElementById('device-modal').classList.add('show');
}

function closeModal() { document.getElementById('device-modal').classList.remove('show'); }

async function saveDevice() {
  const payload = {
    Deepmind: document.getElementById('dev-Deepmind').value.trim(),
    IP: document.getElementById('dev-IP').value.trim(),
    Password: document.getElementById('dev-Password').value.trim(),
    HttpPort: parseInt(document.getElementById('dev-HttpPort').value) || 80,
    RtspPort: parseInt(document.getElementById('dev-RtspPort').value) || 554,
    Scheme: document.getElementById('dev-Scheme').value,
    SearchBeforeDownload: document.getElementById('dev-SearchBeforeDownload').value === 'true',
  };
  try {
    let r;
    if (editingDm) {
      r = await fetch(`/api/devices/${editingDm}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    } else {
      r = await fetch('/api/devices', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    }
    if (r.ok) { closeModal(); loadDevices(); }
    else { const e = await r.json(); alert(e.error || '操作失败'); }
  } catch(e) { alert(e.message); }
}

async function deleteDevice(dm) {
  if (!confirm(`确定删除设备 Deepmind=${dm} 吗？`)) return;
  try {
    const r = await fetch(`/api/devices/${dm}`, { method:'DELETE' });
    if (r.ok) loadDevices();
  } catch(e) { alert(e.message); }
}

// ===== 系统设置 =====
async function loadConfig() {
  try {
    const r = await fetch('/api/config');
    const cfg = await r.json();
    ['base_dir','pre_seconds','post_seconds','tail_seconds','tracks_suffix','download_timeout','max_workers','download_delay'].forEach(k => {
      const el = document.getElementById('cfg-' + k);
      if (el) el.value = cfg[k] !== undefined ? cfg[k] : '';
    });
    document.getElementById('webhook-url').textContent = location.origin + '/webhook/event';
  } catch(e) { console.error(e); }
}

async function saveConfig() {
  const payload = {};
  ['base_dir','pre_seconds','post_seconds','tail_seconds','tracks_suffix','download_timeout','max_workers','download_delay'].forEach(k => {
    const el = document.getElementById('cfg-' + k);
    if (el) payload[k] = el.value;
  });
  try {
    const r = await fetch('/api/config', { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    if (r.ok) alert('配置已保存');
  } catch(e) { alert(e.message); }
}

// ===== 测试下载 =====
async function testDownload() {
  const payload = {
    event_id: document.getElementById('test-event_id').value.trim(),
    beginTime: document.getElementById('test-beginTime').value.trim(),
    endTime: document.getElementById('test-endTime').value.trim(),
    Deepmind: document.getElementById('test-deepmind').value.trim(),
    Channel: document.getElementById('test-channel').value.trim(),
    'Task Result': document.getElementById('test-task_result').value.trim(),
  };
  if (!payload.beginTime || !payload.endTime || !payload.Deepmind || !payload.Channel) {
    alert('请填写 Deepmind、通道、开始时间和结束时间'); return;
  }
  try {
    const r = await fetch('/api/test-download', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
    const d = await r.json();
    if (d.ok) { alert('下载已开始: ' + d.event_id); switchTab('dashboard'); }
    else alert('错误: ' + d.error);
  } catch(e) { alert(e.message); }
}

// ===== 自动刷新 =====
setInterval(() => {
  if (document.getElementById('page-dashboard').classList.contains('active')) {
    loadStats(); loadHistory();
  }
}, 10000);

// ===== 初始化 =====
loadStats(); loadHistory(); initSSE();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="NVR 下载管理器 Web GUI")
    parser.add_argument("--host", default="0.0.0.0", help="绑定地址 (默认 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9800, help="绑定端口 (默认 9800)")
    args = parser.parse_args()

    init_db()
    cfg = load_config()
    save_config(cfg)
    init_executor(cfg.get("max_workers", 4))

    log(f"NVR 下载管理器启动于 {args.host}:{args.port}")

    try:
        from waitress import serve
        log("使用 waitress 作为 WSGI 服务器")
        serve(app, host=args.host, port=args.port, threads=32,
              channel_timeout=300, recv_bytes=65536)
    except ImportError:
        log("未安装 waitress，回退到 Flask 开发服务器")
        app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
