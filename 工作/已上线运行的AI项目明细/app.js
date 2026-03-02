/**
 * AI项目明细展示系统 - 主应用逻辑
 * 智能制造推进部 2025
 * 简化版：只负责展示数据，数据通过脚本导入
 */

// ================================
// 全局变量
// ================================
let rawData = [];           // 原始数据
let filteredData = [];      // 筛选后的数据

// ================================
// DOM元素
// ================================
const elements = {
    statsSection: document.getElementById('statsSection'),
    filterSection: document.getElementById('filterSection'),
    tableSection: document.getElementById('tableSection'),
    emptyState: document.getElementById('emptyState'),
    tableBody: document.getElementById('tableBody'),
    loadingOverlay: document.getElementById('loadingOverlay'),
    imageModal: document.getElementById('imageModal'),
    modalImage: document.getElementById('modalImage'),
    modalClose: document.getElementById('modalClose'),
    particles: document.getElementById('particles'),
    // Detail Modal
    detailModal: document.getElementById('detailModal'),
    detailModalContent: document.getElementById('detailModalContent'),
    detailModalClose: document.getElementById('detailModalClose'),
    // Stats
    totalProjects: document.getElementById('totalProjects'),
    onlineProjects: document.getElementById('onlineProjects'),
    totalRevenue: document.getElementById('totalRevenue'),
    totalTimeSaved: document.getElementById('totalTimeSaved'),
    // Filters
    filterFactory: document.getElementById('filterFactory'),
    filterStatus: document.getElementById('filterStatus'),
    filterTimeRange: document.getElementById('filterTimeRange'),
    filterKeyword: document.getElementById('filterKeyword'),
    btnReset: document.getElementById('btnReset'),
    // Actions
    btnPrint: document.getElementById('btnPrint'),
    // Counts
    displayCount: document.getElementById('displayCount'),
    totalCount: document.getElementById('totalCount')
};

// ================================
// 初始化
// ================================
document.addEventListener('DOMContentLoaded', async () => {
    initParticles();
    initEventListeners();
    await loadDataFromAPI();
});

/**
 * 初始化粒子背景效果
 */
function initParticles() {
    const particleCount = 30;
    for (let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        particle.style.left = `${Math.random() * 100}%`;
        particle.style.animationDelay = `${Math.random() * 15}s`;
        particle.style.animationDuration = `${15 + Math.random() * 10}s`;
        elements.particles.appendChild(particle);
    }
}

/**
 * 初始化事件监听器
 */
function initEventListeners() {
    // 筛选器
    elements.filterFactory.addEventListener('change', applyFilters);
    elements.filterStatus.addEventListener('change', applyFilters);
    elements.filterTimeRange.addEventListener('change', applyFilters);
    elements.filterKeyword.addEventListener('input', debounce(applyFilters, 300));
    elements.btnReset.addEventListener('click', resetFilters);

    // 打印
    elements.btnPrint.addEventListener('click', () => window.print());

    // 图片模态框
    elements.modalClose.addEventListener('click', closeModal);
    elements.imageModal.querySelector('.modal-backdrop').addEventListener('click', closeModal);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeModal();
            closeDetailModal();
        }
    });

    // 详情模态框
    if (elements.detailModalClose) {
        elements.detailModalClose.addEventListener('click', closeDetailModal);
    }
    if (elements.detailModal) {
        elements.detailModal.querySelector('.detail-modal-backdrop').addEventListener('click', closeDetailModal);
    }
}

// ================================
// API 数据加载
// ================================

/**
 * 从 API 加载数据
 */
async function loadDataFromAPI() {
    showLoading(true);
    try {
        const data = await getProjectData();
        if (data && data.length > 0) {
            rawData = data.map(normalizeProject);
            filteredData = [...rawData];
            updateUI();
        } else {
            showEmptyState();
        }
    } catch (error) {
        console.error('加载数据失败:', error);
        showEmptyState();
    } finally {
        showLoading(false);
    }
}

// ================================
// UI更新
// ================================

/**
 * 更新整个UI
 */
function updateUI() {
    if (rawData.length === 0) {
        showEmptyState();
        return;
    }

    elements.statsSection.style.display = 'grid';
    elements.filterSection.style.display = 'flex';
    elements.tableSection.style.display = 'block';
    elements.emptyState.style.display = 'none';
    elements.btnPrint.disabled = false;

    updateFilterOptions();
    updateStats();
    renderTable();
    updateCounts();
}

/**
 * 显示空状态
 */
function showEmptyState() {
    elements.statsSection.style.display = 'none';
    elements.filterSection.style.display = 'none';
    elements.tableSection.style.display = 'none';
    elements.emptyState.style.display = 'block';
    elements.btnPrint.disabled = true;
}

/**
 * 更新筛选器选项
 */
function updateFilterOptions() {
    const factories = [...new Set(rawData.map(d => d.factoryName).filter(Boolean))].sort();
    elements.filterFactory.innerHTML = '<option value="">全部工厂</option>' +
        factories.map(f => `<option value="${f}">${f}</option>`).join('');

    const statuses = [...new Set(rawData.map(d => d.status).filter(Boolean))].sort();
    elements.filterStatus.innerHTML = '<option value="">全部状态</option>' +
        statuses.map(s => `<option value="${s}">${s}</option>`).join('');
}

/**
 * 更新统计信息
 */
function updateStats() {
    const stats = calculateProjectStats(filteredData);

    animateNumber(elements.totalProjects, stats.total);
    animateNumber(elements.onlineProjects, stats.online);
    animateNumber(elements.totalRevenue, stats.revenue, true);
    animateNumber(elements.totalTimeSaved, stats.timeSaved, true);
}

/**
 * 数字动画效果
 */
function animateNumber(element, target, isDecimal = false) {
    const duration = 1000;
    const start = parseFloat(element.textContent) || 0;
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const current = start + (target - start) * easeOut;

        element.textContent = isDecimal ? current.toFixed(2) : Math.round(current);

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

/**
 * 渲染数据表格
 */
function renderTable() {
    elements.tableBody.innerHTML = '';

    filteredData.forEach((record, index) => {
        const tr = document.createElement('tr');
        tr.style.animationDelay = `${index * 0.03}s`;

        tr.innerHTML = `
            <td class="col-project-name text-ellipsis" title="${escapeHtml(record.projectName)}">${escapeHtml(record.projectName)}</td>
            <td class="col-factory">${escapeHtml(record.factoryName)}</td>
            <td class="col-goal text-wrap" title="${escapeHtml(record.projectGoal)}">${escapeHtml(record.projectGoal)}</td>
            <td class="col-benefit-desc text-wrap" title="${escapeHtml(record.benefitDesc)}">${escapeHtml(record.benefitDesc)}</td>
            <td class="col-money">${record.moneyBenefit ? record.moneyBenefit.toFixed(2) : '-'}</td>
            <td class="col-time">${record.timeSaved ? record.timeSaved.toFixed(2) : '-'}</td>
            <td>${escapeHtml(record.applicant)}</td>
            <td class="col-date">${escapeHtml(record.createTime)}</td>
            <td class="col-date">${escapeHtml(record.submitTime)}</td>
            <td>${escapeHtml(record.developer)}</td>
            <td class="col-date">${escapeHtml(record.auditTime)}</td>
            <td class="col-date">${escapeHtml(record.onlineTime)}</td>
            <td class="col-date">${escapeHtml(record.cancelTime)}</td>
            <td>${renderStatusTag(record.status)}</td>
            <td>${renderImage(record.alarmImage)}</td>
        `;

        elements.tableBody.appendChild(tr);
    });

    // 绑定图片点击事件
    document.querySelectorAll('.img-thumbnail').forEach(img => {
        img.addEventListener('click', (e) => {
            e.stopPropagation();
            openImageModal(img.src);
        });
    });

    // 绑定表格行点击事件打开详情
    document.querySelectorAll('#tableBody tr').forEach((tr, index) => {
        tr.addEventListener('click', () => {
            const record = filteredData[index];
            if (record) {
                openDetailModal(record);
            }
        });
    });
}

/**
 * 渲染状态标签
 */
function renderStatusTag(status) {
    if (!status) return '<span class="status-tag status-default">-</span>';
    const className = getStatusClass(status);
    return `<span class="status-tag ${className}">${escapeHtml(status)}</span>`;
}

/**
 * 渲染图片
 */
function renderImage(imageUrl) {
    if (imageUrl && (imageUrl.startsWith('/uploads') || imageUrl.startsWith('http'))) {
        return `<img class="img-thumbnail" src="${imageUrl}" alt="报警图例" loading="lazy">`;
    }
    return '<span class="no-image">-</span>';
}

/**
 * 更新记录数显示
 */
function updateCounts() {
    elements.displayCount.textContent = filteredData.length;
    elements.totalCount.textContent = rawData.length;
}

// ================================
// 筛选功能
// ================================

function applyFilters() {
    const factory = elements.filterFactory.value;
    const status = elements.filterStatus.value;
    const timeRange = elements.filterTimeRange.value;
    const keyword = elements.filterKeyword.value.toLowerCase().trim();

    filteredData = rawData.filter(record => {
        if (factory && record.factoryName !== factory) return false;
        if (status && record.status !== status) return false;

        if (timeRange && record.onlineTime && record.onlineTime !== '-') {
            const recordDate = new Date(record.onlineTime);
            const now = new Date();
            let threshold;

            switch (timeRange) {
                case 'month':
                    threshold = new Date(now.setMonth(now.getMonth() - 1));
                    break;
                case 'quarter':
                    threshold = new Date(now.setMonth(now.getMonth() - 3));
                    break;
                case 'halfyear':
                    threshold = new Date(now.setMonth(now.getMonth() - 6));
                    break;
                case 'year':
                    threshold = new Date(now.setFullYear(now.getFullYear() - 1));
                    break;
            }

            if (threshold && recordDate < threshold) return false;
        }

        if (keyword) {
            const searchFields = [
                record.projectName,
                record.factoryName,
                record.applicant,
                record.developer,
                record.projectGoal,
                record.benefitDesc
            ].map(f => (f || '').toLowerCase());

            if (!searchFields.some(f => f.includes(keyword))) return false;
        }

        return true;
    });

    updateStats();
    renderTable();
    updateCounts();
}

function resetFilters() {
    elements.filterFactory.value = '';
    elements.filterStatus.value = '';
    elements.filterTimeRange.value = '';
    elements.filterKeyword.value = '';

    filteredData = [...rawData];
    updateStats();
    renderTable();
    updateCounts();
}

// ================================
// 模态框
// ================================

function openImageModal(src) {
    elements.modalImage.src = src;
    elements.imageModal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    elements.imageModal.classList.remove('active');
    document.body.style.overflow = '';
}

function openDetailModal(project) {
    if (!elements.detailModal || !elements.detailModalContent) return;

    elements.detailModalContent.innerHTML = renderDetailCardContent(project);
    elements.detailModal.classList.add('active');
    document.body.style.overflow = 'hidden';

    const detailImg = elements.detailModalContent.querySelector('.detail-image');
    if (detailImg) {
        detailImg.addEventListener('click', () => {
            openImageModal(detailImg.src);
        });
    }
}

function closeDetailModal() {
    if (!elements.detailModal) return;
    elements.detailModal.classList.remove('active');
    document.body.style.overflow = '';
}

// ================================
// 工具函数
// ================================

function showLoading(show) {
    elements.loadingOverlay.style.display = show ? 'flex' : 'none';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
