// 海康数据集下载器 - Popup脚本

let currentState = {
  datasetId: null,
  versionId: null,
  datasetName: '',
  statistics: {
    totalFiles: 0,
    labeledFiles: 0,
    validLabeledFiles: 0
  },
  capturedCount: 0,
  images: []
};

let isDownloading = false;

// 与content script通信
async function sendToContent(action, data = {}) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error('无法获取当前标签页');

    // 检查是否在海康平台
    if (!tab.url.includes('ai.hikvision.com')) {
      throw new Error('请在海康AI训练平台页面使用此插件');
    }

    console.log('[Popup] 发送消息到content:', action, data);
    const response = await chrome.tabs.sendMessage(tab.id, { action, ...data });
    console.log('[Popup] 收到响应:', response);
    return response;
  } catch (e) {
    console.error('[Popup] 通信失败:', e);
    return { error: e.message, details: e.toString() };
  }
}

// 更新UI显示
async function updateUI() {
  const statusPanel = document.getElementById('statusPanel');
  const statusText = document.getElementById('statusText');
  const datasetInfo = document.getElementById('datasetInfo');
  const downloadOptions = document.getElementById('downloadOptions');
  const downloadButtons = document.getElementById('downloadButtons');
  const clearDataBtn = document.getElementById('clearData');

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab || !tab.url.includes('ai.hikvision.com')) {
      statusPanel.className = 'status-panel error';
      statusText.textContent = '请在海康AI训练平台页面使用此插件';
      hideElements(datasetInfo, downloadOptions, downloadButtons, clearDataBtn);
      return;
    }

    // 获取数据状态
    const response = await sendToContent('getState');

    if (response.error) {
      statusPanel.className = 'status-panel error';
      statusText.textContent = response.error;
      hideElements(datasetInfo, downloadOptions, downloadButtons, clearDataBtn);
      return;
    }

    currentState = { ...currentState, ...response };

    if (currentState.capturedCount === 0) {
      statusPanel.className = 'status-panel';
      statusText.innerHTML = '请在页面中浏览图片以捕获数据<br><small style="color:#999">提示: 如未捕获，请刷新页面后再试</small>';
      hideElements(datasetInfo, downloadOptions, downloadButtons);
      showElements(clearDataBtn);
    } else {
      statusPanel.className = 'status-panel success';
      statusText.textContent = `已捕获 ${currentState.capturedCount} 张图片的数据`;
      showElements(datasetInfo, downloadOptions, downloadButtons, clearDataBtn);
      updateDatasetInfo();
    }

  } catch (e) {
    statusPanel.className = 'status-panel error';
    statusText.textContent = '连接失败，请刷新页面后重试';
    hideElements(datasetInfo, downloadOptions, downloadButtons);
  }
}

// 更新数据集信息显示
function updateDatasetInfo() {
  document.getElementById('datasetName').textContent =
    currentState.datasetName || '未命名数据集';
  document.getElementById('datasetId').textContent =
    currentState.datasetId ? `${currentState.datasetId}/${currentState.versionId}` : '--';
  document.getElementById('totalFiles').textContent = currentState.statistics.totalFiles || 0;
  document.getElementById('labeledFiles').textContent = currentState.statistics.labeledFiles || 0;
  document.getElementById('capturedFiles').textContent = currentState.capturedCount || 0;
}

// 显示/隐藏元素
function showElements(...elements) {
  elements.forEach(el => el && (el.style.display = ''));
}

function hideElements(...elements) {
  elements.forEach(el => el && (el.style.display = 'none'));
}

// 导出标注JSON
async function exportAnnotations() {
  if (isDownloading) return;

  const response = await sendToContent('exportAnnotations');

  if (response.error || !response.success) {
    console.error('[Popup] 导出失败:', response);
    showNotification('导出失败: ' + (response?.error || '未知错误'), 'error');
    return;
  }

  const data = response.data;
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);

  const datasetName = data.datasetName || `dataset_${data.datasetId}`;
  const filename = `${datasetName}_annotations_${formatDate(new Date())}.json`;

  await chrome.downloads.download({
    url: url,
    filename: filename,
    saveAs: false
  });

  URL.revokeObjectURL(url);
  showNotification('标注数据已导出');
}

// 下载图片和标注
async function downloadAll() {
  if (isDownloading) return;

  const includeImages = document.getElementById('includeImages').checked;
  const format = document.getElementById('outputFormat').value;

  // 获取图片列表
  const response = await sendToContent('getImageDownloads');

  if (response.error || !response.success) {
    showNotification('获取下载列表失败', 'error');
    return;
  }

  const images = response.images;
  if (images.length === 0) {
    showNotification('没有可下载的图片', 'error');
    return;
  }

  isDownloading = true;
  updateProgressPanel(true);

  try {
    // 先导出标注JSON
    await exportAnnotations();

    // 如果需要下载图片
    if (includeImages) {
      await downloadImages(images);
    }

    showNotification('下载完成！');
  } catch (e) {
    showNotification('下载失败: ' + e.message, 'error');
  } finally {
    isDownloading = false;
    updateProgressPanel(false);
  }
}

// 下载图片
async function downloadImages(images) {
  const total = images.length;
  const batchSize = 5; // 并发下载数量

  for (let i = 0; i < total; i += batchSize) {
    const batch = images.slice(i, i + batchSize);

    updateProgress(
      Math.round((i / total) * 100),
      `正在下载: ${batch[0].fileName} (${i + 1}/${total})`
    );

    // 并发下载当前批次
    await Promise.all(batch.map(img => downloadImage(img)));

    // 小延迟避免请求过快
    if (i + batchSize < total) {
      await sleep(100);
    }
  }

  updateProgress(100, '下载完成');
}

// 下载单个图片
async function downloadImage(image) {
  try {
    // 通过background script下载，避免CORS问题
    await chrome.runtime.sendMessage({
      action: 'downloadImage',
      url: image.url,
      filename: `images/${sanitizeFilename(image.fileName)}`
    });
  } catch (e) {
    console.error('下载图片失败:', image.fileName, e);
  }
}

// 更新进度面板
function updateProgressPanel(show) {
  const panel = document.getElementById('progressPanel');
  const downloadButtons = document.getElementById('downloadButtons');

  if (show) {
    panel.style.display = 'block';
    downloadButtons.style.display = 'none';
  } else {
    panel.style.display = 'none';
    downloadButtons.style.display = '';
  }
}

// 更新进度
function updateProgress(percent, text) {
  document.getElementById('progressFill').style.width = `${percent}%`;
  document.getElementById('progressPercent').textContent = `${percent}%`;
  if (text) {
    document.getElementById('progressText').textContent = text;
    document.getElementById('currentFile').textContent = text;
  }
}

// 清空数据
async function clearData() {
  if (!confirm('确定要清空已捕获的所有数据吗？')) return;

  await sendToContent('clearData');
  currentState = {
    datasetId: null,
    versionId: null,
    datasetName: '',
    statistics: { totalFiles: 0, labeledFiles: 0, validLabeledFiles: 0 },
    capturedCount: 0,
    images: []
  };

  updateUI();
  showNotification('数据已清空');
}

// 刷新数据
async function refreshData() {
  const refreshBtn = document.getElementById('refreshData');
  refreshBtn.disabled = true;
  refreshBtn.innerHTML = '<span class="icon">⏳</span> 刷新中...';

  await updateUI();

  refreshBtn.disabled = false;
  refreshBtn.innerHTML = '<span class="icon">🔄</span> 刷新数据';
}

// 显示通知
function showNotification(message, type = 'success') {
  const div = document.createElement('div');
  div.style.cssText = `
    position: fixed;
    bottom: 16px;
    left: 50%;
    transform: translateX(-50%);
    background: ${type === 'success' ? '#34a853' : '#ea4335'};
    color: white;
    padding: 12px 24px;
    border-radius: 24px;
    font-size: 14px;
    z-index: 10000;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    animation: slideUp 0.3s ease;
  `;
  div.textContent = message;
  document.body.appendChild(div);

  setTimeout(() => {
    div.style.animation = 'slideDown 0.3s ease';
    setTimeout(() => div.remove(), 300);
  }, 2500);
}

// 工具函数
function sanitizeFilename(filename) {
  return filename.replace(/[<>:"/\\|?*]/g, '_');
}

function formatDate(date) {
  return date.toISOString().slice(0, 19).replace(/[:T]/g, '-');
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// 监听来自background的消息
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'dataUpdated') {
    // 数据更新时刷新UI
    updateUI();
  }
  return true;
});

// 事件绑定
document.addEventListener('DOMContentLoaded', () => {
  updateUI();

  document.getElementById('downloadCurrent').addEventListener('click', downloadAll);
  document.getElementById('downloadAnnotationsOnly').addEventListener('click', exportAnnotations);
  document.getElementById('clearData').addEventListener('click', clearData);
  document.getElementById('refreshData').addEventListener('click', refreshData);
});

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
  @keyframes slideUp {
    from { opacity: 0; transform: translate(-50%, 20px); }
    to { opacity: 1; transform: translate(-50%, 0); }
  }
  @keyframes slideDown {
    from { opacity: 1; transform: translate(-50%, 0); }
    to { opacity: 0; transform: translate(-50%, 20px); }
  }
`;
document.head.appendChild(style);
