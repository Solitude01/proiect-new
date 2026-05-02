/**
 * Instance Portal JavaScript
 * Handles instance management, CRUD operations, and UI interactions.
 */

// State
let instances = [];
let instanceToDelete = null;
let currentView = 'active';    // 'active' | 'trash'
let trashCount = 0;

// DOM Elements
const instanceGrid = document.getElementById('instanceGrid');
const emptyState = document.getElementById('emptyState');
const totalInstancesEl = document.getElementById('totalInstances');
const totalConnectionsEl = document.getElementById('totalConnections');
const createModal = document.getElementById('createModal');
const editModal = document.getElementById('editModal');
const deleteModal = document.getElementById('deleteModal');
const createForm = document.getElementById('createForm');
const editForm = document.getElementById('editForm');
const toastContainer = document.getElementById('toastContainer');

let currentEditInstance = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    console.log('[Portal] DOM Loaded, initializing...');

    // Check elements exist
    const createBtn = document.getElementById('createInstanceBtn');
    const createModalEl = document.getElementById('createModal');

    if (!createBtn) {
        console.error('[Portal] Create button not found!');
    } else {
        console.log('[Portal] Create button found, binding click event');
        createBtn.addEventListener('click', (e) => {
            console.log('[Portal] Create button clicked');
            openCreateModal();
        });
    }

    if (!createModalEl) {
        console.error('[Portal] Create modal not found!');
    }

    if (createForm) {
        createForm.addEventListener('submit', handleCreateSubmit);
    }

    const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', handleDeleteConfirm);
    }

    const deleteConfirmInput = document.getElementById('deleteConfirmInput');
    if (deleteConfirmInput) {
        deleteConfirmInput.addEventListener('input', updateDeleteConfirmState);
    }

    if (editForm) {
        editForm.addEventListener('submit', handleEditSubmit);
    }

    loadInstances().then(() => startConnectionPolling());
    updateTime();
    setInterval(updateTime, 1000);

    console.log('[Portal] Initialization complete');
});

// Update header time
function updateTime() {
    const timeEl = document.querySelector('.header-time');
    if (timeEl) {
        const now = new Date();
        timeEl.textContent = now.toLocaleTimeString('zh-CN', { hour12: false });
    }
}

// Load instances from API
async function loadInstances() {
    try {
        const type = currentView === 'trash' ? 'trash' : 'active';
        const response = await fetch(`/api/instances?type=${type}`);
        const data = await response.json();

        instances = data.instances || [];
        renderInstances();
        updateStats();

        // Also fetch trash count for the tab badge
        if (currentView === 'active') {
            fetchTrashCount();
        }
    } catch (error) {
        console.error('Failed to load instances:', error);
        showToast('error', '加载失败', '无法加载实例列表');
    }
}

async function fetchTrashCount() {
    try {
        const response = await fetch('/api/instances?type=trash');
        const data = await response.json();
        trashCount = (data.instances || []).length;
        document.getElementById('trashCount').textContent = trashCount;
    } catch (e) { /* ignore */ }
}

// Switch between active/trash views
function switchView(view) {
    if (view === currentView) return;
    currentView = view;

    // Update tab active states
    document.querySelectorAll('.view-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.view === view);
    });

    // Reload instances for the new view
    loadInstances().then(() => {
        if (currentView === 'active') startConnectionPolling();
    });
}

// Periodically refresh connection counts (every 5s)
let connPollTimer = null;
function startConnectionPolling() {
    if (connPollTimer) return;
    connPollTimer = setInterval(async () => {
        // Don't poll if a modal is open
        if (document.querySelector('.modal.active')) return;
        try {
            const response = await fetch('/api/instances');
            const data = await response.json();
            if (!data.instances) return;
            // Update connection count badges only (no full re-render)
            data.instances.forEach(inst => {
                const badge = document.querySelector(`.instance-card .card-conn-count[data-id="${inst.instance_id}"]`);
                if (badge) {
                    badge.textContent = `${inst.connected_clients || 0} 连接`;
                    badge.title = `${inst.connected_clients || 0} 个客户端已连接`;
                }
            });
        } catch (e) {
            // Silently ignore poll errors
        }
    }, 5000);
}

// Update statistics
function updateStats() {
    totalInstancesEl.textContent = instances.length;

    // Calculate total connections from live data
    let connections = 0;
    if (currentView === 'active') {
        connections = instances.reduce((sum, i) => sum + (i.connected_clients || 0), 0);
    }
    totalConnectionsEl.textContent = connections;

    // Update tab count badges
    if (currentView === 'active') {
        document.getElementById('activeCount').textContent = instances.length;
    } else {
        document.getElementById('trashCount').textContent = instances.length;
        trashCount = instances.length;
    }
}

// Render instance grid
function renderInstances() {
    if (instances.length === 0) {
        instanceGrid.style.display = 'none';
        emptyState.style.display = 'flex';
        return;
    }

    instanceGrid.style.display = 'grid';
    emptyState.style.display = 'none';

    // Update empty state text for trash
    if (currentView === 'trash' && instances.length === 0) {
        emptyState.querySelector('h2').textContent = '回收站为空';
        emptyState.querySelector('p').textContent = '删除的实例将会出现在这里';
    } else if (currentView === 'active' && instances.length === 0) {
        emptyState.querySelector('h2').textContent = '暂无实例';
        emptyState.querySelector('p').textContent = '点击上方按钮创建第一个实例';
    }

    // Render trash cards
    if (currentView === 'trash') {
        instanceGrid.innerHTML = instances.map(instance => renderTrashCard(instance)).join('');
        return;
    }

    instanceGrid.innerHTML = instances.map(instance => {
        const isEnabled = instance.enabled !== false;
        const hasLA = instance.la_ip && instance.la_ip !== '--';
        const statusClass = isEnabled ? (hasLA ? 'online' : 'offline') : 'disabled-status';
        const statusText = isEnabled ? (hasLA ? '在线' : '待配置') : '已禁用';
        const connCount = instance.connected_clients || 0;
        const desc = instance.description || '';
        return `
        <div class="instance-card${isEnabled ? '' : ' disabled'}">
            <span class="card-bracket-br"></span>

            <!-- Header: Name + Status Badge -->
            <div class="card-header">
                <div class="card-title-row">
                    <span class="card-title">${escapeHtml(instance.name)}</span>
                    <span class="card-id">${escapeHtml(instance.instance_id)}</span>
                </div>
                <div class="card-status ${statusClass}">
                    <span class="status-dot"></span>
                    ${statusText}
                </div>
                ${isEnabled ? `<span class="card-conn-count" data-id="${escapeHtml(instance.instance_id)}" title="${connCount} 个客户端已连接">${connCount} 连接</span>` : ''}
            </div>

            <!-- Data Grid -->
            <div class="card-info">
                ${desc ? `<div class="info-item" style="grid-column: 1/-1;">
                    <span class="info-label">描述</span>
                    <span class="info-value">${escapeHtml(desc)}</span>
                </div>` : ''}
                <div class="info-item">
                    <span class="info-label">LA 地址</span>
                    <span class="info-value">${instance.la_ip || '--'}:${instance.la_port || '--'}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">创建时间</span>
                    <span class="info-value">${formatDate(instance.created_at)}</span>
                </div>
            </div>

            <!-- Action Bar -->
            <div class="card-actions">
                ${isEnabled
                    ? `<a href="/${instance.instance_id}/dashboard" class="btn btn-primary" target="_blank">进入控制台</a>`
                    : `<span class="btn btn-primary" style="opacity: 0.35; cursor: not-allowed; pointer-events: none;">已禁用</span>`
                }
                <button class="btn btn-secondary" onclick="openEditModal('${instance.instance_id}')" title="编辑实例">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style="vertical-align: -1px;">
                        <path d="M11.5 1.5l3 3L5 14H2v-3L11.5 1.5z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/>
                    </svg>
                </button>
                <span class="card-actions-spacer"></span>
                <label class="toggle-switch" onclick="event.stopPropagation()" title="${isEnabled ? '点击禁用' : '点击启用'}" aria-label="${isEnabled ? '禁用实例' : '启用实例'}">
                    <input type="checkbox" ${isEnabled ? 'checked' : ''} onchange="event.stopPropagation(); showToggleConfirm(this, '${instance.instance_id}', '${escapeHtml(instance.name)}', ${isEnabled})">
                    <span class="toggle-track"></span>
                    <span class="toggle-thumb"></span>
                </label>
                <button class="btn btn-danger" onclick="openDeleteModal('${instance.instance_id}', '${escapeHtml(instance.name)}')" title="删除实例">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style="vertical-align: -1px;">
                        <path d="M3 4h10M6 4V2h4v2M5 4v10a1 1 0 001 1h4a1 1 0 001-1V4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                </button>
            </div>
        </div>
    `;
    }).join('');
}

// Toggle instance enabled/disabled
// Show inline popover for toggle confirmation
function showToggleConfirm(checkbox, instanceId, instanceName, currentlyEnabled) {
    // Revert checkbox immediately
    checkbox.checked = currentlyEnabled;

    // Remove any existing popover
    dismissTogglePopover();

    const action = currentlyEnabled ? '禁用' : '启用';
    const label = checkbox.closest('.toggle-switch');
    if (!label) return;
    const card = label.closest('.instance-card');
    if (!card) return;

    // Create popover
    const popover = document.createElement('div');
    popover.className = 'confirm-popover';
    popover.id = 'togglePopover';
    popover.innerHTML = `
        <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 0.5rem; font-size: 0.8125rem; color: var(--text-primary);">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style="color: var(--accent-red);">
                <path d="M8 6v4M8 11v1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                <circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.5"/>
            </svg>
            确认${action}实例
        </div>
        <div class="confirm-name-display" style="margin-bottom: 0.625rem; padding: 0.4rem 0.625rem;">
            <span class="confirm-name-label">实例</span>
            <strong class="confirm-name-value">${escapeHtml(instanceName)}</strong>
        </div>
        <input type="text"
               class="confirm-text-input"
               id="toggleConfirmInput"
               placeholder="输入实例名称以确认..."
               autocomplete="off"
               onpaste="return false"
               ondrop="return false"
               style="margin-bottom: 0.625rem;">
        <div style="display: flex; gap: 0.5rem; justify-content: flex-end;">
            <button class="btn btn-secondary" onclick="dismissTogglePopover()" style="font-size: 0.75rem; padding: 0.3rem 0.6rem;">取消</button>
            <button class="btn btn-danger"
                    id="toggleConfirmBtn"
                    disabled
                    style="font-size: 0.75rem; padding: 0.3rem 0.6rem;">
                ${action}
            </button>
        </div>
    `;

    card.style.position = 'relative';
    card.appendChild(popover);

    // Bind input validation
    const input = popover.querySelector('#toggleConfirmInput');
    const btn = popover.querySelector('#toggleConfirmBtn');
    input.addEventListener('input', () => {
        const match = input.value.trim() === instanceName;
        input.classList.toggle('match', match && input.value.trim().length > 0);
        input.classList.toggle('mismatch', !match && input.value.trim().length > 0);
        btn.disabled = !match;
    });

    // Confirm action
    btn.addEventListener('click', () => {
        if (input.value.trim() === instanceName) {
            dismissTogglePopover();
            toggleInstanceEnabled(instanceId, currentlyEnabled);
        }
    });

    // Focus input
    setTimeout(() => input.focus(), 100);

    // Close on Escape
    const escHandler = (e) => { if (e.key === 'Escape') dismissTogglePopover(); };
    document.addEventListener('keydown', escHandler);
    popover._escHandler = escHandler;
}

function dismissTogglePopover() {
    const popover = document.getElementById('togglePopover');
    if (popover) {
        if (popover._escHandler) {
            document.removeEventListener('keydown', popover._escHandler);
        }
        popover.remove();
    }
}

// Close popover when clicking outside
document.addEventListener('click', (e) => {
    const popover = document.getElementById('togglePopover');
    if (popover && !popover.contains(e.target) && !e.target.closest('.toggle-switch')) {
        dismissTogglePopover();
    }
});

async function toggleInstanceEnabled(instanceId, currentlyEnabled) {
    const action = currentlyEnabled ? '禁用' : '启用';

    try {
        const response = await fetch(`/api/instances/${instanceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: !currentlyEnabled })
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast('success', `${action}成功`, `实例已${action}`);
            await loadInstances();
        } else {
            showToast('error', `${action}失败`, result.detail || '未知错误');
            // Revert UI on failure
            await loadInstances();
        }
    } catch (error) {
        console.error(`Failed to ${action} instance:`, error);
        showToast('error', `${action}失败`, '网络错误或服务器无响应');
        await loadInstances();
    }
}

// Modal functions
function openCreateModal() {
    console.log('[Portal] Opening create modal...');
    if (!createModal) {
        console.error('[Portal] createModal element is null!');
        return;
    }
    createModal.classList.add('active');
    console.log('[Portal] Modal active class added');

    const instanceIdInput = document.getElementById('instanceId');
    if (instanceIdInput) {
        instanceIdInput.focus();
    }
}

function closeCreateModal() {
    createModal.classList.remove('active');
    createForm.reset();
}

let deleteConfirmInstanceName = '';

function openDeleteModal(instanceId, instanceName) {
    instanceToDelete = instanceId;
    deleteConfirmInstanceName = instanceName;
    document.getElementById('deleteInstanceName').textContent = instanceName;

    // Reset input and button
    const input = document.getElementById('deleteConfirmInput');
    if (input) {
        input.value = '';
        input.className = 'confirm-text-input';
    }
    const btn = document.getElementById('confirmDeleteBtn');
    if (btn) btn.disabled = true;

    deleteModal.classList.add('active');
    // Focus input after modal animation
    setTimeout(() => { if (input) input.focus(); }, 200);
}

function closeDeleteModal() {
    deleteModal.classList.remove('active');
    instanceToDelete = null;
    deleteConfirmInstanceName = '';
}


// Handle create form submission
async function handleCreateSubmit(e) {
    e.preventDefault();

    const submitBtn = createForm.querySelector('button[type="submit"]');
    submitBtn.classList.add('loading');

    const formData = new FormData(createForm);

    const data = {
        instance_id: formData.get('instance_id').trim(),
        name: formData.get('name').trim(),
        la_ip: formData.get('la_ip').trim(),
        la_port: parseInt(formData.get('la_port'), 10),
        description: formData.get('description').trim()
    };

    try {
        const response = await fetch('/api/instances', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast('success', '创建成功', `实例 "${data.name}" 已创建`);
            closeCreateModal();
            await loadInstances();
        } else {
            showToast('error', '创建失败', result.detail || '未知错误');
        }
    } catch (error) {
        console.error('Failed to create instance:', error);
        showToast('error', '创建失败', '网络错误或服务器无响应');
    } finally {
        submitBtn.classList.remove('loading');
    }
}

// Real-time validation for delete confirmation input
function updateDeleteConfirmState() {
    const input = document.getElementById('deleteConfirmInput');
    const btn = document.getElementById('confirmDeleteBtn');
    if (!input || !btn) return;

    const typed = input.value.trim();
    const match = typed === deleteConfirmInstanceName;

    input.classList.toggle('match', match && typed.length > 0);
    input.classList.toggle('mismatch', !match && typed.length > 0);
    btn.disabled = !match;
}

// Handle delete confirmation
async function handleDeleteConfirm() {
    if (!instanceToDelete) return;

    // Verify name match
    const input = document.getElementById('deleteConfirmInput');
    if (!input || input.value.trim() !== deleteConfirmInstanceName) {
        showToast('error', '名称不匹配', '请输入正确的实例名称以确认删除');
        return;
    }

    const deleteBtn = document.getElementById('confirmDeleteBtn');
    deleteBtn.classList.add('loading');

    try {
        const response = await fetch(`/api/instances/${instanceToDelete}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast('success', '删除成功', '实例已删除');
            closeDeleteModal();
            await loadInstances();
        } else {
            showToast('error', '删除失败', result.detail || '未知错误');
        }
    } catch (error) {
        console.error('Failed to delete instance:', error);
        showToast('error', '删除失败', '网络错误或服务器无响应');
    } finally {
        deleteBtn.classList.remove('loading');
    }
}

// Toast notification system
function showToast(type, title, message) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: `<svg viewBox="0 0 20 20" fill="none"><path d="M4 10L8 14L16 6" stroke="var(--accent-green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
        error: `<svg viewBox="0 0 20 20" fill="none"><path d="M5 5L15 15M15 5L5 15" stroke="var(--accent-red)" stroke-width="2" stroke-linecap="round"/></svg>`,
        warning: `<svg viewBox="0 0 20 20" fill="none"><path d="M10 6V10M10 14H10.01" stroke="var(--accent-orange)" stroke-width="2" stroke-linecap="round"/></svg>`,
        info: `<svg viewBox="0 0 20 20" fill="none"><path d="M10 6V10M10 14H10.01" stroke="var(--accent-cyan)" stroke-width="2" stroke-linecap="round"/></svg>`
    };

    toast.innerHTML = `
        <div class="toast-icon">${icons[type]}</div>
        <div class="toast-content">
            <div class="toast-title">${escapeHtml(title)}</div>
            <div class="toast-message">${escapeHtml(message)}</div>
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 3L11 11M11 3L3 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
        </button>
    `;

    toastContainer.appendChild(toast);

    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.classList.add('out');
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// Utility functions
// Render a trash card (different from active card)
function renderTrashCard(instance) {
    const deletedTime = formatRelativeTime(instance.deleted_at);
    const desc = instance.description || '';
    return `
    <div class="instance-card trashed">
        <span class="card-bracket-br"></span>

        <div class="card-header">
            <div class="card-title-row">
                <span class="card-title">${escapeHtml(instance.name)}</span>
                <span class="card-id">${escapeHtml(instance.instance_id)}</span>
            </div>
            <div class="card-status trashed-status">
                <span class="status-dot"></span>
                已删除 ${deletedTime}
            </div>
        </div>

        <div class="card-info">
            ${desc ? `<div class="info-item" style="grid-column: 1/-1;">
                <span class="info-label">描述</span>
                <span class="info-value">${escapeHtml(desc)}</span>
            </div>` : ''}
            <div class="info-item">
                <span class="info-label">LA 地址</span>
                <span class="info-value">${instance.la_ip || '--'}:${instance.la_port || '--'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">创建时间</span>
                <span class="info-value">${formatDate(instance.created_at)}</span>
            </div>
        </div>

        <div class="card-actions">
            <button class="btn btn-restore" onclick="restoreInstance('${escapeHtml(instance.instance_id)}', '${escapeHtml(instance.name)}')">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style="vertical-align: -1px;">
                    <path d="M2 8a6 6 0 0112 0M4 6l-2 2 2 2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                恢复实例
            </button>
            <span class="card-actions-spacer"></span>
            <button class="btn btn-danger" onclick="permanentlyDeleteInstance('${escapeHtml(instance.instance_id)}', '${escapeHtml(instance.name)}')" title="永久删除">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style="vertical-align: -1px;">
                    <path d="M3 4h10M6 4V2h4v2M5 4v10a1 1 0 001 1h4a1 1 0 001-1V4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                永久删除
            </button>
        </div>
    </div>`;
}

// Format deleted_at to relative time
function formatRelativeTime(isoString) {
    if (!isoString) return '';
    const now = Date.now();
    const then = new Date(isoString).getTime();
    const diff = Math.floor((now - then) / 1000);
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    return formatDate(isoString);
}

// Restore instance from trash
async function restoreInstance(instanceId, instanceName) {
    // Show confirmation dialog
    if (!confirm(`确定要恢复实例 "${instanceName}" 吗？`)) return;

    try {
        const response = await fetch(`/api/instances/${instanceId}/restore`, { method: 'POST' });
        const result = await response.json();

        if (response.ok && result.success) {
            showToast('success', '恢复成功', `实例 "${instanceName}" 已恢复`);
            switchView('active');
        } else {
            showToast('error', '恢复失败', result.detail || '未知错误');
        }
    } catch (error) {
        console.error('Failed to restore instance:', error);
        showToast('error', '恢复失败', '网络错误或服务器无响应');
    }
}

// Permanent delete from trash
async function permanentlyDeleteInstance(instanceId, instanceName) {
    if (!confirm(`此操作不可撤销！确定要永久删除实例 "${instanceName}" 吗？`)) return;
    if (!confirm(`再次确认：永久删除后无法恢复。继续吗？`)) return;

    try {
        const response = await fetch(`/api/instances/${instanceId}/permanent`, { method: 'DELETE' });
        const result = await response.json();

        if (response.ok && result.success) {
            showToast('success', '已永久删除', `实例 "${instanceName}" 已彻底移除`);
            await loadInstances();
            // Refresh trash count
            fetchTrashCount();
        } else {
            showToast('error', '删除失败', result.detail || '未知错误');
        }
    } catch (error) {
        console.error('Failed to permanently delete instance:', error);
        showToast('error', '删除失败', '网络错误或服务器无响应');
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return '--';
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

// Close modals on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeCreateModal();
        closeEditModal();
        closeDeleteModal();
    }
});

// ============================================================================
// Edit Instance Functions
// ============================================================================

async function openEditModal(instanceId) {
    console.log('[Portal] Opening edit modal for:', instanceId);
    currentEditInstance = instanceId;

    try {
        const response = await fetch(`/api/instances/${instanceId}`);
        if (!response.ok) {
            showToast('error', '加载失败', '无法获取实例配置');
            return;
        }

        const data = await response.json();
        const instance = data.instance;
        if (!instance) {
            showToast('error', '错误', '实例数据为空');
            return;
        }

        // Fill basic info
        document.getElementById('editInstanceId').value = instance.instance_id;
        document.getElementById('editInstanceName').value = instance.name || '';
        document.getElementById('editLaIp').value = instance.la_config?.ip || '';
        document.getElementById('editLaPort').value = instance.la_config?.port || 8080;
        document.getElementById('editDescription').value = instance.description || '';
        document.getElementById('editEnabled').checked = instance.enabled !== false;

        editModal.classList.add('active');
    } catch (error) {
        console.error('[Portal] Failed to load instance:', error);
        showToast('error', '加载失败', '网络错误或服务器无响应');
    }
}

function closeEditModal() {
    editModal.classList.remove('active');
    if (editForm) editForm.reset();
    currentEditInstance = null;
}

async function handleEditSubmit(e) {
    e.preventDefault();

    const submitBtn = editForm.querySelector('button[type="submit"]');
    submitBtn.classList.add('loading');

    const data = {
        name: document.getElementById('editInstanceName').value,
        description: document.getElementById('editDescription').value,
        enabled: document.getElementById('editEnabled').checked,
        la_config: {
            ip: document.getElementById('editLaIp').value,
            port: parseInt(document.getElementById('editLaPort').value, 10)
        }
    };

    console.log('[EditSubmit] Sending data:', JSON.stringify(data, null, 2));

    try {
        const response = await fetch(`/api/instances/${currentEditInstance}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast('success', '保存成功', '实例配置已更新');
            closeEditModal();
            await loadInstances();
        } else {
            showToast('error', '保存失败', result.detail || '未知错误');
        }
    } catch (error) {
        console.error('Failed to update instance:', error);
        showToast('error', '保存失败', '网络错误或服务器无响应');
    } finally {
        submitBtn.classList.remove('loading');
    }
}
