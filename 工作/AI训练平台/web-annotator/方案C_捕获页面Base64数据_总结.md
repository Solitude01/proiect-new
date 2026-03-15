# 海康数据集下载器 - 方案C：捕获页面Base64数据

## 方案概述

### 核心思路
**捕获页面已解码的 base64 图片数据**，直接使用页面已经解码好的图片，避免重新从 OSS 下载时遇到的 gzip 解压问题。

```
页面加载图片 → 解码为 base64 → 设置到 img 标签
                      ↓
              插件拦截并存储 base64
                      ↓
              用户下载时直接使用
```

### 为什么这个方案有效
1. **数据已解码**: 页面已经将 gzip 压缩的 OSS 数据解码为原始图片
2. **无需再次请求**: 避免了重复下载和可能的解压问题
3. **直接可用**: base64 数据可以直接用于下载，无需转换
4. **区分原图/缩略图**: 通过数据长度和尺寸智能识别

---

## 文件修改

### 1. `injected.js` - Base64 捕获逻辑

#### 新增功能
- 拦截 `HTMLImageElement.prototype.setAttribute('src', ...)`
- 拦截 `img.src` setter
- 使用 MutationObserver 监听动态添加的图片
- 扫描页面已存在的 base64 图片

#### 关键代码
```javascript
// 判断是否为缩略图
function checkIfThumbnail(img, base64Data) {
  // 策略1: base64 长度 > 100000（约75KB）→ 一定是原图
  if (base64Data && base64Data.length > 100000) {
    return false;
  }
  // 策略2: base64 长度 < 30000（约22KB）→ 一定是缩略图
  if (base64Data && base64Data.length < 30000) {
    return true;
  }
  // 策略3: 检查图片尺寸
  if (img.width > 0 && img.height > 0) {
    if (img.width >= 800 || img.height >= 600) {
      return false;
    }
    if (img.width < 200 && img.height < 200) {
      return true;
    }
  }
  return false;
}

// 提取图片ID（支持React组件）
function extractImgIdFromElement(img) {
  // 1. data 属性
  if (img.dataset && img.dataset.fileId) {
    return img.dataset.fileId;
  }
  // 2. 父元素
  const parent = img.closest('[data-file-id], [data-id], [id]');
  if (parent) {
    return parent.dataset.fileId || parent.dataset.id || parent.id;
  }
  // 3. React fiber props
  const reactKey = Object.keys(img).find(key =>
    key.startsWith('__reactFiber') || key.startsWith('__reactInternalInstance')
  );
  if (reactKey) {
    const fiber = img[reactKey];
    if (fiber && fiber.memoizedProps) {
      if (fiber.memoizedProps.fileId) return fiber.memoizedProps.fileId;
      if (fiber.memoizedProps.id) return fiber.memoizedProps.id;
      if (fiber.memoizedProps.src) {
        const srcMatch = fiber.memoizedProps.src.match(/\/img\/([a-zA-Z0-9]+)(?:\?|$)/);
        if (srcMatch) return srcMatch[1];
      }
    }
  }
  return null;
}
```

---

### 2. `content.js` - Base64 存储与下载

#### 新增存储
```javascript
const base64ImageData = new Map();     // 存储 base64 数据
const pendingBase64Data = new Map();   // 待关联的 base64
```

#### 关联机制
```javascript
function associateBase64WithImage(imgId, base64Data) {
  // 1. 直接通过 imgId 查找
  let img = dataStore.images.get(imgId);

  // 2. 通过数字ID → UUID 映射查找
  if (!img && numericToUuidMap.has(imgId)) {
    const uuidKey = numericToUuidMap.get(imgId);
    img = dataStore.images.get(uuidKey);
  }

  // 3. 尝试所有图片匹配 imgId 字段
  if (!img) {
    for (const [key, value] of dataStore.images.entries()) {
      if (value.imgId === imgId) {
        img = value;
        break;
      }
    }
  }

  if (img) {
    img.base64Data = base64Data;
  } else {
    // 暂存，等待图片数据加载
    pendingBase64Data.set(imgId, base64Data);
  }
}
```

#### 下载优先级
```javascript
async function exportAll() {
  // 预扫描页面上的 base64 图片
  const allDataImages = Array.from(document.querySelectorAll('img[src^="data:image"]'));
  const largeBase64Images = allDataImages.filter(img => img.src.length > 100000);

  for (const img of images) {
    // 1. 优先使用 base64 数据
    if (img.base64Data) {
      await downloadImageWithBase64(img, fileName);
    }
    // 2. 其次使用真实 URL
    else if (img.realUrl) {
      await downloadImageWithFallback(img.realUrl, fileName, folderName);
    }
    // 3. 尝试页面实时获取
    else {
      // 查找页面上最大的 base64 图片
    }
  }
}
```

---

## 解决的问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 下载图片无法查看 | gzip 压缩数据未被正确解压 | 直接使用页面解码后的 base64 |
| 335KB 原图被跳过 | 缩略图判断阈值过低 (<50KB) | 提高阈值：>100KB 一定是原图 |
| imgId 提取失败 | 页面使用 React，无 data 属性 | 访问 React fiber props 提取 |
| base64 无法关联 | ID 不匹配 | 备用机制：自动关联最大 base64 |

---

## 预期控制台输出

### 成功捕获 base64
```
[海康下载器] 捕获原图 base64 (setAttribute): app 长度: 335062
[海康下载器] 存储原图base64: app 长度: 335062
[海康下载器] 关联到待关联的base64数据: xxx.jpg 通过key: app
[海康下载器] 使用base64数据下载: xxx.jpg 长度: 335062
[海康下载器] base64下载成功: xxx.jpg
```

### 缩略图被过滤
```
[海康下载器] 捕获到缩略图，跳过: unknown 长度: 778
[海康下载器] 捕获到缩略图，跳过: unknown 长度: 906
```

---

## 使用说明

1. **打开海康数据集页面**
2. **浏览图片列表** - 插件会自动捕获图片元数据
3. **点击图片查看详情** - 页面会加载原图并解码为 base64
4. **点击"导出全部"按钮** - 插件会：
   - 优先使用捕获的 base64 数据下载
   - 如果没有 base64，使用 Content Script fetch
   - 如果都没有，尝试页面实时获取

---

## 优势

1. **直接可用**: 使用页面已解码的 base64 数据
2. **无需额外请求**: 不依赖网络 fetch
3. **避免压缩问题**: 绕开 gzip 解压问题
4. **智能识别**: 自动区分原图和缩略图
5. **多重备用**: 即使 base64 捕获失败，仍有 URL 下载作为备用

---

## 更新日期

2026-03-14
