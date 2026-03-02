# Windows Server 桌面工具开发踩坑记录

> 基于「坤云平台定时清理 GUI 管理工具」开发经验整理，Python + tkinter + PyInstaller 技术栈。

---

## 1. 编码问题（最大的坑）

### 问题现象

Python subprocess 调用 PowerShell 脚本，GUI 日志显示全是 `����ģʽ` 乱码。

### 根因

中文 Windows Server 的控制台默认编码是 **GBK (cp936)**，不是 UTF-8。即使在 PowerShell 里设置了 `[Console]::OutputEncoding = UTF8`，在 `CREATE_NO_WINDOW` 无窗口模式下也**不生效**，输出仍然是 GBK。

### 踩过的弯路

| 尝试 | 结果 |
|------|------|
| `subprocess.Popen(encoding="utf-8")` | 乱码，GBK 字节按 UTF-8 解码失败 |
| `-Command` 前缀设置 `[Console]::OutputEncoding = UTF8` | 无窗口模式下无效，仍乱码 |
| `chcp 65001` | 这是 cmd 命令，PowerShell 里不适用 |

### 最终方案：读字节 + 自动检测

```python
def _decode_line(raw_line):
    """优先 UTF-8，失败回退 GBK"""
    try:
        return raw_line.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        pass
    try:
        return raw_line.decode("gbk")
    except (UnicodeDecodeError, AttributeError):
        pass
    return raw_line.decode("utf-8", errors="replace")

# subprocess 不指定 encoding，读原始字节
proc = subprocess.Popen(
    args,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    # 注意：不传 encoding 参数
    creationflags=subprocess.CREATE_NO_WINDOW,
)
for raw_line in proc.stdout:
    line = _decode_line(raw_line).rstrip("\n\r")
```

### 另外：config.json 的 BOM 问题

Windows 上很多编辑器（记事本、VS）保存 UTF-8 文件会带 BOM 头（`EF BB BF`），Python 的 `json.load` 用 `encoding="utf-8"` 会报错：

```
json.decoder.JSONDecodeError: Unexpected UTF-8 BOM
```

**解决：** 读 JSON 统一用 `encoding="utf-8-sig"`，自动处理有无 BOM 两种情况。

---

## 2. subprocess 调用 PowerShell

### `-File` vs `-Command`

| 方式 | 特点 |
|------|------|
| `-File script.ps1` | 路径含中文时容易出问题，参数传递更严格 |
| `-Command '& "script.ps1"'` | 更灵活，可以在脚本前插入初始化命令 |

推荐用 `-Command`，即使编码设置在无窗口下不生效，至少路径传递更可靠：

```python
args = [
    "powershell.exe",
    "-ExecutionPolicy", "Bypass",
    "-NoProfile",
    "-Command",
    f'& "{script_path}" -ConfigPath "{config_path}"',
]
```

### 隐藏窗口

```python
creationflags=subprocess.CREATE_NO_WINDOW
```

不加这个，每次执行 PowerShell 都会闪一个黑色窗口。

### 返回码

PowerShell 脚本失败时返回码可能是很大的数字（如 `4294770688` = `0xFFFF0000`），不要只判断 `== 0`。

---

## 3. tkinter 实时日志显示

### 核心模式：Thread + Queue + after 轮询

GUI 线程不能阻塞，所以 subprocess 必须在子线程运行，通过 Queue 传递数据：

```
子线程: subprocess 逐行读取 → queue.put(line)
主线程: root.after(100ms) → queue.get_nowait() → Text.insert()
```

### 关键细节

- `Text` 控件必须 `state=DISABLED` 防止用户编辑，插入前临时改为 `NORMAL`
- 插入后调用 `text.see(tk.END)` 自动滚动到底部
- 用 `None` 作为 sentinel 值标记子线程结束

---

## 4. PyInstaller 打包

### 路径解析

打包后 `__file__` 指向临时解压目录 `_MEIPASS`，不是 exe 所在目录：

```python
def get_project_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)  # exe 所在目录
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```

### `--add-data` 的坑

`--add-data "config.json;."` 会把文件打包进 exe 内部（解压到 `_MEIPASS`），但如果这些文件需要用户编辑或被外部程序读取（如 PowerShell 脚本），应该放在 exe 旁边，代码里用 `sys.executable` 定位，而不是从 `_MEIPASS` 读。

### 在干净虚拟环境中打包

避免把开发环境的多余依赖打进去，减小体积：

```bat
python -m venv .build_venv
.build_venv\Scripts\pip install pyinstaller
.build_venv\Scripts\pyinstaller --onefile --windowed gui/main.py
rmdir /s /q .build_venv
```

### 代理导致 pip 失败

如果开发机开了代理，venv 里的 pip 可能继承代理设置导致 `Failed to parse` 错误。解决：

```bash
# bash 环境
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
pip install pyinstaller

# 或 cmd
set HTTP_PROXY=
set HTTPS_PROXY=
pip install pyinstaller
```

---

## 5. UAC 提权

GUI 本身不需要管理员权限，只在安装/卸载计划任务时按需提权：

```python
import ctypes

ret = ctypes.windll.shell32.ShellExecuteW(
    None,                    # 父窗口
    "runas",                 # 动词：请求提权
    "powershell.exe",        # 程序
    f'-File "{script}"',     # 参数
    None,                    # 工作目录
    1                        # SW_SHOWNORMAL
)
# 返回值 > 32 表示成功，≤ 32 表示失败（用户拒绝/其他错误）
```

不要让整个 GUI 以管理员运行，否则拖拽文件等功能会受 UIPI 限制。

---

## 6. 项目结构建议

```
项目根目录/
├── 核心脚本 (.ps1/.bat)      # 实际业务逻辑
├── config.json               # 外部可编辑配置
├── gui/
│   ├── main.py               # 入口 + 主窗口
│   ├── tab_xxx.py            # 每个功能一个标签页模块
│   ├── utils.py              # subprocess、配置读写、路径
│   └── widgets.py            # 复用组件
└── build.bat                 # 一键打包
```

**核心原则：** GUI 只做展示和调度，通过 subprocess 调用现有脚本，不重复实现业务逻辑。这样脚本可以独立在命令行跑，GUI 只是加了一层壳。

---

## 速查清单

开发 Windows Server 桌面工具前过一遍：

- [ ] subprocess 读输出用**原始字节 + 自动解码**（UTF-8 → GBK fallback）
- [ ] 读 JSON 文件用 `utf-8-sig` 编码
- [ ] PowerShell 调用用 `-Command` 而非 `-File`
- [ ] subprocess 加 `CREATE_NO_WINDOW` 避免弹窗
- [ ] PyInstaller 路径用 `sys.executable` 而非 `__file__`
- [ ] 需要用户编辑的文件放 exe 旁边，不要打包进 exe
- [ ] 在干净 venv 中打包
- [ ] UAC 提权用 `ShellExecuteW` 按需提权，不要整体提权
- [ ] 长任务放子线程，Queue + after 轮询更新 GUI
