#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简易回放视频下载 + 截图 —— 最简 CLI 示例

三种模式：
  [下载 MP4]   python 简易回放下载.py -d 20 -c 5 -b "..." -e "..."
  [实时抓拍]   python 简易回放下载.py -d 20 -c 5 --snapshot
  [历史截图]   python 简易回放下载.py -d 20 -c 5 --frame "2026-05-12 10:00:00"

依赖：
  pip install requests
  历史截图模式可选: ffmpeg (PATH 中可用)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from typing import List, Tuple

import requests
from requests.auth import HTTPDigestAuth

# ── 项目根目录（脚本所在目录）──────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEEPMIND_JSON = os.path.join(SCRIPT_DIR, "Deepmind.json")


# ═══════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════

def load_deepmind_map(path: str) -> dict:
    """加载设备注册表 Deepmind.json → {编号: {ip, username, password, ...}}"""
    with open(path, "r", encoding="utf-8") as f:
        arr = json.load(f)

    m = {}
    for item in arr:
        dm = str(item.get("Deepmind", "")).strip()
        ip = str(item.get("IP", "")).strip()
        if not dm or not ip:
            continue
        m[dm] = {
            "ip": ip,
            "username": str(item.get("Username", "admin")).strip() or "admin",
            "password": str(item.get("Password", "")).strip(),
            "http_port": int(item.get("HttpPort", 80) or 80),
            "rtsp_port": int(item.get("RtspPort", 554) or 554),
            "scheme": str(item.get("Scheme", "http")).strip().lower() or "http",
            "verify_tls": bool(item.get("VerifyTLS", False)),
        }
    return m


def to_hik_time(ts: str) -> str:
    """"2026-05-12 10:00:00" → "20260512T100000Z" """
    dt = datetime.strptime(ts.split(".")[0], "%Y-%m-%d %H:%M:%S")
    return dt.strftime("%Y%m%dT%H%M%SZ")


def build_download_url(cfg: dict, channel: str, begin: str, end: str,
                       tracks_suffix: str = "01") -> str:
    """构建海康 ISAPI 回放下载 URL。"""
    t1 = to_hik_time(begin)
    t2 = to_hik_time(end)
    playback = (
        f"rtsp://{cfg['ip']}:{cfg['rtsp_port']}/Streaming/tracks/"
        f"{channel}{tracks_suffix}?starttime={t1}%26endtime={t2}"
    )
    return (f"{cfg['scheme']}://{cfg['ip']}:{cfg['http_port']}"
            f"/ISAPI/ContentMgmt/download?playbackURI={playback}")


def download_hik_mp4(url: str, cfg: dict, out_file: str,
                     timeout: int = 300) -> None:
    """流式下载 MP4 → .part 临时文件 → os.replace 原子化"""
    s = requests.Session()
    s.trust_env = False  # 禁用系统代理

    resp = s.get(url, auth=HTTPDigestAuth(cfg["username"], cfg["password"]),
                 stream=True, timeout=timeout, verify=cfg["verify_tls"])

    if resp.status_code != 200:
        body = (resp.text or "")[:300]
        raise RuntimeError(f"HTTP {resp.status_code}: {body}")

    tmp = out_file + ".part"
    try:
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        os.replace(tmp, out_file)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


# ═══════════════════════════════════════════════════════════
# 下载单段视频
# ═══════════════════════════════════════════════════════════

def download_segment(cfg: dict, channel: str, begin: str, end: str,
                     out_dir: str, tracks: str = "01",
                     timeout: int = 300) -> str:
    """下载一段视频，返回输出文件路径。"""
    t1 = to_hik_time(begin)
    t2 = to_hik_time(end)
    fname = f"ch{channel}_{t1}_{t2}.mp4"
    out_path = os.path.join(out_dir, fname)

    url = build_download_url(cfg, channel, begin, end, tracks)
    print(f"  下载: {fname} ...", end=" ", flush=True)
    download_hik_mp4(url, cfg, out_path, timeout)
    fsize_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"✓ 完成 ({fsize_mb:.1f} MB)")
    return out_path


# ═══════════════════════════════════════════════════════════
# 实时抓拍（JPEG）
# ═══════════════════════════════════════════════════════════

def build_snapshot_url(cfg: dict, channel: str, tracks_suffix: str = "01") -> str:
    """构建海康 ISAPI 实时抓图 URL。
    
    GET /ISAPI/Streaming/channels/{channel}{tracks}/picture → JPEG
    """
    return (f"{cfg['scheme']}://{cfg['ip']}:{cfg['http_port']}"
            f"/ISAPI/Streaming/channels/{channel}{tracks_suffix}/picture")


def capture_snapshot(cfg: dict, channel: str, out_dir: str,
                     tracks: str = "01", timeout: int = 30) -> str:
    """抓取实时快照，返回输出文件路径。"""
    url = build_snapshot_url(cfg, channel, tracks)
    now = datetime.now().strftime("%Y%m%dT%H%M%S")
    fname = f"snapshot_ch{channel}_{now}.jpg"
    out_path = os.path.join(out_dir, fname)

    print(f"  抓拍: {fname} ...", end=" ", flush=True)
    s = requests.Session()
    s.trust_env = False
    resp = s.get(url, auth=HTTPDigestAuth(cfg["username"], cfg["password"]),
                 timeout=timeout, verify=cfg["verify_tls"])

    if resp.status_code != 200:
        body = (resp.text or "")[:300]
        raise RuntimeError(f"HTTP {resp.status_code}: {body}")

    with open(out_path, "wb") as f:
        f.write(resp.content)
    fsize_kb = len(resp.content) / 1024
    print(f"✓ 完成 ({fsize_kb:.1f} KB)")
    return out_path


# ═══════════════════════════════════════════════════════════
# 历史时刻截图（从回放流抽取一帧）
# ═══════════════════════════════════════════════════════════

def _ffmpeg_available() -> bool:
    """检查 ffmpeg 是否在 PATH 中可用。"""
    return shutil.which("ffmpeg") is not None


def capture_frame(cfg: dict, channel: str, moment: str, out_dir: str,
                  tracks: str = "01", timeout: int = 60) -> str:
    """从回放流中截取指定时刻的一帧图片。

    策略：
      1. 下载该时刻前后各 1 秒的短视频（共 2 秒）
      2. 用 ffmpeg 抽取时间戳最接近的那一帧 → JPG
      3. 无 ffmpeg 时，回退为保存短视频本身

    返回输出文件路径。
    """
    t_moment = datetime.strptime(moment.split(".")[0], "%Y-%m-%d %H:%M:%S")
    begin = (t_moment - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
    end = (t_moment + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
    t_hik = t_moment.strftime("%Y%m%dT%H%M%SZ")

    # 先下载短视频
    print(f"  下载片段 ({begin} → {end}) ...", end=" ", flush=True)
    clip_name = f"frame_ch{channel}_{t_hik}.mp4"
    clip_path = os.path.join(out_dir, clip_name)
    url = build_download_url(cfg, channel, begin, end, tracks)
    download_hik_mp4(url, cfg, clip_path, timeout)
    fsize_mb = os.path.getsize(clip_path) / (1024 * 1024)
    print(f"✓ ({fsize_mb:.1f} MB)")

    # 用 ffmpeg 抽帧
    if _ffmpeg_available():
        jpg_name = f"frame_ch{channel}_{t_hik}.jpg"
        jpg_path = os.path.join(out_dir, jpg_name)
        # 抽取 1 秒处的帧（即目标时刻）
        print(f"  抽帧 → {jpg_name} ...", end=" ", flush=True)
        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", "1", "-i", clip_path,
             "-vframes", "1", "-q:v", "2", jpg_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            # ffmpeg 报错时保留短视频
            print(f"⚠ ffmpeg 失败，保留短视频: {clip_name}")
            return clip_path
        fsize_kb = os.path.getsize(jpg_path) / 1024
        print(f"✓ ({fsize_kb:.1f} KB)")
        # 清理临时短视频
        try:
            os.remove(clip_path)
        except OSError:
            pass
        return jpg_path
    else:
        print(f"  ⓘ 未安装 ffmpeg，已保留短视频: {clip_name}")
        print(f"    安装 ffmpeg 后可手动抽帧:")
        print(f"    ffmpeg -ss 1 -i \"{clip_path}\" -vframes 1 -q:v 2 output.jpg")
        return clip_path


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="简易回放下载/截图 —— 输入超脑名称+通道号+时间戳",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 下载 MP4 视频
  python 简易回放下载.py -d 20 -c 5 \\
    -b "2026-05-12 10:00:00" -e "2026-05-12 10:05:00"

  # 实时抓拍（当前画面）
  python 简易回放下载.py -d 20 -c 5 --snapshot

  # 历史时刻截图（从回放中抽取一帧）
  python 简易回放下载.py -d 20 -c 5 --frame "2026-05-12 10:00:00"

  # 批量历史截图（从文件读取时间点列表）
  python 简易回放下载.py -d 20 -c 5 --frame @moments.txt

时间点文件格式 (moments.txt)，每行一个时刻：
  2026-05-12 10:00:00
  2026-05-12 11:30:00
  2026-05-12 14:00:00

  # 1K/2K 子码流
  python 简易回放下载.py -d 20 -c 5 --snapshot --tracks 02
        """,
    )
    parser.add_argument("-d", "--deepmind", required=True,
                        help="超脑编号，如 20（对应 Deepmind.json 中的 Deepmind 字段）")
    parser.add_argument("-c", "--channel", required=True,
                        help="通道号，如 5（通道5主码流实际 tracks 后缀为 501）")

    # 下载参数
    parser.add_argument("-b", "--begin",
                        help="开始时间，格式 YYYY-MM-DD HH:MM:SS")
    parser.add_argument("-e", "--end",
                        help="结束时间，格式 YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--segments",
                        help="分段文件路径，每行: 开始时间 结束时间")

    # 截图参数
    parser.add_argument("--snapshot", action="store_true",
                        help="实时抓拍模式：抓取当前实时画面（JPEG）")
    parser.add_argument("--frame",
                        help="历史截图模式：从回放中抽取指定时刻的一帧。"
                             "值可为时刻字符串，或 @文件路径 批量截图")

    # 通用参数
    parser.add_argument("-o", "--out-dir", default=SCRIPT_DIR,
                        help="输出目录 (默认: 脚本所在目录)")
    parser.add_argument("--tracks", default="01",
                        help="tracks 后缀: 01=主码流/1K, 02=子码流/2K (默认 01)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="超时秒数 (默认: 下载 300, 截图 60)")
    parser.add_argument("--json", default=DEEPMIND_JSON,
                        help="Deepmind.json 路径 (默认: 脚本同目录)")

    args = parser.parse_args()

    # ── 1. 加载设备 ──
    if not os.path.exists(args.json):
        print(f"✗ 找不到设备配置文件: {args.json}")
        return 1

    dm_map = load_deepmind_map(args.json)
    dm_key = args.deepmind.strip()
    if dm_key not in dm_map:
        print(f"✗ 超脑编号 '{dm_key}' 不在 {args.json} 中")
        print(f"  可用编号: {', '.join(sorted(dm_map.keys()))}")
        return 1

    cfg = dm_map[dm_key]
    channel = args.channel.strip()

    print(f"设备: 超脑 {dm_key}  ({cfg['ip']})")
    print(f"通道: {channel}  码流: {args.tracks}")
    print(f"输出: {args.out_dir}")
    print("-" * 50)

    os.makedirs(args.out_dir, exist_ok=True)

    # ── 2. 模式分发 ──

    # 模式 A：实时抓拍
    if args.snapshot:
        print("模式: 实时抓拍 (JPEG)\n")
        try:
            out = capture_snapshot(cfg, channel, args.out_dir,
                                   args.tracks, min(args.timeout, 60))
            print(f"\n{'='*50}")
            print(f"✓ 抓拍完成: {out}")
            return 0
        except Exception as ex:
            print(f"\n✗ 抓拍失败: {ex}")
            return 1

    # 模式 B：历史时刻截图
    if args.frame:
        print("模式: 历史时刻截图 (需要 ffmpeg)\n")

        # 解析时刻列表
        moments: List[str] = []
        frame_arg = args.frame.strip()
        if frame_arg.startswith("@"):
            # 从文件读取
            fp = frame_arg[1:]
            if not os.path.exists(fp):
                print(f"✗ 找不到时刻文件: {fp}")
                return 1
            with open(fp, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        moments.append(line)
        else:
            moments.append(frame_arg)

        if not moments:
            print("✗ 没有要截图的时间点")
            return 1

        print(f"待截图: {len(moments)} 个时刻\n")
        ok, fail = 0, 0
        for i, m in enumerate(moments, 1):
            print(f"[{i}/{len(moments)}] {m}")
            try:
                out = capture_frame(cfg, channel, m, args.out_dir,
                                    args.tracks, min(args.timeout, 120))
                ok += 1
            except Exception as ex:
                print(f"  ✗ 失败: {ex}")
                fail += 1

        print(f"\n{'='*50}")
        print(f"完成: 成功 {ok}, 失败 {fail}, 共 {len(moments)}")
        return 0 if fail == 0 else 1

    # 模式 C：默认 — 下载 MP4
    segments: List[Tuple[str, str]] = []
    if args.segments:
        with open(args.segments, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) == 2:
                    b, e = parts[0], parts[1]
                elif len(parts) >= 4:
                    b = f"{parts[0]} {parts[1]}"
                    e = f"{parts[2]} {parts[3]}"
                else:
                    continue
                segments.append((b, e))
    elif args.begin and args.end:
        segments.append((args.begin, args.end))
    else:
        print("✗ 请选择一种模式:")
        print("  下载 MP4:  -b + -e  或  --segments 文件")
        print("  实时抓拍:  --snapshot")
        print("  历史截图:  --frame \"YYYY-MM-DD HH:MM:SS\"")
        return 1

    if not segments:
        print("✗ 没有要下载的时间段")
        return 1

    print(f"模式: 下载 MP4")
    print(f"待下载: {len(segments)} 段\n")
    ok, fail = 0, 0
    for i, (b, e) in enumerate(segments, 1):
        print(f"[{i}/{len(segments)}] {b} → {e}")
        try:
            download_segment(cfg, channel, b, e,
                             args.out_dir, args.tracks, args.timeout)
            ok += 1
        except Exception as ex:
            print(f"  ✗ 失败: {ex}")
            fail += 1

    print(f"\n{'='*50}")
    print(f"完成: 成功 {ok}, 失败 {fail}, 共 {len(segments)}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
