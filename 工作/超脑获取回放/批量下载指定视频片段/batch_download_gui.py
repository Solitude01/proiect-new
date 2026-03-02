#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""超脑回放视频批量下载 GUI 工具"""

import os
import sys
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from download_event import load_deepmind_map, download_hik_mp4

# ---------------------
# 常量
# ---------------------
# PyInstaller 打包后 __file__ 指向临时解压目录，需要用 exe 所在路径
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEEPMIND_JSON = os.path.join(SCRIPT_DIR, "Deepmind.json")
FILENAME_RE = re.compile(r"ch(\d+)_(\d{8}T\d{6}Z)_(\d{8}T\d{6}Z)\.mp4")

# 分辨率 → tracks 后缀映射
RESOLUTION_MAP = {
    "1K": "01",   # 主码流
    "2K": "02",   # 子码流
}


def parse_paste(text):
    """从粘贴文本中提取文件信息列表。

    返回 [(channel, start, end, filename), ...]
    """
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = FILENAME_RE.search(line)
        if m:
            ch, t1, t2 = m.group(1), m.group(2), m.group(3)
            filename = f"ch{ch}_{t1}_{t2}.mp4"
            results.append((ch, t1, t2, filename))
    return results


def build_url(ip, scheme, http_port, rtsp_port, channel, t1, t2, tracks_suffix="01"):
    """直接用海康时间格式构建下载 URL。"""
    playback_uri = (
        f"rtsp://{ip}:{rtsp_port}/Streaming/tracks/{channel}{tracks_suffix}"
        f"?starttime={t1}%26endtime={t2}"
    )
    return f"{scheme}://{ip}:{http_port}/ISAPI/ContentMgmt/download?playbackURI={playback_uri}"


class BatchDownloadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("超脑回放视频批量下载")
        self.root.geometry("750x680")
        self.root.resizable(True, True)

        self.dm_map = {}
        self.dm_keys = []
        self.downloading = False
        self._cancel_event = threading.Event()

        self._build_ui()
        self._load_devices()

    # ----- UI -----
    def _build_ui(self):
        pad = dict(padx=8, pady=4)

        # 超脑选择
        row = ttk.Frame(self.root)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="超脑设备:").pack(side="left")
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(row, textvariable=self.device_var, state="readonly", width=40)
        self.device_combo.pack(side="left", padx=(4, 0))

        # 通道号
        row2 = ttk.Frame(self.root)
        row2.pack(fill="x", **pad)
        ttk.Label(row2, text="通道号:").pack(side="left")
        self.channel_var = tk.StringVar()
        self.channel_entry = ttk.Entry(row2, textvariable=self.channel_var, width=10)
        self.channel_entry.pack(side="left", padx=(4, 0))
        ttk.Label(row2, text="(留空则从文件名自动识别)").pack(side="left", padx=(8, 0))

        # 分辨率
        row_res = ttk.Frame(self.root)
        row_res.pack(fill="x", **pad)
        ttk.Label(row_res, text="分辨率:").pack(side="left")
        self.resolution_var = tk.StringVar(value="1K")
        self.res_combo = ttk.Combobox(row_res, textvariable=self.resolution_var, width=10, values=["1K", "2K"])
        self.res_combo.pack(side="left", padx=(4, 0))
        ttk.Label(row_res, text="自定义 tracks 后缀:").pack(side="left", padx=(16, 0))
        self.tracks_suffix_var = tk.StringVar()
        ttk.Entry(row_res, textvariable=self.tracks_suffix_var, width=6).pack(side="left", padx=(4, 0))
        ttk.Label(row_res, text="(填写则覆盖分辨率选择, 如 01/02/03)").pack(side="left", padx=(4, 0))

        # 并发数
        row_conc = ttk.Frame(self.root)
        row_conc.pack(fill="x", **pad)
        ttk.Label(row_conc, text="并发线程数:").pack(side="left")
        self.workers_var = tk.IntVar(value=3)
        ttk.Spinbox(row_conc, from_=1, to=10, textvariable=self.workers_var, width=5).pack(side="left", padx=(4, 0))
        ttk.Label(row_conc, text="(同时下载的文件数, 建议 1~5)").pack(side="left", padx=(8, 0))

        # 粘贴区域
        ttk.Label(self.root, text="粘贴文件列表 (dir 输出或纯文件名):").pack(anchor="w", **pad)
        self.text_input = tk.Text(self.root, height=10, wrap="none")
        self.text_input.pack(fill="both", expand=True, **pad)

        # 输出目录
        row3 = ttk.Frame(self.root)
        row3.pack(fill="x", **pad)
        ttk.Label(row3, text="输出目录:").pack(side="left")
        self.outdir_var = tk.StringVar(value=SCRIPT_DIR)
        ttk.Entry(row3, textvariable=self.outdir_var, width=50).pack(side="left", padx=(4, 4), fill="x", expand=True)
        ttk.Button(row3, text="浏览...", command=self._browse_dir).pack(side="left")

        # 按钮行
        btn_row = ttk.Frame(self.root)
        btn_row.pack(fill="x", **pad)
        self.start_btn = ttk.Button(btn_row, text="开始下载", command=self._on_start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn_row, text="停止下载", command=self._on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.parse_btn = ttk.Button(btn_row, text="预览解析", command=self._on_preview)
        self.parse_btn.pack(side="left", padx=(8, 0))

        # 进度条
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", **pad)

        # 日志区域
        ttk.Label(self.root, text="下载日志:").pack(anchor="w", **pad)
        self.log_text = tk.Text(self.root, height=10, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, **pad)

        # 状态标签配色
        self.log_text.tag_configure("ok", foreground="green")
        self.log_text.tag_configure("err", foreground="red")
        self.log_text.tag_configure("info", foreground="blue")

    def _load_devices(self):
        try:
            self.dm_map = load_deepmind_map(DEEPMIND_JSON)
        except Exception as e:
            messagebox.showerror("加载设备失败", str(e))
            return
        self.dm_keys = sorted(self.dm_map.keys(), key=lambda k: int(k) if k.isdigit() else k)
        display = [f"Deepmind {k} - {self.dm_map[k]['ip']}" for k in self.dm_keys]
        self.device_combo["values"] = display
        if display:
            self.device_combo.current(0)

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir_var.get())
        if d:
            self.outdir_var.set(d)

    def _log(self, msg, tag=None):
        self.log_text.configure(state="normal")
        if tag:
            self.log_text.insert("end", msg + "\n", tag)
        else:
            self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # ----- 解析 -----
    def _get_selected_device(self):
        idx = self.device_combo.current()
        if idx < 0:
            return None
        return self.dm_keys[idx]

    def _parse_input(self):
        text = self.text_input.get("1.0", "end")
        return parse_paste(text)

    def _on_preview(self):
        items = self._parse_input()
        self._clear_log()
        if not items:
            self._log("未解析到任何有效文件名", "err")
            return
        self._log(f"共解析到 {len(items)} 个文件:", "info")
        for ch, t1, t2, fn in items:
            self._log(f"  ch={ch}  {t1} → {t2}  [{fn}]")

    # ----- 下载 -----
    def _on_stop(self):
        if self.downloading:
            self._cancel_event.set()
            self._log("正在停止下载...", "err")

    def _on_start(self):
        if self.downloading:
            return

        dm_key = self._get_selected_device()
        if not dm_key:
            messagebox.showwarning("提示", "请选择超脑设备")
            return

        items = self._parse_input()
        if not items:
            messagebox.showwarning("提示", "未解析到任何有效文件名")
            return

        outdir = self.outdir_var.get().strip()
        if not outdir or not os.path.isdir(outdir):
            messagebox.showwarning("提示", "请选择有效的输出目录")
            return

        override_ch = self.channel_var.get().strip()

        # 确定 tracks 后缀
        custom_suffix = self.tracks_suffix_var.get().strip()
        if custom_suffix:
            tracks_suffix = custom_suffix
        else:
            tracks_suffix = RESOLUTION_MAP.get(self.resolution_var.get(), "01")

        max_workers = self.workers_var.get()

        self.downloading = True
        self._cancel_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress_var.set(0)
        self._clear_log()

        cfg = self.dm_map[dm_key]
        res_label = custom_suffix if custom_suffix else self.resolution_var.get()
        self._log(f"设备: Deepmind {dm_key} ({cfg['ip']})", "info")
        self._log(f"分辨率: {res_label} (tracks 后缀: {tracks_suffix})", "info")
        self._log(f"待下载: {len(items)} 个文件, 并发: {max_workers} 线程\n", "info")

        thread = threading.Thread(
            target=self._download_worker,
            args=(cfg, items, outdir, override_ch, tracks_suffix, max_workers),
            daemon=True,
        )
        thread.start()

    def _download_one(self, idx, total, cfg, ch, t1, t2, filename, outdir, tracks_suffix):
        """下载单个文件，返回 (filename, success, error_msg)。"""
        if self._cancel_event.is_set():
            return (filename, False, "已取消")

        ip = cfg["ip"]
        out_path = os.path.join(outdir, filename)
        self.root.after(0, self._log, f"[{idx}/{total}] 下载中: {filename} ...", "info")

        try:
            url = build_url(ip, cfg["scheme"], cfg["http_port"], cfg["rtsp_port"], ch, t1, t2, tracks_suffix)
            download_hik_mp4(
                url=url,
                username=cfg["username"],
                password=cfg["password"],
                out_file=out_path,
                timeout=300,
                verify_tls=cfg["verify_tls"],
                cancel_event=self._cancel_event,
            )
            self.root.after(0, self._log, f"  ✓ 完成: {filename}", "ok")
            return (filename, True, None)
        except InterruptedError:
            self.root.after(0, self._log, f"  ⊘ 取消: {filename}", "err")
            return (filename, False, "已取消")
        except Exception as e:
            self.root.after(0, self._log, f"  ✗ 失败: {filename} — {e}", "err")
            return (filename, False, str(e))

    def _download_worker(self, cfg, items, outdir, override_ch, tracks_suffix, max_workers):
        total = len(items)
        success = 0
        fail = 0
        cancelled_count = 0
        done_count = 0
        lock = threading.Lock()

        def update_progress():
            nonlocal done_count
            with lock:
                done_count += 1
                pct = done_count / total * 100
            self.root.after(0, self.progress_var.set, pct)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for i, (ch, t1, t2, filename) in enumerate(items, 1):
                if self._cancel_event.is_set():
                    break
                if override_ch:
                    ch = override_ch
                    filename = f"ch{ch}_{t1}_{t2}.mp4"
                future = executor.submit(
                    self._download_one, i, total, cfg, ch, t1, t2, filename, outdir, tracks_suffix
                )
                futures[future] = filename

            # 取消尚未开始的 futures
            if self._cancel_event.is_set():
                for f in futures:
                    f.cancel()

            for future in as_completed(futures):
                if future.cancelled():
                    cancelled_count += 1
                    update_progress()
                    continue
                _, ok, err_msg = future.result()
                if ok:
                    success += 1
                elif err_msg == "已取消":
                    cancelled_count += 1
                else:
                    fail += 1
                update_progress()

                if self._cancel_event.is_set():
                    for f in futures:
                        f.cancel()
                    break

        cancelled = self._cancel_event.is_set()
        tag = "err" if cancelled else "info"
        status = " (已手动停止)" if cancelled else ""
        summary = f"\n下载完成{status}: 成功 {success}, 失败 {fail}, 取消 {cancelled_count}, 共 {total}"
        self.root.after(0, self._log, summary, tag)
        self.root.after(0, self._finish_download)

    def _finish_download(self):
        self.downloading = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    BatchDownloadApp(root)
    root.mainloop()
