# 超脑设备 ISAPI 接口文档

## 基础信息

| 项目 | 说明 |
|------|------|
| 协议 | HTTP/HTTPS |
| 认证方式 | Digest Authentication (摘要认证) |
| 默认账号 | admin |
| 数据格式 | JSON / XML |
| 编码类型 | UTF-8 |

---

## 1. 获取通道列表

获取设备上所有接入的监控点通道。

### 请求

```http
GET /ISAPI/ContentMgmt/InputProxy/channels HTTP/1.1
Host: {device_ip}:{port}
Authorization: Digest username="admin", ...
```

### 响应

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
    <!-- ... 更多通道 -->
</InputProxyChannelList>
```

### 字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| id | 通道ID | 1, 2, 3... |
| name | 通道名称 | Camera 01 |

### Python 调用示例

```python
import requests
from requests.auth import HTTPDigestAuth
import xml.etree.ElementTree as ET

url = "http://10.30.5.112/ISAPI/ContentMgmt/InputProxy/channels"
auth = HTTPDigestAuth('admin', 'password')

resp = requests.get(url, auth=auth, timeout=10)

if resp.status_code == 200:
    root = ET.fromstring(resp.text)
    channels = []
    for channel in root.iter():
        if channel.tag.endswith('InputProxyChannel'):
            ch_id = None
            ch_name = "未知"
            for child in channel.iter():
                if child.tag.endswith('id'):
                    ch_id = child.text
                elif child.tag.endswith('name'):
                    ch_name = child.text
            if ch_id:
                channels.append({'id': ch_id, 'name': ch_name})
    print(f"发现 {len(channels)} 个通道: {channels}")
```

---

## 2. AIOP事件查询

查询AI智能分析的事件。

### 请求

```http
POST /ISAPI/Intelligent/AIOpenPlatform/AIIntelligentSearch?format=json HTTP/1.1
Host: {device_ip}:{port}
Content-Type: application/json
Authorization: Digest username="admin", ...
```

### 请求体

```json
{
    "SearchCondition": {
        "searchID": "8F61817B-8F5D-425C-8E30-12F9DEA69F1C",
        "searchResultPosition": 0,
        "maxResults": 30,
        "startTime": "2026-03-05T00:00:00+08:00",
        "endTime": "2026-03-05T23:59:59+08:00",
        "engine": [],
        "taskType": "videoTask",
        "minConfidence": 0,
        "secondVerifyAlarmEnabled": false,
        "AIOPDataUrlEnabled": true,
        "channelID": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "secondVerifyAlarmType": "succ"
    }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| searchID | String | 是 | 查询唯一标识符（UUID） |
| searchResultPosition | Int | 是 | 查询结果起始位置 |
| maxResults | Int | 是 | 最大返回结果数 |
| startTime | String | 是 | 开始时间（ISO8601格式） |
| endTime | String | 是 | 结束时间（ISO8601格式） |
| taskType | String | 是 | 任务类型，固定值"videoTask" |
| channelID | Array | 是 | 通道ID列表 [1,2,3,...] |
| minConfidence | Int | 否 | 最小置信度 |
| secondVerifyAlarmEnabled | Bool | 否 | 是否启用二次验证 |
| AIOPDataUrlEnabled | Bool | 否 | 是否返回AIOP数据URL |
| secondVerifyAlarmType | String | 否 | 二次验证类型，"succ"表示成功 |

### 响应

```json
{
    "SearchResult": {
        "searchID": "8F61817B-8F5D-425C-8E30-12F9DEA69F1C",
        "responseStatusStrg": "OK",
        "numOfMatches": 3,
        "totalMatches": 3,
        "AIAlarmInfo": [
            {
                "dateTime": "2026-03-05T19:50:33+08:00",
                "channelID": 9,
                "ruleID": 1,
                "ruleName": "人员检测",
                "confidence": 99,
                "url": "http://.../picture/...",
                "AIOPDataUrl": "http://.../AIOPData?..."
            }
        ]
    }
}
```

### 响应字段

| 字段 | 说明 |
|------|------|
| responseStatusStrg | 响应状态：OK / NO_MATCHES |
| numOfMatches | 匹配记录数 |
| AIAlarmInfo | AI告警列表 |
| dateTime | 事件发生时间 |
| channelID | 通道ID |
| ruleName | 规则名称 |
| confidence | 置信度（%） |
| url | 抓拍图片URL |

### Python 调用示例

```python
import requests
from requests.auth import HTTPDigestAuth
from datetime import datetime
import uuid

url = "http://10.30.5.112/ISAPI/Intelligent/AIOpenPlatform/AIIntelligentSearch?format=json"
auth = HTTPDigestAuth('admin', 'password')

payload = {
    "SearchCondition": {
        "searchID": str(uuid.uuid4()).upper(),
        "searchResultPosition": 0,
        "maxResults": 30,
        "startTime": "2026-03-05T00:00:00+08:00",
        "endTime": "2026-03-05T23:59:59+08:00",
        "engine": [],
        "taskType": "videoTask",
        "minConfidence": 0,
        "secondVerifyAlarmEnabled": False,
        "AIOPDataUrlEnabled": True,
        "channelID": [1, 2, 3, 4, 5, 6, 7, 8, 9],
        "secondVerifyAlarmType": "succ"
    }
}

headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

resp = requests.post(url, json=payload, auth=auth, headers=headers, timeout=30)

if resp.status_code == 200:
    data = resp.json()
    result = data.get('SearchResult', {})
    print(f"状态: {result.get('responseStatusStrg')}")
    print(f"匹配数: {result.get('numOfMatches')}")
    
    for alarm in result.get('AIAlarmInfo', []):
        print(f"通道{alarm['channelID']} {alarm['dateTime']} 置信度{alarm['confidence']}%")
```

---

## 3. 全部事件查询

查询设备的全部事件记录。

### 请求

```http
POST /ISAPI/ContentMgmt/eventRecordSearch?format=json HTTP/1.1
Host: {device_ip}:{port}
Content-Type: application/json
Authorization: Digest username="admin", ...
```

### 请求体

```json
{
    "EventSearchDescription": {
        "searchID": "D59DED50-B14F-4631-89A3-FC7A82DE7D87",
        "searchResultPosition": 0,
        "maxResults": 30,
        "timeSpanList": [
            {
                "startTime": "2026-03-05T00:00:00+08:00",
                "endTime": "2026-03-05T23:59:59+08:00"
            }
        ],
        "type": "all",
        "eventType": "all",
        "channels": [1]
    }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| searchID | String | 是 | 查询唯一标识符 |
| searchResultPosition | Int | 是 | 查询结果起始位置 |
| maxResults | Int | 是 | 最大返回结果数 |
| timeSpanList | Array | 是 | 时间范围列表 |
| startTime | String | 是 | 开始时间 |
| endTime | String | 是 | 结束时间 |
| type | String | 是 | 查询类型，"all"表示全部 |
| eventType | String | 是 | 事件类型，"all"表示全部 |
| channels | Array | 是 | 通道ID列表 |

### 响应

```json
{
    "EventSearchResult": {
        "searchID": "D59DED50-B14F-4631-89A3-FC7A82DE7D87",
        "responseStatusStrg": "OK",
        "numOfMatches": 10,
        "matchList": [
            {
                "time": "2026-03-05T19:50:33+08:00",
                "channel": 1,
                "eventType": "VMD",
                "data": "..."
            }
        ]
    }
}
```

### Python 调用示例

```python
import requests
from requests.auth import HTTPDigestAuth

url = "http://10.30.5.112/ISAPI/ContentMgmt/eventRecordSearch?format=json"
auth = HTTPDigestAuth('admin', 'password')

payload = {
    "EventSearchDescription": {
        "searchID": str(uuid.uuid4()).upper(),
        "searchResultPosition": 0,
        "maxResults": 30,
        "timeSpanList": [{
            "startTime": "2026-03-05T00:00:00+08:00",
            "endTime": "2026-03-05T23:59:59+08:00"
        }],
        "type": "all",
        "eventType": "all",
        "channels": [1, 2, 3]
    }
}

resp = requests.post(url, json=payload, auth=auth, timeout=30)

if resp.status_code == 200:
    data = resp.json()
    result = data.get('EventSearchResult', {})
    print(f"状态: {result.get('responseStatusStrg')}")
    print(f"事件数: {result.get('numOfMatches')}")
```

---

## 4. 心跳保活

保持会话活跃。

### 请求

```http
PUT /ISAPI/Security/sessionHeartbeat?JumpChildDev=true HTTP/1.1
Host: {device_ip}:{port}
Content-Length: 0
Authorization: Digest username="admin", ...
```

### 响应

```http
HTTP/1.1 200 OK
```

---

## 错误码

| HTTP状态码 | 说明 | 解决方案 |
|------------|------|----------|
| 200 | 成功 | - |
| 401 | 认证失败 | 检查用户名密码 |
| 403 | 权限不足 | 检查账号权限 |
| 404 | 通道不存在 | 检查通道ID |
| 500 | 服务器内部错误 | 稍后重试 |
| 503 | 服务不可用 | 检查设备状态 |

---

## 时间格式说明

### ISO8601格式
```
YYYY-MM-DDTHH:MM:SS+08:00
```

示例：
- `2026-03-05T00:00:00+08:00` - 北京时间凌晨
- `2026-03-05T23:59:59+08:00` - 北京时间午夜

### Python转换

```python
from datetime import datetime

# 转换为ISO8601格式
dt = datetime.now()
iso_str = dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")

# 从字符串解析
dt = datetime.strptime("2026-03-05T12:00:00+08:00"[:19], "%Y-%m-%dT%H:%M:%S")
```

---

## 完整使用流程

```python
# 1. 创建设备客户端
from requests.auth import HTTPDigestAuth

base_url = "http://10.30.5.112"
auth = HTTPDigestAuth('admin', 'password')

# 2. 获取通道列表
channels_url = f"{base_url}/ISAPI/ContentMgmt/InputProxy/channels"
resp = requests.get(channels_url, auth=auth)
channels = parse_channels(resp.text)  # 解析XML

# 3. 查询AIOP事件
aiop_url = f"{base_url}/ISAPI/Intelligent/AIOpenPlatform/AIIntelligentSearch?format=json"
payload = {
    "SearchCondition": {
        "searchID": str(uuid.uuid4()).upper(),
        "channelID": [int(ch['id']) for ch in channels],  # 所有通道
        "startTime": "2026-03-05T00:00:00+08:00",
        "endTime": "2026-03-05T23:59:59+08:00",
        "taskType": "videoTask",
        "minConfidence": 0,
        "secondVerifyAlarmEnabled": False,
        "AIOPDataUrlEnabled": True,
        "secondVerifyAlarmType": "succ"
    }
}
resp = requests.post(aiop_url, json=payload, auth=auth)
data = resp.json()

# 4. 处理结果
for alarm in data['SearchResult']['AIAlarmInfo']:
    print(f"通道{alarm['channelID']}: {alarm['dateTime']} 置信度{alarm['confidence']}%")
```
