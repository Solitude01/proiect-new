/**
 * Instance Portal JavaScript
 * Handles instance management, CRUD operations, and UI interactions.
 */

// State
let instances = [];
let instanceToDelete = null;
let buttonIndexCounter = 0;  // 全局按钮索引计数器，确保唯一性

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
    buttonIndexCounter = 0;  // 重置计数器
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

    // Collect button configs
    const buttons = [];
    const container = document.getElementById('createButtonsContainer');
    const rows = container.querySelectorAll('.button-config-row');

    rows.forEach((row, index) => {
        // 从第一个输入框的 name 属性中提取实际索引
        const firstInput = row.querySelector('input[name^="btn_label_"]');
        const actualIndex = firstInput ? firstInput.name.replace('btn_label_', '') : index;

        const label = row.querySelector(`[name="btn_label_${actualIndex}"]`)?.value;
        const buttonType = row.querySelector(`[name="btn_type_${actualIndex}"]`)?.value || 'command';
        const color = row.querySelector(`[name="btn_color_${actualIndex}"]`)?.value;
        const endpoint = row.querySelector(`[name="btn_endpoint_${actualIndex}"]`)?.value;
        const method = row.querySelector(`[name="btn_method_${actualIndex}"]`)?.value;
        const payloadStr = row.querySelector(`[name="btn_payload_${actualIndex}"]`)?.value;

        let payload = {};
        try {
            payload = payloadStr ? JSON.parse(payloadStr) : {};
        } catch (e) {
            console.warn('Invalid JSON payload for button', label);
        }

        if (label) {
            buttons.push({
                id: `btn_${Date.now()}_${index}`,
                label: label,
                command: label,
                color: color,
                endpoint: endpoint || '/api/control',
                method: method || 'POST',
                payload: payload,
                button_type: buttonType
            });
        }
    });

    const data = {
        instance_id: formData.get('instance_id').trim(),
        name: formData.get('name').trim(),
        la_ip: formData.get('la_ip').trim(),
        la_port: parseInt(formData.get('la_port'), 10),
        description: formData.get('description').trim(),
        control_buttons: buttons
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
    buttonIndexCounter = 0;  // 重置计数器

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

        // Fill control buttons
        const container = document.getElementById('editButtonsContainer');
        container.innerHTML = '';

        const buttons = instance.control_buttons || [];
        if (buttons.length === 0) {
            // Add default empty button
            addEditButton();
        } else {
            buttons.forEach((btn, index) => {
                addEditButton(btn, index);
            });
        }

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

// 处理按钮类型切换，自动更新发送内容示例
function handleButtonTypeChange(select, btnIndex) {
    const isInput = select.value === 'input';
    const payloadTextarea = select.closest('.button-config-row').querySelector(`[name="btn_payload_${btnIndex}"]`);

    if (payloadTextarea) {
        if (isInput) {
            // 如果当前是默认的命令格式或为空，则替换为输入按钮示例
            const currentValue = payloadTextarea.value.trim();
            if (currentValue === '{"action": "start"}' || currentValue === '' || currentValue === '{}') {
                payloadTextarea.value = '{"value": "{{input}}"}';
            }
        } else {
            // 如果当前是输入按钮格式，则替换为命令按钮示例
            const currentValue = payloadTextarea.value.trim();
            if (currentValue.includes('{{input}}')) {
                payloadTextarea.value = '{"action": "start"}';
            }
        }
    }
}

function addEditButton(btnData = null, index = null) {
    const container = document.getElementById('editButtonsContainer');
    // 使用传入的索引或全局计数器，确保唯一性
    const btnIndex = index !== null ? index : buttonIndexCounter++;

    const div = document.createElement('div');
    div.className = 'button-config-row';
    // 保留原始按钮ID，用于保存时识别
    if (btnData?.id) {
        div.dataset.buttonId = btnData.id;
    }
    div.innerHTML = `
        <div class="form-row">
            <div class="form-group">
                <label>按钮名称</label>
                <input type="text" name="btn_label_${btnIndex}" required placeholder="启动生产"
                    value="${btnData ? escapeHtml(btnData.label) : ''}">
            </div>
            <div class="form-group">
                <label>按钮颜色</label>
                <select name="btn_color_${btnIndex}">
                    <option value="green" ${btnData?.color === 'green' ? 'selected' : ''}>绿色</option>
                    <option value="red" ${btnData?.color === 'red' ? 'selected' : ''}>红色</option>
                    <option value="blue" ${btnData?.color === 'blue' || !btnData ? 'selected' : ''}>蓝色</option>
                    <option value="orange" ${btnData?.color === 'orange' ? 'selected' : ''}>橙色</option>
                </select>
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>按钮类型</label>
                <select name="btn_type_${btnIndex}" onchange="handleButtonTypeChange(this, ${btnIndex})">
                    <option value="command" ${btnData?.button_type === 'command' || !btnData ? 'selected' : ''}>命令按钮</option>
                    <option value="input" ${btnData?.button_type === 'input' ? 'selected' : ''}>输入按钮(带输入框)</option>
                </select>
            </div>
            <div class="form-group">
                <label>命令标识</label>
                <input type="text" name="btn_command_${btnIndex}" placeholder="START_PRODUCTION"
                    value="${btnData ? escapeHtml(btnData.command || '') : ''}">
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>端点路径</label>
                <input type="text" name="btn_endpoint_${btnIndex}" placeholder="/api/control"
                    value="${btnData ? escapeHtml(btnData.endpoint || '/api/control') : '/api/control'}">
            </div>
            <div class="form-group">
                <label>HTTP 方法</label>
                <select name="btn_method_${btnIndex}">
                    <option value="POST" ${btnData?.method === 'POST' || !btnData ? 'selected' : ''}>POST</option>
                    <option value="GET" ${btnData?.method === 'GET' ? 'selected' : ''}>GET</option>
                    <option value="PUT" ${btnData?.method === 'PUT' ? 'selected' : ''}>PUT</option>
                </select>
            </div>
        </div>
        <div class="form-group">
            <label>发送内容 (JSON格式)</label>
            <textarea name="btn_payload_${btnIndex}" rows="2" placeholder='{"action": "start"}'
                >${btnData && btnData.payload ? JSON.stringify(btnData.payload, null, 2) : '{"action": "start"}'}</textarea>
            <div class="form-hint" style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">
                输入按钮可使用 <code>{{input}}</code> 作为占位符，会被替换为用户输入的值
            </div>
        </div>
        <button type="button" class="btn btn-danger btn-small" onclick="this.closest('.button-config-row').remove()">删除此按钮</button>
        <hr style="border-color: var(--border-subtle); margin: 1rem 0;">
    `;
    container.appendChild(div);
}

function addCreateButton() {
    const container = document.getElementById('createButtonsContainer');
    const btnIndex = buttonIndexCounter++;

    const div = document.createElement('div');
    div.className = 'button-config-row';
    div.innerHTML = `
        <div class="form-row">
            <div class="form-group">
                <label>按钮名称</label>
                <input type="text" name="btn_label_${btnIndex}" required placeholder="按钮名称">
            </div>
            <div class="form-group">
                <label>按钮类型</label>
                <select name="btn_type_${btnIndex}" onchange="handleButtonTypeChange(this, ${btnIndex})">
                    <option value="command" selected>命令按钮</option>
                    <option value="input">输入按钮(带输入框)</option>
                </select>
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>按钮颜色</label>
                <select name="btn_color_${btnIndex}">
                    <option value="green">绿色</option>
                    <option value="red">红色</option>
                    <option value="blue" selected>蓝色</option>
                    <option value="orange">橙色</option>
                </select>
            </div>
            <div class="form-group">
                <label>HTTP 方法</label>
                <select name="btn_method_${btnIndex}">
                    <option value="POST" selected>POST</option>
                    <option value="GET">GET</option>
                    <option value="PUT">PUT</option>
                </select>
            </div>
        </div>
        <div class="form-group">
            <label>端点路径</label>
            <input type="text" name="btn_endpoint_${btnIndex}" placeholder="/api/control" value="/api/control">
        </div>
        <div class="form-group">
            <label>发送内容 (JSON格式)</label>
            <textarea name="btn_payload_${btnIndex}" rows="2" placeholder='{"action": "start"}'>{"action": "start"}</textarea>
            <div class="form-hint" style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">
                输入按钮可使用 <code>{{input}}</code> 作为占位符，会被替换为用户输入的值
            </div>
        </div>
        <button type="button" class="btn btn-danger btn-small" onclick="this.closest('.button-config-row').remove()">删除此按钮</button>
        <hr style="border-color: var(--border-subtle); margin: 1rem 0;">
    `;
    container.appendChild(div);
}

async function handleEditSubmit(e) {
    e.preventDefault();

    const submitBtn = editForm.querySelector('button[type="submit"]');
    submitBtn.classList.add('loading');

    // Collect button configs
    const buttons = [];
    const container = document.getElementById('editButtonsContainer');
    const rows = container.querySelectorAll('.button-config-row');

    rows.forEach((row, index) => {
        // 从第一个输入框的 name 属性中提取实际索引
        const firstInput = row.querySelector('input[name^="btn_label_"]');
        const actualIndex = firstInput ? firstInput.name.replace('btn_label_', '') : index;

        const buttonTypeSelect = row.querySelector(`[name="btn_type_${actualIndex}"]`);
        const buttonType = buttonTypeSelect?.value || 'command';
        console.log(`[EditSubmit] Row ${index}: actualIndex=${actualIndex}, buttonType=${buttonType}`, buttonTypeSelect);

        const label = row.querySelector(`[name="btn_label_${actualIndex}"]`)?.value;
        const color = row.querySelector(`[name="btn_color_${actualIndex}"]`)?.value;
        const endpoint = row.querySelector(`[name="btn_endpoint_${actualIndex}"]`)?.value;
        const method = row.querySelector(`[name="btn_method_${actualIndex}"]`)?.value;
        const command = row.querySelector(`[name="btn_command_${actualIndex}"]`)?.value || label;
        const payloadStr = row.querySelector(`[name="btn_payload_${actualIndex}"]`)?.value;

        let payload = {};
        try {
            payload = payloadStr ? JSON.parse(payloadStr) : {};
        } catch (e) {
            console.warn('Invalid JSON payload for button', label);
        }

        if (label) {
            // 尝试从已有的 data-id 属性获取原始ID，否则生成新ID
            const existingId = row.dataset.buttonId;
            const btnId = existingId || `btn_${Date.now()}_${index}`;

            buttons.push({
                id: btnId,
                label: label,
                command: command,
                color: color,
                endpoint: endpoint || '/api/control',
                method: method || 'POST',
                payload: payload,
                button_type: buttonType
            });
        }
    });

    const data = {
        name: document.getElementById('editInstanceName').value,
        description: document.getElementById('editDescription').value,
        la_config: {
            ip: document.getElementById('editLaIp').value,
            port: parseInt(document.getElementById('editLaPort').value, 10)
        },
        control_buttons: buttons
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
