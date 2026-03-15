// 注入到页面的脚本 - 用于拦截API请求
// 通过postMessage与content script通信

(function() {
  'use strict';

  console.log('[海康下载器] 注入脚本已加载');

  // 发送数据到content script
  function sendToContent(api, response) {
    window.postMessage({
      type: 'HIKVISION_API_RESPONSE',
      api: api,
      response: response,
      timestamp: Date.now()
    }, '*');
  }

  // 拦截fetch
  const originalFetch = window.fetch;
  window.fetch = async function(...args) {
    const [url, config] = args;
    const fullUrl = url.toString();
    const response = await originalFetch.apply(this, args);

    if (fullUrl.includes('/file/offset-list/query') ||
        fullUrl.includes('/files/targets/query') ||
        fullUrl.includes('/label-status/statistic')) {

      console.log('[海康下载器] 拦截到fetch:', fullUrl);

      try {
        const clone = response.clone();
        const data = await clone.json();
        console.log('[海康下载器] fetch响应:', data);
        sendToContent(fullUrl, data);
      } catch (e) {
        console.log('[海康下载器] fetch解析失败:', e.message);
      }
    }

    return response;
  };

  // 拦截XHR
  const originalXHROpen = XMLHttpRequest.prototype.open;
  const originalXHRSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this._url = url;
    this._method = method;
    return originalXHROpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function(...args) {
    const xhr = this;

    xhr.addEventListener('load', function() {
      const url = xhr._url || '';

      if (url.includes('/file/offset-list/query') ||
          url.includes('/files/targets/query') ||
          url.includes('/label-status/statistic')) {

        console.log('[海康下载器] 拦截到XHR:', url);

        try {
          const data = JSON.parse(xhr.responseText);
          console.log('[海康下载器] XHR响应:', data);
          sendToContent(url, data);
        } catch (e) {
          console.log('[海康下载器] XHR解析失败:', e.message);
        }
      }
    });

    return originalXHRSend.apply(this, args);
  };

  // 监听来自content script的获取标注请求
  window.addEventListener('message', function(e) {
    if (e.source !== window) return;
    if (!e.data || e.data.type !== 'HIKVISION_FETCH_ANNOTATIONS') return;

    console.log('[海康下载器] 收到获取标注请求:', e.data.fileIds.length, '张图片');

    // 由于无法直接调用平台API（需要认证），这里记录请求
    // 实际标注数据需要用户点击图片触发平台自动请求
    console.log('[海康下载器] 提示：请点击图片查看详情以触发标注数据加载');
  });

  // 监听来自content script的图片下载请求
  window.addEventListener('message', async function(e) {
    if (e.source !== window) return;
    if (!e.data || e.data.type !== 'HIKVISION_DOWNLOAD_IMAGE') return;

    const { url, fileId } = e.data;
    console.log('[海康下载器] 收到下载请求:', fileId, url.substring(0, 80) + '...');

    try {
      // 在页面上下文中 fetch（天然携带所有 Cookie）
      const response = await fetch(url, {
        headers: { 'Accept': 'image/*,*/*' }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const blob = await response.blob();
      console.log('[海康下载器] 获取到 Blob:', blob.size, 'bytes, type:', blob.type);

      if (blob.size < 100) {
        throw new Error(`Blob too small (${blob.size} bytes)`);
      }

      // 转换为 Data URL
      const reader = new FileReader();
      reader.onloadend = () => {
        console.log('[海康下载器] 转换为 Data URL, 长度:', reader.result.length);
        window.postMessage({
          type: 'HIKVISION_DOWNLOAD_RESULT',
          fileId: fileId,
          dataUrl: reader.result,
          success: true
        }, '*');
      };
      reader.onerror = (err) => {
        console.error('[海康下载器] FileReader 错误:', err);
        window.postMessage({
          type: 'HIKVISION_DOWNLOAD_RESULT',
          fileId: fileId,
          error: 'FileReader failed',
          success: false
        }, '*');
      };
      reader.readAsDataURL(blob);
    } catch (err) {
      console.error('[海康下载器] 下载失败:', err.message);
      window.postMessage({
        type: 'HIKVISION_DOWNLOAD_RESULT',
        fileId: fileId,
        error: err.message,
        success: false
      }, '*');
    }
  });

  // 拦截图片加载请求（img标签的src）
  const originalImageDescriptor = Object.getOwnPropertyDescriptor(Image.prototype, 'src');
  Object.defineProperty(Image.prototype, 'src', {
    set: function(url) {
      if (url && url.includes('oss-cn-hangzhou.aliyuncs.com') &&
          url.includes('/img/') && !url.includes('/imgthumbnail/')) {
        console.log('[海康下载器] 拦截到图片URL:', url.substring(0, 100) + '...');
        // 发送真实图片URL到content script
        window.postMessage({
          type: 'HIKVISION_IMAGE_URL',
          url: url,
          timestamp: Date.now()
        }, '*');
      }
      return originalImageDescriptor.set.call(this, url);
    },
    get: function() {
      return originalImageDescriptor.get.call(this);
    }
  });

  // ===== 方案C：捕获页面Base64图片数据 =====

  // 存储已捕获的base64数据，避免重复发送
  const capturedBase64 = new Set();

  // 从元素中提取图片ID
  function extractImgIdFromElement(img) {
    // 尝试从data属性获取
    if (img.dataset && img.dataset.fileId) {
      return img.dataset.fileId;
    }
    if (img.dataset && img.dataset.id) {
      return img.dataset.id;
    }

    // 尝试从父元素获取
    const parent = img.closest('[data-file-id], [data-id], [id]');
    if (parent) {
      return parent.dataset.fileId || parent.dataset.id || parent.id;
    }

    // 尝试从URL参数中提取（如果是通过src设置的）
    const src = img.getAttribute('src');
    if (src && src.includes('oss-cn-hangzhou.aliyuncs.com')) {
      const match = src.match(/\/img\/([a-zA-Z0-9]+)(?:\?|$)/);
      if (match) return match[1];
    }

    // 尝试从页面的全局变量或上下文中获取
    // 海康平台可能会将图片ID存储在React组件的props或state中
    // 尝试访问元素的react属性
    const reactKey = Object.keys(img).find(key => key.startsWith('__reactFiber') || key.startsWith('__reactInternalInstance'));
    if (reactKey) {
      const fiber = img[reactKey];
      if (fiber && fiber.memoizedProps) {
        // 尝试从props中获取ID
        if (fiber.memoizedProps.fileId) return fiber.memoizedProps.fileId;
        if (fiber.memoizedProps.id) return fiber.memoizedProps.id;
        if (fiber.memoizedProps.imgId) return fiber.memoizedProps.imgId;
        if (fiber.memoizedProps.src) {
          const srcMatch = fiber.memoizedProps.src.match(/\/img\/([a-zA-Z0-9]+)(?:\?|$)/);
          if (srcMatch) return srcMatch[1];
        }
      }
      // 尝试从父组件的props中获取
      if (fiber && fiber.return && fiber.return.memoizedProps) {
        if (fiber.return.memoizedProps.fileId) return fiber.return.memoizedProps.fileId;
        if (fiber.return.memoizedProps.id) return fiber.return.memoizedProps.id;
        if (fiber.return.memoizedProps.imgId) return fiber.return.memoizedProps.imgId;
      }
    }

    // 生成一个基于元素位置的临时ID
    return null;
  }

  // 判断是否为缩略图（根据尺寸和数据长度）
  function checkIfThumbnail(img, base64Data) {
    // 策略1：根据base64数据长度判断（最可靠）
    // base64 长度 > 100000（约75KB原始数据）一定是原图
    if (base64Data && base64Data.length > 100000) {
      return false; // 一定是原图，不是缩略图
    }

    // 策略2：根据base64数据长度判断（缩略图通常较小）
    if (base64Data && base64Data.length < 30000) { // 约22KB原始数据
      return true; // 一定是缩略图
    }

    // 策略3：检查图片尺寸（如果已知且较大）
    if (img.width > 0 && img.height > 0) {
      if (img.width >= 800 || img.height >= 600) {
        return false; // 尺寸大，是原图
      }
      if (img.width < 200 && img.height < 200) {
        return true; // 尺寸很小，是缩略图
      }
    }

    // 默认：中等大小的数据（30000-100000）认为是原图
    // 因为缩略图通常很小，而原图经过压缩后也可能在这个范围
    return false;
  }

  // 拦截HTMLImageElement.prototype.setAttribute
  const originalSetAttribute = HTMLImageElement.prototype.setAttribute;
  HTMLImageElement.prototype.setAttribute = function(name, value) {
    if (name === 'src' && value && typeof value === 'string' && value.startsWith('data:image')) {
      // 提取图片ID
      const imgId = extractImgIdFromElement(this);

      // 判断是否为缩略图
      const isThumbnail = checkIfThumbnail(this, value);

      // 使用数据内容的前100个字符作为唯一标识，避免重复捕获
      const contentId = value.substring(0, 100);

      if (!isThumbnail && imgId && !capturedBase64.has(contentId)) {
        capturedBase64.add(contentId);
        console.log('[海康下载器] 捕获原图 base64 (setAttribute):', imgId, '长度:', value.length);
        window.postMessage({
          type: 'HIKVISION_IMAGE_BASE64',
          imgId: imgId,
          base64Data: value,
          isThumbnail: false
        }, '*');
      } else if (isThumbnail) {
        console.log('[海康下载器] 捕获到缩略图，跳过:', imgId || 'unknown', '长度:', value.length);
      }
    }
    return originalSetAttribute.call(this, name, value);
  };

  // 拦截img.src直接赋值
  const originalSrcDescriptor = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
  Object.defineProperty(HTMLImageElement.prototype, 'src', {
    get: function() {
      return originalSrcDescriptor.get.call(this);
    },
    set: function(value) {
      if (value && typeof value === 'string' && value.startsWith('data:image')) {
        // 提取图片ID
        const imgId = extractImgIdFromElement(this);

        // 判断是否为缩略图
        const isThumbnail = checkIfThumbnail(this, value);

        // 使用数据内容的前100个字符作为唯一标识，避免重复捕获
        const contentId = value.substring(0, 100);

        if (!isThumbnail && imgId && !capturedBase64.has(contentId)) {
          capturedBase64.add(contentId);
          console.log('[海康下载器] 捕获原图 base64 (src setter):', imgId, '长度:', value.length);
          window.postMessage({
            type: 'HIKVISION_IMAGE_BASE64',
            imgId: imgId,
            base64Data: value,
            isThumbnail: false
          }, '*');
        } else if (isThumbnail) {
          console.log('[海康下载器] 捕获到缩略图，跳过:', imgId || 'unknown', '长度:', value.length);
        }
      }
      return originalSrcDescriptor.set.call(this, value);
    }
  });

  // 监听DOM中已经存在的和新增的图片元素
  function observeImages() {
    // 处理页面上已存在的图片
    document.querySelectorAll('img[src^="data:image"]').forEach(img => {
      const src = img.getAttribute('src');
      const imgId = extractImgIdFromElement(img);
      const isThumbnail = checkIfThumbnail(img, src);
      const contentId = src.substring(0, 100);

      if (!isThumbnail && imgId && !capturedBase64.has(contentId)) {
        capturedBase64.add(contentId);
        console.log('[海康下载器] 捕获已存在原图 base64:', imgId, '长度:', src.length);
        window.postMessage({
          type: 'HIKVISION_IMAGE_BASE64',
          imgId: imgId,
          base64Data: src,
          isThumbnail: false
        }, '*');
      }
    });
  }

  // 使用MutationObserver监听新增的图片
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === Node.ELEMENT_NODE) {
          // 如果新增的是img元素
          if (node.tagName === 'IMG' && node.src && node.src.startsWith('data:image')) {
            const imgId = extractImgIdFromElement(node);
            const isThumbnail = checkIfThumbnail(node, node.src);
            const contentId = node.src.substring(0, 100);

            if (!isThumbnail && imgId && !capturedBase64.has(contentId)) {
              capturedBase64.add(contentId);
              console.log('[海康下载器] 捕获新增原图 base64:', imgId, '长度:', node.src.length);
              window.postMessage({
                type: 'HIKVISION_IMAGE_BASE64',
                imgId: imgId,
                base64Data: node.src,
                isThumbnail: false
              }, '*');
            }
          }

          // 检查新增元素内部是否有img
          if (node.querySelectorAll) {
            node.querySelectorAll('img[src^="data:image"]').forEach(img => {
              const src = img.getAttribute('src');
              const imgId = extractImgIdFromElement(img);
              const isThumbnail = checkIfThumbnail(img, src);
              const contentId = src.substring(0, 100);

              if (!isThumbnail && imgId && !capturedBase64.has(contentId)) {
                capturedBase64.add(contentId);
                console.log('[海康下载器] 捕获子元素原图 base64:', imgId, '长度:', src.length);
                window.postMessage({
                  type: 'HIKVISION_IMAGE_BASE64',
                  imgId: imgId,
                  base64Data: src,
                  isThumbnail: false
                }, '*');
              }
            });
          }
        }
      });
    });
  });

  // 启动观察器
  observer.observe(document.body || document.documentElement, {
    childList: true,
    subtree: true
  });

  // 初始扫描
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', observeImages);
  } else {
    observeImages();
  }

  console.log('[海康下载器] 拦截器已设置（含图片URL拦截和Base64捕获）');
})();
