"""
COCO 标注查看工具 (GUI + FiftyOne)
"""

import sys
import os
import shutil
import subprocess
import tempfile
import threading
import traceback
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from datetime import datetime


REQUIRED_PACKAGES = [
    ("fiftyone", "fiftyone"),
    ("pycocotools", "pycocotools"),
]


def check_and_install(parent):
    """检查并安装 fiftyone 及依赖"""
    missing = []
    for module_name, pip_name in REQUIRED_PACKAGES:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        return True

    result = messagebox.askyesno(
        "依赖缺失",
        f"缺少以下依赖: {'、'.join(missing)}\n是否立即安装？\n(需要网络连接，约 1-2 分钟)"
    )
    if not result:
        return False

    parent.config(cursor="watch")
    parent.update()
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install"] + missing + ["-q"],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        parent.config(cursor="")
        messagebox.showinfo("安装完成", f"依赖安装成功: {', '.join(missing)}")
        return True
    except Exception as e:
        parent.config(cursor="")
        messagebox.showerror("安装失败", str(e))
        return False


class CocoViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("COCO 标注查看器")
        self.root.geometry("700x680")
        self.root.resizable(True, True)
        self.root.minsize(660, 600)
        self.root.configure(bg="#f0f0f0")

        self.session = None
        self.dataset = None
        self._thumb_dir = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # ── 标题 ──
        title = ttk.Label(
            self.root, text="COCO 标注数据集查看器",
            font=("Microsoft YaHei", 16, "bold"), background="#f0f0f0"
        )
        title.pack(pady=(16, 10))

        # ── 配置区域 ──
        frame = ttk.LabelFrame(self.root, text="路径配置", padding=10)
        frame.pack(fill="x", padx=20, pady=(0, 10))

        # 图片目录
        self._add_path_row(frame, "图片目录:", "images_path", row=0,
                           desc="存放 COCO 数据集的图片文件夹")
        # 标注文件
        self._add_path_row(frame, "标注文件:", "labels_path", row=1,
                           desc="COCO 格式的 JSON 标注文件 (.json)",
                           file_mode=True)

        # ── 高级选项 ──
        adv = ttk.LabelFrame(self.root, text="高级选项", padding=10)
        adv.pack(fill="x", padx=20, pady=(0, 10))

        ttk.Label(adv, text="数据集名称:", background="#f0f0f0").grid(
            row=0, column=0, sticky="w", padx=(0, 6))
        self.name_var = tk.StringVar(value="coco_preview")
        ttk.Entry(adv, textvariable=self.name_var, width=30).grid(row=0, column=1, sticky="w")

        ttk.Label(adv, text="Web 端口:", background="#f0f0f0").grid(
            row=0, column=2, sticky="w", padx=(14, 6))
        self.port_var = tk.IntVar(value=5151)
        ttk.Entry(adv, textvariable=self.port_var, width=8).grid(row=0, column=3, sticky="w")

        # ── 日志级别 ──
        ttk.Label(adv, text="日志级别:", background="#f0f0f0").grid(
            row=0, column=4, sticky="w", padx=(14, 6))
        self.log_level_var = tk.StringVar(value="详细")
        log_combo = ttk.Combobox(adv, textvariable=self.log_level_var,
                                  values=["简要", "详细", "调试"], width=6, state="readonly")
        log_combo.grid(row=0, column=5, sticky="w")

        # ── 内存控制 (第2行) ──
        ttk.Label(adv, text="样本上限:", background="#f0f0f0").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=(8, 0))
        self.max_samples_var = tk.StringVar(value="0")
        ttk.Entry(adv, textvariable=self.max_samples_var, width=8).grid(
            row=1, column=1, sticky="w", pady=(8, 0))

        ttk.Label(adv, text="(0=不限制，大内存机器可设 0)", foreground="gray",
                  background="#f0f0f0", font=("", 8)).grid(
            row=1, column=1, sticky="w", padx=(56, 0), pady=(8, 0))

        self.shuffle_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(adv, text="随机抽样", variable=self.shuffle_var).grid(
            row=1, column=2, sticky="w", padx=(0, 6), pady=(8, 0))

        self.thumb_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(adv, text="生成缩略图(慢,省内存)", variable=self.thumb_var).grid(
            row=1, column=2, sticky="w", padx=(80, 0), pady=(8, 0))

        ttk.Label(adv, text="网格缩放:", background="#f0f0f0").grid(
            row=1, column=3, sticky="w", padx=(0, 6), pady=(8, 0))
        self.grid_zoom_var = tk.IntVar(value=4)
        ttk.Scale(adv, from_=1, to=10, variable=self.grid_zoom_var, orient="horizontal",
                  length=80).grid(row=1, column=4, sticky="w", pady=(8, 0))
        ttk.Label(adv, textvariable=self.grid_zoom_var, width=2,
                  background="#f0f0f0").grid(row=1, column=4, sticky="w", padx=(82, 0), pady=(8, 0))

        # ── 操作按钮 ──
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=(6, 10))

        self.load_btn = ttk.Button(
            btn_frame, text="📥 加载数据集", command=self._load_dataset, width=18
        )
        self.load_btn.pack(side="left", padx=6)

        self.open_btn = ttk.Button(
            btn_frame, text="🌐 打开浏览器查看", command=self._open_browser, width=18,
            state="disabled"
        )
        self.open_btn.pack(side="left", padx=6)

        # ── 进度条 ──
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", padx=20, pady=(0, 6))

        # ── 日志输出 ──
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=4)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 6))

        # 日志工具栏
        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill="x", pady=(0, 4))

        self.copy_btn = ttk.Button(
            log_toolbar, text="📋 一键复制日志", command=self._copy_log, width=16
        )
        self.copy_btn.pack(side="left", padx=(0, 6))

        self.clear_btn = ttk.Button(
            log_toolbar, text="🗑 清空日志", command=self._clear_log, width=12
        )
        self.clear_btn.pack(side="left")

        # 复制状态提示
        self.copy_hint = ttk.Label(log_toolbar, text="", foreground="green", background="#f0f0f0")
        self.copy_hint.pack(side="left", padx=10)

        self.log_text = tk.Text(
            log_frame, height=10, wrap="word", font=("Consolas", 9),
            bg="#1e1e1e", fg="#d4d4d4", relief="flat", borderwidth=0,
            insertbackground="white"
        )
        self.log_text.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

        # 配置日志颜色 tag
        self.log_text.tag_configure("error", foreground="#f44747")
        self.log_text.tag_configure("warn", foreground="#e5c07b")
        self.log_text.tag_configure("success", foreground="#98c379")
        self.log_text.tag_configure("info", foreground="#61afef")
        self.log_text.tag_configure("debug", foreground="#808080")

    def _add_path_row(self, parent, label, attr, row, desc, file_mode=False):
        ttk.Label(parent, text=label, background="#f0f0f0").grid(
            row=row, column=0, sticky="e", padx=(0, 6), pady=6)

        var = tk.StringVar()
        setattr(self, attr + "_var", var)
        entry = ttk.Entry(parent, textvariable=var, width=52)
        entry.grid(row=row, column=1, sticky="we", pady=6)

        def browse():
            if file_mode:
                path = filedialog.askopenfilename(
                    title="选择 COCO 标注文件",
                    filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
                )
            else:
                path = filedialog.askdirectory(title="选择图片目录")
            if path:
                var.set(path)

        ttk.Button(parent, text="浏览...", command=browse, width=7).grid(
            row=row, column=2, padx=(4, 0), pady=6)

    def _now(self):
        return datetime.now().strftime("%H:%M:%S")

    def _log(self, msg, tag=None):
        timestamp = self._now()
        line = f"[{timestamp}] {msg}\n"
        if tag:
            self.log_text.insert("end", line, tag)
        else:
            self.log_text.insert("end", line)
        self.log_text.see("end")
        self.root.update_idletasks()

    def _debug(self, msg):
        if self.log_level_var.get() in ("调试",):
            self._log(f"[DEBUG] {msg}", "debug")

    def _info(self, msg):
        self._log(f"[INFO] {msg}", "info")

    def _warn(self, msg):
        self._log(f"[WARN] {msg}", "warn")

    def _error(self, msg):
        self._log(f"[ERROR] {msg}", "error")

    def _success(self, msg):
        self._log(f"[SUCCESS] {msg}", "success")

    def _copy_log(self):
        content = self.log_text.get("1.0", "end-1c")
        if not content.strip():
            self.copy_hint.config(text="日志为空，无需复制", foreground="gray")
            self.root.after(2000, lambda: self.copy_hint.config(text=""))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.copy_hint.config(text="✅ 已复制到剪贴板", foreground="green")
        self._debug("日志已复制到剪贴板")
        self.root.after(2000, lambda: self.copy_hint.config(text=""))

    def _clear_log(self):
        self.log_text.delete("1.0", "end")
        self._log("日志已清空")

    def _make_gbk_safe_copy(self, original_path, coco_data):
        """创建 GBK 安全的 JSON 临时副本，解决 eta 库在 Windows 上的编码问题"""
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="coco_safe_",
            delete=False, encoding="utf-8"
        )
        try:
            json.dump(coco_data, tmp, ensure_ascii=True)
            tmp.close()
            self._debug(f"已创建编码安全副本: {tmp.name}")
            return Path(tmp.name)
        except Exception:
            try:
                Path(tmp.name).unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def _show_error_dialog(self, title, summary, detail):
        """显示可滚动的错误窗口（避免弹窗超出屏幕，支持复制）"""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.geometry("640x420")
        dlg.minsize(400, 280)
        dlg.transient(self.root)
        dlg.grab_set()

        # 摘要
        ttk.Label(dlg, text=summary, wraplength=600,
                  font=("Microsoft YaHei", 10, "bold"), background="#f0f0f0").pack(
            padx=16, pady=(16, 6), anchor="w")

        # 可滚动详情
        ttk.Label(dlg, text="详细信息（可选中后 Ctrl+C 复制）:",
                  background="#f0f0f0").pack(padx=16, anchor="w")

        frame = ttk.Frame(dlg)
        frame.pack(fill="both", expand=True, padx=16, pady=(4, 8))

        detail_text = tk.Text(frame, wrap="none", font=("Consolas", 9),
                              bg="#1e1e1e", fg="#d4d4d4")
        detail_text.pack(side="left", fill="both", expand=True)

        detail_scroll_y = ttk.Scrollbar(frame, command=detail_text.yview)
        detail_scroll_y.pack(side="right", fill="y")
        detail_scroll_x = ttk.Scrollbar(dlg, orient="horizontal", command=detail_text.xview)
        detail_scroll_x.pack(fill="x", padx=16)
        detail_text.config(yscrollcommand=detail_scroll_y.set, xscrollcommand=detail_scroll_x.set)
        detail_text.insert("1.0", detail)

        # 按钮栏
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=(0, 12))

        def copy_detail():
            dlg.clipboard_clear()
            dlg.clipboard_append(f"{summary}\n\n{detail}")
            copy_btn.config(text="✅ 已复制")

        copy_btn = ttk.Button(btn_frame, text="📋 复制错误信息", command=copy_detail)
        copy_btn.pack(side="left", padx=6)

        ttk.Button(btn_frame, text="关闭", command=dlg.destroy).pack(side="left", padx=6)

    def _set_loading(self, loading):
        if loading:
            self.progress.start(10)
            self.load_btn.config(state="disabled")
            self.open_btn.config(state="disabled")
        else:
            self.progress.stop()
            self.load_btn.config(state="normal")

    def _load_dataset(self):
        images = self.images_path_var.get().strip()
        labels = self.labels_path_var.get().strip()

        if not images:
            messagebox.showwarning("路径缺失", "请选择图片目录")
            return
        if not labels:
            messagebox.showwarning("路径缺失", "请选择 COCO 标注文件")
            return

        images_path = Path(images)
        labels_path = Path(labels)

        self._debug(f"图片目录原始输入: '{images}'")
        self._debug(f"标注文件原始输入: '{labels}'")
        self._debug(f"图片目录解析路径: {images_path}")
        self._debug(f"标注文件解析路径: {labels_path}")

        if not images_path.exists():
            self._error(f"图片目录不存在: {images_path.resolve()}")
            return
        if not labels_path.exists():
            self._error(f"标注文件不存在: {labels_path.resolve()}")
            return

        # 打印路径信息
        self._info(f"图片目录: {images_path.resolve()}")
        self._info(f"标注文件: {labels_path.resolve()}")

        # 标注文件基本信息
        try:
            stat = labels_path.stat()
            self._debug(f"标注文件大小: {stat.st_size:,} 字节")
            self._debug(f"标注文件修改时间: {datetime.fromtimestamp(stat.st_mtime)}")
        except Exception:
            self._debug("无法读取标注文件信息")

        # 尝试读取 JSON 快速校验
        try:
            with open(labels_path, "r", encoding="utf-8") as f:
                coco_data = json.load(f)
            self._debug("JSON 解析成功")
            self._info(f"JSON 顶层字段: {list(coco_data.keys())}")

            if "images" in coco_data:
                self._info(f"图片条目数: {len(coco_data['images'])}")
                if coco_data["images"]:
                    first_img = coco_data["images"][0]
                    self._debug(f"第一条图片信息: {first_img}")
            if "annotations" in coco_data:
                self._info(f"标注条目数: {len(coco_data['annotations'])}")
            if "categories" in coco_data:
                cat_names = [c.get("name", "?") for c in coco_data["categories"]]
                self._info(f"类别列表 ({len(coco_data['categories'])}): {cat_names}")
        except json.JSONDecodeError as e:
            self._error(f"JSON 解析失败 (第 {e.lineno} 行, 第 {e.colno} 列): {e.msg}")
            self._error(f"请检查文件格式是否正确 —— 常见原因: 中文逗号、多余逗号、编码问题")
            self._debug(f"完整异常:\n{traceback.format_exc()}")
            return
        except UnicodeDecodeError as e:
            self._error(f"文件编码读取失败: {e}")
            self._debug(f"完整异常:\n{traceback.format_exc()}")
            return
        except Exception as e:
            self._error(f"读取标注文件失败: {e}")
            self._debug(f"完整异常:\n{traceback.format_exc()}")
            return

        # 检查图片目录
        try:
            img_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}
            img_files = [f for f in images_path.iterdir()
                         if f.is_file() and f.suffix.lower() in img_extensions]
            self._info(f"图片目录下找到 {len(img_files)} 个图片文件")
            if len(img_files) <= 10:
                self._debug(f"图片文件列表: {[f.name for f in img_files]}")
        except Exception as e:
            self._error(f"扫描图片目录失败: {e}")
            self._debug(f"完整异常:\n{traceback.format_exc()}")
            return

        if not check_and_install(self.root):
            return

        # 存下解析后的数据，供 _do_load 编码修复用
        self._coco_data = coco_data

        # 读取内存控制参数
        try:
            max_samples = int(self.max_samples_var.get())
            if max_samples <= 0:
                max_samples = None
        except ValueError:
            max_samples = None
        shuffle = self.shuffle_var.get()
        thumb_enabled = self.thumb_var.get()

        self._set_loading(True)
        self._info("开始后台加载数据集...")
        threading.Thread(
            target=self._do_load,
            args=(images_path, labels_path, max_samples, shuffle, thumb_enabled),
            daemon=True
        ).start()

    def _do_load(self, images_path, labels_path, max_samples, shuffle, thumb_enabled):
        safe_copy = None
        try:
            import fiftyone as fo

            name = self.name_var.get().strip() or "coco_preview"

            self._debug(f"FiftyOne 版本: {fo.__version__}")
            self._debug(f"数据集名称: {name}")
            self._debug(f"max_samples: {max_samples}, shuffle: {shuffle}")

            existing = fo.list_datasets()
            self._debug(f"现有数据集列表: {existing}")

            if name in fo.list_datasets():
                self._warn(f"已存在同名数据集 [{name}]，正在覆盖...")
                fo.delete_dataset(name)
                self._debug(f"已删除旧数据集 [{name}]")

            # 创建 GBK 安全副本（解决 eta 库在 Windows 上的编码问题）
            actual_labels_path = labels_path
            coco_data = getattr(self, "_coco_data", None)
            if coco_data is not None:
                safe_copy = self._make_gbk_safe_copy(labels_path, coco_data)
                self._debug("将使用编码安全副本替代原始标注文件")
                self._info(f"检测到包含中文等字符，已自动处理编码兼容（临时文件: {safe_copy.name}）")
                actual_labels_path = safe_copy

            self._info("正在通过 FiftyOne 解析 COCO 数据集（大文件可能较慢）...")
            self._info("（此阶段需校验所有图片文件，1187 张约需 30-120 秒，请耐心等待）")

            # 构建 kwargs
            from_dir_kwargs = dict(
                dataset_type=fo.types.COCODetectionDataset,
                data_path=str(images_path),
                labels_path=str(actual_labels_path),
                name=name,
            )
            if max_samples is not None:
                from_dir_kwargs["max_samples"] = max_samples
                self._info(f"样本上限: {max_samples}")
            if shuffle:
                from_dir_kwargs["shuffle"] = True
                from_dir_kwargs["seed"] = 42
                self._info("已启用随机抽样 (seed=42)")

            import time
            t0 = time.time()
            self.dataset = fo.Dataset.from_dir(**from_dir_kwargs)
            elapsed = time.time() - t0
            self._info(f"数据集解析完成（耗时 {elapsed:.1f} 秒）")

            self._debug(f"数据集对象创建完成，class={type(self.dataset).__name__}")

            self._success("数据集加载完成！")
            self._info(f"图片总数: {len(self.dataset)}")

            # 统计标注
            label_fields = self.dataset.get_field_schema(embedded_doc_type=fo.Detections)
            self._debug(f"检测标注字段: {label_fields}")

            if label_fields:
                field = list(label_fields.keys())[0]
                classes = self.dataset.distinct(f"{field}.detections.label")
                self._info(f"标注类别 ({len(classes)}): {classes}")

                if self.log_level_var.get() in ("详细", "调试"):
                    for cls in sorted(classes):
                        count = self.dataset.count(f"{field}.detections.label == '{cls}'")
                        self._debug(f"  类别 '{cls}': {count} 个实例")
            else:
                self._warn("未检测到任何标注字段")

            self._debug(f"数据集媒体类型: {self.dataset.media_type}")
            try:
                sample = self.dataset.first()
                self._debug(f"样本字段: {list(sample.field_names)}")
            except Exception:
                self._debug("无法获取样本字段信息")

            # ── 生成缩略图（可选，大幅降低 App 内存）──
            if thumb_enabled:
                self._info(f"正在生成缩略图（共 {len(self.dataset)} 张，请耐心等待...）")
                try:
                    import fiftyone.utils.image as foui
                    import time
                    t0 = time.time()
                    thumb_dir = tempfile.mkdtemp(prefix="coco_thumbs_")
                    self._debug(f"缩略图目录: {thumb_dir}")
                    foui.transform_images(
                        self.dataset,
                        size=(-1, 160),
                        output_field="thumbnail_path",
                        output_dir=thumb_dir,
                        num_workers=min(8, os.cpu_count() or 4),
                        progress=True,
                    )
                    elapsed = time.time() - t0
                    self._thumb_dir = thumb_dir

                    self.dataset.app_config.media_fields = ["filepath", "thumbnail_path"]
                    self.dataset.app_config.grid_media_field = "thumbnail_path"
                    self.dataset.app_config.modal_media_field = "filepath"
                    self.dataset.save()
                    self._success(f"缩略图生成完成（耗时 {elapsed:.1f} 秒），网格视图将使用低分辨率预览")
                except Exception as e:
                    self._warn(f"缩略图生成失败（将直接使用原图）: {e}")
                    self._thumb_dir = None
            else:
                self._info("已跳过缩略图生成（可在高级选项中启用）")

            self.root.after(0, self._on_loaded)

        except Exception as e:
            err_summary = str(e)
            err_detail = traceback.format_exc()
            self._error(err_summary)
            self._debug(f"完整异常栈:\n{err_detail}")

            if "UnicodeDecodeError" in err_detail or "gbk" in err_detail.lower():
                self._warn("检测到编码问题：JSON 文件可能包含 GBK 无法解码的 UTF-8 字符")
                self._info("可以尝试: 用记事本打开 JSON → 另存为 → 编码选 UTF-8")

            if "Memory" in err_summary or "memory" in err_summary.lower():
                self._warn("内存不足！建议：设置样本上限（如 200）或关闭其他程序后重试")
            if "DatabaseService" in err_detail or "failed to bind" in err_detail:
                self._warn("MongoDB 端口被占用，正在尝试清理...")
                try:
                    subprocess.run(["taskkill", "/f", "/im", "mongod.exe"],
                                   capture_output=True, timeout=10)
                    self._info("已清理残留进程，请重新点击「加载数据集」")
                except Exception:
                    self._info("请手动运行: taskkill /f /im mongod.exe 后重试")

            self.root.after(0, lambda msg=err_summary, detail=err_detail: self._on_error(msg, detail))
        finally:
            if safe_copy is not None:
                try:
                    safe_copy.unlink(missing_ok=True)
                    self._debug(f"已清理临时文件: {safe_copy.name}")
                except Exception:
                    pass

    def _on_close(self):
        """关闭窗口时清理资源"""
        self._debug("正在清理资源...")
        if self.dataset is not None:
            try:
                name = self.dataset.name
                self.dataset.delete()
                self._debug(f"已删除数据集 [{name}]")
            except Exception:
                pass
        if getattr(self, "_thumb_dir", None):
            try:
                shutil.rmtree(self._thumb_dir, ignore_errors=True)
                self._debug("已清理缩略图目录")
            except Exception:
                pass
        self.root.destroy()

    def _on_loaded(self):
        self._coco_data = None  # 释放 JSON 数据内存
        self._set_loading(False)
        self.open_btn.config(state="normal")
        self._info("数据集已就绪，可以打开浏览器查看标注")

    def _on_error(self, msg, detail):
        self._set_loading(False)
        self._error(f"加载失败，详情见弹窗")
        self._show_error_dialog("加载失败", msg, detail)

    def _open_browser(self):
        if self.dataset is None:
            messagebox.showwarning("未加载", "请先加载数据集")
            return

        port = self.port_var.get() or 5151

        self._info(f"准备启动 FiftyOne 服务...")
        threading.Thread(target=self._do_launch, args=(port,), daemon=True).start()

    def _do_launch(self, port):
        try:
            import fiftyone as fo
            from fiftyone.core.config import AppConfig

            self._info(f"启动 FiftyOne 服务，端口: {port}，浏览器将自动打开...")

            grid_zoom = self.grid_zoom_var.get()
            config = AppConfig({"grid_zoom": grid_zoom})
            self._debug(f"App 网格缩放级别: {grid_zoom}")

            session = fo.launch_app(self.dataset, port=port, config=config)
            self.session = session

            self._debug(f"FiftyOne session 类型: {type(session).__name__}")
            self._success("浏览器已打开，可在网页中交互式浏览标注")
            self._info("关闭浏览器标签页后，按 Ctrl+C 或关闭本窗口退出")

            session.wait()
        except Exception as e:
            err_detail = traceback.format_exc()
            self._error(f"启动 FiftyOne 失败: {e}")
            self._debug(f"完整异常栈:\n{err_detail}")


def main():
    root = tk.Tk()
    app = CocoViewerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
