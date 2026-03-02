import requests
import json
from datetime import datetime
import os

class HikvisionNVRDownloader:
    def __init__(self, nvr_ip, nvr_port=80, username='admin', password=''):
        """
        初始化海康NVR下载器
        :param nvr_ip: NVR的IP地址
        :param nvr_port: NVR的端口，默认80
        :param username: 登录用户名
        :param password: 登录密码
        """
        self.nvr_ip = nvr_ip
        self.nvr_port = nvr_port
        self.username = username
        self.password = password
        self.base_url = f"http://{nvr_ip}:{nvr_port}"
        
    def download_playback(self, channel, begin_time, end_time, save_path=None):
        """
        下载指定通道和时间段的回放视频
        :param channel: 通道号
        :param begin_time: 开始时间，格式: "2026-02-10 13:20:22.955"
        :param end_time: 结束时间，格式: "2026-02-10 13:20:26.108"
        :param save_path: 保存路径，默认为当前目录
        :return: 下载的文件路径
        """
        # 转换时间格式为海康格式 (YYYYMMDDTHHMMSSZ)
        begin_dt = datetime.strptime(begin_time.split('.')[0], "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(end_time.split('.')[0], "%Y-%m-%d %H:%M:%S")
        
        begin_formatted = begin_dt.strftime("%Y%m%dT%H%M%SZ")
        end_formatted = end_dt.strftime("%Y%m%dT%H%M%SZ")
        
        # 构建下载URL
        download_url = (
            f"{self.base_url}/ISAPI/ContentMgmt/download?"
            f"playbackURI=rtsp://{self.nvr_ip}:{self.nvr_port}/Streaming/tracks/{channel}01?"
            f"starttime={begin_formatted}&endtime={end_formatted}"
        )
        
        # 设置保存路径
        if save_path is None:
            save_path = f"playback_ch{channel}_{begin_dt.strftime('%Y%m%d_%H%M%S')}.mp4"
        
        try:
            print(f"开始下载通道 {channel} 的视频...")
            print(f"时间段: {begin_time} 到 {end_time}")
            
            # 发送下载请求
            response = requests.get(
                download_url,
                auth=requests.auth.HTTPDigestAuth(self.username, self.password),
                stream=True,
                timeout=30
            )
            
            if response.status_code == 200:
                # 保存视频文件
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                print(f"视频下载成功: {save_path}")
                return save_path
            else:
                print(f"下载失败，状态码: {response.status_code}")
                print(f"响应内容: {response.text}")
                return None
                
        except Exception as e:
            print(f"下载过程中出错: {str(e)}")
            return None


def process_webhook_data(webhook_data):
    """
    处理webhook接收到的数据并下载视频
    :param webhook_data: webhook接收到的数据
    """
    body = webhook_data.get('body', {})
    
    # 提取必要信息
    event_id = body.get('event_id')
    channel = body.get('Channel')
    begin_time = body.get('beginTime')
    end_time = body.get('endTime')
    task_result = body.get('Task Result')
    deepmind = body.get('Deepmind')
    
    print(f"\n处理事件: {event_id}")
    print(f"任务结果: {task_result}")
    print(f"Deepmind设备: {deepmind}")
    print(f"通道: {channel}")
    
    # 创建下载器实例（需要修改为你的NVR IP和认证信息）
    downloader = HikvisionNVRDownloader(
        nvr_ip="10.30.5.112",  # 从webhook数据中的host提取
        username="admin",  # 替换为实际用户名
        password="wdzn6688"  # 替换为实际密码
    )
    
    # 下载视频
    save_filename = f"event_{event_id}_{task_result}_ch{channel}.mp4"
    result = downloader.download_playback(
        channel=channel,
        begin_time=begin_time,
        end_time=end_time,
        save_path=save_filename
    )
    
    return result


# 使用示例
if __name__ == "__main__":
    # 模拟webhook接收到的数据
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
            "beginTime": "2026-02-10 13:32:05.552",
            "endTime": "2026-02-10 13:35:16.568",
            "Deepmind": "20",
            "Channel": "5"
        }
    }
    
    # 处理webhook数据并下载视频
    process_webhook_data(webhook_data)
    
    # 或者直接使用下载器
    # downloader = HikvisionNVRDownloader(
    #     nvr_ip="10.30.43.199",
    #     username="admin",
    #     password="your_password"
    # )
    # downloader.download_playback(
    #     channel="11",
    #     begin_time="2026-02-10 13:20:22.955",
    #     end_time="2026-02-10 13:20:26.108"
    # )