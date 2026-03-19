# 海康威视AI开放平台数据集导出工具

自动从海康威视AI开放平台下载数据集的图片和标注数据。

## 功能特性

- **GUI界面**: 图形化操作界面，简单易用
- **自动识别**: 从当前浏览器页面自动提取数据集ID和版本ID
- **批量下载**: 并发下载所有已标注图片和对应标注
- **一一对应**: 图片和标注使用相同文件名，便于管理
- **进度显示**: 实时显示下载进度
- **断点续传**: 自动跳过已下载的文件
- **时间戳子文件夹**: 每次下载创建独立的子文件夹，避免覆盖
- **备选认证**: WebSocket失败时自动使用browser_cookie3读取cookies

## 目录结构

```
hikvision-dataset-tool/
├── main.py              # 主程序入口
├── requirements.txt     # Python依赖
├── README.md            # 使用说明
├── core/                # 核心模块
│   ├── auth.py         # 认证管理
│   ├── api_client.py   # API客户端
│   └── downloader.py   # 下载器
├── browser/            # 浏览器集成
│   └── bb_browser_bridge.py  # bb-browser CDP桥接
└── gui/                # GUI界面
    └── main_window.py  # tkinter主窗口
```

## 安装

1. 确保已安装Python 3.8+
2. 安装依赖:
```bash
pip install -r requirements.txt
```

3. 确保已安装并启动 bb-browser:
```bash
bb-browser
```

## 使用方法

### GUI模式（推荐）

启动图形界面，操作更直观：

```bash
python main.py --gui
```

在GUI界面中：
1. 点击"连接浏览器"获取当前页面信息
2. 选择下载目录
3. 点击"开始下载"

### 命令行模式

#### 自动模式

1. 在浏览器中登录海康AI平台并打开目标数据集页面
2. 运行程序:
```bash
python main.py --auto
```

程序会自动:
- 从当前浏览器页面提取 dataset_id 和 version_id
- 获取认证token
- 下载所有已标注图片和标注数据

#### 指定输出目录

```bash
python main.py --auto --output ./my_dataset
```

#### 手动模式

```bash
python main.py --dataset 100149930 --version 100240402 --token "your_token_here"
```

## 输出目录结构

每次下载会创建一个带时间戳的子文件夹，避免覆盖之前的数据：

```
~/Downloads/
└── dataset_{dataset_id}_20250319_143052/    # 时间戳子文件夹
    ├── images/                              # 原始图片
    │   ├── image001.jpg
    │   └── image002.jpg
    └── annotations/                         # 标注数据（JSON格式）
        ├── image001.json
        └── image002.json
```

## 标注格式

每个标注JSON文件包含:
```json
{
  "file_id": "xxx",
  "file_name": "xxx.jpg",
  "width": 1280,
  "height": 720,
  "annotations": [
    {
      "id": "xxx",
      "label_name": "人",
      "label_item_name": "防护四件套",
      "bbox": {
        "xmin": 768,
        "ymin": 109,
        "xmax": 852,
        "ymax": 393
      }
    }
  ]
}
```

## 常见问题

### Q: 提示"未找到海康AI平台页面"
A: 请确保:
1. bb-browser已启动 (`bb-browser`)
2. 已在Chrome中打开海康AI平台的数据集页面
3. URL包含 `/overall/{dataset_id}/{version_id}/gallery`

### Q: 提示"无法从浏览器获取token"
A: 请确保已登录海康AI平台，且bb-browser连接的是同一个浏览器实例。

### Q: WebSocket 403 Forbidden 错误
A: Chrome 111+ 加强了WebSocket安全策略。解决方案：
1. **推荐**: 启动 bb-browser 时添加参数：
   ```bash
   bb-browser --remote-allow-origins="*"
   ```
2. **备选**: 程序会自动使用 browser_cookie3 从本地浏览器cookie数据库读取（无需额外操作）

### Q: 图片下载后无法打开
A: 程序已修复此问题，确保：
1. 使用最新版本代码
2. 图片请求已添加正确的 `Accept: image/*` header
3. 文件完整性检查会自动删除损坏的文件

### Q: 下载速度慢
A: 可以调整并发数：
- GUI模式：在界面中调整"并发数"设置
- 命令行模式：修改 `main.py` 中的 `max_concurrent` 参数（默认5）

## 技术说明

- 使用 **Chrome DevTools Protocol (CDP)** 与bb-browser通信
- 使用 **aiohttp** 进行异步并发下载
- API端点: `https://ai.hikvision.com/api/saas/ai-training/algorithms`
