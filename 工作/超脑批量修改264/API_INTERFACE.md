# 海康威视 ISAPI 接口文档

本文档描述与海康威视 NVR（超脑）设备交互的 ISAPI 接口。

## 基础信息

| 项目 | 说明 |
|------|------|
| 协议 | HTTP/HTTPS |
| 认证方式 | Digest Authentication (摘要认证) |
| 默认账号 | admin |
| 数据格式 | XML |
| 编码类型 | UTF-8 |

## 接口列表

### 1. 获取通道列表

获取设备上所有接入的监控点通道。

**请求:**

```http
GET /ISAPI/ContentMgmt/InputProxy/channels HTTP/1.1
Host: {device_ip}:{port}
Authorization: Digest username="admin", ...
```

**响应:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<InputProxyChannelList>
    <InputProxyChannel>
        <id>1</id>
        <name>Camera 01</name>
        <sourceInputPortDescriptor>
            <managePortNo>0</managePortNo>
        </sourceInputPortDescriptor>
    </InputProxyChannel>
    <InputProxyChannel>
        <id>2</id>
        <name>Camera 02</name>
    </InputProxyChannel>
</InputProxyChannelList>
```

**字段说明:**

| 字段 | 说明 |
|------|------|
| id | 通道ID (1, 2, 3...) |
| name | 通道名称 |

---

### 2. 获取通道流媒体配置

获取指定通道的流媒体配置（包括编码格式）。

**请求:**

```http
GET /ISAPI/ContentMgmt/StreamingProxy/channels/{stream_id} HTTP/1.1
Host: {device_ip}:{port}
Authorization: Digest username="admin", ...
```

**参数:**

| 参数 | 说明 | 示例 |
|------|------|------|
| stream_id | 码流ID，格式: {通道ID}01 | 101 (通道1主码流), 201 (通道2主码流) |

**响应:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<StreamingChannel>
    <id>101</id>
    <channelName>101</channelName>
    <enabled>true</enabled>
    <Video>
        <enabled>true</enabled>
        <videoCodecType>H.265</videoCodecType>
        <videoResolutionWidth>1920</videoResolutionWidth>
        <videoResolutionHeight>1080</videoResolutionHeight>
        <videoQualityControlType>vbr</videoQualityControlType>
        <vbrUpperCap>6144</vbrUpperCap>
        <maxFrameRate>2500</maxFrameRate>
        <GovLength>50</GovLength>
    </Video>
    <Audio>
        <enabled>false</enabled>
        <audioCompressionType>G.711alaw</audioCompressionType>
    </Audio>
</StreamingChannel>
```

**关键字段:**

| 字段 | 说明 | 可选值 |
|------|------|--------|
| videoCodecType | 视频编码格式 | H.264, H.265, MJPEG |
| videoResolutionWidth | 视频宽度 | 1920, 1280, 704... |
| videoResolutionHeight | 视频高度 | 1080, 720, 576... |
| videoQualityControlType | 码率控制 | vbr (可变), cbr (固定) |
| vbrUpperCap | 码率上限 (Kbps) | 1024, 2048, 4096, 6144... |
| maxFrameRate | 最大帧率 (x100) | 2500 = 25fps |

---

### 3. 修改通道流媒体配置

修改指定通道的流媒体配置（用于修改编码格式）。

**请求:**

```http
PUT /ISAPI/ContentMgmt/StreamingProxy/channels/{stream_id} HTTP/1.1
Host: {device_ip}:{port}
Content-Type: application/xml
Authorization: Digest username="admin", ...

{XML配置内容}
```

**请求体示例:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<StreamingChannel>
    <id>101</id>
    <channelName>101</channelName>
    <enabled>true</enabled>
    <Video>
        <enabled>true</enabled>
        <videoCodecType>H.264</videoCodecType>
        <videoResolutionWidth>1920</videoResolutionWidth>
        <videoResolutionHeight>1080</videoResolutionHeight>
        <videoQualityControlType>vbr</videoQualityControlType>
        <vbrUpperCap>6144</vbrUpperCap>
        <maxFrameRate>2500</maxFrameRate>
        <GovLength>50</GovLength>
    </Video>
</StreamingChannel>
```

**重要说明:**

- PUT 请求会**完整覆盖**原有配置
- 必须先 GET 获取完整配置，修改目标字段后再 PUT
- 只发送部分字段会导致其他配置丢失

**响应:**

```http
HTTP/1.1 200 OK
Content-Type: application/xml

<?xml version="1.0" encoding="UTF-8"?>
<ResponseStatus>
    <requestURL>/ISAPI/ContentMgmt/StreamingProxy/channels/101</requestURL>
    <statusCode>1</statusCode>
    <statusString>OK</statusString>
</ResponseStatus>
```

---

## 流 ID 计算规则

| 通道 ID | 主码流 ID | 子码流 ID |
|---------|-----------|-----------|
| 1 | 101 | 102 |
| 2 | 201 | 202 |
| 3 | 301 | 302 |
| N | N01 | N02 |

**公式:** `stream_id = channel_id * 100 + stream_type`
- stream_type: 1=主码流, 2=子码流

---

## Python 调用示例

### 1. Digest 认证

```python
from requests.auth import HTTPDigestAuth

auth = HTTPDigestAuth('admin', 'password')
```

### 2. 获取通道列表

```python
import requests
import xml.etree.ElementTree as ET

url = "http://10.30.5.112/ISAPI/ContentMgmt/InputProxy/channels"
response = requests.get(url, auth=auth, timeout=10)

if response.status_code == 200:
    root = ET.fromstring(response.text)
    channels = []
    for channel in root.iter():
        if channel.tag.endswith('InputProxyChannel'):
            for child in channel.iter():
                if child.tag.endswith('id'):
                    channels.append(child.text)
    print(f"发现通道: {channels}")  # ['1', '2', '3']
```

### 3. 获取编码格式

```python
def get_codec_type(xml_text):
    """从 XML 中提取编码类型"""
    root = ET.fromstring(xml_text)
    for elem in root.iter():
        if elem.tag.endswith('videoCodecType'):
            return elem.text
    return None

url = "http://10.30.5.112/ISAPI/ContentMgmt/StreamingProxy/channels/101"
response = requests.get(url, auth=auth, timeout=10)

if response.status_code == 200:
    codec = get_codec_type(response.text)
    print(f"当前编码: {codec}")  # H.264 或 H.265
```

### 4. 修改编码格式

```python
def set_codec_type(xml_text, new_codec="H.264"):
    """修改 XML 中的编码类型"""
    root = ET.fromstring(xml_text)
    for elem in root.iter():
        if elem.tag.endswith('videoCodecType'):
            elem.text = new_codec
            return ET.tostring(root, encoding='unicode')
    return None

# 1. 获取当前配置
url = "http://10.30.5.112/ISAPI/ContentMgmt/StreamingProxy/channels/101"
resp_get = requests.get(url, auth=auth, timeout=10)
xml_config = resp_get.text

# 2. 修改编码
new_xml = set_codec_type(xml_config, "H.264")

# 3. 回写配置
headers = {'Content-Type': 'application/xml'}
resp_put = requests.put(url, data=new_xml.encode('utf-8'),
                        headers=headers, auth=auth, timeout=10)

if resp_put.status_code == 200:
    print("修改成功")
else:
    print(f"修改失败: {resp_put.status_code}")
```

---

## 错误码

| HTTP状态码 | 说明 |
|------------|------|
| 200 | 成功 |
| 401 | 认证失败（用户名或密码错误）|
| 403 | 权限不足 |
| 404 | 通道不存在 |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

---

## curl 测试命令

### 获取通道列表

```bash
curl --digest -u admin:password \
  "http://10.30.5.112/ISAPI/ContentMgmt/InputProxy/channels"
```

### 获取通道配置

```bash
curl --digest -u admin:password \
  "http://10.30.5.112/ISAPI/ContentMgmt/StreamingProxy/channels/101"
```

### 修改通道配置

```bash
curl --digest -u admin:password -X PUT \
  -H "Content-Type: application/xml" \
  -d '<?xml version="1.0"?><StreamingChannel>...</StreamingChannel>' \
  "http://10.30.5.112/ISAPI/ContentMgmt/StreamingProxy/channels/101"
```
