/**
 * Instance Portal JavaScript
 * Handles instance management, CRUD operations, and UI interactions.
 */

// State
let instances = [];
let instanceToDelete = null;

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

    if (editForm) {
        editForm.addEventListener('submit', handleEditSubmit);
    }

    loadInstances();
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
        const response = await fetch('/api/instances');
        const data = await response.json();

        instances = data.instances || [];
        renderInstances();
        updateStats();
    } catch (error) {
        console.error('Failed to load instances:', error);
        showToast('error', '加载失败', '无法加载实例列表');
    }
}

// Update statistics
function updateStats() {
    totalInstancesEl.textContent = instances.length;

    // Calculate total connections (in a real app, this would come from the backend)
    let connections = 0;
    // For now, just show random-ish connections based on instances
    connections = instances.filter(i => i.la_ip).length;
    totalConnectionsEl.textContent = connections;
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

    instanceGrid.innerHTML = instances.map(instance => `
        <div class="instance-card">
            <div class="card-header">
                <div>
                    <div class="card-title">${escapeHtml(instance.name)}</div>
                    <div class="card-id">${escapeHtml(instance.instance_id)}</div>
                </div>
                <div class="card-status ${instance.la_ip ? 'active' : 'inactive'}">
                    <span class="status-dot"></span>
                    ${instance.la_ip ? '已配置' : '未配置'}
                </div>
            </div>
            <div class="card-info">
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
                <a href="/${instance.instance_id}/dashboard" class="btn btn-primary">
                    进入控制台
                </a>
                <button class="btn btn-secondary" onclick="openEditModal('${instance.instance_id}')">
                    编辑
                </button>
                <button class="btn btn-secondary" onclick="openDeleteModal('${instance.instance_id}', '${escapeHtml(instance.name)}')">
                    删除
                </button>
            </div>
        </div>
    `).join('');
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

function openDeleteModal(instanceId, instanceName) {
    instanceToDelete = instanceId;
    document.getElementById('deleteInstanceName').textContent = instanceName;
    deleteModal.classList.add('active');
}

function closeDeleteModal() {
    deleteModal.classList.remove('active');
    instanceToDelete = null;
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

// Handle delete confirmation
async function handleDeleteConfirm() {
    if (!instanceToDelete) return;

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
