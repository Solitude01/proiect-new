/**
 * AI项目展示系统 - 业务人员展示页面逻辑
 * 智能制造推进部 2025
 * 改造版：使用 API 替代 LocalStorage
 */

// ================================
// 主题管理器
// ================================
const ThemeManager = {
    STORAGE_KEY: 'ai-project-theme',
    LIGHT_THEME: 'light',
    DARK_THEME: 'dark',

    /**
     * 初始化主题
     */
    init() {
        this.applyTheme(this.getSavedTheme());
        this.bindEvents();
    },

    /**
     * 获取保存的主题
     */
    getSavedTheme() {
        return localStorage.getItem(this.STORAGE_KEY) || this.DARK_THEME;
    },

    /**
     * 应用主题
     */
    applyTheme(theme) {
        if (theme === this.LIGHT_THEME) {
            document.documentElement.setAttribute('data-theme', 'light');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
        localStorage.setItem(this.STORAGE_KEY, theme);
    },

    /**
     * 切换主题
     */
    toggle() {
        const currentTheme = this.getSavedTheme();
        const newTheme = currentTheme === this.LIGHT_THEME ? this.DARK_THEME : this.LIGHT_THEME;
        console.log('切换主题:', currentTheme, '->', newTheme);
        this.applyTheme(newTheme);
        console.log('data-theme 属性:', document.documentElement.getAttribute('data-theme'));
    },

    /**
     * 绑定事件
     */
    bindEvents() {
        const toggleBtn = document.getElementById('themeToggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggle());
        }
    }
};

// ================================
// 全局变量
// ================================
let projectData = [];
let filteredData = [];

// DOM 元素
const elements = {
    projectsGrid: document.getElementById('projectsGrid'),
    projectCount: document.getElementById('projectCount'),
    emptyState: document.getElementById('emptyState'),
    statsBar: document.getElementById('statsBar'),
    filterBar: document.getElementById('filterBar'),
    filterFactory: document.getElementById('filterFactory'),
    filterStatus: document.getElementById('filterStatus'),
    searchInput: document.getElementById('searchInput'),
    statTotal: document.getElementById('statTotal'),
    statTime: document.getElementById('statTime'),
    detailModal: document.getElementById('detailModal'),
    detailModalContent: document.getElementById('detailModalContent'),
    detailModalClose: document.getElementById('detailModalClose'),
    imageModal: document.getElementById('imageModal'),
    modalImage: document.getElementById('modalImage'),
    modalClose: document.getElementById('modalClose'),
    particles: document.getElementById('particles'),
    // 申请项目弹窗相关元素
    btnApplyProject: document.getElementById('btnApplyProject'),
    applyModal: document.getElementById('applyModal'),
    applyModalClose: document.getElementById('applyModalClose'),
    applyModalCloseBtn: document.getElementById('applyModalCloseBtn')
};

// ================================
// 初始化
// ================================
document.addEventListener('DOMContentLoaded', async () => {
    ThemeManager.init();  // 最先执行，避免闪烁
    initParticles();
    initEventListeners();
    await loadData();
});

/**
 * 初始化粒子背景效果
 */
function initParticles() {
    const particleCount = 25;
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
 * 从 API 加载数据
 */
async function loadData() {
    try {
        const data = await getProjectData();
        projectData = data.map(normalizeProject);
        filteredData = [...projectData];

        if (projectData.length === 0) {
            showEmptyState();
        } else {
            updateUI();
        }
    } catch (error) {
        console.error('加载数据失败:', error);
        showEmptyState();
    }
}

/**
 * 初始化事件监听器
 */
function initEventListeners() {
    // 筛选器
    elements.filterFactory.addEventListener('change', applyFilters);
    elements.filterStatus.addEventListener('change', applyFilters);
    elements.searchInput.addEventListener('input', debounce(applyFilters, 300));

    // 详情模态框
    elements.detailModalClose.addEventListener('click', closeDetailModal);
    elements.detailModal.querySelector('.detail-modal-backdrop').addEventListener('click', closeDetailModal);

    // 图片模态框
    elements.modalClose.addEventListener('click', closeImageModal);
    elements.imageModal.querySelector('.modal-backdrop').addEventListener('click', closeImageModal);

    // 申请项目弹窗
    elements.btnApplyProject.addEventListener('click', (e) => {
        e.preventDefault();
        openApplyModal();
    });
    elements.applyModalClose.addEventListener('click', closeApplyModal);
    elements.applyModalCloseBtn.addEventListener('click', closeApplyModal);
    elements.applyModal.querySelector('.apply-modal-backdrop').addEventListener('click', closeApplyModal);

    // 可复制文本点击事件
    document.querySelectorAll('.contact-value.copyable').forEach(el => {
        el.addEventListener('click', (e) => {
            const textToCopy = el.dataset.copy || el.textContent;
            copyToClipboard(textToCopy);
        });
    });

    // ESC 关闭
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeDetailModal();
            closeImageModal();
            closeApplyModal();
        }
    });
}

// ================================
// UI 更新
// ================================

/**
 * 更新整个 UI
 */
function updateUI() {
    elements.emptyState.style.display = 'none';
    elements.statsBar.style.display = 'flex';
    elements.filterBar.style.display = 'flex';

    updateFilterOptions();
    updateStats();
    renderProjectCards();
    updateProjectCount();
}

/**
 * 显示空状态
 */
function showEmptyState() {
    elements.emptyState.style.display = 'block';
    elements.statsBar.style.display = 'none';
    elements.filterBar.style.display = 'none';
    elements.projectsGrid.innerHTML = '';
    elements.projectCount.innerHTML = '';
}

/**
 * 更新筛选器选项
 */
function updateFilterOptions() {
    // 工厂选项
    const factories = [...new Set(projectData.map(d => d.factoryName).filter(Boolean))].sort();
    elements.filterFactory.innerHTML = '<option value="">全部工厂</option>' +
        factories.map(f => `<option value="${f}">${f}</option>`).join('');

    // 状态选项
    const statuses = [...new Set(projectData.map(d => d.status).filter(Boolean))].sort();
    elements.filterStatus.innerHTML = '<option value="">全部状态</option>' +
        statuses.map(s => `<option value="${s}">${s}</option>`).join('');
}

/**
 * 更新统计信息
 */
function updateStats() {
    const stats = calculateProjectStats(filteredData);

    animateNumber(elements.statTotal, stats.total);
    animateNumber(elements.statTime, stats.timeSaved, true);
}

/**
 * 数字动画效果
 */
function animateNumber(element, target, isDecimal = false) {
    const duration = 800;
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
 * 渲染项目卡片
 */
function renderProjectCards() {
    elements.projectsGrid.innerHTML = '';

    if (filteredData.length === 0) {
        elements.projectsGrid.innerHTML = `
            <div class="no-data-message" style="grid-column: 1 / -1;">
                <p>没有找到匹配的项目</p>
            </div>
        `;
        return;
    }

    filteredData.forEach((project, index) => {
        const card = createProjectCard(project, index);
        elements.projectsGrid.appendChild(card);
    });

    // 添加卡片鼠标跟踪效果
    addCardMouseTracking();
}

/**
 * 创建项目卡片
 */
function createProjectCard(project, index) {
    const card = document.createElement('div');
    card.className = 'project-card';
    card.style.animationDelay = `${index * 0.08}s`;

    card.innerHTML = `
        <div class="card-header">
            <h3 class="card-title">${escapeHtmlShared(project.projectName)}</h3>
        </div>
        <div class="card-factory">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M3 21h18"></path>
                <path d="M5 21V7l8-4v18"></path>
                <path d="M19 21V11l-6-4"></path>
                <path d="M9 9v.01"></path>
                <path d="M9 12v.01"></path>
                <path d="M9 15v.01"></path>
                <path d="M9 18v.01"></path>
            </svg>
            ${escapeHtmlShared(project.factoryName) || '未指定'}
        </div>
        <p class="card-goal">${escapeHtmlShared(project.projectGoal) || '暂无描述'}</p>
        <div class="card-metrics">
            <div class="card-metric">
                <span class="card-metric-value money">${project.moneyBenefit ? project.moneyBenefit.toFixed(2) : '0'}</span>
                <span class="card-metric-label">收益(万元)</span>
            </div>
            <div class="card-metric">
                <span class="card-metric-value time">${project.timeSaved ? project.timeSaved.toFixed(2) : '0'}</span>
                <span class="card-metric-label">结余(小时/月)</span>
            </div>
        </div>
    `;

    card.addEventListener('click', () => openDetailModal(project));

    return card;
}

/**
 * 添加卡片鼠标跟踪效果
 */
function addCardMouseTracking() {
    document.querySelectorAll('.project-card').forEach(card => {
        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = ((e.clientX - rect.left) / rect.width) * 100;
            const y = ((e.clientY - rect.top) / rect.height) * 100;
            card.style.setProperty('--mouse-x', `${x}%`);
            card.style.setProperty('--mouse-y', `${y}%`);
        });
    });
}

/**
 * 更新项目数量显示
 */
function updateProjectCount() {
    elements.projectCount.innerHTML = `显示 <span>${filteredData.length}</span> 个项目，共 <span>${projectData.length}</span> 个`;
}

// ================================
// 筛选功能
// ================================

/**
 * 应用筛选器
 */
function applyFilters() {
    const factory = elements.filterFactory.value;
    const status = elements.filterStatus.value;
    const keyword = elements.searchInput.value.toLowerCase().trim();

    filteredData = projectData.filter(record => {
        if (factory && record.factoryName !== factory) return false;
        if (status && record.status !== status) return false;
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
    renderProjectCards();
    updateProjectCount();
}

// ================================
// 模态框
// ================================

/**
 * 打开项目详情模态框
 */
function openDetailModal(project) {
    elements.detailModalContent.innerHTML = renderDetailCardContent(project);
    elements.detailModal.classList.add('active');
    document.body.style.overflow = 'hidden';

    // 绑定详情图片点击事件
    const detailImg = elements.detailModalContent.querySelector('.detail-image');
    if (detailImg) {
        detailImg.addEventListener('click', () => {
            openImageModal(detailImg.src);
        });
    }
}

/**
 * 关闭项目详情模态框
 */
function closeDetailModal() {
    elements.detailModal.classList.remove('active');
    document.body.style.overflow = '';
}

/**
 * 打开图片模态框
 */
function openImageModal(src) {
    elements.modalImage.src = src;
    elements.imageModal.classList.add('active');
}

/**
 * 关闭图片模态框
 */
function closeImageModal() {
    elements.imageModal.classList.remove('active');
}

/**
 * 打开申请项目弹窗
 */
function openApplyModal() {
    elements.applyModal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

/**
 * 关闭申请项目弹窗
 */
function closeApplyModal() {
    elements.applyModal.classList.remove('active');
    document.body.style.overflow = '';
}

// ================================
// 工具函数
// ================================

/**
 * 防抖函数
 */
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

/**
 * 复制文本到剪贴板
 */
function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showCopyToast();
        }).catch(err => {
            console.error('复制失败:', err);
            fallbackCopyToClipboard(text);
        });
    } else {
        fallbackCopyToClipboard(text);
    }
}

/**
 * 降级复制方案（兼容旧浏览器）
 */
function fallbackCopyToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.select();
    try {
        document.execCommand('copy');
        showCopyToast();
    } catch (err) {
        console.error('复制失败:', err);
    }
    document.body.removeChild(textArea);
}

/**
 * 显示复制成功提示
 */
function showCopyToast() {
    const toast = document.getElementById('copyToast');
    if (!toast) return;

    toast.classList.add('show');
    setTimeout(() => {
        toast.classList.remove('show');
    }, 2000);
}
