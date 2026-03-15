// 海康AI训练平台数据捕获器
// 直接在content script中拦截，不依赖页面注入

(function() {
  'use strict';

  console.log('[海康下载器] Content script 加载');

  // 数据存储
  const dataStore = {
    images: new Map(),
    annotations: new Map(),
    datasetId: null,
    versionId: null,
    datasetName: '',
    statistics: { totalFiles: 0, labeledFiles: 0, validLabeledFiles: 0 }
  };

  // 存储真实图片URL（从OSS获取的带签名URL）
  const realImageUrls = new Map();

  // 存储待关联的真实URL（当URL到达时图片元数据尚未加载）
  const pendingRealUrls = new Map();

  // 存储数字ID到UUID的映射（解决ID格式不匹配问题）
  const numericToUuidMap = new Map();

  // 存储base64图片数据（方案C：捕获页面Base64数据）
  const base64ImageData = new Map();

  // 存储待关联的base64数据
  const pendingBase64Data = new Map();

  // 将 Blob 转换为 Data URL
  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  // 通过 injected.js 在页面上下文中下载图片
  function downloadImageViaInjected(url, fileId) {
    return new Promise((resolve, reject) => {
      // 监听返回结果
      const handler = (e) => {
        if (e.source !== window) return;
        if (e.data?.type === 'HIKVISION_DOWNLOAD_RESULT' && e.data.fileId === fileId) {
          window.removeEventListener('message', handler);
          if (e.data.success) {
            resolve(e.data.dataUrl);
          } else {
            reject(new Error(e.data.error || '下载失败'));
          }
        }
      };
      window.addEventListener('message', handler);

      // 发送下载请求到 injected.js
      window.postMessage({
        type: 'HIKVISION_DOWNLOAD_IMAGE',
        url: url,
        fileId: fileId
      }, '*');

      // 超时处理
      setTimeout(() => {
        window.removeEventListener('message', handler);
        reject(new Error('下载超时'));
      }, 30000);
    });
  }

  // 提取数据集ID
  function extractDatasetInfo() {
    const url = window.location.href;
    let match = url.match(/#\/overall\/(\d+)\/(\d+)/);
    if (match) return { datasetId: match[1], versionId: match[2] };
    match = url.match(/\/datasets\/(\d+)\/(\d+)/);
    if (match) return { datasetId: match[1], versionId: match[2] };
    return null;
  }

  // 通过script标签注入拦截代码（使用src而不是inline）
  function setupInterceptors() {
    const script = document.createElement('script');
    script.src = chrome.runtime.getURL('injected.js');
    script.onload = function() {
      this.remove();
    };
    (document.head || document.documentElement).appendChild(script);
  }

  // 监听来自注入脚本的消息
  window.addEventListener('message', function(e) {
    if (e.source !== window) return;
    if (!e.data || !e.data.type) return;

    if (e.data.type === 'HIKVISION_API_RESPONSE') {
      console.log('[海康下载器] 收到API响应:', e.data.api);

      const data = e.data.response;

      if (e.data.api.includes('/file/offset-list/query')) {
        handleImageList(data.data || data);
      }
      if (e.data.api.includes('/files/targets/query')) {
        handleAnnotations(data.data || data);
      }
      if (e.data.api.includes('/label-status/statistic')) {
        handleStatistics(data.data || data);
      }
    }

    // 监听真实图片URL
    if (e.data.type === 'HIKVISION_IMAGE_URL') {
      handleRealImageUrl(e.data.url);
    }

    // 监听base64图片数据（方案C）
    if (e.data.type === 'HIKVISION_IMAGE_BASE64') {
      handleBase64ImageData(e.data);
    }
  });

  // 处理真实图片URL
  function handleRealImageUrl(url) {
    if (!url) return;

    // 从URL中提取imgId（包含字母和数字）
    // URL格式: https://saas-trainningdata-test.oss-cn-hangzhou.aliyuncs.com/img/{imgId}?Expires=...
    const match = url.match(/\/img\/([a-zA-Z0-9]+)(?:\?|$)/);
    if (!match) return;

    const numericId = match[1];
    realImageUrls.set(numericId, url);

    // 调试日志
    console.log('[海康下载器] 收到真实URL，numericId:', numericId);
    console.log('[海康下载器] dataStore keys:', Array.from(dataStore.images.keys()));
    console.log('[海康下载器] ID映射表:', Array.from(numericToUuidMap.entries()));

    // 先尝试直接用数字ID查找（兼容旧情况）
    let img = dataStore.images.get(numericId);

    // 如果没找到，尝试通过映射查找（数字ID -> UUID）
    if (!img && numericToUuidMap.has(numericId)) {
      const uuidKey = numericToUuidMap.get(numericId);
      img = dataStore.images.get(uuidKey);
      console.log('[海康下载器] 通过映射找到图片:', numericId, '->', uuidKey, img ? '成功' : '失败');
    }

    if (img) {
      img.realUrl = url;
      console.log('[海康下载器] 已关联真实URL到图片:', img.fileName);
      updateRealUrlCount();
      return;
    }

    // 如果图片尚未加载，暂存URL，稍后重试
    console.log('[海康下载器] 收到真实URL但图片尚未加载，numericId:', numericId, '等待映射建立');
    pendingRealUrls.set(numericId, url);

    // 设置延迟重试（1秒后）- 此时映射应该已建立
    setTimeout(() => {
      let img = dataStore.images.get(numericId);
      if (!img && numericToUuidMap.has(numericId)) {
        img = dataStore.images.get(numericToUuidMap.get(numericId));
      }
      if (img && pendingRealUrls.has(numericId)) {
        img.realUrl = pendingRealUrls.get(numericId);
        pendingRealUrls.delete(numericId);
        console.log('[海康下载器] 延迟关联成功:', img.fileName);
        updateRealUrlCount();
      }
    }, 1000);

    // 更新面板显示待关联数量
    updateRealUrlCount();
  }

  // 处理base64图片数据（方案C）
  function handleBase64ImageData(data) {
    const { imgId, base64Data, isThumbnail } = data;

    if (isThumbnail) {
      console.log('[海康下载器] 忽略缩略图base64:', imgId);
      return;
    }

    if (!imgId) {
      console.log('[海康下载器] base64数据没有imgId，尝试其他方式关联...');
      // 尝试用base64数据本身作为临时key存储
      const tempId = 'base64_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      base64ImageData.set(tempId, base64Data);
      pendingBase64Data.set(tempId, base64Data);
      console.log('[海康下载器] 使用临时ID存储base64:', tempId, '长度:', base64Data.length);
      return;
    }

    // 存储base64数据
    base64ImageData.set(imgId, base64Data);
    console.log('[海康下载器] 存储原图base64:', imgId, '长度:', base64Data.length);

    // 尝试关联到图片
    associateBase64WithImage(imgId, base64Data);
  }

  // 关联base64数据到图片对象
  function associateBase64WithImage(imgId, base64Data) {
    // 先尝试直接用imgId查找
    let img = dataStore.images.get(imgId);

    // 如果没找到，尝试通过映射查找（数字ID -> UUID）
    if (!img && numericToUuidMap.has(imgId)) {
      const uuidKey = numericToUuidMap.get(imgId);
      img = dataStore.images.get(uuidKey);
    }

    // 尝试所有图片，匹配imgId字段
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
      console.log('[海康下载器] 已关联base64到图片:', img.fileName);
      updateBase64Count();
    } else {
      // 暂存，等待图片数据加载
      pendingBase64Data.set(imgId, base64Data);
      console.log('[海康下载器] base64数据暂存，等待图片加载:', imgId);
    }
  }

  // 更新base64数据计数显示
  function updateBase64Count() {
    const statusEl = document.getElementById('hikv-status');
    if (statusEl) {
      const base64Count = Array.from(dataStore.images.values()).filter(img => img.base64Data).length;
      const realUrlCount = Array.from(dataStore.images.values()).filter(img => img.realUrl).length;
      const pendingCount = pendingBase64Data.size;

      let statusText = `数据集共 ${dataStore.statistics.totalFiles} 张，已标注 ${dataStore.statistics.labeledFiles} 张`;
      if (base64Count > 0) {
        statusText += `<br>有base64数据: ${base64Count} 张`;
      } else if (realUrlCount > 0) {
        statusText += `<br>可下载: ${realUrlCount} 张`;
      }
      if (pendingCount > 0) {
        statusText += `<br>待关联base64: ${pendingCount} 张`;
      }

      statusEl.innerHTML = statusText;
      statusEl.style.color = base64Count > 0 || realUrlCount > 0 ? '#34a853' : '#999';
    }

    // 更新状态信息
    updateStatusInfo();
  }

  // 更新真实URL数量显示
  function updateRealUrlCount() {
    const statusEl = document.getElementById('hikv-status');
    if (statusEl) {
      const realUrlCount = Array.from(dataStore.images.values()).filter(img => img.realUrl).length;
      const base64Count = Array.from(dataStore.images.values()).filter(img => img.base64Data).length;
      const pendingCount = pendingRealUrls.size;
      const pendingBase64Count = pendingBase64Data.size;

      let statusText = `数据集共 ${dataStore.statistics.totalFiles} 张，已标注 ${dataStore.statistics.labeledFiles} 张`;
      if (dataStore.images.size > 0) {
        statusText += `<br>已累积: ${dataStore.images.size} 张`;
      }
      if (base64Count > 0) {
        statusText += ` | base64: ${base64Count}`;
      }
      if (realUrlCount > 0) {
        statusText += ` | URL: ${realUrlCount}`;
      }
      if (pendingCount > 0 || pendingBase64Count > 0) {
        statusText += `<br>待关联: ${pendingCount + pendingBase64Count} 张`;
      }

      statusEl.innerHTML = statusText;
      statusEl.style.color = (realUrlCount > 0 || base64Count > 0) ? '#34a853' : '#999';
    }

    // 更新状态信息
    updateStatusInfo();
  }

  // 更新状态信息显示
  function updateStatusInfo() {
    const infoEl = document.getElementById('hikv-info');
    if (infoEl) {
      const pendingCount = pendingRealUrls.size;
      const pendingBase64Count = pendingBase64Data.size;
      const realUrlCount = Array.from(dataStore.images.values()).filter(img => img.realUrl).length;
      const base64Count = Array.from(dataStore.images.values()).filter(img => img.base64Data).length;
      const totalImages = dataStore.images.size;
      const withDownloadData = base64Count + realUrlCount;

      if (totalImages === 0) {
        infoEl.innerHTML = '💡 请先浏览图片列表以加载数据';
        infoEl.style.color = '#999';
      } else if (withDownloadData === 0) {
        infoEl.innerHTML = '💡 点击图片查看详情以获取下载数据';
        infoEl.style.color = '#ff9800';
      } else if (withDownloadData < totalImages) {
        infoEl.innerHTML = `⚠️ 可下载 ${withDownloadData}/${totalImages} 张，继续点击图片获取剩余数据`;
        infoEl.style.color = '#ff9800';
      } else {
        infoEl.innerHTML = `✅ ${withDownloadData} 张图片可下载`;
        infoEl.style.color = '#34a853';
      }
    }
  }

  // 处理图片列表
  function handleImageList(data) {
    console.log('[海康下载器] handleImageList 被调用:', data);
    if (!data) {
      console.log('[海康下载器] 图片数据为空');
      return;
    }

    const items = Array.isArray(data) ? data : (data.list || data.records || []);
    console.log('[海康下载器] 图片数量:', items.length);

    // 调试：打印第一张图片的完整数据结构
    if (items.length > 0) {
      console.log('[海康下载器] 第一张图片完整数据:', JSON.stringify(items[0], null, 2));
    }

    // 统计新增和更新的数量
    let addedCount = 0;
    let updatedCount = 0;

    items.forEach(item => {
      if (item.id) {
        // 检查是否已存在（去重）
        const existingImg = dataStore.images.get(item.id);
        if (existingImg) {
          console.log('[海康下载器] 图片已存在，更新数据:', item.id);
          // 保留已有的 base64Data 和 realUrl
          // 只更新基本元数据
          existingImg.width = item.frameWidth || item.width || existingImg.width;
          existingImg.height = item.frameHeight || item.height || existingImg.height;
          existingImg.fileName = item.fileName || existingImg.fileName;
          updatedCount++;
          return;
        }

        // cloudUrl 可能是 base64 缩略图，保存但标记为缩略图
        let cloudUrl = item.cloudUrl;
        const isBase64Thumbnail = cloudUrl && cloudUrl.startsWith('data:');

        if (cloudUrl && !cloudUrl.startsWith('http') && !isBase64Thumbnail) {
          cloudUrl = 'https://' + cloudUrl;
        }

        // 提取文件名（如果没有fileName，从URL中提取）
        let fileName = item.fileName;

        // 确保文件名有扩展名
        const hasExtension = fileName && /\.(jpg|jpeg|png|gif|webp|bmp)$/i.test(fileName);

        if (!fileName || !hasExtension) {
          if (cloudUrl && !isBase64Thumbnail) {
            // 尝试从URL中提取带扩展名的文件名
            const match = cloudUrl.match(/\/([^\/]+\.(jpg|jpeg|png|gif|webp|bmp))/i);
            if (match) {
              fileName = match[1];
            } else {
              // 如果URL中没有扩展名，使用item.id并添加.jpg
              fileName = `image_${item.id}.jpg`;
            }
          } else {
            fileName = `image_${item.id}.jpg`;
          }
        }

        // 从 cloudUrl 中提取 imgId（用于关联真实图片URL）
        let imgId = null;
        if (cloudUrl && !isBase64Thumbnail) {
          // 尝试从URL中提取 imgId
          // URL格式: https://.../img/{imgId}?...
          const imgIdMatch = cloudUrl.match(/\/img\/([a-zA-Z0-9]+)(?:\?|$)/);
          if (imgIdMatch) {
            imgId = imgIdMatch[1];
            console.log('[海康下载器] 从cloudUrl提取到imgId:', imgId);
          }
        }

        // 如果 imgId 是数字格式，建立数字ID到UUID的映射
        if (imgId && /^\d+$/.test(imgId)) {
          numericToUuidMap.set(imgId, item.id);
          console.log('[海康下载器] 建立ID映射:', imgId, '->', item.id);
        }

        // 使用 item.id（UUID）作为存储 key，保持一致性
        const storeKey = item.id;

        // 检查是否已有真实URL（从之前拦截的或待关联的）
        // 优先通过数字ID映射查找
        let realUrl = null;
        if (imgId && numericToUuidMap.has(imgId)) {
          realUrl = realImageUrls.get(imgId);
        }
        // 再尝试直接用UUID查找
        if (!realUrl) {
          realUrl = realImageUrls.get(item.id);
        }

        // 检查是否有待关联的真实URL（通过数字ID）
        if (!realUrl && imgId && pendingRealUrls.has(imgId)) {
          realUrl = pendingRealUrls.get(imgId);
          pendingRealUrls.delete(imgId);
          console.log('[海康下载器] 关联到已存在的真实URL:', fileName, '通过imgId:', imgId);
        }

        // 检查是否有待关联的base64数据（通过数字ID或imgId）
        let base64Data = null;
        if (imgId && pendingBase64Data.has(imgId)) {
          base64Data = pendingBase64Data.get(imgId);
          pendingBase64Data.delete(imgId);
          console.log('[海康下载器] 关联到已存在的base64数据:', fileName, '通过imgId:', imgId);
        }

        // 如果没有找到，尝试匹配所有待关联的base64数据（取第一个足够大的）
        if (!base64Data && pendingBase64Data.size > 0) {
          for (const [key, value] of pendingBase64Data.entries()) {
            if (value.length > 50000) { // 只考虑较大的base64数据
              base64Data = value;
              pendingBase64Data.delete(key);
              console.log('[海康下载器] 关联到待关联的base64数据:', fileName, '通过key:', key);
              break;
            }
          }
        }

        dataStore.images.set(item.id, {
          id: item.id,
          imgId: imgId,
          fileName: fileName,
          cloudUrl: cloudUrl,
          realUrl: realUrl || null,
          base64Data: base64Data,
          isBase64Thumbnail: isBase64Thumbnail,
          width: item.frameWidth || item.width,
          height: item.frameHeight || item.height,
          annotations: dataStore.annotations.get(item.id) || []
        });

        addedCount++;
        console.log('[海康下载器] 图片数据已存储，key:', item.id, '当前总数:', dataStore.images.size);
        console.log('[海康下载器] 添加图片:', item.id, fileName, imgId ? `(imgId: ${imgId})` : '', isBase64Thumbnail ? '(base64缩略图)' : '');
      }
    });

    console.log(`[海康下载器] 本次处理: 新增 ${addedCount} 张, 更新 ${updatedCount} 张`);

    const info = extractDatasetInfo();
    if (info) {
      dataStore.datasetId = info.datasetId;
      dataStore.versionId = info.versionId;
    }

    console.log('[海康下载器] 当前总图片数:', dataStore.images.size);
    updatePanel();
    updateRealUrlCount();
  }

  // 处理标注
  function handleAnnotations(data) {
    console.log('[海康下载器] handleAnnotations 被调用:', data);
    if (!data) {
      console.log('[海康下载器] 标注数据为空');
      return;
    }

    // 处理不同格式的响应
    let items = [];
    if (Array.isArray(data)) {
      items = data;
    } else if (data.list) {
      items = data.list;
    } else if (data.data) {
      items = Array.isArray(data.data) ? data.data : [data.data];
    }

    console.log('[海康下载器] 标注数据项数:', items.length);

    items.forEach(item => {
      if (item.fileId) {
        // 处理 formData 或 targets 或 annotations
        const anns = item.formData || item.targets || item.annotations || [];
        console.log('[海康下载器] 图片标注:', item.fileId, '标注数:', anns.length);
        dataStore.annotations.set(item.fileId, anns);

        // 遍历所有图片，找到 id 匹配的图片（因为现在图片可能使用 imgId 作为 key）
        let found = false;
        for (const [key, img] of dataStore.images.entries()) {
          if (img.id === item.fileId) {
            img.annotations = anns;
            console.log('[海康下载器] 已关联标注到图片:', img.fileName);
            found = true;
            break;
          }
        }

        if (!found) {
          console.log('[海康下载器] 未找到对应图片:', item.fileId);
        }
      }
    });

    updatePanel();
  }

  // 处理统计
  function handleStatistics(data) {
    if (!data) return;
    dataStore.statistics = {
      totalFiles: data.fileNum || 0,
      labeledFiles: data.labelFileNum || 0,
      validLabeledFiles: data.validLabelFileNum || 0
    };
    updatePanel();
  }

  // 更新面板
  function updatePanel() {
    const countEl = document.getElementById('hikv-count');
    if (countEl) countEl.textContent = dataStore.images.size;

    const annotatedEl = document.getElementById('hikv-annotated');
    if (annotatedEl) annotatedEl.textContent = getAnnotatedCount();

    // 更新统计信息
    const statsEl = document.getElementById('hikv-stats');
    if (statsEl) {
      const images = Array.from(dataStore.images.values());
      const annotatedCount = images.filter(img => img.annotations && img.annotations.length > 0).length;
      const withBase64 = images.filter(img => img.base64Data).length;
      const withRealUrl = images.filter(img => img.realUrl).length;
      const withImageData = withBase64 + withRealUrl;

      statsEl.textContent = `已标注: ${annotatedCount} | 有图片: ${withImageData} (base64:${withBase64}, url:${withRealUrl})`;
    }

    updateRealUrlCount();
  }

  // 计算有标注的图片数
  function getAnnotatedCount() {
    let count = 0;
    dataStore.images.forEach(img => {
      if (img.annotations && img.annotations.length > 0) count++;
    });
    return count;
  }

  // 辅助函数：根据图片文件名生成标注文件名
  function getAnnotationFileName(imageFileName, imageId) {
    console.log('[海康下载器] 生成标注文件名, imageFileName:', imageFileName, 'imageId:', imageId);

    if (!imageFileName) {
      // 只有没有文件名时才使用 imageId
      const fallbackName = `image_${imageId || 'unknown'}.json`;
      console.log('[海康下载器] 无文件名，使用回退名称:', fallbackName);
      return fallbackName;
    }

    // 提取文件名（不含路径）
    const baseName = imageFileName.replace(/^.*[\\/]/, '');

    // 将图片扩展名替换为 .json
    const jsonName = baseName.replace(/\.(jpg|jpeg|png|gif|webp|bmp)$/i, '.json');

    // 如果替换失败（没有匹配到图片扩展名），强制添加.json
    if (jsonName === baseName) {
      const result = `${baseName}.json`;
      console.log('[海康下载器] 生成的标注文件名(无扩展名):', result);
      return result;
    }

    console.log('[海康下载器] 生成的标注文件名:', jsonName);
    return jsonName;
  }

  // 清空所有数据
  function clearAllData() {
    dataStore.images.clear();
    dataStore.annotations.clear();
    realImageUrls.clear();
    pendingRealUrls.clear();
    numericToUuidMap.clear();
    base64ImageData.clear();
    pendingBase64Data.clear();
    updatePanel();
    console.log('[海康下载器] 所有数据已清空');
    alert('数据已清空！当前图片数: 0');
  }

  // 辅助函数：导出汇总文件
  async function exportSummaryFile(images, folderName, timestamp) {
    const summaryData = {
      datasetId: dataStore.datasetId,
      versionId: dataStore.versionId,
      exportTime: new Date().toISOString(),
      totalImages: images.length,
      annotatedImages: images.filter(img => img.annotations && img.annotations.length > 0).length,
      imageList: images.map(img => ({
        id: img.id,
        fileName: img.fileName,
        annotationFile: getAnnotationFileName(img.fileName, img.id),
        annotationCount: (img.annotations || []).length
      }))
    };

    const jsonContent = JSON.stringify(summaryData, null, 2);
    const blob = new Blob([jsonContent], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    try {
      await chrome.runtime.sendMessage({
        action: 'downloadJson',
        url: url,
        filename: `summary_${timestamp}.json`,
        datasetId: folderName
      });
    } catch (e) {
      console.error('[海康下载器] 汇总文件导出失败:', e);
    }

    URL.revokeObjectURL(url);
  }

  // 导出数据 - 每张图片一个独立的标注文件
  async function exportData() {
    const images = Array.from(dataStore.images.values());
    const folderName = dataStore.datasetId || 'dataset_export';
    const timestamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');

    let successCount = 0;
    let failedCount = 0;

    // 遍历每张图片，导出独立的标注文件
    for (const img of images) {
      // 生成标注文件名（与图片文件名对应，扩展名改为.json）
      const annotationFileName = getAnnotationFileName(img.fileName, img.id);

      // 构建单张图片的标注数据
      const singleAnnotationData = {
        datasetId: dataStore.datasetId,
        versionId: dataStore.versionId,
        exportTime: new Date().toISOString(),
        image: {
          id: img.id,
          fileName: img.fileName,
          width: img.width,
          height: img.height,
          annotationCount: (img.annotations || []).length
        },
        annotations: img.annotations || []
      };

      // 创建 Blob 和 URL
      const jsonContent = JSON.stringify(singleAnnotationData, null, 2);
      const blob = new Blob([jsonContent], { type: 'application/json' });
      const url = URL.createObjectURL(blob);

      try {
        // 下载单个标注文件到 annotations/ 子文件夹
        await chrome.runtime.sendMessage({
          action: 'downloadJson',
          url: url,
          filename: `annotations/${annotationFileName}`,
          datasetId: folderName
        });
        successCount++;
        console.log(`[海康下载器] 标注已导出: ${annotationFileName}`);
      } catch (e) {
        failedCount++;
        console.error(`[海康下载器] 导出失败: ${annotationFileName}`, e);

        // 使用备用下载方式
        const a = document.createElement('a');
        a.href = url;
        a.download = annotationFileName;
        a.click();
      }

      URL.revokeObjectURL(url);

      // 添加小延迟避免请求过快
      await new Promise(resolve => setTimeout(resolve, 50));
    }

    // 同时导出一个汇总文件
    await exportSummaryFile(images, folderName, timestamp);

    const annotated = getAnnotatedCount();
    console.log(`[海康下载器] 标注导出完成: ${successCount} 成功, ${failedCount} 失败`);
    alert(`标注导出完成!\n保存位置: hikvision_datasets/${folderName}/annotations/\n成功: ${successCount} 个文件\n有标注图片: ${annotated} 张`);

    return folderName;
  }

  // 下载图片 - 使用Content Script fetch（最可靠的方式）
  async function downloadImageWithFallback(url, fileName, folderName) {
    // 直接使用 Content Script 下载（避免chrome.downloads.download()获取gzip压缩数据）
    try {
      console.log('[海康下载器] 使用Content Script下载图片...');
      console.log('[海康下载器] URL:', url.substring(0, 80) + '...');

      const response = await fetch(url, {
        headers: { 'Accept': 'image/*,*/*' }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const blob = await response.blob();
      console.log('[海康下载器] 获取到 Blob:', blob.size, 'bytes, type:', blob.type);

      if (blob.size < 100) {
        throw new Error(`Blob too small (${blob.size} bytes)`);
      }

      // 检查是否是gzip压缩（通过读取前几个字节）
      const firstBytes = await blob.slice(0, 2).text();
      if (firstBytes.charCodeAt(0) === 0x1F && firstBytes.charCodeAt(1) === 0x8B) {
        console.warn('[海康下载器] 警告: 获取到gzip压缩数据，尝试解压...');
        // 如果浏览器自动解压失败，这是一个问题
        // 但通常fetch会自动处理gzip解压
      }

      // 创建 Blob URL 并直接下载
      const blobUrl = URL.createObjectURL(blob);

      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);

      // 延迟释放 Blob URL
      setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);

      console.log('[海康下载器] Content Script下载成功:', fileName);
      return { success: true, method: 'content-script' };
    } catch (e) {
      console.error('[海康下载器] Content Script下载失败:', e.message);
      return { success: false, error: e.message };
    }
  }

  // 使用base64数据下载图片（方案C）
  async function downloadImageWithBase64(img, fileName) {
    if (!img.base64Data) {
      return { success: false, error: 'No base64 data available' };
    }

    try {
      console.log('[海康下载器] 使用base64数据下载:', fileName, '长度:', img.base64Data.length);
      console.log('[海康下载器] base64前100字符:', img.base64Data.substring(0, 100));

      // 验证base64数据格式
      if (!img.base64Data.startsWith('data:image')) {
        console.error('[海康下载器] base64数据格式不正确，缺少data:image前缀');
        return { success: false, error: 'Invalid base64 format' };
      }

      // base64数据已经是Data URL格式，直接下载
      const a = document.createElement('a');
      a.href = img.base64Data;
      a.download = fileName;
      a.style.display = 'none';
      document.body.appendChild(a);

      // 使用setTimeout确保点击事件被处理
      setTimeout(() => {
        a.click();
        setTimeout(() => {
          document.body.removeChild(a);
        }, 100);
      }, 0);

      console.log('[海康下载器] base64下载触发成功:', fileName);
      return { success: true, method: 'base64' };
    } catch (e) {
      console.error('[海康下载器] base64下载失败:', e.message);
      return { success: false, error: e.message };
    }
  }

  // 导出全部（含图片下载）- 优先使用base64数据
  async function exportAll() {
    // 先导出JSON，获取文件夹名
    const folderName = await exportData();

    // 预扫描：获取页面上所有大的base64图片数据
    const allDataImages = Array.from(document.querySelectorAll('img[src^="data:image"]'));
    const largeBase64Images = allDataImages.filter(img => img.src.length > 100000);
    console.log('[海康下载器] 页面中找到的大base64图片:', largeBase64Images.length, '张');

    // 检查有多少图片有下载数据
    const images = Array.from(dataStore.images.values());

    // 如果没有图片有base64数据，但页面上有大的base64图片，尝试匹配
    const imagesWithBase64FromStore = images.filter(img => img.base64Data).length;
    if (imagesWithBase64FromStore === 0 && largeBase64Images.length > 0) {
      console.log('[海康下载器] 没有存储的base64数据，尝试直接使用页面上的数据');
      // 按顺序分配给图片
      images.forEach((img, index) => {
        if (index < largeBase64Images.length) {
          img.base64Data = largeBase64Images[index].src;
          console.log('[海康下载器] 直接分配base64数据:', img.fileName, '长度:', img.base64Data.length);
        }
      });
    }

    const imagesWithBase64 = images.filter(img => img.base64Data);
    const imagesWithRealUrl = images.filter(img => img.realUrl && !img.base64Data);
    const imagesWithDownloadData = images.filter(img => img.base64Data || img.realUrl);
    const imagesWithoutDownloadData = images.filter(img => !img.base64Data && !img.realUrl);

    console.log('[海康下载器] 开始下载图片到文件夹:', folderName);
    console.log('[海康下载器] 共', images.length, '张');
    console.log('[海康下载器] 有base64数据:', imagesWithBase64.length, '张');
    console.log('[海康下载器] 有真实URL:', imagesWithRealUrl.length, '张');

    if (imagesWithDownloadData.length === 0) {
      alert(`没有可下载的图片！\n\n请先浏览图片详情以获取下载数据。\n操作步骤：\n1. 点击图片列表中的任意图片\n2. 等待图片详情页加载完成\n3. 关闭详情页\n4. 重复以上步骤查看更多图片\n5. 再点击"导出全部"按钮`);
      return;
    }

    if (imagesWithoutDownloadData.length > 0) {
      const proceed = confirm(`警告：${imagesWithoutDownloadData.length} 张图片没有下载数据（将跳过）\n\n有下载数据的图片: ${imagesWithDownloadData.length} 张\n  - base64数据: ${imagesWithBase64.length} 张\n  - 真实URL: ${imagesWithRealUrl.length} 张\n\n是否继续下载？`);
      if (!proceed) return;
    }

    let downloaded = 0;
    let skipped = 0;
    let failed = 0;

    for (const img of images) {
      // 确保文件名有扩展名
      let fileName = img.fileName;
      if (!fileName || !/\.(jpg|jpeg|png|gif|webp|bmp)$/i.test(fileName)) {
        fileName = `image_${img.id}.jpg`;
      }

      console.log('[海康下载器] 处理图片:', fileName, '有base64:', !!img.base64Data, '有realUrl:', !!img.realUrl);

      // 优先使用base64数据下载
      if (img.base64Data) {
        console.log('[海康下载器] 准备使用base64下载:', fileName, '长度:', img.base64Data.length);
        const result = await downloadImageWithBase64(img, fileName);
        if (result.success) {
          downloaded++;
        } else {
          // base64下载失败，尝试用URL
          console.log('[海康下载器] base64下载失败，尝试URL:', fileName);
          if (img.realUrl) {
            const urlResult = await downloadImageWithFallback(img.realUrl, fileName, folderName);
            if (urlResult.success) {
              downloaded++;
            } else {
              failed++;
            }
          } else {
            failed++;
          }
        }
      }
      // 其次使用真实URL下载
      else if (img.realUrl) {
        console.log('[海康下载器] 准备使用URL下载:', fileName);
        const result = await downloadImageWithFallback(img.realUrl, fileName, folderName);
        if (result.success) {
          downloaded++;
        } else {
          failed++;
        }
      }
      // 没有下载数据，尝试从页面直接获取
      else {
        console.log('[海康下载器] 尝试从页面直接获取base64:', img.fileName);
        let foundBase64 = null;

        // 方法1：尝试在页面中查找对应的img元素
        if (img.imgId) {
          const imgElement = document.querySelector(`img[src*="${img.imgId}"]`);
          if (imgElement && imgElement.src && imgElement.src.startsWith('data:image') && imgElement.src.length > 50000) {
            foundBase64 = imgElement.src;
          }
        }

        // 方法2：尝试通过data属性查找
        if (!foundBase64) {
          const imgElement = document.querySelector(`img[data-file-id="${img.id}"], img[data-id="${img.id}"]`);
          if (imgElement && imgElement.src && imgElement.src.startsWith('data:image') && imgElement.src.length > 50000) {
            foundBase64 = imgElement.src;
          }
        }

        // 方法3：查找页面上所有data URL图片，找最大的那个
        if (!foundBase64) {
          const allDataImages = Array.from(document.querySelectorAll('img[src^="data:image"]'));
          const largeImages = allDataImages.filter(img => img.src.length > 100000);
          if (largeImages.length > 0) {
            // 取最大的一个
            largeImages.sort((a, b) => b.src.length - a.src.length);
            foundBase64 = largeImages[0].src;
            console.log('[海康下载器] 使用页面中最大的base64图片:', fileName, '长度:', foundBase64.length);
          }
        }

        if (foundBase64) {
          console.log('[海康下载器] 找到页面中的base64数据:', fileName, '长度:', foundBase64.length);
          img.base64Data = foundBase64;
          const result = await downloadImageWithBase64(img, fileName);
          if (result.success) {
            downloaded++;
          } else {
            skipped++;
          }
        } else {
          console.log('[海康下载器] 跳过无下载数据的图片:', img.fileName);
          skipped++;
        }
        continue;
      }

      // 添加延迟避免请求过快
      await new Promise(resolve => setTimeout(resolve, 200));
    }

    console.log(`[海康下载器] 下载完成: ${downloaded} 成功, ${skipped} 跳过, ${failed} 失败`);
    alert(`下载完成!\n文件夹: hikvision_datasets/${folderName}/\n成功: ${downloaded} 张\n跳过: ${skipped} 张（未浏览）\n失败: ${failed} 张\n\n请检查浏览器下载文件夹`);
  }

  // 导出已标注的图片（JSON + 图片）
  async function exportAnnotated() {
    const images = Array.from(dataStore.images.values());
    const annotatedImages = images.filter(img =>
      img.annotations && img.annotations.length > 0
    );

    if (annotatedImages.length === 0) {
      alert('没有找到已标注的图片');
      return;
    }

    const folderName = dataStore.datasetId || 'dataset_export';
    const timestamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');

    let successCount = 0;
    let failedCount = 0;

    console.log(`[海康下载器] 开始导出已标注图片: ${annotatedImages.length} 张`);

    // 导出标注文件
    for (const img of annotatedImages) {
      const annotationFileName = getAnnotationFileName(img.fileName, img.id);
      const singleAnnotationData = {
        datasetId: dataStore.datasetId,
        versionId: dataStore.versionId,
        exportTime: new Date().toISOString(),
        image: {
          id: img.id,
          fileName: img.fileName,
          width: img.width,
          height: img.height,
          annotationCount: (img.annotations || []).length
        },
        annotations: img.annotations || []
      };

      const jsonContent = JSON.stringify(singleAnnotationData, null, 2);
      const blob = new Blob([jsonContent], { type: 'application/json' });
      const url = URL.createObjectURL(blob);

      try {
        await chrome.runtime.sendMessage({
          action: 'downloadJson',
          url: url,
          filename: `annotations/${annotationFileName}`,
          datasetId: folderName
        });
        successCount++;
        console.log(`[海康下载器] 标注已导出: ${annotationFileName}`);
      } catch (e) {
        failedCount++;
        console.error(`[海康下载器] 导出失败: ${annotationFileName}`, e);
      }

      URL.revokeObjectURL(url);
      await new Promise(resolve => setTimeout(resolve, 50));
    }

    // 导出汇总文件
    await exportSummaryFile(annotatedImages, folderName, timestamp);

    // 下载图片
    let downloaded = 0, skipped = 0, failed = 0;
    for (const img of annotatedImages) {
      const fileName = img.fileName || `image_${img.id}.jpg`;

      if (img.base64Data) {
        const result = await downloadImageWithBase64(img, fileName);
        if (result.success) downloaded++;
        else failed++;
      } else if (img.realUrl) {
        const result = await downloadImageWithFallback(img.realUrl, fileName, folderName);
        if (result.success) downloaded++;
        else failed++;
      } else {
        skipped++;
      }

      await new Promise(resolve => setTimeout(resolve, 200));
    }

    console.log(`[海康下载器] 已标注图片导出完成: 标注 ${successCount} 成功, 图片 ${downloaded} 成功`);
    alert(`已标注图片导出完成!\n标注文件: ${successCount} 成功, ${failedCount} 失败\n图片: ${downloaded} 成功, ${skipped} 跳过, ${failed} 失败`);
  }

  // 只导出图片（不导出JSON）
  async function exportImages() {
    const images = Array.from(dataStore.images.values());
    const folderName = dataStore.datasetId || 'dataset_export';

    if (images.length === 0) {
      alert('没有可导出的图片');
      return;
    }

    // 检查有多少图片可以下载
    const imagesWithBase64 = images.filter(img => img.base64Data);
    const imagesWithRealUrl = images.filter(img => img.realUrl && !img.base64Data);
    const imagesWithoutDownloadData = images.filter(img => !img.base64Data && !img.realUrl);

    console.log('[海康下载器] 开始导出图片:');
    console.log('[海康下载器] - 有base64:', imagesWithBase64.length);
    console.log('[海康下载器] - 有URL:', imagesWithRealUrl.length);
    console.log('[海康下载器] - 无数据:', imagesWithoutDownloadData.length);

    if (imagesWithBase64.length === 0 && imagesWithRealUrl.length === 0) {
      alert(`没有可下载的图片！\n\n请点击图片查看详情以获取下载数据。`);
      return;
    }

    let downloaded = 0;
    let skipped = 0;
    let failed = 0;

    for (const img of images) {
      const fileName = img.fileName || `image_${img.id}.jpg`;

      if (img.base64Data) {
        const result = await downloadImageWithBase64(img, fileName);
        if (result.success) downloaded++;
        else failed++;
      } else if (img.realUrl) {
        const result = await downloadImageWithFallback(img.realUrl, fileName, folderName);
        if (result.success) downloaded++;
        else failed++;
      } else {
        skipped++;
      }

      await new Promise(resolve => setTimeout(resolve, 200));
    }

    alert(`图片导出完成!\n成功: ${downloaded} 张\n跳过: ${skipped} 张（无数据）\n失败: ${failed} 张`);
  }

  // 获取标注数据
  async function fetchAnnotations() {
    const images = Array.from(dataStore.images.values());

    if (images.length === 0) {
      alert('请先浏览图片列表');
      return;
    }

    // 检查是否有标注
    const annotatedCount = getAnnotatedCount();
    if (annotatedCount > 0) {
      alert(`已经获取到 ${annotatedCount} 张图片的标注数据\n如需更多，请继续浏览图片详情`);
      return;
    }

    alert(`当前已捕获 ${images.length} 张图片，但没有标注数据。

获取标注的方法：
1. 点击图片列表中的任意图片
2. 在图片详情页面等待标注加载
3. 关闭详情页后，插件会自动捕获标注数据
4. 重复以上步骤获取更多图片的标注`);

    console.log('[海康下载器] 提示用户点击图片获取标注');
  }

  // 创建面板
  function createPanel() {
    if (document.getElementById('hikvision-panel')) return;

    const panel = document.createElement('div');
    panel.id = 'hikvision-panel';
    panel.innerHTML = `
      <div style="background: linear-gradient(135deg, #1a73e8, #4285f4); color: white; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center; cursor: move;">
        <span style="font-weight: 600; font-size: 14px;">🏭 海康下载器</span>
        <button id="hikv-minimize" style="background: rgba(255,255,255,0.2); border: none; color: white; width: 24px; height: 24px; border-radius: 4px; cursor: pointer;">_</button>
      </div>
      <div style="padding: 12px;">
        <div style="margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #eee;">
          <div>图片: <span id="hikv-count" style="color: #1a73e8; font-weight: 700; font-size: 16px;">0</span> 张</div>
          <div>标注: <span id="hikv-annotated" style="color: #34a853; font-weight: 700;">0</span> 张</div>
          <div id="hikv-stats" style="font-size: 11px; color: #666; margin-top: 4px;">已标注: 0 | 有图片: 0</div>
          <div id="hikv-status" style="font-size: 11px; color: #999; margin-top: 4px;">等待API请求...</div>
          <div id="hikv-info" style="font-size: 11px; color: #999; margin-top: 4px; font-weight: 500;">等待API请求...</div>
        </div>

        <!-- 导出JSON区域 -->
        <div style="margin-bottom: 8px;">
          <button id="hikv-export-json" style="width: 100%; padding: 8px; background: #1a73e8; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px;">📄 导出所有JSON</button>
        </div>

        <!-- 导出图片区域 -->
        <div style="margin-bottom: 8px;">
          <button id="hikv-export-images" style="width: 100%; padding: 8px; background: #9c27b0; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px;">🖼️ 导出所有图片</button>
        </div>

        <!-- 导出已标注 -->
        <div style="margin-bottom: 8px;">
          <button id="hikv-export-annotated" style="width: 100%; padding: 8px; background: #ff9800; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px;">⭐ 导出已标注(JSON+图片)</button>
        </div>

        <!-- 导出全部 -->
        <div style="margin-bottom: 8px;">
          <button id="hikv-export-all" style="width: 100%; padding: 8px; background: #34a853; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 13px;">📦 导出全部(JSON+图片)</button>
        </div>

        <!-- 操作按钮 -->
        <div style="display: flex; justify-content: space-between; margin-top: 12px; padding-top: 8px; border-top: 1px solid #eee;">
          <button id="hikv-refresh" style="background: #f5f5f5; border: 1px solid #ddd; color: #1a73e8; padding: 4px 8px; border-radius: 4px; font-size: 11px; cursor: pointer;">🔄 重新获取</button>
          <button id="hikv-clear" style="background: #ffebee; border: 1px solid #ffcdd2; color: #c62828; padding: 4px 8px; border-radius: 4px; font-size: 11px; cursor: pointer;">🗑️ 清空数据</button>
          <button id="hikv-close" style="background: #f5f5f5; border: 1px solid #ddd; color: #666; padding: 4px 8px; border-radius: 4px; font-size: 11px; cursor: pointer;">关闭</button>
        </div>
      </div>
    `;

    panel.style.cssText = `
      position: fixed;
      top: 80px;
      right: 20px;
      width: 200px;
      background: white;
      border-radius: 10px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
      z-index: 2147483647;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 13px;
    `;

    document.body.appendChild(panel);

    // 事件绑定
    panel.querySelector('#hikv-minimize').onclick = () => {
      const content = panel.querySelector('div:nth-child(2)');
      content.style.display = content.style.display === 'none' ? 'block' : 'none';
    };

    panel.querySelector('#hikv-close').onclick = () => panel.remove();

    // 导出所有JSON
    panel.querySelector('#hikv-export-json').onclick = () => exportData().then(folderName => {
      console.log('[海康下载器] JSON已导出到文件夹:', folderName);
    });

    // 导出所有图片
    panel.querySelector('#hikv-export-images').onclick = exportImages;

    // 导出已标注(JSON+图片)
    panel.querySelector('#hikv-export-annotated').onclick = exportAnnotated;

    // 导出全部(JSON+图片)
    panel.querySelector('#hikv-export-all').onclick = exportAll;

    // 重新获取按钮 - 清空数据并提示重新浏览
    panel.querySelector('#hikv-refresh').onclick = () => {
      if (confirm('确定要重新获取数据吗？当前所有数据将被清空。')) {
        clearAllData();
        alert('数据已清空，请重新浏览页面以获取最新数据');
      }
    };

    // 清空按钮
    panel.querySelector('#hikv-clear').onclick = () => {
      if (confirm('确定要清空所有数据吗？')) {
        clearAllData();
      }
    };

    // 拖拽
    const header = panel.querySelector('div:first-child');
    let isDragging = false, startX, startY, startLeft, startTop;

    header.onmousedown = (e) => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      startLeft = panel.offsetLeft;
      startTop = panel.offsetTop;
    };

    document.onmousemove = (e) => {
      if (!isDragging) return;
      panel.style.right = 'auto';
      panel.style.left = (startLeft + e.clientX - startX) + 'px';
      panel.style.top = (startTop + e.clientY - startY) + 'px';
    };

    document.onmouseup = () => isDragging = false;

    console.log('[海康下载器] 面板已创建');
  }

  // 初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      createPanel();
      setupInterceptors();
    });
  } else {
    createPanel();
    setupInterceptors();
  }

  // 暴露到全局（content script的window）
  window.hikvisionDownloader = {
    getState: () => ({
      imagesCount: dataStore.images.size,
      annotatedCount: getAnnotatedCount(),
      datasetId: dataStore.datasetId,
      statistics: dataStore.statistics
    }),
    export: exportData,
    exportAll: exportAll,
    exportAnnotated: exportAnnotated,
    exportImages: exportImages,
    clearAllData: clearAllData,
    fetchAnnotations: fetchAnnotations,
    getImages: () => Array.from(dataStore.images.values())
  };

  // 监听来自background的消息
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'togglePanel') {
      const panel = document.getElementById('hikvision-panel');
      if (panel) {
        panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
      } else {
        createPanel();
      }
      sendResponse({ success: true });
    }

    // 监听来自 background 的真实图片 URL
    if (request.action === 'realImageUrl') {
      console.log('[海康下载器] 从 background 收到真实URL:', request.fileId);
      handleRealImageUrl(request.url);
      sendResponse({ success: true });
    }

    // ==================== 下载测试：方式3（Content Script 携带Cookie）====================
    if (request.action === 'downloadTestViaContent') {
      console.log('[下载测试] Content方式 - 收到下载请求:', request.imgId);
      (async () => {
        try {
          // 注意：不能使用 credentials: 'include'，因为OSS返回Access-Control-Allow-Origin: *，与credentials冲突
          // content script与页面同源，默认会携带Cookie
          const response = await fetch(request.url, {
            headers: { 'Accept': 'image/*,*/*' }
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }

          const blob = await response.blob();
          console.log('[下载测试] Content方式 - Blob获取:', blob.size, 'bytes, type:', blob.type);

          if (blob.size < 100) {
            throw new Error(`Blob too small (${blob.size} bytes)`);
          }

          // 转换为 Data URL
          const dataUrl = await blobToDataUrl(blob);

          // 发送回 background 下载
          const result = await chrome.runtime.sendMessage({
            action: 'downloadImage',
            url: dataUrl,
            filename: request.filename.replace(/^hikvision_datasets\//, '')
          });

          console.log('[下载测试] Content方式 - 下载结果:', result);
          sendResponse({ success: true, result });
        } catch (e) {
          console.error('[下载测试] Content方式 - 失败:', e);
          sendResponse({ success: false, error: e.message });
        }
      })();
      return true; // 保持消息通道开放
    }
    // =================================================================

    return true;
  });

  console.log('[海康下载器] 初始化完成');
  console.log('[海康下载器] 提示: hikvisionDownloader.getState()');
})();
