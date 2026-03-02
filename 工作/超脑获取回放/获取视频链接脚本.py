import requests
import json
from datetime import datetime


class HikvisionPlaybackURL:
    def __init__(self, nvr_ip, nvr_port=80, rtsp_port=554, username='admin', password=''):
        self.nvr_ip = nvr_ip
        self.nvr_port = nvr_port
        self.rtsp_port = rtsp_port
        self.username = username
        self.password = password
        self.base_url = f"http://{nvr_ip}:{nvr_port}"

    def _format_time(self, time_str):
        """将 '2026-02-10 13:20:22.955' 格式转为海康格式 '20260210T132022Z'"""
        dt = datetime.strptime(time_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y%m%dT%H%M%SZ")

    def get_rtsp_url(self, channel, begin_time, end_time):
        """
        获取RTSP回放链接（可直接用VLC等播放器打开）
        :param channel: 通道号
        :param begin_time: 开始时间，格式: "2026-02-10 13:20:22.955"
        :param end_time: 结束时间，格式: "2026-02-10 13:20:26.108"
        :return: RTSP播放链接
        """
        begin_fmt = self._format_time(begin_time)
        end_fmt = self._format_time(end_time)

        rtsp_url = (
            f"rtsp://{self.username}:{self.password}@{self.nvr_ip}:{self.rtsp_port}"
            f"/Streaming/tracks/{channel}01?starttime={begin_fmt}&endtime={end_fmt}"
        )
        return rtsp_url

    def get_http_preview_url(self, channel, begin_time, end_time):
        """
        获取HTTP预览回放链接（可在浏览器或程序中直接请求流）
        :param channel: 通道号
        :param begin_time: 开始时间
        :param end_time: 结束时间
        :return: HTTP回放流链接
        """
        begin_fmt = self._format_time(begin_time)
        end_fmt = self._format_time(end_time)

        http_url = (
            f"{self.base_url}/ISAPI/ContentMgmt/StreamingProxy/trackID/{channel}01"
            f"?starttime={begin_fmt}&endtime={end_fmt}"
        )
        return http_url

    def get_playback_urls(self, channel, begin_time, end_time):
        """
        一次性返回所有可用的回放链接
        :return: dict 包含 rtsp 和 http 链接
        """
        return {
            "rtsp": self.get_rtsp_url(channel, begin_time, end_time),
            "http_stream": self.get_http_preview_url(channel, begin_time, end_time),
        }

    def generate_playback_html(self, channel, begin_time, end_time, save_path=None):
        """
        生成一个本地HTML文件，嵌入VLC Web插件或video标签来播放回放
        :return: HTML文件路径
        """
        rtsp_url = self.get_rtsp_url(channel, begin_time, end_time)
        http_url = self.get_http_preview_url(channel, begin_time, end_time)

        begin_dt = datetime.strptime(begin_time.split('.')[0], "%Y-%m-%d %H:%M:%S")
        if save_path is None:
            save_path = f"playback_ch{channel}_{begin_dt.strftime('%Y%m%d_%H%M%S')}.html"

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>回放 - 通道{channel}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #1a1a2e; color: #eee; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ color: #e94560; }}
        .info {{ background: #16213e; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .info p {{ margin: 8px 0; }}
        .url-box {{ background: #0f3460; padding: 12px; border-radius: 4px; word-break: break-all;
                    font-family: monospace; font-size: 14px; margin: 10px 0; cursor: pointer; }}
        .url-box:hover {{ background: #1a4a7a; }}
        .label {{ color: #e94560; font-weight: bold; }}
        .copy-btn {{ background: #e94560; color: white; border: none; padding: 6px 16px;
                     border-radius: 4px; cursor: pointer; margin-left: 10px; }}
        .copy-btn:hover {{ background: #c73650; }}
        .tip {{ color: #aaa; font-size: 13px; margin-top: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>NVR 回放链接</h1>
        <div class="info">
            <p><span class="label">通道：</span>{channel}</p>
            <p><span class="label">开始时间：</span>{begin_time}</p>
            <p><span class="label">结束时间：</span>{end_time}</p>
            <p><span class="label">NVR地址：</span>{self.nvr_ip}</p>
        </div>

        <h2>RTSP 回放链接</h2>
        <div class="url-box" onclick="copyText(this)" title="点击复制">{rtsp_url}</div>
        <p class="tip">可直接用 VLC 播放器打开此链接播放回放视频</p>

        <h2>HTTP 流链接</h2>
        <div class="url-box" onclick="copyText(this)" title="点击复制">{http_url}</div>
        <p class="tip">可在程序中通过 HTTP 请求获取视频流（需 Digest 认证）</p>

        <h2>VLC 命令行播放</h2>
        <div class="url-box" onclick="copyText(this)" title="点击复制">vlc "{rtsp_url}"</div>
        <p class="tip">在终端中执行此命令直接播放</p>
    </div>

    <script>
        function copyText(el) {{
            navigator.clipboard.writeText(el.innerText).then(() => {{
                const original = el.style.background;
                el.style.background = '#2ecc71';
                setTimeout(() => el.style.background = original, 500);
            }});
        }}
    </script>
</body>
</html>"""

        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"HTML播放页面已生成: {save_path}")
        return save_path


def get_playback_link(webhook_data):
    """
    处理webhook数据，返回回放链接（不下载）
    :param webhook_data: webhook接收到的数据
    :return: dict 包含所有可用的播放链接
    """
    body = webhook_data.get('body', {})

    event_id = body.get('event_id')
    channel = body.get('Channel')
    begin_time = body.get('beginTime')
    end_time = body.get('endTime')
    task_result = body.get('Task Result')
    deepmind = body.get('Deepmind')

    print(f"事件: {event_id} | 结果: {task_result} | 通道: {channel}")

    client = HikvisionPlaybackURL(
        nvr_ip="10.30.5.112",
        username="admin",
        password="wdzn6688"
    )

    urls = client.get_playback_urls(channel, begin_time, end_time)

    print(f"RTSP链接: {urls['rtsp']}")
    print(f"HTTP链接: {urls['http_stream']}")

    return urls


if __name__ == "__main__":
    webhook_data = {
        "headers": {
            "content-type": "application/json",
            "host": "10.30.43.199:5678",
            "content-length": "232"
        },
        "body": {
            "event_id": "电感测试1的唯一识别ID",
            "Task Result": "NG",
            "event_time": "2026-02-10 13:32:16.568",
            "beginTime": "2026-02-10 13:34:05.552",
            "endTime": "2026-02-10 13:35:05.568",
            "Deepmind": "20",
            "Channel": "2"
        }
    }

    # 方式1: 直接获取链接
    urls = get_playback_link(webhook_data)

    # 方式2: 生成HTML播放页面
    client = HikvisionPlaybackURL(
        nvr_ip="10.30.5.112",
        username="admin",
        password="wdzn6688"
    )
    client.generate_playback_html(
        channel="2",
        begin_time="2026-02-10 13:32:05.552",
        end_time="2026-02-10 13:35:16.568"
    )

    # 方式3: 在其他脚本中调用
    # from 获取回放链接 import HikvisionPlaybackURL
    # client = HikvisionPlaybackURL(nvr_ip="10.30.5.112", username="admin", password="wdzn6688")
    # rtsp_url = client.get_rtsp_url(channel="5", begin_time="...", end_time="...")
    # 然后用 rtsp_url 直接播放
