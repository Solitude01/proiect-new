#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from xml.etree import ElementTree as ET

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


def to_iso_time(ts: str) -> str:
    """
    "2026-02-10 18:43:05.139" -> "2026-02-10T18:43:05Z"
    """
    dt = datetime.strptime(ts.split(".")[0], "%Y-%m-%d %H:%M:%S")
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _make_session() -> requests.Session:
    """不读取环境代理"""
    s = requests.Session()
    s.trust_env = False
    return s


def load_deepmind_map(deepmind_json_path: str) -> Dict[str, Dict[str, Any]]:
    """
    支持旧格式（只有 IP/Password）和新格式（带 HttpPort/RtspPort/Scheme 等）

    推荐字段（可选）：
      Username: 默认 admin
      HttpPort: 默认 80
      RtspPort: 默认 554
      Scheme:   默认 http (可填 https)
      VerifyTLS: 默认 false（https 时是否校验证书）
      SearchBeforeDownload: 默认 false
        某些 NVR 型号（如 iDS-96064NX）不支持按时间直接下载，
        需要先搜索录像获取文件名，再用 POST+XML 方式下载。
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
        search_before_download = bool(item.get("SearchBeforeDownload", False))

        m[dm] = {
            "ip": ip,
            "username": username,
            "password": password,
            "http_port": http_port,
            "rtsp_port": rtsp_port,
            "scheme": scheme,
            "verify_tls": verify_tls,
            "search_before_download": search_before_download,
        }
    return m


# -----------------------------
# 搜索录像（按文件名下载的 NVR 需要）
# -----------------------------
def search_recording(
    nvr_ip: str,
    scheme: str,
    http_port: int,
    username: str,
    password: str,
    track_id: str,
    start_time: str,
    end_time: str,
    verify_tls: bool = False,
) -> Optional[Dict[str, str]]:
    """
    POST /ISAPI/ContentMgmt/search 搜索录像文件。
    返回 {"playbackURI": ..., "name": ..., "size": ...} 或 None。
    start_time / end_time 格式: "2026-02-26 10:23:09.000"
    """
    search_url = f"{scheme}://{nvr_ip}:{http_port}/ISAPI/ContentMgmt/search"

    t1 = to_iso_time(start_time)
    t2 = to_iso_time(end_time)

    search_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<CMSearchDescription>'
        f'<searchID>{uuid.uuid4()}</searchID>'
        '<trackList>'
        f'<trackID>{track_id}</trackID>'
        '</trackList>'
        '<timeSpanList>'
        '<timeSpan>'
        f'<startTime>{t1}</startTime>'
        f'<endTime>{t2}</endTime>'
        '</timeSpan>'
        '</timeSpanList>'
        '<maxResults>40</maxResults>'
        '<searchResultPostion>0</searchResultPostion>'
        '<metadataList>'
        '<metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor>'
        '</metadataList>'
        '</CMSearchDescription>'
    )

    s = _make_session()
    resp = s.post(
        search_url,
        data=search_xml.encode("utf-8"),
        headers={"Content-Type": "application/xml"},
        auth=HTTPDigestAuth(username, password),
        timeout=15,
        verify=verify_tls,
    )

    if resp.status_code != 200:
        return None

    # 解析 XML 响应，提取 playbackURI
    ns = {"ns": "http://www.isapi.org/ver20/XMLSchema"}
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None

    # 移除命名空间前缀以简化查找
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    matches = root.findall(".//searchMatchItem")
    if not matches:
        return None

    # 找到时间范围覆盖我们需要时段的录像片段
    best = None
    for match in matches:
        uri_elem = match.find(".//playbackURI")
        name_elem = match.find(".//name")
        if uri_elem is not None and uri_elem.text:
            result = {"playbackURI": uri_elem.text}
            if name_elem is not None and name_elem.text:
                result["name"] = name_elem.text
            # 从 URI 提取 size
            size_match = re.search(r'size=(\d+)', uri_elem.text)
            if size_match:
                result["size"] = size_match.group(1)
            best = result

    return best


# -----------------------------
# 构建下载请求
# -----------------------------
def build_download_url(
    nvr_ip: str,
    scheme: str,
    http_port: int,
    rtsp_port: int,
    channel: str,
    begin_time: str,
    end_time: str,
    tracks_suffix: str = "01",
) -> Tuple[str, str]:
    """
    普通 GET 模式（支持按时间下载的 NVR），返回 (url, "")。
    """
    t1 = to_hik_time(begin_time)
    t2 = to_hik_time(end_time)

    # & 必须写成 %26（因为 playbackURI 本身是 query 参数）
    playback_uri = (
        f"rtsp://{nvr_ip}:{rtsp_port}/Streaming/tracks/{channel}{tracks_suffix}"
        f"?starttime={t1}%26endtime={t2}"
    )
    url = f"{scheme}://{nvr_ip}:{http_port}/ISAPI/ContentMgmt/download?playbackURI={playback_uri}"
    return url, ""


def build_download_by_name(
    nvr_ip: str,
    scheme: str,
    http_port: int,
    search_playback_uri: str,
    begin_time: str,
    end_time: str,
) -> Tuple[str, str]:
    """
    POST+XML 模式（按文件名下载的 NVR）。
    用搜索返回的 playbackURI 为基础，替换 starttime/endtime 为实际需要的时段。
    返回 (url, xml_body)。
    """
    t1 = to_hik_time(begin_time)
    t2 = to_hik_time(end_time)

    # 替换搜索结果中的 starttime/endtime 为实际需要的时段
    uri = search_playback_uri
    uri = re.sub(r'starttime=\w+', f'starttime={t1}', uri)
    uri = re.sub(r'endtime=\w+', f'endtime={t2}', uri)

    # XML 中 & 需要转义为 &amp;
    uri_xml = uri.replace("&", "&amp;")

    url = f"{scheme}://{nvr_ip}:{http_port}/ISAPI/ContentMgmt/download"
    xml_body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<downloadRequest>\n'
        f'<playbackURI>{uri_xml}</playbackURI>\n'
        '</downloadRequest>'
    )
    return url, xml_body


# -----------------------------
# 下载
# -----------------------------
def download_hik_mp4(
    url: str,
    username: str,
    password: str,
    out_file: str,
    timeout: int = 180,
    verify_tls: bool = False,
    xml_body: str = "",
) -> None:
    s = _make_session()

    if xml_body:
        resp = s.post(
            url,
            data=xml_body.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
            auth=HTTPDigestAuth(username, password),
            stream=True,
            timeout=timeout,
            verify=verify_tls,
        )
    else:
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
            body_preview = (resp.text or "")[:600]
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
    with open(tmp_file, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    os.replace(tmp_file, out_file)


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

    track_id = f"{channel}{args.tracks_suffix}"

    if cfg.get("search_before_download", False):
        rec = search_recording(
            nvr_ip=nvr_ip, scheme=scheme, http_port=http_port,
            username=username, password=password,
            track_id=track_id,
            start_time=args.beginTime, end_time=args.endTime,
            verify_tls=verify_tls,
        )
        if not rec:
            raise RuntimeError(f"未搜索到录像 track={track_id} {args.beginTime}~{args.endTime}")
        url, xml_body = build_download_by_name(
            nvr_ip=nvr_ip, scheme=scheme, http_port=http_port,
            search_playback_uri=rec["playbackURI"],
            begin_time=args.beginTime, end_time=args.endTime,
        )
    else:
        url, xml_body = build_download_url(
            nvr_ip=nvr_ip, scheme=scheme, http_port=http_port,
            rtsp_port=rtsp_port, channel=channel,
            begin_time=args.beginTime, end_time=args.endTime,
            tracks_suffix=args.tracks_suffix,
        )

    download_hik_mp4(
        url=url, username=username, password=password,
        out_file=out_file, timeout=args.timeout,
        verify_tls=verify_tls, xml_body=xml_body,
    )

    print(json.dumps({"ok": True, "event_id": event_id, "file": out_file}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
