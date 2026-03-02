#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any

import requests
from requests.auth import HTTPDigestAuth


# -----------------------------
# helpers
# -----------------------------
def to_hik_time(ts: str) -> str:
    """
    "2026-02-10 18:43:05.139" -> "20260210T184305Z"
    """
    dt = datetime.strptime(ts.split(".")[0], "%Y-%m-%d %H:%M:%S")
    return dt.strftime("%Y%m%dT%H%M%SZ")


def safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def short_headers(headers: Dict[str, str]) -> Dict[str, str]:
    keep = {
        "server",
        "date",
        "content-type",
        "content-length",
        "connection",
        "via",
        "x-cache",
        "www-authenticate",
    }
    out: Dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in keep:
            out[k] = v
    return out


def load_deepmind_map(deepmind_json_path: str) -> Dict[str, Dict[str, Any]]:
    """
    支持旧格式（只有 IP/Password）和新格式（带 HttpPort/RtspPort/Scheme 等）

    推荐字段（可选）：
      Username: 默认 admin
      HttpPort: 默认 80
      RtspPort: 默认 554
      Scheme:   默认 http (可填 https)
      VerifyTLS: 默认 false（https 时是否校验证书）
    """
    with open(deepmind_json_path, "r", encoding="utf-8") as f:
        arr = json.load(f)

    m: Dict[str, Dict[str, Any]] = {}
    for item in arr:
        dm = str(item.get("Deepmind", "")).strip()
        ip = str(item.get("IP", "")).strip()
        if not dm or not ip:
            continue

        # 兼容：你给的 JSON 里 Deepmind=20 没写 HttpPort/RtspPort/Scheme，也能跑
        username = str(item.get("Username", "admin")).strip() or "admin"
        password = str(item.get("Password", "")).strip()

        # 允许写成数字或字符串
        def to_int(v, default: int) -> int:
            if v is None or v == "":
                return default
            try:
                return int(v)
            except Exception:
                return default

        http_port = to_int(item.get("HttpPort", 80), 80)
        rtsp_port = to_int(item.get("RtspPort", 554), 554)

        scheme = str(item.get("Scheme", "http")).strip().lower() or "http"
        if scheme not in ("http", "https"):
            scheme = "http"

        verify_tls = bool(item.get("VerifyTLS", False))

        m[dm] = {
            "ip": ip,
            "username": username,
            "password": password,
            "http_port": http_port,
            "rtsp_port": rtsp_port,
            "scheme": scheme,
            "verify_tls": verify_tls,
        }
    return m


def build_download_url(
    nvr_ip: str,
    scheme: str,
    http_port: int,
    rtsp_port: int,
    channel: str,
    begin_time: str,
    end_time: str,
    tracks_suffix: str = "01",
) -> str:
    """
    海康 ISAPI 回放下载：
      {scheme}://IP:{http_port}/ISAPI/ContentMgmt/download?playbackURI=rtsp://IP:{rtsp_port}/Streaming/tracks/{channel}{tracks_suffix}?starttime=...%26endtime=...
    """
    t1 = to_hik_time(begin_time)
    t2 = to_hik_time(end_time)

    # 注意：& 必须写成 %26（因为 playbackURI 本身是 query 参数）
    playback_uri = (
        f"rtsp://{nvr_ip}:{rtsp_port}/Streaming/tracks/{channel}{tracks_suffix}"
        f"?starttime={t1}%26endtime={t2}"
    )
    return f"{scheme}://{nvr_ip}:{http_port}/ISAPI/ContentMgmt/download?playbackURI={playback_uri}"


def download_hik_mp4(
    url: str,
    username: str,
    password: str,
    out_file: str,
    timeout: int = 180,
    verify_tls: bool = False,
    cancel_event=None,
) -> None:
    # ✅ 关键：不读取环境代理（HTTP_PROXY/HTTPS_PROXY/NO_PROXY）
    s = requests.Session()
    s.trust_env = False

    resp = s.get(
        url,
        auth=HTTPDigestAuth(username, password),
        stream=True,
        timeout=timeout,
        verify=verify_tls,
    )

    if resp.status_code != 200:
        body_preview = ""
        try:
            body_preview = (resp.text or "")[:300]
        except Exception:
            body_preview = ""

        raise RuntimeError(
            json.dumps(
                {
                    "http_status": resp.status_code,
                    "headers": short_headers(dict(resp.headers)),
                    "body_preview": body_preview,
                    "url": url,
                },
                ensure_ascii=False,
            )
        )

    tmp_file = out_file + ".part"
    try:
        with open(tmp_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("下载已取消")
                if chunk:
                    f.write(chunk)
        os.replace(tmp_file, out_file)
    except BaseException:
        # 取消或异常时清理临时文件
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError:
                pass
        raise


# -----------------------------
# main
# -----------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Download Hikvision event clip to NAS folder by begin/end time.")
    ap.add_argument("--event_id", required=True)
    ap.add_argument("--beginTime", required=True)
    ap.add_argument("--endTime", required=True)
    ap.add_argument("--Deepmind", required=True)
    ap.add_argument("--Channel", required=True)

    ap.add_argument("--base_dir", default="/vol1/1000/aa/LA")
    ap.add_argument("--deepmind_json", default="/scripts/Deepmind.json")

    # 可覆盖 JSON 的端口/协议（一般不需要）
    ap.add_argument("--http_port", type=int, default=None)
    ap.add_argument("--rtsp_port", type=int, default=None)
    ap.add_argument("--scheme", type=str, default=None)

    ap.add_argument("--tracks_suffix", type=str, default="01")
    ap.add_argument("--timeout", type=int, default=180)

    args = ap.parse_args()

    event_id = str(args.event_id).strip()
    deepmind = str(args.Deepmind).strip()
    channel = str(args.Channel).strip()

    dm_map = load_deepmind_map(args.deepmind_json)
    if deepmind not in dm_map:
        raise RuntimeError(f"Deepmind={deepmind} not found in {args.deepmind_json}")

    cfg = dm_map[deepmind]
    nvr_ip = cfg["ip"]
    username = cfg["username"]
    password = cfg["password"]
    http_port = cfg["http_port"]
    rtsp_port = cfg["rtsp_port"]
    scheme = cfg["scheme"]
    verify_tls = cfg["verify_tls"]

    # 允许命令行覆盖（排错用）
    if args.http_port is not None:
        http_port = int(args.http_port)
    if args.rtsp_port is not None:
        rtsp_port = int(args.rtsp_port)
    if args.scheme is not None:
        s = str(args.scheme).strip().lower()
        if s in ("http", "https"):
            scheme = s

    # 事件目录：/vol1/1000/aa/LA/{event_id}/
    event_dir = os.path.join(args.base_dir, event_id)
    safe_mkdir(event_dir)

    b = to_hik_time(args.beginTime)
    e = to_hik_time(args.endTime)
    out_file = os.path.join(event_dir, f"ch{channel}_{b}_{e}.mp4")

    url = build_download_url(
        nvr_ip=nvr_ip,
        scheme=scheme,
        http_port=http_port,
        rtsp_port=rtsp_port,
        channel=channel,
        begin_time=args.beginTime,
        end_time=args.endTime,
        tracks_suffix=args.tracks_suffix,
    )

    download_hik_mp4(
        url=url,
        username=username,
        password=password,
        out_file=out_file,
        timeout=args.timeout,
        verify_tls=verify_tls,
    )

    print(json.dumps({"ok": True, "event_id": event_id, "file": out_file}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
