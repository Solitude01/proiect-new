# AGENTS.md - 项目开发指南

> 本文档面向 AI 编程助手，描述项目结构、技术栈和开发规范。
> 项目语言：中文（注释和文档主要使用中文）

## 项目概述

本项目是一个**AI/安防工具集仓库**，包含多个独立的 Python 工具和 Web 应用程序，主要用于：

- **数据格式转换**：Labelme ↔ COCO ↔ 海康威视标注格式转换
- **安防设备管理**：海康威视 NVR（超脑）设备批量配置工具
- **视频流处理**：VLC 播放列表生成、视频格式转换
- **AI 项目管理**：可视化仪表盘展示已上线 AI 项目
- **自动化运维**：定时清理、文件同步等 Windows 平台运维脚本

### 项目组织结构

```
d:\proiect/
├── 工作/                 # 进行中/活跃的项目
│   ├── 超脑批量修改264/    # NVR 编码格式批量修改工具
│   ├── 超脑获取回放/       # 视频回放下载工具
│   ├── 已上线运行的AI项目明细/  # Web 可视化仪表盘
│   ├── AI能力画像文档/     # Excel 数据处理工具
│   ├── 辅助监控系统/       # 事件监控下载工具
│   └── ...
├── 已完结/               # 已完成/归档的项目
│   ├── labelme2coco/     # Labelme 转 COCO 格式
│   ├── coco_validator_gui/   # COCO 数据集验证工具
│   ├── labelme to hik格式转换/  # 标注格式转换工具
│   ├── vlc播放列表/       # M3U 播放列表生成器
│   ├── 坤云平台定时处理/    # Windows 定时清理服务
│   └── ...
├── 创意/                 # 实验性/原型项目
├── 垃圾桶/               # 废弃/待清理的项目
├── auto-py-to-exe/       # Python 打包工具（第三方）
├── .venv/                # Python 虚拟环境
└── output/               # 打包输出目录
```

## 技术栈

### 核心语言与运行时

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.14+ | 主要开发语言 |
| PowerShell | 5.1+ | Windows 自动化脚本 |
| .NET SDK | 8.0.413 | 备用（C# 项目） |
| Node.js | - | 可选（n8n 工作流） |

### Python 依赖环境

```
虚拟环境位置: d:\proiect\.venv\
Python 解释器: Python 3.14.0
激活方式: .venv\Scripts\activate.bat (Windows)
```

**常用依赖包**：
- `tkinter` - GUI 界面（Python 标准库）
- `requests` - HTTP 请求（海康 ISAPI 接口）
- `numpy`, `pillow`, `tqdm` - 图像处理与进度显示
- `openpyxl` - Excel 文件处理
- `pyinstaller` - 打包为可执行文件
- `eel` - Python-JavaScript 混合桌面应用

### 开发工具

- **IDE**: VS Code（配置在 `.vscode/`）
- **版本控制**: Git
- **打包工具**: auto-py-to-exe / PyInstaller

## 模块架构

### 1. GUI 工具类模块

典型结构（以 `labelme2coco` 为例）：

```
项目目录/
├── main.py                    # 程序入口
├── <功能>_gui.py              # GUI 主程序
├── *_core.py                  # 核心逻辑（与 UI 分离）
├── requirements.txt           # 依赖列表
├── README.md                  # 使用说明（中文）
├── config.json               # 配置文件（如有）
└── icon.ico                  # 程序图标
```

**设计模式**：
- 核心逻辑与 GUI 分离（`converter_core.py` + `gui_components.py`）
- 使用 `tkinter` 或 `tkinter.ttk` 构建界面
- 多线程处理耗时操作（`threading` 模块）
- 日志输出到 GUI 文本框

### 2. Web 应用模块

以 `已上线运行的AI项目明细` 为例：

```
├── index.html / business.html / planet.html  # 页面
├── *.js                      # JavaScript 逻辑（按页面分离）
├── styles.css                # 样式表
├── app.js                    # 后端 API（Node.js）
├── import_excel.py           # Excel 数据导入脚本
└── CCC.xlsx                  # 数据源（大型 Excel）
```

### 3. 自动化脚本类

以 `坤云平台定时处理` 为例：

```
├── cleanup.ps1               # 主清理脚本
├── install.ps1               # 安装/卸载定时任务
├── config.json               # 清理规则配置
└── README.md                 # 运维文档
```

## 开发规范

### 代码风格

1. **语言**：代码注释和文档字符串使用**中文**
2. **编码**：文件保存为 UTF-8（处理中文路径和标签）
3. **GUI 框架**：优先使用 `tkinter`，复杂界面使用 `ttk` 主题
4. **日志**：打印到控制台同时输出到 GUI 文本框

### 文件命名规范

```
# Python 文件
<功能>_gui.py          # GUI 版本
<功能>_core.py         # 核心逻辑
<功能>.py              # 命令行版本
<功能>_<版本>.py        # 迭代版本（如 excel-2-json-txt_v2.py）

# 配置和数据
config.json           # 配置文件
*.json               # 设备列表、API 配置等
requirements.txt     # Python 依赖

# 文档
README.md            # 项目说明（必须包含）
需求.md               # 需求文档
使用说明.md            # 详细使用说明
```

### 依赖管理

每个独立项目应包含 `requirements.txt`：

```txt
# 基础依赖示例
requests>=2.28.0
numpy
pillow
tqdm
openpyxl
send2trash
```

**安装命令**：
```powershell
# 确保在虚拟环境中
.venv\Scripts\activate
pip install -r requirements.txt
```

## 构建与打包

### 使用 auto-py-to-exe 打包

```powershell
# 1. 进入 auto-py-to-exe 目录
cd d:\proiect\auto-py-to-exe

# 2. 启动打包工具
python -m auto_py_to_exe

# 3. 在浏览器中配置打包选项：
#    - Script Location: 选择要打包的 .py 文件
#    - Onefile: 单文件模式（推荐）
#    - Window Based: 隐藏控制台（GUI 程序）
#    - Icon: 选择 .ico 图标文件
#    - Additional Files: 添加配置文件、模板等

# 4. 输出目录默认在 auto-py-to-exe/output/
```

### 使用 PyInstaller 命令行打包

```powershell
# 基础打包命令
pyinstaller --onefile --windowed --icon=icon.ico script.py

# 包含数据文件
pyinstaller --onefile --windowed --add-data "config.json;." script.py
```

### PowerShell 脚本打包

部分项目提供 `build.bat` 或 `.ps1` 脚本自动打包：

```powershell
# 示例：坤云平台定时处理
.\install.ps1          # 安装定时任务
.\cleanup.ps1          # 手动执行清理
```

## 测试策略

### 单元测试

`auto-py-to-exe` 目录包含测试用例：

```
auto-py-to-exe/tests/
├── test_imports.py
├── test_library_dependencies.py
└── test_packaging.py
```

### 手动测试清单

发布前检查：
- [ ] 虚拟环境激活后能否正常运行
- [ ] 依赖是否完整（`pip install -r requirements.txt` 后测试）
- [ ] GUI 界面中文显示正常
- [ ] 打包后的 exe 能否独立运行
- [ ] 配置文件路径是否正确（使用相对路径）

## 配置说明

### 海康设备配置文件（Deepmind.json）

多个项目使用统一的设备配置格式：

```json
[
    {
        "Deepmind": "设备ID",
        "IP": "10.x.x.x",
        "Password": "密码",
        "HttpPort": 80,
        "RtspPort": 554,
        "Scheme": "http"
    }
]
```

### 代理配置

项目中的 `proxy/` 目录和网络工具可能使用代理：

```powershell
# 常用代理设置（Clash）
$env:HTTP_PROXY="http://10.30.44.154:7897"
$env:HTTPS_PROXY="http://10.30.44.154:7897"
```

## Git 提交规范

```bash
# 常用 Git 命令（参考 git保存版本.txt）
git add .
git commit -m "描述修改内容"
git push
```

### 忽略文件规则（.gitignore）

```
# 虚拟环境
/.venv/
__pycache__/
*.pyc

# 二进制和输出
*.exe
output/
build/
dist/
*.spec

# 媒体文件
*.png *.jpg *.jpeg
*.xlsx *.docx *.pptx

# 项目特定
.dotnet/
auto-py-to-exe/output/
```

## 安全注意事项

1. **凭据管理**：设备密码存储在 `Deepmind.json` 中，**不要提交到 Git**
2. **API Token**：AI 接口 Token 存储在本地配置，避免硬编码
3. **网络访问**：内网工具使用 `10.x.x.x` 网段，通过路由表区分内外网
4. **代理安全**：代理配置仅在必要时启用，避免敏感数据经过外部代理

## 常见任务速查

### 新建项目

1. 在 `工作/` 目录下创建项目文件夹
2. 创建 `README.md` 描述项目用途
3. 创建 `requirements.txt` 记录依赖
4. 开发完成后，归档到 `已完结/`

### 调试 GUI 程序

```python
# 在代码中添加调试信息
import traceback
try:
    # 你的代码
except Exception as e:
    print(f"错误: {e}")
    traceback.print_exc()
```

### 处理中文路径

```python
# 确保文件操作支持中文路径
import os
os.path.abspath(path)  # 处理中文文件名
```

## 参考资料

- 海康威视 ISAPI 接口文档：`工作/超脑批量修改264/API_INTERFACE.md`
- 指令速查：`工作/指令.txt`（包含网络配置、代理设置等）
- 百度云 API：`工作/百度云/` 目录
