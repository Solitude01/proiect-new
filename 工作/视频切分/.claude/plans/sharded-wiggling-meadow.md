:
修复输出目录不生效问题

## 问题分析

用户反馈输出目录设置后不生效，图片实际输出到了视频文件所在目录。

### 根本原因

代码中 `extract_frames` 函数使用 `os.path.join(output_dir, filename)` 构建输出路径。如果 `output_dir` 为空字符串或无效路径，`os.path.join` 会返回相对路径，导致文件保存到当前工作目录（即视频文件所在目录）。

### 问题点

1. `validate_inputs` 虽然检查了输出目录，但没有强制要求用户必须选择输出目录
2. `extraction_worker` 中获取 `output_path` 时可能返回空字符串
3. 临时文件和最终文件都使用 `os.path.join`，当 `output_dir` 为空时会出问题

### 修复方案

**方案A：强制要求选择输出目录（推荐）**
- 如果用户没有选择输出目录，使用视频文件所在目录作为默认输出目录
- 在界面上明确显示输出目录，让用户知道文件会输出到哪里

**方案B：自动设置默认输出目录**
- 当用户选择视频文件时，自动将输出目录设置为视频文件所在目录
- 用户仍可以手动更改

采用方案B，更用户友好：

```python
def select_video(self):
    """选择视频文件，自动设置输出目录为视频所在文件夹"""
    path = filedialog.askopenfilename(...)
    if path:
        self.video_path.set(path)
        # 自动设置输出目录为视频所在目录
        video_dir = os.path.dirname(path)
        self.output_path.set(video_dir)
        ...
```

### 额外改进

1. 在视频选择后自动设置输出目录
2. 显示完整的输出路径，让用户清楚知道文件会保存到哪里
3. 添加调试日志，方便排查路径问题

## 实施步骤

修改 `1.py`：
1. 修改 `select_video` 方法，自动设置输出目录为视频所在目录
2. 修改 `select_output` 方法，允许用户覆盖默认目录
3. 确保 `extract_frames` 正确处理路径

## 验证

1. 选择视频文件，观察输出目录是否自动设置为视频所在目录
2. 运行提取，确认文件输出到正确位置
3. 手动更改输出目录，确认可以覆盖默认值
