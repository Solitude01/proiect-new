/**
 * Business View JavaScript
 * Full-featured view identical to dashboard
 */

class BusinessViewManager {
    constructor() {
        this.instanceId = document.body.dataset.instanceId;
        this.viewUid = document.body.dataset.viewUid;
        this.isBusinessView = true;
        this.ws = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.reconnectTimer = null;
        this.maxReconnectDelay = 30000;
        this.pingInterval = null;
        this.lastPongTime = Date.now();

        // Terminal state
        this.logs = [];
        this.logFilter = 'all';
        this.isPaused = false;
        this.maxLogs = 1000;
        this.logsOffset = 0;

        // Metrics cache
        this.metrics = {};
        this.metricsMappings = [];

        // Audio alerts
        this.audioAlertRules = [];
        this.audioFiles = [];
        this.lastAlertTimes = {}; // For time filtering
        this.audioAlertMatchEnabled = false; // Default: play all sounds without matching
        this.audioAlertsEnabled = true; // Global audio alerts switch, default: enabled

        // DOM elements
        this.connectionGate = document.getElementById('connectionGate');
        this.connectBtn = document.getElementById('connectBtn');
        this.gateStatus = document.getElementById('gateStatus');

        this.init();
    }

    async init() {
        // Bind connection button
        if (this.connectBtn) {
            this.connectBtn.addEventListener('click', () => this.unlockAndConnect());
        }

        // Terminal tabs
        document.querySelectorAll('.terminal-tabs .tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.setLogFilter(e.target.dataset.filter));
        });

        // Terminal actions
        document.getElementById('clearLogs').addEventListener('click', () => this.clearLogs());
        document.getElementById('pauseLogs').addEventListener('click', () => this.togglePause());

        // Audio controls
        const muteBtn = document.getElementById('muteBtn');
        const volumeSlider = document.getElementById('volumeSlider');

        volumeSlider.value = window.audioManager.volume * 100;
        this.updateVolumeSliderColor(window.audioManager.volume * 100);

        muteBtn.addEventListener('click', () => {
            const isMuted = window.audioManager.toggleMute();
            this.updateMuteIcon(isMuted);
        });

        volumeSlider.addEventListener('input', (e) => {
            const value = e.target.value;
            window.audioManager.setVolume(value / 100);
            this.updateVolumeSliderColor(value);
        });

        this.updateMuteIcon(window.audioManager.isAudioMuted);

        // Control buttons
        this.bindControlButtons();

        // Add audio alert button listener
        const addAudioAlertBtn = document.getElementById('addAudioAlertBtn');
        if (addAudioAlertBtn) {
            addAudioAlertBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.addAudioAlertRule();
            });
        }

        // Audio file upload listener
        const audioFileInput = document.getElementById('audioFileInput');
        if (audioFileInput) {
            audioFileInput.addEventListener('change', (e) => {
                this.handleAudioFileUpload(e);
            });
        }

        // Update time
        this.updateTime();
        setInterval(() => this.updateTime(), 1000);

        // Load config and connect
        await this.loadConfig();
        await this.loadAudioAlertConfig();
    }

    bindControlButtons() {
        const controlGrid = document.getElementById('controlGrid');
        if (!controlGrid) return;

        controlGrid.addEventListener('click', (e) => {
            const btn = e.target.closest('.control-btn');
            if (!btn) return;
            this.handleControlClick(btn);
        });
    }

    async handleControlClick(button) {
        const buttonId = button.dataset.id;
        const command = button.dataset.command;
        const type = button.dataset.type;

        if (!buttonId || !command) {
            console.error('[Control] Missing buttonId or command');
            return;
        }

        let inputValue = null;
        if (type === 'input') {
            const inputField = document.getElementById(`input-${buttonId}`);
            inputValue = inputField ? inputField.value.trim() : '';
            if (!inputValue) {
                this.showToast('warning', '请输入参数');
                return;
            }
        }

        button.classList.add('loading');

        try {
            const response = await fetch(`/api/${this.instanceId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    command: command,
                    button_id: buttonId,
                    input_value: inputValue
                })
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('success', '命令已发送', result.message || command);
                this.addLog('control', `[${command}] ${inputValue || ''}`);
            } else {
                this.showToast('error', '发送失败', result.detail || '未知错误');
            }
        } catch (error) {
            console.error('[Control] Failed to send command:', error);
            this.showToast('error', '网络错误', '无法连接到服务器');
        } finally {
            button.classList.remove('loading');
        }
    }

    async unlockAndConnect() {
        this.connectBtn.disabled = true;

        // Check if already disabled
        if (this.connectBtn.textContent === '已禁用') {
            return;
        }

        this.gateStatus.textContent = '正在初始化音频...';

        const audioUnlocked = await window.audioManager.initialize();
        if (audioUnlocked) {
            this.gateStatus.textContent = '音频已解锁，正在加载配置...';
        }

        await this.loadAudioAlertConfig();
        await this.loadPersistedLogs(100);

        this.gateStatus.textContent = '正在连接 WebSocket...';
        await this.connectWebSocket();
    }

    async loadConfig() {
        try {
            // Use view_uid to fetch config from console - ensures business view always reflects console settings
            const response = await fetch(`/api/view/${this.viewUid}`);
            const data = await response.json();

            if (data.instance) {
                // Update instance_id from fetched config (parent console instance)
                this.instanceId = data.instance.instance_id;

                const instance = data.instance;
                if (instance.metrics_mappings) {
                    this.metricsMappings = instance.metrics_mappings;
                } else if (instance.metrics_mapping) {
                    this.metricsMappings = Object.entries(instance.metrics_mapping).map(([key, name]) => ({
                        la_key: key,
                        display_name: name,
                        unit: '',
                        data_type: 'string'
                    }));
                }
                console.log('[BusinessView] Config loaded from console:', this.instanceId);

                // Check if instance is disabled
                if (instance.enabled === false) {
                    console.warn('[BusinessView] Instance is disabled');
                    this.showDisabledWarning();
                    return;
                }
            }
        } catch (error) {
            console.error('[BusinessView] Failed to load config:', error);
        }
    }

    showDisabledWarning() {
        if (this.connectionGate) {
            this.connectionGate.style.display = 'flex';
            this.gateStatus.textContent = '此实例已被禁用 — 无法查看实时数据';
            if (this.connectBtn) {
                this.connectBtn.disabled = true;
                this.connectBtn.textContent = '已禁用';
                this.connectBtn.style.opacity = '0.5';
                this.connectBtn.style.cursor = 'not-allowed';
            }
        }
    }

    async loadAudioAlertConfig() {
        try {
            // Use view_uid to fetch config from console - ensures business view always reflects console settings
            const response = await fetch(`/api/view/${this.viewUid}`);
            const data = await response.json();

            if (data.instance) {
                // Sync instance_id
                this.instanceId = data.instance.instance_id;

                const rules = data.instance.audio_alerts || [
                    { keyword: 'ERROR', sound: 'error', min_interval: 0 },
                    { keyword: 'WARNING', sound: 'warning', min_interval: 0 }
                ];

                this.audioAlertRules = rules;
                this.audioFiles = data.instance.audio_files || [];

                // Load audio alert match switch (default: false)
                this.audioAlertMatchEnabled = data.instance.audio_alert_match_enabled === true;
                console.log('[BusinessView] Audio alert match enabled:', this.audioAlertMatchEnabled);

                this.audioAlertsEnabled = data.instance.audio_alerts_enabled !== false;
                console.log('[BusinessView] Audio alerts enabled:', this.audioAlertsEnabled);

                this.renderAlertPreview(rules);
                this.renderAudioAlertRules(rules);
                this.renderAudioFilesList(this.audioFiles);
            }
        } catch (error) {
            console.error('[BusinessView] Failed to load audio config:', error);
        }
    }

    renderAlertPreview(rules) {
        // Update badge count
        const badge = document.getElementById('alertCountBadge');
        if (badge) badge.textContent = rules.length;

        // Update total count
        const totalCount = document.getElementById('totalRulesCount');
        if (totalCount) totalCount.textContent = rules.length;

        // Update preview (show first rule)
        const preview = document.getElementById('alertRulesPreview');
        if (preview && rules.length > 0) {
            const firstRule = rules[0];
            preview.innerHTML = `
                <div class="alert-rule-preview" style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.75rem; background: var(--bg-tertiary); border-radius: 4px; font-size: 0.8125rem;">
                    <span class="status-dot" style="background: var(--accent-green); animation: pulse-dot 2s ease-in-out infinite;"></span>
                    <span style="color: var(--text-secondary);">关键词:</span>
                    <span style="color: var(--text-primary); font-weight: 500;">${this.escapeHtml(firstRule.keyword)}</span>
                    <span style="margin-left: auto; color: var(--text-muted); font-size: 0.75rem;">等 <span id="totalRulesCount">${rules.length}</span> 条规则</span>
                </div>
            `;
        } else if (preview) {
            preview.innerHTML = `
                <div class="alert-rule-preview" style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.75rem; background: var(--bg-tertiary); border-radius: 4px; font-size: 0.8125rem;">
                    <span style="color: var(--text-muted);">暂无告警规则</span>
                </div>
            `;
        }
    }

    renderAudioAlertRules(rules) {
        const container = document.getElementById('alertConfigList');
        if (!container) return;

        if (rules.length === 0) {
            container.innerHTML = `
                <div style="padding: 0.75rem; text-align: center; color: var(--text-muted); font-size: 0.8125rem;">
                    暂无告警规则
                </div>
            `;
            return;
        }

        const self = this;
        container.innerHTML = rules.map((rule, index) => {
            // Build audio file options for this rule
            const audioFileOptions = (this.audioFiles || []).map(f =>
                `<option value="${f.id}" ${rule.audio_file_id === f.id ? 'selected' : ''}>${this.escapeHtml(f.name)}</option>`
            ).join('');

            return `
            <div class="alert-rule-item" data-index="${index}" style="padding: 0.75rem; background: var(--bg-tertiary); border-radius: 4px; margin-bottom: 0.5rem; font-size: 0.8125rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <strong style="color: var(--accent-cyan);">规则 ${index + 1}</strong>
                    <button class="alert-rule-delete-btn" data-index="${index}" style="background: transparent; border: none; color: var(--accent-red); cursor: pointer; font-size: 0.75rem;">删除</button>
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">关键词</label>
                    <input type="text" class="alert-rule-keyword" data-index="${index}" value="${this.escapeHtml(rule.keyword)}" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.5rem;">
                    <div>
                        <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">内置声音</label>
                        <select class="alert-rule-sound" data-index="${index}" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                            <option value="error" ${rule.sound === 'error' ? 'selected' : ''}>Error (高频)</option>
                            <option value="warning" ${rule.sound === 'warning' ? 'selected' : ''}>Warning (中频)</option>
                            <option value="stop" ${rule.sound === 'stop' ? 'selected' : ''}>Stop (低频)</option>
                            <option value="info" ${rule.sound === 'info' ? 'selected' : ''}>Info (提示)</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">自定义音频</label>
                        <select class="alert-rule-audio-file" data-index="${index}" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                            <option value="">-- 不使用 --</option>
                            ${audioFileOptions}
                        </select>
                    </div>
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">报警间隔 (分钟，0=不限制)</label>
                    <input type="number" class="alert-rule-interval" data-index="${index}" min="0" max="1440" value="${rule.min_interval || 0}" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                </div>
                <button class="alert-rule-test-btn btn btn-secondary" data-index="${index}" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">测试</button>
            </div>
            `;
        }).join('');

        // Bind event listeners after rendering
        container.querySelectorAll('.alert-rule-keyword').forEach(input => {
            input.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                self.updateAlertRule(index, 'keyword', e.target.value);
            });
        });

        container.querySelectorAll('.alert-rule-sound').forEach(select => {
            select.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                self.updateAlertRule(index, 'sound', e.target.value);
            });
        });

        container.querySelectorAll('.alert-rule-audio-file').forEach(select => {
            select.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                self.updateAlertRule(index, 'audio_file_id', e.target.value);
            });
        });

        container.querySelectorAll('.alert-rule-interval').forEach(input => {
            input.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                self.updateAlertRule(index, 'min_interval', parseInt(e.target.value) || 0);
            });
        });

        container.querySelectorAll('.alert-rule-test-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
                self.testAlertRule(index);
            });
        });

        container.querySelectorAll('.alert-rule-delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
                self.deleteAlertRule(index);
            });
        });
    }

    connectWebSocket() {
        return new Promise((resolve) => {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/${this.instanceId}`;

            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('[WebSocket] Connected');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateConnectionStatus(true);
                this.hideConnectionGate();
                this.startPingInterval();
                this.addLog('connection', 'WebSocket 已连接');
                resolve(true);
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (e) {
                    console.error('[WebSocket] Parse error:', e);
                }
            };

            this.ws.onerror = (error) => {
                console.error('[WebSocket] Error:', error);
                this.addLog('error', 'WebSocket 连接错误');
            };

            this.ws.onclose = () => {
                console.log('[WebSocket] Disconnected');
                this.isConnected = false;
                this.stopPingInterval();
                this.updateConnectionStatus(false);
                this.addLog('warning', 'WebSocket 连接已断开');
                this.scheduleReconnect();
                resolve(false);
            };
        });
    }

    handleMessage(data) {
        switch (data.type) {
            case 'connection':
                break;
            case 'pong':
                this.lastPongTime = Date.now();
                break;
            case 'data':
                this.handleDataUpdate(data.payload);
                break;
            case 'alert':
                this.handleAlert(data.payload);
                break;
            case 'config_sync':
                this.handleConfigSync(data.payload);
                break;
            default:
                console.log('[WebSocket] Unknown type:', data.type);
        }
    }

    /**
     * Handle config sync from dashboard
     */
    handleConfigSync(payload) {
        console.log('[BusinessView] Received config sync:', payload);

        if (payload.metrics_mappings) {
            this.metricsMappings = payload.metrics_mappings;
            this.renderMetrics();
        }

        if (payload.audio_alerts) {
            this.audioAlertRules = payload.audio_alerts;
            this.renderAlertPreview(this.audioAlertRules);
            this.renderAudioAlertRules(this.audioAlertRules);
        }

        if (payload.audio_files) {
            this.audioFiles = payload.audio_files;
            this.renderAudioFilesList(this.audioFiles);
        }

        if (payload.audio_alerts_enabled !== undefined) {
            this.audioAlertsEnabled = payload.audio_alerts_enabled;
            console.log('[BusinessView] Audio alerts enabled synced:', this.audioAlertsEnabled);
        }

        this.showToast('info', '配置已更新', '从控制台接收到最新配置');
        this.addLog('info', '[配置同步] 已更新业务视图配置');
    }

    handleDataUpdate(payload) {
        const timestamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        document.getElementById('lastUpdate').textContent = `最后更新: ${timestamp}`;

        if (typeof payload === 'object' && payload !== null) {
            Object.entries(payload).forEach(([key, value]) => {
                this.metrics[key] = { value: value, lastUpdate: Date.now() };
            });
            this.renderMetrics();
        }

        this.addLog('data', JSON.stringify(payload, null, 2));
    }

    renderMetrics() {
        const container = document.getElementById('metricsGrid');
        if (!container || !this.metricsMappings.length) return;

        container.innerHTML = this.metricsMappings.map(mapping => {
            const data = this.metrics[mapping.la_key];
            const value = data ? data.value : '-';
            return `
                <div class="metric-card">
                    <div class="metric-label">${this.escapeHtml(mapping.display_name)}</div>
                    <div class="metric-value">
                        ${this.formatMetricValue(value, mapping)}
                        ${mapping.unit ? `<span class="metric-unit">${this.escapeHtml(mapping.unit)}</span>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    formatMetricValue(value, mapping) {
        if (value === null || value === undefined || value === '-') return '-';
        if (mapping.data_type === 'number' && typeof value === 'number') {
            return value.toFixed(mapping.format ? parseInt(mapping.format) : 2);
        }
        return this.escapeHtml(String(value));
    }

    handleAlert(payload) {
        const level = payload.level || 'info';
        const message = payload.message || JSON.stringify(payload);

        this.addLog(level === 'critical' ? 'error' : level, `[${level.toUpperCase()}] ${message}`);

        if (!window.audioManager.isAudioMuted && this.audioAlertsEnabled) {
            this.playMatchingAlertSound(message, level);
        }
    }

    async playMatchingAlertSound(message, level) {
        const upperMessage = message.toUpperCase();

        console.log('[BusinessView] Looking for matching rule:', { message: upperMessage, level, rules: this.audioAlertRules, files: this.audioFiles, matchEnabled: this.audioAlertMatchEnabled });

        // If match switch is disabled (default), play sound directly without keyword matching
        if (!this.audioAlertMatchEnabled) {
            console.log('[BusinessView] Keyword matching disabled, playing default sound for level:', level);
            await this.playAlertSound(level, null);
            return;
        }

        // Default sound mappings for common keywords
        const defaultMappings = {
            'ERROR': 'error',
            '故障': 'error',
            'WARNING': 'warning',
            '警告': 'warning',
            'STOP': 'stop',
            '停止': 'stop',
            'ALERT': 'error'
        };

        // Find matching rule
        let matchedRule = null;
        let matchedFileUrl = null;
        let soundToPlay = level; // Default to level-based sound
        let shouldPlay = true;

        if (this.audioAlertRules && this.audioAlertRules.length > 0) {
            for (const rule of this.audioAlertRules) {
                const keyword = (rule.keyword || '').toUpperCase();
                if (!keyword || keyword === 'KEYWORD') continue; // Skip empty/default keywords

                console.log('[BusinessView] Checking rule:', { keyword, match: upperMessage.includes(keyword) });
                if (upperMessage.includes(keyword)) {
                    matchedRule = rule;
                    soundToPlay = rule.sound || level;

                    // Check time interval filter
                    const minInterval = rule.min_interval || 0;
                    if (minInterval > 0) {
                        const now = Date.now();
                        const lastTime = this.lastAlertTimes[keyword];
                        const intervalMs = minInterval * 60 * 1000;

                        if (lastTime && (now - lastTime) < intervalMs) {
                            console.log(`[BusinessView] Skipped ${keyword} alert, within ${minInterval}min interval`);
                            shouldPlay = false;
                            continue;
                        }
                        this.lastAlertTimes[keyword] = now;
                    }

                    // Check for custom audio file
                    if (rule.audio_file_id && this.audioFiles) {
                        const audioFile = this.audioFiles.find(f => f.id === rule.audio_file_id);
                        if (audioFile) {
                            matchedFileUrl = audioFile.url;
                            console.log('[BusinessView] Found custom audio file:', audioFile.name);
                        }
                    }

                    if (shouldPlay) break;
                }
            }
        }

        // If no rule matched but message contains default keywords, use those
        if (!matchedRule) {
            for (const [keyword, sound] of Object.entries(defaultMappings)) {
                if (upperMessage.includes(keyword)) {
                    soundToPlay = sound;
                    console.log('[BusinessView] Using default mapping:', { keyword, sound });
                    break;
                }
            }
        }

        if (shouldPlay) {
            console.log('[BusinessView] Playing sound:', { sound: soundToPlay, fileUrl: matchedFileUrl });
            await this.playAlertSound(soundToPlay, matchedFileUrl);
        }
    }

    async playAlertSound(soundName, audioFileUrl = null) {
        if (window.audioManager) {
            await window.audioManager.playSound(soundName, audioFileUrl);
        }
    }

    async testFirstAlertRule() {
        if (this.audioAlertRules && this.audioAlertRules.length > 0) {
            const rule = this.audioAlertRules[0];
            await this.playAlertSound(rule.sound);
        } else {
            await this.playAlertSound('error');
        }
    }

    // Logs management
    addLog(type, message) {
        if (this.isPaused) return;

        const timestamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        const log = { id: Date.now() + Math.random(), timestamp, type, message };

        this.logs.push(log);
        if (this.logs.length > this.maxLogs) {
            this.logs = this.logs.slice(-this.maxLogs);
        }

        if (this.shouldShowLog(log)) {
            this.renderLogLine(log);
        }

        this.persistLog(log);
    }

    async persistLog(log) {
        try {
            await fetch(`/api/${this.instanceId}/logs`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(log)
            });
        } catch (error) {
            console.error('[Log] Persist failed:', error);
        }
    }

    async loadPersistedLogs(limit = 100) {
        try {
            const response = await fetch(`/api/${this.instanceId}/logs?limit=${limit}&offset=${this.logsOffset}`);
            const data = await response.json();

            if (data.logs && data.logs.length > 0) {
                this.logs = data.logs.concat(this.logs);
                this.logsOffset += data.logs.length;
                this.renderAllLogs();
            }
        } catch (error) {
            console.error('[Log] Load failed:', error);
        }
    }

    setLogFilter(filter) {
        this.logFilter = filter;

        // Update tab UI
        document.querySelectorAll('.terminal-tabs .tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.filter === filter);
        });

        // Re-render logs
        this.renderAllLogs();
    }

    shouldShowLog(log) {
        if (this.logFilter === 'all') return true;
        const typeMap = {
            'data': ['data'],
            'control': ['success', 'control'],
            'alert': ['error', 'warning', 'alert']
        };
        return typeMap[this.logFilter] && typeMap[this.logFilter].includes(log.type);
    }

    renderLogLine(log) {
        const terminal = document.getElementById('terminalContent');
        if (!terminal) return;

        const line = document.createElement('div');
        line.className = `terminal-line alert-${log.type}`;

        const typeColors = {
            info: 'var(--accent-cyan)',
            data: 'var(--accent-cyan)',
            error: 'var(--accent-red)',
            warning: 'var(--accent-orange)',
            success: 'var(--accent-green)',
            connection: 'var(--accent-cyan)',
            control: 'var(--accent-orange)'
        };

        line.innerHTML = `
            <span class="terminal-time">${log.timestamp}</span>
            <span class="terminal-type" style="color: ${typeColors[log.type] || 'var(--text-secondary)'};">[${log.type.toUpperCase()}]</span>
            <span class="terminal-message">${this.escapeHtml(String(log.message)).replace(/\n/g, '<br>')}</span>
        `;

        terminal.appendChild(line);
        terminal.scrollTop = terminal.scrollHeight;
    }

    renderAllLogs() {
        const terminal = document.getElementById('terminalContent');
        if (!terminal) return;

        const welcomeLines = terminal.querySelectorAll('.terminal-welcome');
        terminal.innerHTML = '';
        welcomeLines.forEach(line => terminal.appendChild(line));

        this.logs.forEach(log => {
            if (this.shouldShowLog(log)) this.renderLogLine(log);
        });
    }

    clearLogs() {
        if (confirm('确定要清空日志吗？')) {
            this.logs = [];
            const terminal = document.getElementById('terminalContent');
            if (terminal) {
                const welcomeLines = terminal.querySelectorAll('.terminal-welcome');
                terminal.innerHTML = '';
                welcomeLines.forEach(line => terminal.appendChild(line));
            }
            fetch(`/api/${this.instanceId}/logs`, { method: 'DELETE' });
        }
    }

    togglePause() {
        this.isPaused = !this.isPaused;
        const icon = document.getElementById('pauseIcon');
        if (icon) {
            icon.innerHTML = this.isPaused
                ? '<rect x="5" y="3" width="6" height="10" rx="1" fill="currentColor"/><rect x="12" y="3" width="6" height="10" rx="1" fill="currentColor"/>'
                : '<rect x="4" y="3" width="3" height="10" rx="1" fill="currentColor"/><rect x="9" y="3" width="3" height="10" rx="1" fill="currentColor"/>';
        }
    }

    // UI Helpers
    hideConnectionGate() {
        if (this.connectionGate) {
            this.connectionGate.style.opacity = '0';
            setTimeout(() => {
                this.connectionGate.style.display = 'none';
            }, 300);
        }
    }

    updateConnectionStatus(connected) {
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        if (connected) {
            dot.classList.add('connected');
            text.textContent = '已连接';
        } else {
            dot.classList.remove('connected');
            text.textContent = '未连接';
        }
    }

    updateMuteIcon(isMuted) {
        const icon = document.getElementById('volumeIcon');
        if (isMuted) {
            icon.innerHTML = '<path d="M3 7H6L10 3V17L6 13H3V7Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M14 9L18 13M18 9L14 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>';
            icon.style.color = 'var(--accent-red)';
        } else {
            icon.innerHTML = '<path d="M3 7H6L10 3V17L6 13H3V7Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M14 7C15.5 8.5 15.5 11.5 14 13M17 4C20 7 20 13 17 16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>';
            icon.style.color = '';
        }
    }

    updateVolumeSliderColor(value) {
        const slider = document.getElementById('volumeSlider');
        if (slider) {
            slider.style.background = `linear-gradient(to right, var(--accent-cyan) 0%, var(--accent-cyan) ${value}%, var(--bg-tertiary) ${value}%, var(--bg-tertiary) 100%)`;
        }
    }

    updateTime() {
        const el = document.getElementById('headerTime');
        if (el) el.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    }

    showToast(type, title, message = '') {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-title">${this.escapeHtml(title)}</div>
            ${message ? `<div class="toast-message">${this.escapeHtml(message)}</div>` : ''}
        `;

        container.appendChild(toast);
        setTimeout(() => toast.classList.add('show'), 10);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Reconnection
    scheduleReconnect() {
        if (this.reconnectTimer) return;
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay);
        this.reconnectAttempts++;

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            if (!this.isConnected) this.connectWebSocket();
        }, delay);
    }

    startPingInterval() {
        this.pingInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping' }));
                if (Date.now() - this.lastPongTime > 30000) {
                    this.ws.close();
                }
            }
        }, 5000);  // 每5秒发送一次心跳，避免Windows空闲超时
    }

    stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    // Audio Alert Management
    async updateAlertRule(index, field, value) {
        if (this.audioAlertRules[index]) {
            this.audioAlertRules[index][field] = value;
            console.log(`[AudioAlert] Updated rule ${index}: ${field} = ${value}`);

            // Save to server
            try {
                const response = await fetch(`/api/instances/${this.instanceId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ audio_alerts: this.audioAlertRules })
                });

                if (response.ok) {
                    this.showToast('success', '已保存', '规则已更新');
                } else {
                    this.showToast('error', '保存失败', '无法保存规则');
                }
            } catch (error) {
                console.error('[BusinessView] Failed to save rule:', error);
                this.showToast('error', '保存失败', '网络错误');
            }
        }
    }

    testAlertRule(index) {
        if (this.audioAlertRules[index]) {
            const rule = this.audioAlertRules[index];
            // Find audio file URL if specified
            let audioFileUrl = null;
            if (rule.audio_file_id && this.audioFiles) {
                const audioFile = this.audioFiles.find(f => f.id === rule.audio_file_id);
                if (audioFile) {
                    audioFileUrl = audioFile.url;
                }
            }
            this.playAlertSound(rule.sound, audioFileUrl);
            this.showToast('info', '测试音频', `播放: ${rule.keyword}`);
        }
    }

    async deleteAlertRule(index) {
        if (confirm('确定要删除这条告警规则吗？')) {
            this.audioAlertRules.splice(index, 1);
            this.renderAudioAlertRules(this.audioAlertRules);
            this.renderAlertPreview(this.audioAlertRules);
            this.showToast('success', '规则已删除');

            // Save to server
            try {
                await fetch(`/api/instances/${this.instanceId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ audio_alerts: this.audioAlertRules })
                });
            } catch (error) {
                console.error('[BusinessView] Failed to save after delete:', error);
            }
        }
    }

    async addAudioAlertRule() {
        const keyword = prompt('输入触发关键词 (如: ERROR, STOP):');
        if (!keyword) return;

        const newRule = {
            keyword: keyword,
            sound: 'error',
            min_interval: 0,
            audio_file_id: ''
        };

        this.audioAlertRules.push(newRule);
        this.renderAudioAlertRules(this.audioAlertRules);
        this.renderAlertPreview(this.audioAlertRules);
        this.showToast('success', '规则已添加', `关键词: ${keyword}`);

        // Save to server
        try {
            await fetch(`/api/instances/${this.instanceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ audio_alerts: this.audioAlertRules })
            });
        } catch (error) {
            console.error('[BusinessView] Failed to save after add:', error);
        }
    }

    // Audio Files Management
    renderAudioFilesList(files) {
        const container = document.getElementById('audioFilesList');
        if (!container) return;

        const self = this;
        if (files.length === 0) {
            container.innerHTML = `
                <div style="padding: 0.75rem; text-align: center; color: var(--text-muted); font-size: 0.8125rem;">
                    暂无自定义音频文件
                </div>
            `;
            return;
        }

        container.innerHTML = files.map((file) => `
            <div class="audio-file-item" style="display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; background: var(--bg-tertiary); border-radius: 4px; margin-bottom: 0.5rem; font-size: 0.8125rem;">
                <div style="display: flex; align-items: center; gap: 0.5rem; overflow: hidden;">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style="flex-shrink: 0; color: var(--accent-cyan);">
                        <path d="M8 2V14M2 8H14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                    <span style="color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${self.escapeHtml(file.name)}">${self.escapeHtml(file.name)}</span>
                </div>
                <div style="display: flex; gap: 0.5rem; flex-shrink: 0;">
                    <button class="btn btn-secondary audio-file-play" data-url="${file.url}" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">播放</button>
                    <button class="btn btn-danger audio-file-delete" data-id="${file.id}" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">删除</button>
                </div>
            </div>
        `).join('');

        // Bind event listeners
        container.querySelectorAll('.audio-file-play').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const url = e.target.dataset.url;
                self.playAudioFile(url);
            });
        });

        container.querySelectorAll('.audio-file-delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const fileId = e.target.dataset.id;
                self.deleteAudioFile(fileId);
            });
        });
    }

    async playAudioFile(url) {
        if (window.audioManager) {
            await window.audioManager.playSound('custom', url);
        }
    }

    async handleAudioFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        const name = prompt('为音频文件命名:', file.name);
        if (!name) return;

        const formData = new FormData();
        formData.append('file', file);
        formData.append('name', name);

        try {
            const response = await fetch(`/api/${this.instanceId}/audio/upload`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('success', '上传成功', `文件 "${name}" 已上传`);
                this.loadAudioAlertConfig();
            } else {
                this.showToast('error', '上传失败', result.detail || '未知错误');
            }
        } catch (error) {
            console.error('Failed to upload audio file:', error);
            this.showToast('error', '上传失败', '网络错误或服务器无响应');
        }

        // Reset input
        event.target.value = '';
    }

    async deleteAudioFile(fileId) {
        if (!confirm('确定要删除这个音频文件吗?')) return;

        try {
            const response = await fetch(`/api/${this.instanceId}/audio/${fileId}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('success', '删除成功', '音频文件已删除');
                this.loadAudioAlertConfig();
            } else {
                this.showToast('error', '删除失败', result.detail || '未知错误');
            }
        } catch (error) {
            console.error('Failed to delete audio file:', error);
            this.showToast('error', '删除失败', '网络错误或服务器无响应');
        }
    }

    // Settings Panel Functions
    toggleSettingsPanel() {
        const panel = document.getElementById('settingsPanel');
        const overlay = document.getElementById('settingsPanelOverlay');
        if (!panel || !overlay) return;

        const isVisible = panel.style.display !== 'none';
        panel.style.display = isVisible ? 'none' : 'block';
        overlay.style.display = isVisible ? 'none' : 'block';

        if (!isVisible) {
            this.loadSettingsPanel();
        }
    }

    async loadSettingsPanel() {
        try {
            // Use view_uid to fetch config from console - ensures business view always reflects console settings
            const response = await fetch(`/api/view/${this.viewUid}`);
            const data = await response.json();

            if (data.instance) {
                const instance = data.instance;
                // Sync instance_id
                this.instanceId = instance.instance_id;

                const viewUidInput = document.getElementById('settingsViewUid');
                const viewLinkSpan = document.getElementById('settingsViewLink');

                let currentUid = instance.view_uid;
                if (!currentUid) {
                    currentUid = this.generateUid();
                }

                if (viewUidInput) viewUidInput.value = currentUid;

                if (viewLinkSpan) {
                    const protocol = window.location.protocol;
                    const hostname = window.location.hostname;
                    const fullUrl = `${protocol}//${hostname}:6010/view/${currentUid}`;
                    viewLinkSpan.innerHTML = `<a href="${fullUrl}" target="_blank" style="color: var(--accent-cyan);">${fullUrl}</a>`;
                }

                this.tempMetricsMappings = instance.metrics_mappings || [];
                this.renderSettingsMetricsList(this.tempMetricsMappings);

                this.tempControlButtons = instance.control_buttons || [];
                this.renderSettingsControlButtons(this.tempControlButtons);
            }
        } catch (error) {
            console.error('[BusinessView] Failed to load settings:', error);
        }
    }

    renderSettingsMetricsList(mappings) {
        const container = document.getElementById('settingsMetricsList');
        if (!container) return;

        if (mappings.length === 0) {
            container.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.875rem;">暂无指标映射配置</div>';
            return;
        }

        const self = this;
        container.innerHTML = mappings.map((mapping, index) => `
            <div class="metric-mapping-item">
                <input type="text" placeholder="LA字段名" value="${this.escapeHtml(mapping.la_key || '')}" data-field="la_key" data-index="${index}">
                <input type="text" placeholder="显示名称" value="${this.escapeHtml(mapping.display_name || '')}" data-field="display_name" data-index="${index}">
                <input type="text" placeholder="单位" value="${this.escapeHtml(mapping.unit || '')}" data-field="unit" data-index="${index}" style="width: 60px;">
                <button class="remove-mapping-btn" data-index="${index}" title="删除">删除</button>
            </div>
        `).join('');

        container.querySelectorAll('input').forEach(input => {
            input.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                const field = e.target.dataset.field;
                self.updateMetricsMapping(index, field, e.target.value);
            });
        });

        container.querySelectorAll('.remove-mapping-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
                self.removeMetricsMapping(index);
            });
        });
    }

    renderSettingsControlButtons(buttons) {
        const container = document.getElementById('settingsControlButtons');
        if (!container) return;

        if (buttons.length === 0) {
            container.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.875rem;">暂无控制按钮</div>';
            return;
        }

        const self = this;
        container.innerHTML = buttons.map((btn, index) => `
            <div class="control-button-item">
                <input type="text" placeholder="标签" value="${this.escapeHtml(btn.label || '')}" data-field="label" data-index="${index}">
                <input type="text" placeholder="命令" value="${this.escapeHtml(btn.command || '')}" data-field="command" data-index="${index}">
                <select data-field="color" data-index="${index}">
                    <option value="green" ${btn.color === 'green' ? 'selected' : ''}>绿色</option>
                    <option value="red" ${btn.color === 'red' ? 'selected' : ''}>红色</option>
                    <option value="blue" ${btn.color === 'blue' ? 'selected' : ''}>蓝色</option>
                    <option value="orange" ${btn.color === 'orange' ? 'selected' : ''}>橙色</option>
                </select>
                <button class="remove-control-btn" data-index="${index}" title="删除">删除</button>
            </div>
        `).join('');

        container.querySelectorAll('input, select').forEach(input => {
            input.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                const field = e.target.dataset.field;
                self.updateControlButton(index, field, e.target.value);
            });
        });

        container.querySelectorAll('.remove-control-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.index);
                self.removeControlButton(index);
            });
        });
    }

    addMetricsMapping() {
        if (!this.tempMetricsMappings) {
            this.tempMetricsMappings = [];
        }
        this.tempMetricsMappings.push({
            la_key: '',
            display_name: '',
            unit: '',
            data_type: 'string',
            format: ''
        });
        this.renderSettingsMetricsList(this.tempMetricsMappings);
    }

    removeMetricsMapping(index) {
        if (this.tempMetricsMappings) {
            this.tempMetricsMappings.splice(index, 1);
            this.renderSettingsMetricsList(this.tempMetricsMappings);
        }
    }

    updateMetricsMapping(index, field, value) {
        if (this.tempMetricsMappings && this.tempMetricsMappings[index]) {
            this.tempMetricsMappings[index][field] = value;
        }
    }

    addControlButtonInSettings() {
        if (!this.tempControlButtons) {
            this.tempControlButtons = [];
        }
        this.tempControlButtons.push({
            id: 'btn_' + Date.now(),
            label: '',
            command: '',
            color: 'blue',
            button_type: 'command'
        });
        this.renderSettingsControlButtons(this.tempControlButtons);
    }

    removeControlButton(index) {
        if (this.tempControlButtons) {
            this.tempControlButtons.splice(index, 1);
            this.renderSettingsControlButtons(this.tempControlButtons);
        }
    }

    updateControlButton(index, field, value) {
        if (this.tempControlButtons && this.tempControlButtons[index]) {
            this.tempControlButtons[index][field] = value;
        }
    }

    regenerateViewUid() {
        const newUid = this.generateUid();
        const viewUidInput = document.getElementById('settingsViewUid');
        if (viewUidInput) {
            viewUidInput.value = newUid;
        }

        const viewLinkSpan = document.getElementById('settingsViewLink');
        if (viewLinkSpan) {
            const protocol = window.location.protocol;
            const hostname = window.location.hostname;
            const fullUrl = `${protocol}//${hostname}:6010/view/${newUid}`;
            viewLinkSpan.innerHTML = `<a href="${fullUrl}" target="_blank" style="color: var(--accent-cyan);">${fullUrl}</a>`;
        }
    }

    generateUid() {
        return Array.from({length: 16}, () =>
            'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'[Math.floor(Math.random() * 62)]
        ).join('');
    }

    async saveSettings() {
        try {
            const viewUid = document.getElementById('settingsViewUid')?.value || '';

            const updates = {
                view_uid: viewUid,
                metrics_mappings: this.tempMetricsMappings || [],
                control_buttons: this.tempControlButtons || []
            };

            const response = await fetch(`/api/instances/${this.instanceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });

            if (response.ok) {
                this.showToast('success', '保存成功', '设置已保存');
                this.toggleSettingsPanel();
                await this.loadConfig();
                await this.loadAudioAlertConfig();
            } else {
                const error = await response.text();
                this.showToast('error', '保存失败', error);
            }
        } catch (error) {
            console.error('[BusinessView] Failed to save settings:', error);
            this.showToast('error', '保存失败', '网络错误');
        }
    }
}

// Global UI functions
function toggleAlertConfig() {
    const content = document.getElementById('alertConfigContent');
    const icon = document.getElementById('collapseIcon');
    if (!content) return;
    const isVisible = content.style.display !== 'none';
    content.style.display = isVisible ? 'none' : 'block';
    if (icon) icon.style.transform = isVisible ? 'rotate(0deg)' : 'rotate(180deg)';
}

function expandAlertConfig() {
    const preview = document.getElementById('alertRulesPreview');
    const full = document.getElementById('alertConfigFull');
    const btn = document.getElementById('expandAlertConfigBtn');
    if (preview) preview.style.display = 'none';
    if (full) full.style.display = 'block';
    if (btn) btn.style.display = 'none';
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new BusinessViewManager();
});
