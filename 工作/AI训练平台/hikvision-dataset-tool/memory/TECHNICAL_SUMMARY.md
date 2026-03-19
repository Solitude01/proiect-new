# 海康威视AI平台数据集导出工具 - 技术总结

## 1. 核心功能

该工具用于从海康威视AI开放平台导出数据集（图片+标注），支持以下特性：
- 批量下载已标注图片
- 自动解密加密图片（AES-ECB）
- 导出标注数据为JSON格式
- 支持并发下载
- GUI/CLI双模式

---

## 2. API接口汇总

### 基础信息
```python
BASE_URL = "https://ai.hikvision.com/api/saas/ai-training/algorithms"
```

### 2.1 获取标签列表
**Endpoint:** `POST /datasets/label/list`

**Request:**
```python
{
    "dataSetVersionId": version_id
}
```

**Response:**
```python
{
    "code": "200",
    "data": {
        "labelList": [
            {"name": "标签名", "num": 100}
        ]
    }
}
```

### 2.2 获取图片列表（分页）
**Endpoint:** `POST /datasets/file/offset-list/query`

**Request:**
```python
{
    "dataSetId": dataset_id,
    "dataSetVersionId": version_id,
    "offset": 0,
    "pageSize": 100,
    "isTag": 1,  # 1=已标注, 0=未标注, -1=全部
    "labelIds": "[]",
    "sortType": 1,  # 上传时间降序
    "fileName": "",
    "tagUserInfos": "[{}]",
    "labelProperty": ""
}
```

**Response:**
```python
{
    "code": "200",
    "data": {
        "dataList": [
            {
                "id": "文件ID",
                "fileName": "图片名.jpg",
                "cloudUrl": "图片URL",
                "thumbnailCloudUrl": "缩略图URL",
                "frameWidth": 1920,
                "frameHeight": 1080,
                "labelStatus": 1,
                "tagUserName": "标注人",
                "createTime": "2024-01-01 12:00:00",
                "key": "AES解密密钥"  # 可能为空
            }
        ],
        "page": {
            "total": 1000
        }
    }
}
```

### 2.3 批量获取标注数据
**Endpoint:** `POST /datasets/files/targets/query`

**Request:**
```python
{
    "dataSetVersionId": version_id,
    "fileIds[0]": "file_id_1",
    "fileIds[1]": "file_id_2",
    # ... 最多50个
}
```

**Response:**
```python
{
    "code": "200",
    "data": [
        {
            "fileId": "文件ID",
            "formData": [
                {
                    "id": "标注ID",
                    "labelId": "标签ID",
                    "labelName": "标签名",
                    "labelItemName": "标签项名",
                    "labelSetName": "标签集名",
                    "bndBox": {
                        "xmin": 100,
                        "ymin": 100,
                        "xmax": 200,
                        "ymax": 200
                    },
                    "tagCoord": "100 100 200 200",  # 备选格式
                    "property": {},
                    "orderNum": "1"
                }
            ]
        }
    ]
}
```

---

## 3. 认证机制

### 3.1 Token获取方式
1. **Browser Cookie3**: 从本地浏览器数据库读取 `ai.hikvision.com` 的cookies
2. **WebSocket CDP**: 通过Chrome DevTools Protocol获取（需开启远程调试）
3. **手动输入**: 用户直接提供token

### 3.2 请求头格式
```python
{
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "content-type": "application/x-www-form-urlencoded",
    "origin": "https://ai.hikvision.com",
    "referer": "https://ai.hikvision.com/intellisense/ai-training/console/data/",
    "token": "your_token_here",
    "projectid": "9a323db2bce24cd69ce018e41eff6e68",
    "user-agent": "Mozilla/5.0..."
}
```

### 3.3 Cookies包含字段
- `token`: 认证令牌（必需）
- `accountName`: 账户名
- `subAccountName`: 子账户名
- `projectId`: 项目ID
- `visitor`: "false"

---

## 4. 图片解密方法

### 4.1 加密流程（海康端）
图片采用 **AES-128-ECB** 加密，流程：
1. 读取图片文件 → Base64编码
2. 包装成 Data URI: `data:image/jpeg;base64,xxx`
3. AES-ECB加密（密钥由服务端提供）
4. Base64编码传输

### 4.2 解密代码
```python
from Crypto.Cipher import AES
import base64

def decrypt_image(encrypted_b64: str, key: str) -> bytes:
    """解密海康威视加密图片（AES-ECB + Base64）"""
    # 1. Base64 解码得到加密数据
    encrypted_data = base64.b64decode(encrypted_b64)

    # 2. AES-ECB 解密
    cipher = AES.new(key.encode('utf-8'), AES.MODE_ECB)
    decrypted = cipher.decrypt(encrypted_data)

    # 3. 去除 PKCS7 填充
    pad_len = decrypted[-1]
    if 1 <= pad_len <= 16:
        decrypted = decrypted[:-pad_len]

    # 4. 解码为 Data URI 字符串
    data_uri = decrypted.decode('utf-8')

    # 5. 提取 Base64 部分并解码为图片bytes
    if 'base64,' in data_uri:
        img_b64 = data_uri.split('base64,')[1]
        return base64.b64decode(img_b64)

    raise ValueError("无效的 Data URI 格式")
```

### 4.3 解密验证
解密成功的JPEG文件应以 `FF D8 FF` 开头（JPEG magic bytes）

---

## 5. 代码架构

```
hikvision-dataset-tool/
├── main.py                    # 主入口
├── core/
│   ├── auth.py               # 认证管理
│   ├── api_client.py         # API封装
│   └── downloader.py         # 下载器（含解密）
├── browser/
│   └── bb_browser_bridge.py  # 浏览器CDP桥接
├── gui/
│   └── main_window.py        # GUI界面
└── config.json               # 配置文件（自动保存token）
```

### 核心类关系
```
MainWindow (GUI)
    └── AuthManager (认证)
    └── DatasetDownloader (下载)
        └── HikvisionAPIClient (API)
        └── decrypt_image (解密)
```

---

## 6. 使用模式

### 6.1 GUI模式（推荐）
```bash
python main.py --gui
```
- 支持手动输入token
- 自动保存/恢复配置
- 进度条显示

### 6.2 自动模式（需浏览器）
```bash
python main.py --auto
```
- 从bb-browser获取当前页面信息
- 自动提取dataset_id/version_id

### 6.3 手动模式（命令行）
```bash
python main.py --dataset 100149930 --version 100240402 --token "xxx"
```

---

## 7. 关键依赖

```
pycryptodome      # AES解密
requests          # HTTP请求
browser_cookie3   # 浏览器cookie读取（可选）
websocket-client  # CDP通信（可选）
```

---

## 8. 已知限制

1. **图片加密**: 部分图片需解密，必须有正确的key
2. **Token有效期**: 海康token会过期，需定期更新
3. **并发限制**: 默认5并发，过高可能触发限流
4. **batch限制**: 标注接口每次最多50个file_id

---

## 9. 扩展方向

1. **增量下载**: 记录已下载文件，避免重复
2. **格式转换**: 支持导出COCO/YOLO格式
3. **筛选功能**: 按标签、标注人、时间筛选
4. **断点续传**: 支持大数据集中断恢复
5. **多数据集**: 批量导出多个数据集
