import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime


NVR_IP = "10.30.5.112"
NVR_PORT = 80
USERNAME = "admin"
PASSWORD = "wdzn6688"
CHANNEL = "5"
BEGIN_TIME = "2026-02-10 13:32:05"
END_TIME = "2026-02-10 13:35:16"

BASE = f"http://{NVR_IP}:{NVR_PORT}"
AUTH = HTTPDigestAuth(USERNAME, PASSWORD)

# 转换时间格式
begin_dt = datetime.strptime(BEGIN_TIME, "%Y-%m-%d %H:%M:%S")
end_dt = datetime.strptime(END_TIME, "%Y-%m-%d %H:%M:%S")
t1_hik = begin_dt.strftime("%Y%m%dT%H%M%SZ")      # 20260210T133205Z
t2_hik = end_dt.strftime("%Y%m%dT%H%M%SZ")
t1_iso = begin_dt.strftime("%Y-%m-%dT%H:%M:%SZ")   # 2026-02-10T13:32:05Z
t2_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

ch = CHANNEL
ch2 = f"{int(CHANNEL):02d}"  # 05

# ============================================================
# 所有可能的回放 HTTP 接口，逐个测试
# ============================================================
urls = {
    # --- 方式1: ContentMgmt/download (原下载脚本用的，肯定能通) ---
    "1-download接口(原脚本)": (
        f"{BASE}/ISAPI/ContentMgmt/download?"
        f"playbackURI=rtsp://{NVR_IP}:{NVR_PORT}/Streaming/tracks/{ch}01?"
        f"starttime={t1_hik}%26endtime={t2_hik}"
    ),

    # --- 方式2: Streaming/channels 回放 ---
    "2a-Streaming/channels(tracks格式)": (
        f"{BASE}/ISAPI/Streaming/tracks/{ch}01?"
        f"starttime={t1_hik}&endtime={t2_hik}"
    ),
    "2b-Streaming/channels/通道01": (
        f"{BASE}/ISAPI/Streaming/channels/{ch}01?"
        f"starttime={t1_hik}&endtime={t2_hik}"
    ),
    "2c-Streaming/channels/通道02(子码流)": (
        f"{BASE}/ISAPI/Streaming/channels/{ch}02?"
        f"starttime={t1_hik}&endtime={t2_hik}"
    ),

    # --- 方式3: ContentMgmt/search + playback ---
    "3a-StreamingProxy/channels": (
        f"{BASE}/ISAPI/ContentMgmt/StreamingProxy/channels/{ch}01?"
        f"starttime={t1_hik}&endtime={t2_hik}"
    ),
    "3b-StreamingProxy/trackID": (
        f"{BASE}/ISAPI/ContentMgmt/StreamingProxy/trackID/{ch}01?"
        f"starttime={t1_hik}&endtime={t2_hik}"
    ),

    # --- 方式4: 录像回放专用接口 ---
    "4a-record/tracks回放": (
        f"{BASE}/ISAPI/ContentMgmt/record/tracks/{ch}01?"
        f"starttime={t1_hik}&endtime={t2_hik}"
    ),
    "4b-playback/URI格式": (
        f"{BASE}/ISAPI/ContentMgmt/PlaybackURI?"
        f"channels={ch}&starttime={t1_hik}&endtime={t2_hik}"
    ),

    # --- 方式5: search查录像片段 ---
    "5-search录像片段(POST)": (
        f"{BASE}/ISAPI/ContentMgmt/search"
    ),

    # --- 方式6: 直接用 /doc/page 海康web界面 ---
    "6a-海康web回放页面": f"{BASE}/doc/page/playback.asp",
    "6b-海康web登录页": f"{BASE}/doc/page/login.asp",

    # --- 方式7: download换一种URI编码 ---
    "7-download(完整URI编码)": (
        f"{BASE}/ISAPI/ContentMgmt/download?"
        f"playbackURI=rtsp://{NVR_IP}/Streaming/tracks/{ch}01"
        f"?starttime={t1_hik}%26endtime={t2_hik}"
        f"&name=playback_{ch}_{t1_hik}.mp4"
    ),
}

# 方式5 search 需要 POST XML body
SEARCH_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<CMSearchDescription>
  <searchID>1</searchID>
  <trackList>
    <trackID>{ch}01</trackID>
  </trackList>
  <timeSpanList>
    <timeSpan>
      <startTime>{t1_iso}</startTime>
      <endTime>{t2_iso}</endTime>
    </timeSpan>
  </timeSpanList>
  <maxResults>10</maxResults>
  <searchResultPostion>0</searchResultPostion>
  <metadataList>
    <metadataDescriptor>//recordType.meta.std-cgi.com</metadataDescriptor>
  </metadataList>
</CMSearchDescription>"""


print("=" * 70)
print(f"  海康NVR HTTP回放接口测试")
print(f"  NVR: {NVR_IP}  通道: {CHANNEL}")
print(f"  时间: {BEGIN_TIME} ~ {END_TIME}")
print("=" * 70)

for name, url in urls.items():
    try:
        if name == "5-search录像片段(POST)":
            resp = requests.post(
                url, data=SEARCH_XML, auth=AUTH, timeout=10,
                headers={"Content-Type": "application/xml"}
            )
        else:
            resp = requests.get(url, auth=AUTH, timeout=10, stream=True)

        content_type = resp.headers.get("Content-Type", "")
        content_len = resp.headers.get("Content-Length", "未知")
        status = resp.status_code

        # 判断结果
        if status == 200:
            # 读一小部分内容判断类型
            preview = resp.content[:500] if not name.startswith("1-") else b"(skip)"
            resp.close()

            if b"notSupport" in preview or b"Invalid" in preview:
                result = "不支持(Invalid Operation)"
            elif b"<html" in preview.lower() or b"<!doctype" in preview.lower():
                result = f"返回HTML页面 (可能是web界面)"
            elif content_type.startswith("video/") or content_type == "application/octet-stream":
                result = f"返回视频流! Content-Type={content_type} 大小={content_len}"
            elif "xml" in content_type:
                # 显示XML内容前200字符
                text = preview.decode("utf-8", errors="replace")[:200]
                result = f"返回XML:\n    {text}"
            else:
                text = preview.decode("utf-8", errors="replace")[:150]
                result = f"Content-Type={content_type}\n    {text}"
        else:
            resp.close()
            result = f"HTTP {status}"

        icon = "OK" if status == 200 and "不支持" not in result else "  "
        print(f"\n[{icon}] {name}")
        print(f"    URL: {url[:120]}...")
        print(f"    状态: {status} | {result}")

    except Exception as e:
        print(f"\n[  ] {name}")
        print(f"    URL: {url[:120]}...")
        print(f"    错误: {e}")

print("\n" + "=" * 70)
print("测试完成。标记 [OK] 的是返回200且有实际内容的接口。")
print("=" * 70)
