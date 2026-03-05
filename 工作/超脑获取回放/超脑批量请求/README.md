# 超脑批量查询工具

基于海康威视 ISAPI 接口开发的批量查询和测试工具。

## 工具清单

### 核心工具

| 文件名 | 功能 | 说明 |
|--------|------|------|
| `super_brain_query_tool.py` | 完整查询工具 | 获取通道+选择通道+查询事件，可视化操作 |
| `batch_stress_test.py` | 批量压力测试 | 批量获取通道、批量查询、压力测试 |
| `batch_search_all_channels.py` | 批量查询工具 | 多设备批量查询（保留） |

### 文档

| 文件名 | 说明 |
|--------|------|
| `API_INTERFACE.md` | 接口文档（详细API说明） |
| `README.md` | 使用说明（本文件） |

### 原始curl记录

- `全部事件查询.txt`
- `AIOP事件查询.txt`
- `查询操作.md`
- `查询操作2.md`
- `所有通道-AIOP事件-实时视频任务 查询操作.md`

---

## 快速开始

### 1. 单个设备查询（推荐）

适合：日常查询单个设备的AIOP事件

```bash
python super_brain_query_tool.py
```

**操作步骤**:
1. 左栏点击选择设备
2. 点击"获取通道列表"按钮
3. 中栏勾选要查询的通道（可全选/取消）
4. 右栏设置查询类型和时间
5. 点击"执行查询"

### 2. 批量压力测试

适合：测试多个设备的性能、压力测试

```bash
python batch_stress_test.py
```

**测试类型**:
- **获取通道**: 批量获取多个设备的通道列表
- **单次查询**: 每个设备查询一次AIOP事件
- **压力测试**: 每个设备多次查询，测试并发性能

### 3. 批量设备查询

适合：同时查询多个设备的所有通道

```bash
python batch_search_all_channels.py
```

---

## 功能对比

| 功能 | super_brain_query_tool | batch_stress_test | batch_search_all_channels |
|------|------------------------|-------------------|---------------------------|
| 可视化选择设备 | ✅ | ✅ | ✅ |
| 可视化选择通道 | ✅ | ❌ | ❌ |
| 批量多设备 | ❌ | ✅ | ✅ |
| 获取通道列表 | ✅ | ✅ | ✅ |
| 单次查询 | ✅ | ✅ | ✅ |
| 压力测试 | ❌ | ✅ | ❌ |
| 性能统计 | ❌ | ✅ | ❌ |
| 导出结果 | ❌ | ✅ | ✅ |

---

## 接口说明

### 1. 获取通道列表

```http
GET /ISAPI/ContentMgmt/InputProxy/channels
```

**响应**: XML格式的通道列表

```xml
<InputProxyChannelList>
    <InputProxyChannel>
        <id>1</id>
        <name>Camera 01</name>
    </InputProxyChannel>
</InputProxyChannelList>
```

### 2. AIOP事件查询

```http
POST /ISAPI/Intelligent/AIOpenPlatform/AIIntelligentSearch?format=json
```

**请求体**:
```json
{
    "SearchCondition": {
        "searchID": "...",
        "channelID": [1, 2, 3, 4, 5],
        "startTime": "2026-03-05T00:00:00+08:00",
        "endTime": "2026-03-05T23:59:59+08:00",
        "taskType": "videoTask"
    }
}
```

**响应**:
```json
{
    "SearchResult": {
        "responseStatusStrg": "OK",
        "numOfMatches": 3,
        "AIAlarmInfo": [
            {
                "dateTime": "2026-03-05T19:50:33+08:00",
                "channelID": 9,
                "confidence": 99
            }
        ]
    }
}
```

### 3. 全部事件查询

```http
POST /ISAPI/ContentMgmt/eventRecordSearch?format=json
```

详细接口文档见 `API_INTERFACE.md`

---

## 测试示例

### 获取通道示例

```
设备 DM20 (10.30.5.112):
  [OK] 发现 9 个通道:
    - 通道 1: N12-1-JK184
    - 通道 2: N12-1-JK183
    - 通道 3: Camera 01
    - 通道 4: Camera 01
    - 通道 5: IPCamera 05
    - 通道 6: 通道东7
    - 通道 7: 通道2
    - 通道 8: 通道1
    - 通道 9: N12-4-J10前台通道
```

### AIOP查询示例

```
[OK] 查询成功! (12.4ms)
状态: OK
匹配数: 3

AI告警列表:
  [1] 通道9 2026-03-05 19:50:33 置信度99%
  [2] 通道9 2026-03-05 19:50:32 置信度100%
  [3] 通道9 2026-03-05 19:50:30 置信度99%
```

### 压力测试统计示例

```
测试完成!
总请求: 100
成功: 98 (98.0%)
失败: 2 (2.0%)
响应时间 - 最小: 10ms, 最大: 500ms, 平均: 120ms, 中位数: 110ms
```

---

## 使用场景

### 场景1: 查询单个设备的AI事件

使用 `super_brain_query_tool.py`
- 可视化选择要查询的通道
- 查看详细的AI告警信息
- 灵活设置时间范围

### 场景2: 测试多个设备的通道

使用 `batch_stress_test.py`
- 选择"获取通道"测试类型
- 批量获取所有设备的通道列表
- 导出通道信息

### 场景3: 压力测试设备

使用 `batch_stress_test.py`
- 选择"压力测试"类型
- 设置并发线程数（如10）
- 设置每设备请求数（如50）
- 查看性能统计和响应时间分布

### 场景4: 批量查询所有设备

使用 `batch_search_all_channels.py`
- 选择多个设备
- 选择"所有通道"模式
- 自动获取并查询所有通道
- 导出查询结果

---

## 常见问题

### Q: 获取通道失败？
A: 检查：
- 设备IP是否可达
- 用户名密码是否正确
- 设备是否支持该接口

### Q: 查询返回NO_MATCHES？
A: 表示查询成功但无数据，尝试：
- 扩大时间范围
- 检查通道是否正确
- 确认该时间段有事件发生

### Q: 压力测试时大量失败？
A: 可能是：
- 并发数过高，降低并发线程数
- 请求间隔太短，增加间隔时间
- 设备性能限制

---

## 技术参数

### 认证方式
- HTTP Digest Auth
- 用户名: `admin`
- 密码: 从 `Deepmind.json` 获取

### 支持设备
- 海康威视超脑设备
- 支持ISAPI接口的NVR设备

### 运行环境
- Python 3.8+
- tkinter (GUI)
- requests

---

## 参考文档

- `API_INTERFACE.md` - 详细接口文档
- `查询操作.md` - 原始curl记录
- `所有通道-AIOP事件-实时视频任务 查询操作.md` - 所有通道查询示例
