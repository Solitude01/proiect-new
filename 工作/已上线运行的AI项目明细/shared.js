/**
 * AI项目展示系统 - 共享工具函数
 * 供管理页面、业务页面、星球页面共用
 * 改造版：使用 API 替代 LocalStorage
 */

// API 基地址（通过 nginx 反向代理）
const API_BASE = '/api';

/**
 * 从 API 获取项目数据
 * @returns {Promise<Array>} 项目数据数组
 */
async function getProjectData() {
    try {
        const response = await fetch(`${API_BASE}/projects`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        // 处理图片路径，确保使用正确的 URL
        return data.map(project => ({
            ...project,
            alarmImage: project.alarm_image ? `/uploads/images/${project.alarm_image}` : ''
        }));
    } catch (error) {
        console.error('获取项目数据失败:', error);
        return [];
    }
}

/**
 * 上传 Excel 文件到服务器
 * @param {File} file - Excel 文件
 * @returns {Promise<Object>} 上传结果
 */
async function uploadExcelFile(file) {
    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE}/projects/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `上传失败: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('上传文件失败:', error);
        throw error;
    }
}

/**
 * 获取统计数据
 * @returns {Promise<Object>} 统计数据
 */
async function getStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('获取统计数据失败:', error);
        return null;
    }
}

/**
 * 获取筛选选项
 * @returns {Promise<Object>} 筛选选项（工厂列表、状态列表）
 */
async function getFilterOptions() {
    try {
        const response = await fetch(`${API_BASE}/filters`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('获取筛选选项失败:', error);
        return { factories: [], statuses: [] };
    }
}

/**
 * 检查 API 健康状态
 * @returns {Promise<boolean>}
 */
async function checkApiHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        return response.ok;
    } catch (error) {
        console.error('API 健康检查失败:', error);
        return false;
    }
}

/**
 * 获取状态样式类名
 * @param {string} status - 项目状态
 * @returns {string} CSS类名
 */
function getStatusClass(status) {
    if (!status) return 'status-default';

    const s = status.toLowerCase();

    if (s.includes('上线') || s.includes('已完成') || s.includes('运行中') || s === 'online') {
        return 'status-online';
    } else if (s.includes('进行中') || s.includes('开发中') || s.includes('审核中')) {
        return 'status-progress';
    } else if (s.includes('取消') || s.includes('终止') || s.includes('暂停')) {
        return 'status-cancelled';
    } else if (s.includes('待') || s.includes('申请')) {
        return 'status-pending';
    }

    return 'status-default';
}

/**
 * 获取状态颜色（用于3D展示）
 * @param {string} status - 项目状态
 * @returns {number} 十六进制颜色值
 */
function getStatusColor(status) {
    if (!status) return 0x94a3b8; // 默认灰色

    const s = status.toLowerCase();

    if (s.includes('上线') || s.includes('已完成') || s.includes('运行中') || s === 'online') {
        return 0x10b981; // 绿色
    } else if (s.includes('进行中') || s.includes('开发中') || s.includes('审核中')) {
        return 0xf59e0b; // 橙色
    } else if (s.includes('取消') || s.includes('终止') || s.includes('暂停')) {
        return 0xef4444; // 红色
    } else if (s.includes('待') || s.includes('申请')) {
        return 0x3b82f6; // 蓝色
    }

    return 0x94a3b8; // 默认灰色
}

/**
 * 格式化日期显示
 * @param {string} dateStr - 日期字符串
 * @returns {string} 格式化后的日期
 */
function formatDateDisplay(dateStr) {
    if (!dateStr) return '-';
    // 处理 ISO 格式日期
    if (dateStr.includes('T')) {
        return dateStr.split('T')[0];
    }
    return dateStr;
}

/**
 * HTML 转义
 * @param {string} text - 原始文本
 * @returns {string} 转义后的文本
 */
function escapeHtmlShared(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 计算统计数据（从项目数组计算）
 * @param {Array} data - 项目数据数组
 * @returns {Object} 统计结果
 */
function calculateProjectStats(data) {
    return {
        total: data.length,
        online: data.filter(d => isOnlineStatus(d.status)).length,
        revenue: data.reduce((sum, d) => sum + (parseFloat(d.moneyBenefit || d.money_benefit) || 0), 0),
        timeSaved: data.reduce((sum, d) => sum + (parseFloat(d.timeSaved || d.time_saved) || 0), 0)
    };
}

/**
 * 判断是否为已上线状态
 * @param {string} status - 项目状态
 * @returns {boolean}
 */
function isOnlineStatus(status) {
    if (!status) return false;
    const s = status.toLowerCase();
    return s.includes('上线') || s.includes('已完成') || s.includes('运行中') || s === 'online';
}

/**
 * 标准化项目数据字段名（后端返回 snake_case，前端使用 camelCase）
 * @param {Object} project - 后端返回的项目数据
 * @returns {Object} 标准化后的项目数据
 */
function normalizeProject(project) {
    return {
        id: project.id,
        projectName: project.project_name || project.projectName || '',
        factoryName: project.factory_name || project.factoryName || '',
        projectGoal: project.project_goal || project.projectGoal || '',
        benefitDesc: project.benefit_desc || project.benefitDesc || '',
        moneyBenefit: parseFloat(project.money_benefit || project.moneyBenefit) || 0,
        timeSaved: parseFloat(project.time_saved || project.timeSaved) || 0,
        applicant: project.applicant || '',
        createTime: formatDateDisplay(project.create_time || project.createTime),
        submitTime: formatDateDisplay(project.submit_time || project.submitTime),
        developer: project.developer || '',
        auditTime: formatDateDisplay(project.audit_time || project.auditTime),
        onlineTime: formatDateDisplay(project.online_time || project.onlineTime),
        cancelTime: formatDateDisplay(project.cancel_time || project.cancelTime),
        status: project.status || '',
        alarmImage: project.alarm_image ? `/uploads/images/${project.alarm_image}` : (project.alarmImage || '')
    };
}

/**
 * 渲染项目详情卡片 HTML
 * @param {Object} project - 项目数据对象
 * @returns {string} HTML字符串
 */
function renderDetailCardContent(project) {
    // 标准化项目数据
    const p = normalizeProject(project);

    const timelineItems = [
        { label: '创建', date: p.createTime, icon: 'create' },
        { label: '提交', date: p.submitTime, icon: 'submit' },
        { label: '审核', date: p.auditTime, icon: 'audit' },
        { label: '上线', date: p.onlineTime, icon: 'online' }
    ];

    // 如果有取消时间，添加取消节点
    if (p.cancelTime && p.cancelTime !== '-') {
        timelineItems.push({ label: '取消', date: p.cancelTime, icon: 'cancel' });
    }

    const timelineHtml = timelineItems.map((item, index) => {
        const isActive = item.date && item.date !== '-';
        const isLast = index === timelineItems.length - 1;
        return `
            <div class="timeline-item ${isActive ? 'active' : ''} ${item.icon === 'cancel' ? 'cancelled' : ''}">
                <div class="timeline-dot"></div>
                ${!isLast ? '<div class="timeline-line"></div>' : ''}
                <div class="timeline-content">
                    <span class="timeline-label">${item.label}</span>
                    <span class="timeline-date">${formatDateDisplay(item.date)}</span>
                </div>
            </div>
        `;
    }).join('');

    return `
        <div class="detail-header">
            <h2 class="detail-title">${escapeHtmlShared(p.projectName)}</h2>
            <span class="status-tag ${getStatusClass(p.status)}">${escapeHtmlShared(p.status) || '-'}</span>
        </div>

        <div class="detail-grid">
            <div class="detail-item">
                <span class="detail-label">工厂名称</span>
                <span class="detail-value">${escapeHtmlShared(p.factoryName) || '-'}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">申请人</span>
                <span class="detail-value">${escapeHtmlShared(p.applicant) || '-'}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">开发人</span>
                <span class="detail-value">${escapeHtmlShared(p.developer) || '-'}</span>
            </div>
        </div>

        <div class="detail-section">
            <h3 class="section-title">项目目标</h3>
            <p class="section-content">${escapeHtmlShared(p.projectGoal) || '-'}</p>
        </div>

        ${p.alarmImage && (p.alarmImage.startsWith('/uploads') || p.alarmImage.startsWith('http')) ? `
        <div class="detail-section">
            <h3 class="section-title">报警图例</h3>
            <div class="detail-image-container">
                <img src="${p.alarmImage}" alt="报警图例" class="detail-image">
            </div>
        </div>
        ` : ''}

        <div class="detail-section">
            <h3 class="section-title">收益说明</h3>
            <p class="section-content">${escapeHtmlShared(p.benefitDesc) || '-'}</p>
        </div>

        <div class="detail-metrics">
            <div class="metric-card money">
                <div class="metric-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="12" y1="1" x2="12" y2="23"></line>
                        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
                    </svg>
                </div>
                <div class="metric-content">
                    <span class="metric-value">${p.moneyBenefit ? p.moneyBenefit.toFixed(2) : '0'}</span>
                    <span class="metric-label">收益(万元)</span>
                </div>
            </div>
            <div class="metric-card time">
                <div class="metric-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <polyline points="12 6 12 12 16 14"></polyline>
                    </svg>
                </div>
                <div class="metric-content">
                    <span class="metric-value">${p.timeSaved ? p.timeSaved.toFixed(2) : '0'}</span>
                    <span class="metric-label">结余(小时/月)</span>
                </div>
            </div>
        </div>

        <div class="detail-section">
            <h3 class="section-title">时间线</h3>
            <div class="timeline">
                ${timelineHtml}
            </div>
        </div>
    `;
}

// 导出函数供其他模块使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        getProjectData,
        uploadExcelFile,
        getStats,
        getFilterOptions,
        checkApiHealth,
        getStatusClass,
        getStatusColor,
        formatDateDisplay,
        escapeHtmlShared,
        calculateProjectStats,
        isOnlineStatus,
        normalizeProject,
        renderDetailCardContent,
        API_BASE
    };
}
