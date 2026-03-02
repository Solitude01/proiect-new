/**
 * AI项目星轨 - 土星环展示页面
 * 智能应用组 2025
 *
 * 核心效果: 土星环 (Saturn Ring) + 3D 透视
 * 技术: CSS 3D Transform + Canvas 2D 粒子 + DOM 节点
 */

// ================================
// 全局变量
// ================================
let projectData = [];
let filteredData = [];

// 土星环系统
let saturnNodes = [];     // { element, angle, speed, radius, project, baseSize }
let ringParticles = [];   // Canvas 粒子
let isPaused = false;
let animationId = null;
let lastTimestamp = 0;

// 缩放参数
let zoomLevel = 1;
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 2.5;
const ZOOM_SPEED = 0.001;

// 3D 透视参数
const TILT_ANGLE = 70;   // rotateX 角度 (度)
const TILT_COS = Math.cos(TILT_ANGLE * Math.PI / 180);

// 环带参数
const RING_INNER_RATIO = 0.22;  // 内环半径比 (相对系统尺寸)
const RING_OUTER_RATIO = 0.46;  // 外环半径比

// DOM 元素
const elements = {};

// Canvas 上下文
let starfieldCtx = null;
let ringCtx = null;
let stars = [];

// ================================
// 初始化
// ================================
document.addEventListener('DOMContentLoaded', async () => {
    initElements();
    initStarfieldCanvas();
    initRingParticlesCanvas();
    initEventListeners();
    startStarfieldAnimation();

    try {
        await loadData();
    } catch (error) {
        console.error('初始化失败:', error);
        showEmptyState();
    }
});

/**
 * 初始化 DOM 元素引用
 */
function initElements() {
    elements.saturnSystem = document.getElementById('saturnSystem');
    elements.ringContainer = document.getElementById('ringContainer');
    elements.nodesContainer = document.getElementById('nodesContainer');
    elements.starfieldCanvas = document.getElementById('starfieldCanvas');
    elements.ringParticlesCanvas = document.getElementById('ringParticlesCanvas');
    elements.filterFactory = document.getElementById('filterFactory');
    elements.filterStatus = document.getElementById('filterStatus');
    elements.statTotal = document.getElementById('statTotal');
    elements.statOnline = document.getElementById('statOnline');
    elements.loadingState = document.getElementById('loadingState');
    elements.emptyState = document.getElementById('emptyState');
    elements.pauseBtn = document.getElementById('pauseBtn');
    elements.pauseIcon = document.getElementById('pauseIcon');
    elements.pauseText = document.getElementById('pauseText');
    elements.detailModal = document.getElementById('detailModal');
    elements.detailModalContent = document.getElementById('detailModalContent');
    elements.detailModalClose = document.getElementById('detailModalClose');
    elements.imageModal = document.getElementById('imageModal');
    elements.modalImage = document.getElementById('modalImage');
    elements.modalClose = document.getElementById('modalClose');
}

/**
 * 从 API 加载数据
 */
async function loadData() {
    const data = await getProjectData();

    if (!Array.isArray(data)) {
        showEmptyState();
        return;
    }

    projectData = data.map(normalizeProject);
    filteredData = [...projectData];

    if (projectData.length === 0) {
        showEmptyState();
    } else {
        hideLoadingState();
        updateFilterOptions();
        updateStats();
        buildSaturnRing();
        startAnimation();
    }
}

function showEmptyState() {
    if (elements.loadingState) elements.loadingState.style.display = 'none';
    if (elements.emptyState) elements.emptyState.style.display = 'block';
}

function hideLoadingState() {
    if (elements.loadingState) elements.loadingState.style.display = 'none';
}

// ================================
// 星空背景 (Canvas)
// ================================

function initStarfieldCanvas() {
    const canvas = elements.starfieldCanvas;
    if (!canvas) return;

    starfieldCtx = canvas.getContext('2d');
    resizeStarfieldCanvas();

    // 生成星星
    stars = [];
    for (let i = 0; i < 300; i++) {
        stars.push({
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            size: Math.random() * 1.8 + 0.3,
            brightness: Math.random(),
            twinkleSpeed: 0.5 + Math.random() * 2,
            twinkleOffset: Math.random() * Math.PI * 2
        });
    }
}

function resizeStarfieldCanvas() {
    const canvas = elements.starfieldCanvas;
    if (!canvas) return;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    // 重新分布星星
    stars.forEach(star => {
        star.x = Math.random() * canvas.width;
        star.y = Math.random() * canvas.height;
    });
}

function drawStarfield(time) {
    if (!starfieldCtx) return;
    const canvas = elements.starfieldCanvas;
    const ctx = starfieldCtx;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 深空背景渐变
    const gradient = ctx.createRadialGradient(
        canvas.width / 2, canvas.height / 2, 0,
        canvas.width / 2, canvas.height / 2, canvas.width * 0.7
    );
    gradient.addColorStop(0, '#080818');
    gradient.addColorStop(0.5, '#050510');
    gradient.addColorStop(1, '#030308');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // 绘制星星
    stars.forEach(star => {
        const twinkle = 0.3 + 0.7 * ((Math.sin(time * 0.001 * star.twinkleSpeed + star.twinkleOffset) + 1) / 2);
        const alpha = star.brightness * twinkle;

        ctx.beginPath();
        ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
        ctx.fill();

        // 大星星有十字光芒
        if (star.size > 1.3) {
            ctx.strokeStyle = `rgba(255, 255, 255, ${alpha * 0.3})`;
            ctx.lineWidth = 0.5;
            const len = star.size * 3;
            ctx.beginPath();
            ctx.moveTo(star.x - len, star.y);
            ctx.lineTo(star.x + len, star.y);
            ctx.moveTo(star.x, star.y - len);
            ctx.lineTo(star.x, star.y + len);
            ctx.stroke();
        }
    });
}

let starfieldAnimId = null;
function startStarfieldAnimation() {
    function loop(time) {
        drawStarfield(time);
        starfieldAnimId = requestAnimationFrame(loop);
    }
    starfieldAnimId = requestAnimationFrame(loop);
}

// ================================
// 粒子环 (Canvas)
// ================================

function initRingParticlesCanvas() {
    const canvas = elements.ringParticlesCanvas;
    if (!canvas) return;
    ringCtx = canvas.getContext('2d');
    resizeRingCanvas();
}

function resizeRingCanvas() {
    const canvas = elements.ringParticlesCanvas;
    const system = elements.saturnSystem;
    if (!canvas || !system) return;

    const size = system.offsetWidth || 600;
    canvas.width = size;
    canvas.height = size;
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';
}

function generateRingParticles() {
    ringParticles = [];
    const canvas = elements.ringParticlesCanvas;
    if (!canvas) return;

    const size = canvas.width;
    const cx = size / 2;
    const cy = size / 2;
    const innerR = size * RING_INNER_RATIO;
    const outerR = size * RING_OUTER_RATIO;

    // 生成环带粒子
    const particleCount = 600;
    for (let i = 0; i < particleCount; i++) {
        const angle = Math.random() * Math.PI * 2;
        const r = innerR + Math.random() * (outerR - innerR);
        // 距离环心的归一化位置
        const rNorm = (r - innerR) / (outerR - innerR);

        ringParticles.push({
            angle: angle,
            radius: r,
            speed: (0.02 + Math.random() * 0.01) / (0.5 + rNorm * 0.5),
            size: 0.5 + Math.random() * 1.5,
            brightness: 0.1 + Math.random() * 0.4,
            // 模拟密度变化 - B环最密
            rNorm: rNorm
        });
    }
}

function drawRingParticles(time) {
    if (!ringCtx) return;
    const canvas = elements.ringParticlesCanvas;
    const ctx = ringCtx;
    const size = canvas.width;
    const cx = size / 2;
    const cy = size / 2;

    ctx.clearRect(0, 0, size, size);

    ringParticles.forEach(p => {
        const x = cx + Math.cos(p.angle) * p.radius;
        const y = cy + Math.sin(p.angle) * p.radius;

        // 密度模拟 - 在卡西尼缝附近降低亮度
        const cassiniDist = Math.abs(p.rNorm - 0.55);
        const cassiniDim = cassiniDist < 0.05 ? cassiniDist / 0.05 : 1;

        const alpha = p.brightness * cassiniDim;
        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(200, 200, 220, ${alpha})`;
        ctx.fill();
    });
}

function updateRingParticles(delta) {
    ringParticles.forEach(p => {
        p.angle += p.speed * delta;
    });
}

// ================================
// 土星环 - 项目节点系统
// ================================

/**
 * 构建土星环系统
 */
function buildSaturnRing() {
    clearSaturnNodes();
    resizeRingCanvas();
    generateRingParticles();

    const total = filteredData.length;
    if (total === 0) return;

    const system = elements.saturnSystem;
    if (!system) return;

    const systemSize = system.offsetWidth || 600;
    const centerX = systemSize / 2;
    const centerY = systemSize / 2;
    const innerR = systemSize * RING_INNER_RATIO;
    const outerR = systemSize * RING_OUTER_RATIO;

    // 在环带中随机分布项目节点
    filteredData.forEach((project, i) => {
        // 极坐标: 均匀分布角度 + 随机偏移
        const baseAngle = (i / total) * Math.PI * 2;
        const angle = baseAngle + (Math.random() - 0.5) * (Math.PI * 2 / total) * 0.6;

        // 半径: 在环带内随机分布，但避开卡西尼缝
        let r;
        const rand = Math.random();
        if (rand < 0.45) {
            // B环区域 (内侧) - 45%概率
            r = innerR + (outerR - innerR) * (0.1 + Math.random() * 0.35);
        } else if (rand < 0.9) {
            // A环区域 (外侧) - 45%概率
            r = innerR + (outerR - innerR) * (0.6 + Math.random() * 0.35);
        } else {
            // 卡西尼缝附近 - 10%概率
            r = innerR + (outerR - innerR) * (0.48 + Math.random() * 0.1);
        }

        // 速度: 外层更慢 (开普勒定律模拟)
        const rNorm = (r - innerR) / (outerR - innerR);
        const speed = (0.15 + Math.random() * 0.08) / (0.5 + rNorm * 0.5);

        // 节点大小: 根据状态
        const statusKey = getStatusKey(project.status);
        const baseSize = statusKey === 'online' ? 20 : statusKey === 'progress' ? 16 : 14;

        const nodeEl = createSaturnNode(project, baseSize);
        elements.nodesContainer.appendChild(nodeEl);

        saturnNodes.push({
            element: nodeEl,
            angle: angle,
            speed: speed,
            radius: r,
            project: project,
            baseSize: baseSize
        });
    });
}

/**
 * 创建土星节点 DOM 元素
 */
function createSaturnNode(project, size) {
    const node = document.createElement('div');
    node.className = 'saturn-node';

    const statusKey = getStatusKey(project.status);
    node.setAttribute('data-status', statusKey);

    node.innerHTML = `
        <div class="node-body" style="width:${size}px;height:${size}px;"></div>
        <div class="node-label">
            <div class="node-label-title">${escapeHtml(project.projectName)}</div>
            <div class="node-label-factory">${escapeHtml(project.factoryName) || '未指定'}</div>
        </div>
    `;

    node.addEventListener('click', (e) => {
        e.stopPropagation();
        openDetailModal(project);
    });

    return node;
}

/**
 * 清除节点
 */
function clearSaturnNodes() {
    saturnNodes = [];
    if (elements.nodesContainer) {
        elements.nodesContainer.innerHTML = '';
    }
}

// ================================
// 动画系统
// ================================

function startAnimation() {
    lastTimestamp = performance.now();
    animateLoop(lastTimestamp);
}

function animateLoop(timestamp) {
    const delta = (timestamp - lastTimestamp) / 1000;
    lastTimestamp = timestamp;

    if (!isPaused) {
        // 更新粒子环
        updateRingParticles(delta);
        drawRingParticles(timestamp);

        // 更新项目节点位置
        updateSaturnNodes(delta);
    }

    animationId = requestAnimationFrame(animateLoop);
}

/**
 * 更新项目节点位置 - 与粒子环使用相同的投影
 */
function updateSaturnNodes(delta) {
    const system = elements.saturnSystem;
    if (!system) return;
    const systemSize = system.offsetWidth || 600;
    const cx = systemSize / 2;
    const cy = systemSize / 2;

    saturnNodes.forEach(node => {
        // 更新角度
        node.angle += node.speed * delta;

        // 与粒子使用相同的坐标计算 (极坐标 -> 屏幕坐标)
        const x = Math.cos(node.angle) * node.radius;
        const y = Math.sin(node.angle) * node.radius;

        // 投影到屏幕 - 与 Canvas 粒子一致
        const screenX = cx + x;
        const screenY = cy + y;

        // 深度归一化 (y 正值 = 后方, 负值 = 前方)
        const depthNorm = y / node.radius;

        // 深度效果: 后方的节点更小更暗
        const depthScale = 0.5 + 0.5 * ((1 - depthNorm) / 2);
        const depthOpacity = 0.3 + 0.7 * ((1 - depthNorm) / 2);

        // 判断节点是否在核心后方 (被遮挡)
        const coreScreenRadius = 70;
        const distFromCenter = Math.sqrt(
            (screenX - cx) * (screenX - cx) +
            (screenY - cy) * (screenY - cy)
        );
        const isBehindCore = depthNorm > 0.2 && distFromCenter < coreScreenRadius;
        const occlusionFade = isBehindCore ? 0.1 : 1;

        // 应用位置
        node.element.style.left = screenX + 'px';
        node.element.style.top = screenY + 'px';
        node.element.style.transform = `translate(-50%, -50%) scale(${depthScale})`;
        node.element.style.opacity = depthOpacity * occlusionFade;
        node.element.style.zIndex = depthNorm > 0 ? 1 : 100;
    });
}

/**
 * 切换暂停
 */
function togglePause() {
    isPaused = !isPaused;

    if (elements.pauseText) {
        elements.pauseText.textContent = isPaused ? '继续' : '暂停';
    }
    if (elements.pauseIcon) {
        if (isPaused) {
            elements.pauseIcon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
        } else {
            elements.pauseIcon.innerHTML =
                '<rect x="6" y="4" width="4" height="16"></rect>' +
                '<rect x="14" y="4" width="4" height="16"></rect>';
        }
    }
}

/**
 * 应用缩放
 */
function applyZoom() {
    if (elements.saturnSystem) {
        elements.saturnSystem.style.transform = `translate(-50%, -50%) scale(${zoomLevel})`;
    }
}

// ================================
// 工具函数
// ================================

function getStatusKey(status) {
    if (!status) return 'default';
    const s = status.toLowerCase();

    if (s.includes('上线') || s.includes('已完成') || s.includes('运行中') || s === 'online') {
        return 'online';
    } else if (s.includes('进行中') || s.includes('开发中') || s.includes('审核中')) {
        return 'progress';
    } else if (s.includes('取消') || s.includes('终止') || s.includes('暂停')) {
        return 'cancelled';
    } else if (s.includes('待') || s.includes('申请')) {
        return 'pending';
    }
    return 'default';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function animateNumber(element, target) {
    if (!element) return;
    const current = parseInt(element.textContent) || 0;
    const duration = 500;
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 4);
        element.textContent = Math.round(current + (target - current) * eased);

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

// ================================
// 筛选器
// ================================

function updateFilterOptions() {
    const factories = [...new Set(projectData.map(d => d.factoryName).filter(Boolean))].sort();
    elements.filterFactory.innerHTML = '<option value="">全部工厂</option>' +
        factories.map(f => `<option value="${f}">${f}</option>`).join('');

    const statuses = [...new Set(projectData.map(d => d.status).filter(Boolean))].sort();
    elements.filterStatus.innerHTML = '<option value="">全部状态</option>' +
        statuses.map(s => `<option value="${s}">${s}</option>`).join('');
}

function updateStats() {
    const stats = calculateProjectStats(filteredData);
    animateNumber(elements.statTotal, stats.total);
    animateNumber(elements.statOnline, stats.online);
}

function applyFilters() {
    const factory = elements.filterFactory.value;
    const status = elements.filterStatus.value;

    filteredData = projectData.filter(record => {
        if (factory && record.factoryName !== factory) return false;
        if (status && record.status !== status) return false;
        return true;
    });

    updateStats();
    buildSaturnRing();
}

// ================================
// 事件监听
// ================================

function initEventListeners() {
    if (elements.filterFactory) {
        elements.filterFactory.addEventListener('change', applyFilters);
    }
    if (elements.filterStatus) {
        elements.filterStatus.addEventListener('change', applyFilters);
    }

    if (elements.pauseBtn) {
        elements.pauseBtn.addEventListener('click', togglePause);
    }

    // 滚轮缩放
    if (elements.saturnSystem) {
        elements.saturnSystem.addEventListener('wheel', (e) => {
            e.preventDefault();
            zoomLevel -= e.deltaY * ZOOM_SPEED;
            zoomLevel = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoomLevel));
            applyZoom();
        }, { passive: false });
    }

    if (elements.detailModalClose) {
        elements.detailModalClose.addEventListener('click', closeDetailModal);
    }
    if (elements.detailModal) {
        const backdrop = elements.detailModal.querySelector('.detail-modal-backdrop');
        if (backdrop) backdrop.addEventListener('click', closeDetailModal);
    }
    if (elements.modalClose) {
        elements.modalClose.addEventListener('click', closeImageModal);
    }
    if (elements.imageModal) {
        const backdrop = elements.imageModal.querySelector('.modal-backdrop');
        if (backdrop) backdrop.addEventListener('click', closeImageModal);
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeDetailModal();
            closeImageModal();
        }
    });

    window.addEventListener('resize', debounce(() => {
        resizeStarfieldCanvas();
        if (filteredData.length > 0) {
            buildSaturnRing();
        }
    }, 300));
}

function debounce(fn, delay) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

// ================================
// 模态框
// ================================

function openDetailModal(project) {
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
    if (elements.detailModal) {
        elements.detailModal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

function openImageModal(src) {
    if (elements.modalImage) elements.modalImage.src = src;
    if (elements.imageModal) elements.imageModal.classList.add('active');
}

function closeImageModal() {
    if (elements.imageModal) elements.imageModal.classList.remove('active');
}
