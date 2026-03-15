# 海康数据集下载器 - 实现状态总结

## 项目概述

Chrome 扩展插件，用于从海康威视 AI 训练平台（ai.hikvision.com）批量下载训练数据集，包括原图和标注数据。

---

## 已实现功能

### 1. 核心架构

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| Manifest V3 | `manifest.json` | ✅ 完成 | 基础配置、权限声明 |
| Content Script | `content.js` | ✅ 完成 | 页面数据捕获、UI面板 |
| Injected Script | `injected.js` | ✅ 完成 | API请求拦截 |
| Background SW | `background.js` | ✅ 完成 | 文件下载处理 |

### 2. 数据捕获

- ✅ **API 拦截**: 通过 monkey-patching 拦截 fetch 和 XHR 请求
- ✅ **图片列表捕获**: 拦截 `/file/offset-list/query` 接口
- ✅ **标注数据捕获**: 拦截 `/files/targets/query` 接口
- ✅ **统计数据捕获**: 拦截 `/label-status/statistic` 接口
- ✅ **数据关联**: 通过 fileId 关联图片和标注

### 3. 数据存储结构

```javascript
{
  datasetId: "100089473",
  versionId: "100239915",
  images: Map {
    "fileId" => {
      id: "fileId",
      fileName: "xxx.jpg",
      cloudUrl: "https://...",
      width: 2560,
      height: 1440,
      annotations: [...]
    }
  },
  annotations: Map { "fileId" => [...] }
}
```

### 4. 导出功能

- ✅ **JSON 导出**: 导出完整的标注数据为 JSON 格式
- ✅ **图片批量下载**: 支持批量下载原图
- ✅ **文件夹组织**: 按 `hikvision_datasets/{datasetId}/images/` 结构存储

### 5. 用户界面

- ✅ **浮动面板**: 可拖拽的浮动操作面板
- ✅ **实时统计**: 显示已捕获图片数、标注数
- ✅ **操作按钮**: 导出JSON、导出全部(含图片)、获取标注
- ✅ **状态提示**: 显示数据集统计信息

---

## 已知问题

### 已修复

| 问题 | 原因 | 修复方案 |
|------|------|----------|
| CSP 阻止内联脚本 | Chrome CSP 限制 | 将注入代码移到单独 injected.js 文件 |
| 文件名缺少扩展名 | 正则未考虑路径前缀 | 先提取文件名部分再检查扩展名 |
| 文件未保存到正确文件夹 | 路径构建逻辑问题 | 统一路径结构，避免重复 |
| **图片下载失败（0x49 0x5a 格式错误）** | 下载的是 base64 缩略图而非真实图片 | 使用 webRequest API 拦截 OSS 真实图片 URL |
| **点击完图片还是不下载** | ID 不匹配 + 正则表达式错误 | 使用 imgId 作为 key，修正正则表达式 |
| **图片内容异常（"IZ" 开头，无法查看）** | `chrome.downloads.download()` 不携带页面 Cookie，OSS 服务器返回加密/错误内容 | 改用 `fetch()` + `credentials: 'include'` 获取 Blob，再创建 Object URL 下载 |

**修复详情（2026-03-14 第9轮修复 - Cookie 认证问题）:**
- **问题**: 图片文件以 "IZ" 开头（不是 JPEG 的 "ÿØ"），文件大小正常但无法查看；控制台报错 `URL.createObjectURL is not a function`
- **根本原因**:
  1. `chrome.downloads.download()` API 不会自动携带当前页面的认证 Cookie
  2. Service Worker 中 `URL.createObjectURL` 可能不可用
- **方案（最终版）**:
  1. `content.js`: 使用 `fetch(url, { credentials: 'include' })` 在 content script 中获取图片 Blob（携带页面 Cookie）
  2. `content.js`: 使用 `FileReader` 将 Blob 转换为 Data URL（新增 `blobToDataUrl` 函数）
  3. `content.js`: 将 Data URL 通过消息发送给 `background.js`
  4. `background.js`: 接收 Data URL 并直接使用 `chrome.downloads.download()` 下载
  5. `background.js`: 更新 URL 验证逻辑，接受 `data:` 开头的 URL

**修复详情（2026-03-14）:**
- **问题**: 下载的图片以 `0x49 0x5a` (ASCII "IZ") 开头，不是有效的 JPEG 格式
- **原因**: 图片列表 API 返回的 `cloudUrl` 是 base64 编码的缩略图，真实 OSS URL 需要单独获取
- **方案**:
  1. `manifest.json`: 添加 `webRequest` 权限，添加 OSS 域名到 `host_permissions`
  2. `background.js`: 使用 `chrome.webRequest.onBeforeRequest` 拦截 OSS 图片请求，提取并转发真实 URL
  3. `content.js`: 监听 `realImageUrl` 消息，更新对应图片的 `realUrl` 字段

**修复详情（2026-03-14）第2轮修复:**
- **问题**: 点击完图片后还是不下载，控制台显示"收到真实URL但图片尚未加载"
- **根本原因**:
  1. API 返回的图片 ID (UUID) 与 OSS URL 中的 imgId 是完全不同的两个 ID 系统
  2. 正则表达式 `/(\d+)/` 只匹配数字，但 imgId 包含字母（如 `1755581791382a530a819`）
  3. `dataStore.images.get(parseInt(fileId))` 使用错误，因为 key 是 UUID 字符串而非数字
- **方案**:
  1. `content.js`: 从 `cloudUrl`（缩略图URL）中提取 imgId，使用 imgId 作为 `dataStore.images` 的 key
  2. `content.js` & `background.js`: 修正正则表达式为 `/\/img\/([a-zA-Z0-9]+)/` 以匹配完整的 imgId
  3. `content.js`: 移除 `parseInt()` 调用，直接使用 imgId 字符串作为 key
  4. `content.js`: 修改标注关联逻辑，遍历图片查找 `img.id` 匹配项

### 待验证

- ⏳ 大规模数据集（数百张图片）的下载稳定性
- ⏳ OSS URL 过期处理
- ⏳ 网络中断后的恢复机制

---

## 未实现功能

### 1. 格式转换

- ❌ **YOLO 格式**: 将四边形标注转换为 YOLO 格式 (txt)
- ❌ **COCO 格式**: 导出 COCO 格式的标注文件
- ❌ **VOC 格式**: 支持 Pascal VOC XML 格式

**当前**: 仅支持原始 JSON 格式导出

### 2. 数据完整性

- ❌ **自动翻页**: 自动触发所有分页数据的加载
- ❌ **缺失数据检测**: 检测哪些图片缺少标注
- ❌ **数据校验**: 校验下载图片与标注的完整性

**当前**: 需要用户手动浏览页面触发 API 加载

### 3. 下载管理

- ❌ **下载队列可视化**: 显示下载进度条
- ❌ **断点续传**: 网络中断后从断点继续
- ❌ **并发控制**: 可配置的并发下载数量
- ❌ **ZIP 打包**: 自动打包为 ZIP 文件

**当前**: 简单的顺序下载，固定 100ms 延迟

### 4. 用户体验

- ❌ **设置面板**: 下载路径配置、格式选择
- ❌ **历史记录**: 记录已下载的数据集
- ❌ **筛选功能**: 按标注状态筛选图片
- ❌ **预览功能**: 预览标注框绘制效果

---

## 完整需求列表

### 需求来源

基于 HAR 文件分析，海康 AI 训练平台的 API 结构：

1. **文件列表接口**: `POST /api/saas/ai-training/algorithms/datasets/file/offset-list/query`
   - 返回：图片 ID、文件名、OSS URL、尺寸信息

2. **标注数据接口**: `POST /api/saas/ai-training/algorithms/datasets/files/targets/query`
   - 返回：fileId、标注列表（labelName、tagCoord 四边形坐标）

3. **统计接口**: `POST /api/saas/ai-training/algorithms/datasets/label-status/statistic`
   - 返回：总文件数、已标注数、有效标注数

### 核心需求

```
┌─────────────────────────────────────────────────────┐
│  输入                                               │
│  - 海康平台数据集页面 URL                           │
│  - 用户浏览触发的 API 响应                          │
├─────────────────────────────────────────────────────┤
│  处理                                               │
│  - 拦截并捕获 API 响应数据                          │
│  - 关联图片元数据与标注数据                         │
│  - 批量下载原图                                     │
├─────────────────────────────────────────────────────┤
│  输出                                               │
│  - 原图文件 → hikvision_datasets/{id}/images/      │
│  - 标注文件 → annotations.json / annotations.txt   │
└─────────────────────────────────────────────────────┘
```

### 优先级划分

| 优先级 | 功能 | 状态 |
|--------|------|------|
| P0 | API 拦截与数据捕获 | ✅ 完成 |
| P0 | 图片批量下载 | ✅ 完成 |
| P0 | JSON 导出 | ✅ 完成 |
| P1 | YOLO 格式转换 | ❌ 未实现 |
| P1 | 自动翻页加载 | ❌ 未实现 |
| P2 | 下载进度显示 | ❌ 未实现 |
| P2 | ZIP 打包 | ❌ 未实现 |
| P3 | COCO/VOC 格式 | ❌ 未实现 |
| P3 | 设置面板 | ❌ 未实现 |

---

## 文件清单

```
web-annotator/
├── manifest.json          # 扩展配置
├── background.js          # 后台下载服务
├── content.js             # 内容脚本（主逻辑）
├── injected.js            # 页面注入脚本（API拦截）
├── IMPLEMENTATION_STATUS.md # 本文档
└── icons/                 # 图标目录（可选）
```

---

## 下一步建议

### 短期（高优先级）

1. **测试验证**: 在真实数据集上验证下载完整性
2. **YOLO 格式**: 实现四边形到 YOLO 的转换
3. **错误处理**: 增强网络错误和下载失败处理

### 中期

1. **自动翻页**: 模拟滚动或点击自动加载所有分页
2. **进度显示**: 添加可视化的下载进度条
3. **ZIP 打包**: 使用 JSZip 实现客户端打包

### 长期

1. **多格式支持**: COCO、VOC 等标准格式
2. **智能重试**: 失败自动重试机制
3. **增量更新**: 检测新增图片并增量下载

---

## 使用说明

### 安装

1. 打开 Chrome 扩展管理页 `chrome://extensions/`
2. 开启"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择 `web-annotator` 文件夹

### 使用

1. 访问海康 AI 训练平台数据集页面
2. 点击扩展图标显示浮动面板
3. 浏览图片列表（触发 API 拦截）
4. 点击"导出全部(含图片)"开始下载

---

---

## 新增：自动化测试功能（2026-03-14）

### 背景
为了验证图片下载问题（"IZ" 文件头 vs JPEG "ÿØ"），实现自动化的三种下载方式对比测试。

### 实现方案：选项B - 拦截即下载

当 `webRequest` 拦截到图片 URL 时，自动触发三种下载方式进行对比：

| 下载方式 | 实现位置 | Cookie携带 | 预期结果 |
|---------|---------|-----------|---------|
| 直接下载 | `background.js` | ❌ 否 | ❌ "IZ" 格式 |
| SW fetch | `background.js` | ❌ 否 | ❌ "IZ" 格式 |
| Content fetch | `content.js` | ✅ 是 | ✅ 正常JPEG |

### 代码变更

**`background.js`:**
1. 新增 `downloadTestResults` Map 跟踪下载结果
2. 新增 `downloadImageDirect()` - 方式1：直接下载
3. 新增 `downloadImageWithFetch()` - 方式2：Service Worker fetch
4. 新增 `downloadViaContentScript()` - 方式3：发送到content script下载
5. 新增 `chrome.downloads.onChanged` 监听器 - 验证下载完成结果
6. 在 `webRequest.onBeforeRequest` 中自动触发三种下载测试

**`content.js`:**
1. 新增 `downloadTestViaContent` 消息处理
2. 使用 `fetch(url, { credentials: 'include' })` 携带页面Cookie
3. 将 Blob 转换为 Data URL 后发送给 background 下载

### 测试输出

下载文件保存到不同子文件夹便于对比：
```
hikvision_datasets/
├── test_direct/      # 方式1：直接下载
├── test_fetch/       # 方式2：Service Worker fetch
└── test_content/     # 方式3：Content script fetch（预期正常）
```

控制台输出示例：
```
[下载测试] 开始三种下载方式测试，imgId: 1755581791382a530a819
[下载测试] 直接下载 - 任务创建: 1234 imgId: 1755581791382a530a819
[下载测试] Fetch下载 - 开始: 1755581791382a530a819
[下载测试] Content下载 - 请求发送到tab: 567 imgId: 1755581791382a530a819
[下载测试] 下载完成: { id: 1234, filename: "...", fileSize: 15234, method: "direct" }
[下载测试] 文件大小分析: { id: 1234, method: "direct", size: 15234, likelyValid: true }
```

### 手动测试步骤

1. **加载修改后的扩展**
   - 打开 `chrome://extensions/`
   - 重新加载海康下载器

2. **登录海康平台**
   - 访问 https://ai.hikvision.com
   - 使用账号登录

3. **导航到数据集页面**
   - 进入有图片的数据集
   - 例如：`#/overall/100149930/100240402/gallery`

4. **浏览图片**
   - 点击图片列表中的图片
   - 插件会自动拦截 URL 并触发三种下载方式

5. **验证结果**
   - 检查下载文件夹：`hikvision_datasets/`
   - 对比三个子文件夹中的文件大小和格式
   - 查看控制台输出分析结果

---

*最后更新: 2026-03-14 (新增自动化测试 - 三种下载方式对比)*
