// 海康数据集下载器 - Background Service Worker

// 存储真实图片 URL (fileId -> url)
const realImageUrlMap = new Map();

// 下载测试结果跟踪
const downloadTestResults = new Map();

// 已下载URL去重集合（防止无限循环）
const downloadedUrls = new Set();
const DOWNLOAD_COOLDOWN = 60000; // 60秒内不重复下载同一URL

// 安装时初始化
chrome.runtime.onInstalled.addListener(() => {
  console.log('[海康下载器] 插件已安装');
});

// ==================== 下载测试功能 ====================

/**
 * 方式1: 直接下载（测试是否携带Cookie）
 * 预期结果: ❌ "IZ" 格式（不携带Cookie）
 */
async function downloadImageDirect(url, imgId) {
  const filename = `hikvision_datasets/test_direct/img_${imgId}.jpg`;
  try {
    const downloadId = await chrome.downloads.download({
      url: url,
      filename: filename,
      saveAs: false,
      conflictAction: 'uniquify'
    });
    console.log('[下载测试] 直接下载 - 任务创建:', downloadId, 'imgId:', imgId);
    downloadTestResults.set(downloadId, {
      method: 'direct',
      imgId: imgId,
      url: url,
      startTime: Date.now()
    });
    return downloadId;
  } catch (e) {
    console.error('[下载测试] 直接下载失败:', e);
  }
}

/**
 * 方式2: 使用fetch + Data URL（Service Worker中测试，不带credentials）
 * 预期结果: ❌ "IZ" 格式（Service Worker不共享页面Cookie）
 */
async function downloadImageWithFetch(url, imgId) {
  const filename = `hikvision_datasets/test_fetch/img_${imgId}.jpg`;
  try {
    console.log('[下载测试] Fetch下载 - 开始:', imgId);
    const response = await fetch(url);  // 不带 credentials
    const blob = await response.blob();
    console.log('[下载测试] Fetch下载 - Blob获取:', blob.size, 'bytes, type:', blob.type);

    // 使用 FileReader 转换为 Data URL
    const reader = new FileReader();
    reader.onloadend = async () => {
      const dataUrl = reader.result;
      try {
        const downloadId = await chrome.downloads.download({
          url: dataUrl,
          filename: filename,
          saveAs: false,
          conflictAction: 'uniquify'
        });
        console.log('[下载测试] Fetch下载 - 任务创建:', downloadId, 'imgId:', imgId);
        downloadTestResults.set(downloadId, {
          method: 'fetch',
          imgId: imgId,
          url: url,
          blobSize: blob.size,
          blobType: blob.type,
          startTime: Date.now()
        });
      } catch (e) {
        console.error('[下载测试] Fetch下载任务创建失败:', e);
      }
    };
    reader.onerror = (e) => {
      console.error('[下载测试] FileReader错误:', e);
    };
    reader.readAsDataURL(blob);
  } catch (e) {
    console.error('[下载测试] Fetch下载失败:', e);
  }
}

/**
 * 方式3: 通过 content script 下载（携带页面Cookie）
 * 预期结果: ✅ 正常JPEG（携带页面Cookie）
 */
async function downloadViaContentScript(url, imgId, tabId) {
  try {
    console.log('[下载测试] Content下载 - 请求发送到tab:', tabId, 'imgId:', imgId);
    await chrome.tabs.sendMessage(tabId, {
      action: 'downloadTestViaContent',
      url: url,
      imgId: imgId,
      filename: `hikvision_datasets/test_content/img_${imgId}.jpg`
    });
  } catch (e) {
    console.error('[下载测试] Content下载请求发送失败:', e.message);
  }
}

// 监听下载完成事件，验证下载结果
chrome.downloads.onChanged.addListener((delta) => {
  if (delta.state && delta.state.current === 'complete') {
    chrome.downloads.search({ id: delta.id }, (results) => {
      if (results[0]) {
        const item = results[0];
        const testInfo = downloadTestResults.get(delta.id);

        console.log('[下载测试] 下载完成:', {
          id: delta.id,
          filename: item.filename,
          fileSize: item.fileSize,
          method: testInfo?.method || 'unknown',
          imgId: testInfo?.imgId,
          url: item.url?.substring(0, 80) + '...'
        });

        // 分析文件大小判断是否正常
        // 正常JPEG应该 > 1KB，错误页面通常几百字节
        const isLikelyValid = item.fileSize > 1000;
        console.log('[下载测试] 文件大小分析:', {
          id: delta.id,
          method: testInfo?.method,
          size: item.fileSize,
          likelyValid: isLikelyValid,
          reason: isLikelyValid ? '文件较大，可能是正常图片' : '文件太小，可能是错误页面'
        });
      }
    });
  }
});

// ==================== WebRequest 拦截 ====================

// 使用 webRequest API 拦截 OSS 图片请求
chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    const url = details.url;

    // 检查是否是海康 OSS 图片请求（排除缩略图）
    if (url.includes('oss-cn-hangzhou.aliyuncs.com') &&
        url.includes('/img/') &&
        !url.includes('/imgthumbnail/')) {
      // 从 URL 中提取 imgId（包含字母和数字）
      // URL格式: https://saas-trainningdata-test.oss-cn-hangzhou.aliyuncs.com/img/{imgId}?Expires=...
      const match = url.match(/\/img\/([a-zA-Z0-9]+)(?:\?|$)/);
      if (match) {
        const imgId = match[1];
        realImageUrlMap.set(imgId, url);
        console.log('[海康下载器] 拦截到真实图片URL:', imgId, url.substring(0, 80) + '...');

        // 暂时禁用自动下载测试，防止进入页面时疯狂下载
        // 用户需要手动点击"导出全部"按钮来下载图片
        console.log('[海康下载器] URL已记录，等待手动下载:', imgId);

        // 发送到 content script
        chrome.tabs.sendMessage(details.tabId, {
          action: 'realImageUrl',
          fileId: imgId,
          url: url
        }).catch(err => {
          // 可能 content script 还没加载，忽略错误
          console.log('[海康下载器] 发送消息到 content script 失败:', err.message);
        });
      }
    }
  },
  {
    urls: ['*://*.oss-cn-hangzhou.aliyuncs.com/*']
  }
);

console.log('[海康下载器] webRequest 监听器已注册');

// 点击扩展图标时注入content script并切换面板
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.url || !tab.url.includes('ai.hikvision.com')) {
    console.log('[海康下载器] 不在海康平台页面');
    return;
  }

  console.log('[海康下载器] 点击图标，当前页面:', tab.url);

  try {
    // 先尝试发送消息，如果content script已存在则切换面板
    await chrome.tabs.sendMessage(tab.id, { action: 'togglePanel' });
    console.log('[海康下载器] 面板已切换');
  } catch (e) {
    console.log('[海康下载器] Content script未加载，正在注入...', e.message);

    // 注入content script
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['content.js']
      });
      console.log('[海康下载器] Content script已注入');

      // 等待一下确保脚本执行完成
      await new Promise(resolve => setTimeout(resolve, 500));

      // 再次尝试发送消息
      await chrome.tabs.sendMessage(tab.id, { action: 'togglePanel' });
      console.log('[海康下载器] 面板已显示');
    } catch (injectError) {
      console.error('[海康下载器] 注入失败:', injectError);
    }
  }
});

// 处理来自content script和popup的消息
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('[海康下载器] 收到消息:', request.action, '来自:', sender.tab?.url || 'popup');

  switch (request.action) {
    case 'downloadImage':
      downloadImage(request.url, request.filename, request.datasetId)
        .then(result => sendResponse(result))
        .catch(err => sendResponse({ success: false, error: err.message }));
      return true;

    case 'downloadJson':
      downloadJson(request.url, request.filename, request.datasetId)
        .then(result => sendResponse(result))
        .catch(err => sendResponse({ success: false, error: err.message }));
      return true;

    case 'dataUpdated':
      sendResponse({ success: true });
      break;

    default:
      sendResponse({ error: '未知操作' });
  }

  return true;
});

// 存储当前数据集信息用于构建文件夹路径
let currentDatasetInfo = {
  datasetId: null,
  timestamp: null
};

// 下载单个图片
async function downloadImage(url, filename, datasetId) {
  console.log('[海康下载器] 开始下载:', url, '文件名:', filename);

  // 检查URL
  if (!url) {
    return { success: false, error: 'URL为空' };
  }

  if (!url.startsWith('http://') && !url.startsWith('https://') && !url.startsWith('data:')) {
    return { success: false, error: 'Invalid URL: ' + url.substring(0, 100) };
  }

  // 确保文件名有扩展名（只检查文件名部分，忽略路径）
  let finalFilename = filename;
  const filenameWithoutPath = finalFilename ? finalFilename.replace(/^.*[\\/]/, '') : '';
  if (!finalFilename || !/\.(jpg|jpeg|png|gif|webp|bmp)$/i.test(filenameWithoutPath)) {
    // 尝试从URL提取
    const urlMatch = url.match(/\/([^\/]+\.(jpg|jpeg|png|gif|webp|bmp))/i);
    if (urlMatch) {
      // 保留路径前缀，只替换文件名部分
      const pathPrefix = finalFilename ? finalFilename.replace(/[^\/]*$/, '') : '';
      finalFilename = pathPrefix + urlMatch[1];
    } else {
      finalFilename = `images/image_${Date.now()}.jpg`;
    }
    console.log('[海康下载器] 文件名补全为:', finalFilename);
  }

  // 使用数据集ID构建文件夹路径
  const folderName = datasetId || 'dataset_export';
  // 确保finalFilename不以images/开头（避免重复）
  const cleanFilename = finalFilename.replace(/^images\//, '');
  const fullPath = `hikvision_datasets/${folderName}/images/${cleanFilename}`;

  console.log('[海康下载器] 完整下载路径:', fullPath);
  console.log('[海康下载器] 文件夹:', folderName, '文件名:', cleanFilename);

  try {
    // 检查 URL 是否为 data URL（content.js 已处理 fetch）
    const isDataUrl = url.startsWith('data:');
    console.log('[海康下载器] URL 类型:', isDataUrl ? 'Data URL' : '普通 URL');

    // 使用 chrome.downloads 下载
    const downloadId = await chrome.downloads.download({
      url: url,
      filename: fullPath,
      saveAs: false,
      conflictAction: 'uniquify'
    });

    console.log('[海康下载器] 下载任务已创建:', downloadId);
    return { success: true, downloadId };
  } catch (error) {
    console.error('[海康下载器] 下载失败:', url.substring(0, 100) + '...', error);
    return { success: false, error: error.message };
  }
}

// 下载JSON文件
async function downloadJson(url, filename, datasetId) {
  console.log('[海康下载器] 开始下载JSON:', filename, '到文件夹:', datasetId);

  const folderName = datasetId || 'dataset_export';
  const fullPath = `hikvision_datasets/${folderName}/${filename}`;
  console.log('[海康下载器] JSON完整路径:', fullPath);

  try {
    const downloadId = await chrome.downloads.download({
      url: url,
      filename: fullPath,
      saveAs: false,
      conflictAction: 'uniquify'
    });

    console.log('[海康下载器] JSON下载任务已创建:', downloadId, '路径:', fullPath);
    return { success: true, downloadId };
  } catch (error) {
    console.error('[海康下载器] JSON下载失败:', error);
    return { success: false, error: error.message };
  }
}

console.log('[海康下载器] Background script 已加载');
