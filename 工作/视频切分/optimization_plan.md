# video_frame_extractor.py 优化计划

## 目标文件
- `D:\proiect\工作\视频切分\video_frame_extractor.py`

## 调查范围
对「单视频切分」「单目录切分」「多目录并发切分」三个模式进行全面审查，整理出 12 项待修复问题（含 5 项严重级、7 项中高优先级）。

---

## 严重级问题（Critical / High）

### 1. 多目录模式：`process_ui_queue` 窃取消息导致假死
- **位置**：`process_ui_queue`（约第 2746 行）
- **现象**：主线程每 50ms 用 `get_nowait()` 清空 `ui_queue` 并直接丢弃，导致后台监控线程 `_monitor_multi_progress` 收不到完成/进度消息，表现为进度卡死或 completion 数不对。
- **修复**：删除 `process_ui_queue` 中的 `while True: get_nowait()` 循环，让监控线程独占读取队列。

### 2. 多目录模式：线程池泄漏
- **位置**：`start_multi_directory`（约 2521 行）、`_on_multi_complete`（约 2621 行）
- **现象**：每次开始新任务都会新建 `BatchProcessor` / `ThreadPoolExecutor`，旧线程池未 `shutdown`，完成时也未停止。
- **修复**：
  - `start_multi_directory` 在重新赋值前调用 `self.processor.stop()`。
  - `_on_multi_complete` 结束前调用 `self.processor.stop()`。

### 3. 单目录模式：`stop_event` 未被重置，取消后无法再次启动
- **位置**：`start_single_directory`（约 2212 行）
- **现象**：只要曾在其他模式点过取消（`stop_event.set()`），再进入单目录模式点击「开始切分」会立刻中断，因为该函数没有 `self.stop_event.clear()`。
- **修复**：在函数开头添加 `self.stop_event.clear()`。

### 4. 单视频模式：未捕获异常导致 UI 永久锁死
- **位置**：`_process_single_video`（约 2173 行）
- **现象**：如果 `extract_frames` 抛出异常（权限不足、路径非法等），工作线程直接崩溃，`_on_process_complete` 不会被调用，「开始切分」按钮永远灰显。
- **修复**：用 `try/except` 包裹函数主体，在异常时强制调用 `_on_process_complete(False, str(e))` 释放 UI。

### 5. 单目录模式：重新扫描目录导致索引错位
- **位置**：`start_single_directory`（约 2228 行）
- **现象**：点击开始后再次调用 `extractor.scan_videos(directory)` 生成视频列表，而不是使用 UI 上已经排列好的 `self.single_dir_videos`。如果期间文件被增删，每视频的「切分张数」「子目录名」会按错位索引应用到错误的文件上。
- **修复**：直接取 `[v['path'] for v in self.single_dir_videos]` 作为待处理列表，不再二次扫描。

---

## 中高优先级问题（Medium）

### 6. 单目录模式：状态标签闭包 Bug
- **位置**：`_process_directory_separate`（约 2295 行）
- **现象**：
  ```python
  self.root.after(0, lambda v=video_name: self.status_label.configure(
      text=f"处理中... ({idx+1}/{total_videos}) {v}"
  ))
  ```
  `idx` 在 f-string 中按引用捕获，回调执行时已经是循环最终值，导致所有视频都显示最后一个序号。
- **修复**：`lambda v=video_name, i=idx: ... {i+1}/{total_videos}`。

### 7. 多目录模式：「删除选中」只删第一个
- **位置**：`remove_selected_dir`（约 2055 行）
- **现象**：Treeview 默认支持多选，但代码只处理 `selected[0]`。
- **修复**：逆序遍历所有选中的 item，依次 `pop` + `delete`。

### 8. 视频预览窗口：空双击崩溃
- **位置**：`show_video_preview`（约 2793 行）
- **现象**：`tree.selection()[0]` 在双击空白处或表头时产生 `IndexError`。
- **修复**：先判断 `if tree.selection():` 再取 `[0]`。

### 9. 单视频模式：完成时打开错误或不存在目录
- **位置**：`_on_process_complete`（约 2206 行）
- **现象**：`os.startfile` 打开的是顶层输出目录，而非实际写入帧的子目录；且缺少存在性检查，目录被删除时会崩溃。
- **修复**：将实际写入路径 `video_output` 传给完成回调，并先用 `os.path.exists()` 检查，不存在则 `os.makedirs(..., exist_ok=True)` 后打开。

### 10. 单视频模式：完成回调可能操作已销毁控件
- **位置**：`_on_process_complete`（约 2201 行）
- **现象**：若用户在处理中切换模式，`self.start_btn` 已被 `clear_content` 销毁，`.configure()` 会抛出 `TclError`。
- **修复**：调用前检查 `self.start_btn.winfo_exists()`。

### 11. 单目录模式：重复进入导致 trace 累加
- **位置**：`create_single_directory_ui`（约 1044 行）
- **现象**：每次切到单目录模式都会 `trace_add`，旧 trace 没 `trace_remove`，导致目录变化时 `update_video_list` 被触发多次。
- **修复**：用实例变量（如 `self._single_dir_path_trace`、`self._single_dir_uniform_trace`）保存 trace ID，添加新 trace 前先移除旧的。

### 12. 单目录模式：「单独设置」模式下快捷按钮未被禁用
- **位置**：`on_single_dir_mode_change`（约 1749 行）
- **现象**：切换为「单独设置」时，代码只禁用 `uniform_settings_frame` 的直接子控件。快捷按钮 [50,100,150,200] 放在嵌套的 `quick_frame` 里，未被禁用，仍可点击并偷偷修改统一张数。
- **修复**：递归禁用/启用 `uniform_settings_frame` 内所有子控件（或直接 disable `quick_frame` 所在的容器）。

---

## 建议修改顺序

1. **先修严重级**：消息队列窃取、线程池泄漏、`stop_event` 未清、异常未捕获、索引错位。
2. **再修 UI / 体验**：闭包、删除多选、空双击、`os.startfile`、控件存在性检查。
3. **最后修状态一致性**：trace 累加、快捷按钮禁用。

---

## 验证清单

1. **多目录模式**：添加 2 个以上目录并开始切分，确认进度条正常走到 100% 且不卡死。
2. **单目录取消-重启**：开始切分后点取消，再次点击开始，确认不会立即中断。
3. **单视频异常保护**：给输出目录设只读或传非法路径，确认报错后按钮能恢复可点。
4. **模式切换测试**：在单视频 / 单目录之间来回切换 3-4 次再选目录，确认视频列表只刷新一次。
5. **单目录「单独设置」**：切换到单独设置模式，确认 [50] [100] 等快捷按钮变灰不可点。
