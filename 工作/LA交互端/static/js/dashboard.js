/**
 * Dashboard JavaScript
 * Handles WebSocket connection, real-time data updates, control forwarding,
 * terminal logging, and reconnection logic with exponential backoff.
 */

class DashboardManager {
    constructor() {
        this.instanceId = document.body.dataset.instanceId;
        this.singleInstanceMode = document.body.dataset.singleInstance === 'true';
        this.ws = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.reconnectTimer = null;
        this.maxReconnectDelay = 30000; // 30 seconds max
        this.pingInterval = null;
        this.lastPongTime = Date.now();

        // Terminal state
        this.logs = [];
        this.logFilter = 'all';
        this.isPaused = false;
        this.maxLogs = 1000;

        // Log batch rendering optimization
        this.logBatch = [];
        this.logBatchTimer = null;
        this.logBatchInterval = 50; // 50ms batch processing
        this.isRenderingBatch = false;

        // Scroll handling
        this.userScrolled = false;
        this.autoScrollThreshold = 100; // 100px from bottom to trigger auto-scroll

        // Metrics cache
        this.metrics = {};

        // Audio alert time filtering
        this.lastAlertTimes = {};

        // Audio alert match switch (default: false = play all sounds without matching)
        this.audioAlertMatchEnabled = false;

        // Server info (IP address)
        this.serverIp = null;

        // DOM elements
        this.connectionGate = document.getElementById('connectionGate');
        this.connectBtn = document.getElementById('connectBtn');
        this.gateStatus = document.getElementById('gateStatus');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.statusDot = document.getElementById('statusDot');
        this.statusText = document.getElementById('statusText');
        this.metricsGrid = document.getElementById('metricsGrid');
        this.terminalContent = document.getElementById('terminalContent');
        this.lastUpdateEl = document.getElementById('lastUpdate');

        this.init();
    }

    init() {
        // Connection gate
        this.connectBtn.addEventListener('click', () => this.unlockAndConnect());

        // Control buttons
        document.querySelectorAll('.control-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.handleControlClick(e));
        });

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

        // Restore saved volume
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

        // Initialize view link
        this.initViewLink();

        // Load server info (IP address)
        this.loadServerInfo();

        // Update mute icon initially
        this.updateMuteIcon(window.audioManager.isAudioMuted);

        // Note: loadAudioAlertConfig is now called in unlockAndConnect to ensure config is loaded before WebSocket connects

        // Add audio alert button listener in settings panel will be bound when panel opens

        // Update time
        this.updateTime();
        setInterval(() => this.updateTime(), 1000);

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleKeydown(e));

        // Listen to terminal scroll to detect user manual scroll
        this.terminalContent.addEventListener('scroll', () => {
            this.userScrolled = !this.isUserAtBottom();
        });
    }

    updateMuteIcon(isMuted) {
        const icon = document.getElementById('volumeIcon');
        if (isMuted) {
            icon.innerHTML = `
                <path d="M3 7H6L10 3V17L6 13H3V7Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                <path d="M14 9L18 13M18 9L14 13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            `;
            icon.style.color = 'var(--accent-red)';
        } else {
            icon.innerHTML = `
                <path d="M3 7H6L10 3V17L6 13H3V7Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
                <path d="M14 7C15.5 8.5 15.5 11.5 14 13M17 4C20 7 20 13 17 16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            `;
            icon.style.color = '';
        }
    }

    async loadServerInfo() {
        /* Load server IP address and info */
        try {
            const response = await fetch('/api/server-info');
            if (response.ok) {
                const data = await response.json();
                this.serverIp = data.ip;
                console.log('[Dashboard] Server IP loaded:', this.serverIp);
            }
        } catch (err) {
            console.error('[Dashboard] Failed to load server info:', err);
            // Fallback to localhost
            this.serverIp = '127.0.0.1';
        }
    }

    updateVolumeSliderColor(value) {
        const slider = document.getElementById('volumeSlider');
        if (!slider) return;

        const percentage = value;
        slider.style.background = `linear-gradient(to right, var(--accent-cyan) 0%, var(--accent-cyan) ${percentage}%, var(--bg-tertiary) ${percentage}%, var(--bg-tertiary) 100%)`;
    }

    initViewLink() {
        const viewLinkInput = document.getElementById('viewLinkInput');
        const copyBtn = document.getElementById('copyViewLinkBtn');
        if (!viewLinkInput) return;

        const viewUid = viewLinkInput.dataset.viewUid;

        if (viewUid && viewUid !== 'None' && viewUid !== '') {
            // Business view uses port 6010
            const protocol = window.location.protocol;
            const hostname = window.location.hostname;
            viewLinkInput.value = `${protocol}//${hostname}:6010/view/${viewUid}`;
            if (copyBtn) copyBtn.disabled = false;
        } else {
            viewLinkInput.value = '未配置';
            if (copyBtn) copyBtn.disabled = true;
        }
    }

    updateTime() {
        const timeEl = document.getElementById('headerTime');
        if (timeEl) {
            timeEl.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        }
    }

    async unlockAndConnect() {
        this.connectBtn.disabled = true;
        this.gateStatus.textContent = '正在初始化音频...';

        // Unlock audio context
        const audioUnlocked = await window.audioManager.initialize();
        if (audioUnlocked) {
            this.gateStatus.textContent = '音频已解锁，正在加载配置...';
        }

        // Load audio alert config before connecting WebSocket
        await this.loadAudioAlertConfig();

        // Load persisted logs
        await this.loadPersistedLogs();

        this.gateStatus.textContent = '正在连接 WebSocket...';

        // Connect WebSocket
        await this.connectWebSocket();
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
                this.updateConnectionStatus('connected');
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
                    console.error('[WebSocket] Failed to parse message:', e);
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
                this.updateConnectionStatus('disconnected');
                this.addLog('warning', 'WebSocket 连接已断开');
                this.scheduleReconnect();
                resolve(false);
            };
        });
    }

    scheduleReconnect() {
        if (this.reconnectTimer) return;

        // Exponential backoff with jitter
        const baseDelay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay);
        const jitter = Math.random() * 1000;
        const delay = baseDelay + jitter;

        this.reconnectAttempts++;
        console.log(`[WebSocket] Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts})`);

        this.updateConnectionStatus('reconnecting', Math.round(delay / 1000));

        this.reconnectTimer = setTimeout(async () => {
            this.reconnectTimer = null;
            if (!this.isConnected) {
                await this.connectWebSocket();
            }
        }, delay);
    }

    hideConnectionGate() {
        this.connectionGate.classList.add('hidden');
        // Enable terminal input
        document.getElementById('terminalInput').disabled = false;
    }

    updateConnectionStatus(status, retryIn = null) {
        this.connectionStatus.className = 'connection-status ' + status;

        const statusMap = {
            connected: { text: '已连接', color: 'var(--accent-green)' },
            disconnected: { text: '已断开', color: 'var(--accent-red)' },
            reconnecting: { text: retryIn ? `${retryIn}s 后重连` : '重连中...', color: 'var(--accent-orange)' }
        };

        this.statusText.textContent = statusMap[status].text;
    }

    startPingInterval() {
        this.pingInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'ping' }));

                // Check for pong timeout (30 seconds)
                if (Date.now() - this.lastPongTime > 30000) {
                    console.log('[WebSocket] Pong timeout, reconnecting...');
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

    handleMessage(data) {
        switch (data.type) {
            case 'connection':
                console.log('[WebSocket] Connection confirmed');
                break;

            case 'pong':
                this.lastPongTime = Date.now();
                break;

            case 'data':
                this.handleDataUpdate(data.payload);
                break;

            case 'alert':
                console.log('%c[WebSocket] 收到 alert 消息:', 'color: #ff5722; font-weight: bold;', data);
                this.handleAlert(data.payload);
                break;

            case 'error':
                this.addLog('error', data.message);
                break;

            default:
                console.log('[WebSocket] Unknown message type:', data.type);
        }
    }

    handleAlert(payload) {
        const level = payload.level || 'info';
        const message = payload.message || JSON.stringify(payload);

        console.log('%c[Dashboard] ========== 收到告警消息 ==========', 'background: #ff5722; color: white; font-size: 14px;');
        console.log('[Dashboard] Level:', level);
        console.log('[Dashboard] Message:', message);
        console.log('[Dashboard] Raw payload:', payload);
        console.log('[Dashboard] Timestamp:', new Date().toLocaleString());

        // Add to log
        this.addLog(level === 'critical' ? 'error' : level, `[${level.toUpperCase()}] ${message}`);

        // Find matching audio alert config and play
        if (window.audioManager && !window.audioManager.isAudioMuted) {
            console.log('[Dashboard] Playing alert sound for:', message);
            this.playMatchingAlertSound(message, level);
        } else {
            console.log('[Dashboard] Audio manager not ready or muted:', {
                hasAudioManager: !!window.audioManager,
                isMuted: window.audioManager && window.audioManager.isAudioMuted
            });
        }
    }

    /**
     * Find matching alert config and play appropriate sound
     */
    async playMatchingAlertSound(message, level) {
        const upperMessage = message.toUpperCase();

        console.log('[Dashboard] Looking for matching rule:', { message: upperMessage, level, rules: this.audioAlertRules, files: this.audioFiles, matchEnabled: this.audioAlertMatchEnabled });

        // If match switch is disabled (default), play sound directly without keyword matching
        if (!this.audioAlertMatchEnabled) {
            console.log('[Dashboard] Keyword matching disabled, playing default sound for level:', level);
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
                console.log('[Dashboard] Checking rule:', { keyword, match: upperMessage.includes(keyword) });
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
                            console.log(`[Dashboard] Skipped ${keyword} alert, within ${minInterval}min interval`);
                            shouldPlay = false;
                            break;
                        }
                        this.lastAlertTimes[keyword] = now;
                    }

                    // Find audio file if specified
                    if (rule.audio_file_id && this.audioFiles) {
                        const audioFile = this.audioFiles.find(f => f.id === rule.audio_file_id);
                        if (audioFile) {
                            matchedFileUrl = audioFile.url;
                        }
                    }
                    break;
                }
            }
        }

        if (!shouldPlay) {
            console.log('[Dashboard] Sound skipped due to time interval filter');
            return;
        }

        // If no rule matched, check default mappings
        if (!matchedRule) {
            console.log('[Dashboard] No user rule matched, checking default mappings');
            for (const [keyword, sound] of Object.entries(defaultMappings)) {
                if (upperMessage.includes(keyword)) {
                    soundToPlay = sound;
                    console.log('[Dashboard] Matched default keyword:', keyword, '-> sound:', sound);
                    break;
                }
            }
        }

        console.log('[Dashboard] Playing sound:', { sound: soundToPlay, fileUrl: matchedFileUrl, matchedRule, hasUserRules: !!(this.audioAlertRules && this.audioAlertRules.length > 0) });

        // Play sound (custom file or generated)
        try {
            await this.playAlertSound(soundToPlay, matchedFileUrl);
            console.log('[Dashboard] Sound played successfully');
        } catch (e) {
            console.error('[Dashboard] Failed to play sound:', e);
        }
    }

    async playAlertSound(level, audioFileUrl = null) {
        console.log('[Dashboard] playAlertSound called:', { level, audioFileUrl, hasAudioManager: !!window.audioManager });

        // Play custom audio file if provided
        if (audioFileUrl && window.audioManager) {
            console.log('[Dashboard] Playing custom audio file:', audioFileUrl);
            await window.audioManager.playSound(level, audioFileUrl);
            return;
        }

        // Fallback to generated beep sound
        try {
            const audioManager = window.audioManager;
            if (!audioManager) {
                console.error('[Dashboard] No audio manager available');
                return;
            }

            const audioCtx = audioManager.context;
            if (!audioCtx) {
                console.error('[Dashboard] No audio context available');
                return;
            }

            // Resume context if suspended
            if (audioCtx.state === 'suspended') {
                console.log('[Dashboard] Resuming suspended audio context');
                await audioCtx.resume();
            }

            // Check if muted
            if (audioManager.isMuted) {
                console.log('[Dashboard] Audio is muted, skipping sound');
                return;
            }

            const volume = audioManager.volume || 0.5;
            console.log('[Dashboard] Playing generated sound:', { level, volume, state: audioCtx.state });

            const oscillator = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();

            oscillator.connect(gainNode);
            gainNode.connect(audioCtx.destination);

            const now = audioCtx.currentTime;
            const baseVolume = Math.max(0.1, Math.min(1, volume));

            switch(level) {
                case 'critical':
                    oscillator.frequency.setValueAtTime(880, now);
                    gainNode.gain.setValueAtTime(baseVolume, now);
                    gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.5);
                    oscillator.start(now);
                    oscillator.stop(now + 0.5);
                    break;
                case 'error':
                    oscillator.frequency.setValueAtTime(440, now);
                    oscillator.frequency.exponentialRampToValueAtTime(220, now + 0.3);
                    gainNode.gain.setValueAtTime(baseVolume, now);
                    gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
                    oscillator.start(now);
                    oscillator.stop(now + 0.3);
                    break;
                case 'warning':
                    oscillator.frequency.setValueAtTime(660, now);
                    gainNode.gain.setValueAtTime(baseVolume * 0.8, now);
                    gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
                    oscillator.start(now);
                    oscillator.stop(now + 0.2);
                    break;
                default:
                    oscillator.frequency.setValueAtTime(523, now);
                    gainNode.gain.setValueAtTime(baseVolume * 0.6, now);
                    gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.15);
                    oscillator.start(now);
                    oscillator.stop(now + 0.15);
            }

            console.log('[Dashboard] Oscillator started successfully');
        } catch (e) {
            console.error('[Dashboard] Failed to play alert sound:', e);
        }
    }

    handleDataUpdate(payload) {
        const timestamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        this.lastUpdateEl.textContent = `最后更新: ${timestamp}`;

        // Update metrics
        if (typeof payload === 'object' && payload !== null) {
            Object.entries(payload).forEach(([key, value]) => {
                this.updateMetric(key, value);
            });
        }

        // Add to terminal
        this.addLog('data', JSON.stringify(payload, null, 2));

        // Check for audio alerts using configured rules
        const payloadStr = JSON.stringify(payload);
        if (window.audioManager && !window.audioManager.isAudioMuted) {
            this.playMatchingAlertSound(payloadStr, 'info');
        }
    }

    updateMetric(key, value) {
        // Store metric
        const oldValue = this.metrics[key] && this.metrics[key].value;
        this.metrics[key] = {
            value: value,
            lastUpdate: Date.now(),
            trend: this.calculateTrend(oldValue, value)
        };

        // Render or update metric card
        this.renderMetrics();
    }

    calculateTrend(oldValue, newValue) {
        if (oldValue === undefined || oldValue === null) return null;
        if (typeof newValue === 'number' && typeof oldValue === 'number') {
            if (newValue > oldValue) return 'up';
            if (newValue < oldValue) return 'down';
        }
        return null;
    }

    renderMetrics() {
        const metricEntries = Object.entries(this.metrics);

        if (metricEntries.length === 0) {
            this.metricsGrid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: var(--text-muted);">
                    等待数据...
                </div>
            `;
            return;
        }

        this.metricsGrid.innerHTML = metricEntries.map(([key, data]) => {
            const displayKey = this.formatLabel(key);
            const displayValue = this.formatValue(data.value);
            const trend = data.trend;

            let trendHtml = '';
            if (trend === 'up') {
                trendHtml = '<span class="metric-trend up">↑</span>';
            } else if (trend === 'down') {
                trendHtml = '<span class="metric-trend down">↓</span>';
            }

            const isSmall = String(displayValue).length > 8;

            return `
                <div class="metric-card" data-key="${key}">
                    <div class="metric-header">
                        <span class="metric-label">${displayKey}</span>
                        ${trendHtml}
                    </div>
                    <div class="metric-value ${isSmall ? 'small' : ''}">${displayValue}</div>
                </div>
            `;
        }).join('');
    }

    formatLabel(key) {
        // Convert snake_case or camelCase to readable label
        const label = key
            .replace(/_/g, ' ')
            .replace(/([A-Z])/g, ' $1')
            .toLowerCase()
            .trim();
        return label.charAt(0).toUpperCase() + label.slice(1);
    }

    formatValue(value) {
        if (value === null || value === undefined) return '--';
        if (typeof value === 'number') {
            // Format large numbers
            if (value >= 1000000) return (value / 1000000).toFixed(2) + 'M';
            if (value >= 1000) return (value / 1000).toFixed(1) + 'K';
            if (Number.isInteger(value)) return value.toString();
            return value.toFixed(2);
        }
        return String(value);
    }

    async handleControlClick(e) {
        const btn = e.currentTarget;
        const buttonId = btn.dataset.id;
        const command = btn.dataset.command;
        const buttonType = btn.dataset.type || 'command';

        console.log('[Control] Button clicked:', { buttonId, command, buttonType });

        if (!buttonId) {
            console.error('[Control] No buttonId found');
            return;
        }

        // Prevent double-click
        if (btn.classList.contains('loading')) return;

        // Handle input type button
        let inputValue = null;
        if (buttonType === 'input') {
            const inputFieldId = `input-${buttonId}`;
            const inputField = document.getElementById(inputFieldId);
            console.log('[Control] Looking for input field:', inputFieldId, 'Found:', inputField);
            if (inputField) {
                inputValue = inputField.value.trim();
                console.log('[Control] Input value from field:', inputValue);

                // Validation (防呆) - basic required check for input buttons
                if (!inputValue) {
                    this.showToast('error', '输入错误', '请输入内容后再提交');
                    inputField.classList.add('input-error');
                    setTimeout(() => inputField.classList.remove('input-error'), 3000);
                    inputField.focus();
                    return;
                }

                // Try to parse as number if it looks like a number
                if (/^-?\d+(\.\d+)?$/.test(inputValue)) {
                    inputValue = parseFloat(inputValue);
                }

                // Clear error state
                inputField.classList.remove('input-error');
            } else {
                console.error('[Control] Input field not found! Available inputs:',
                    Array.from(document.querySelectorAll('.control-input-field')).map(el => el.id));
            }
        }

        btn.classList.add('loading');

        try {
            const requestBody = { button_id: buttonId };
            if (inputValue !== null) {
                requestBody.extra_data = { input_value: inputValue };
            }

            const response = await fetch(`/api/${this.instanceId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            const result = await response.json();
            console.log('[Control] Response from server:', result);

            if (result.success) {
                const displayValue = inputValue !== null ? ` (${inputValue})` : '';

                // 如果有警告（如504超时），显示警告而非错误
                if (result.warning) {
                    this.showToast('warning', '命令已发送', result.warning);
                } else {
                    this.showToast('success', '命令已发送', `${command || buttonId}${displayValue} 执行成功`);
                }

                // 详细日志
                const logDetails = [
                    result.warning ? `[控制命令] "${command || buttonId}" ${result.warning}`
                                   : `[控制命令] "${command || buttonId}" 发送成功${displayValue}`,
                    `  方法: ${result.method || 'POST'}`,
                    `  地址: ${result.url || '默认'}`,
                    `  HTTP状态: ${result.status_code}`,
                    `  响应: ${JSON.stringify(result.la_response || {}).substring(0, 100)}`
                ].join('\n');
                this.addLog('control', logDetails);

                // Clear input field after successful send
                if (buttonType === 'input') {
                    const inputField = document.getElementById(`input-${buttonId}`);
                    if (inputField) inputField.value = '';
                }
            } else {
                const errorMsg = result.error || '未知错误';
                this.showToast('error', '命令失败', errorMsg);
                const logDetails = [
                    `[控制命令] "${command || buttonId}" 失败`,
                    `  错误: ${errorMsg}`,
                    `  目标: ${result.url || '未知'}`
                ].join('\n');
                this.addLog('control', logDetails);
            }
        } catch (error) {
            console.error('Control error:', error);
            this.showToast('error', '网络错误', '无法连接到服务器');
            this.addLog('error', `控制命令 "${command || buttonId}" 网络错误`);
        } finally {
            btn.classList.remove('loading');
        }
    }

    addLog(type, message, skipBatch = false) {
        if (this.isPaused) return;

        const timestamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });

        const log = {
            id: Date.now() + Math.random(),
            timestamp,
            type,
            message: String(message).slice(0, 5000) // Limit single log length
        };

        this.logs.push(log);

        // Trim old logs
        if (this.logs.length > this.maxLogs) {
            this.logs = this.logs.slice(-this.maxLogs);
            // If exceeded limit, need to re-render
            this.scheduleBatchRender(true);
            this.persistLog(log);
            return;
        }

        // Batch render or immediate render
        if (skipBatch) {
            this.renderLogLine(log);
        } else {
            this.logBatch.push(log);
            this.scheduleBatchRender();
        }

        // Persist to backend (fire and forget)
        this.persistLog(log);
    }

    scheduleBatchRender(forceFull = false) {
        if (forceFull) {
            this.renderAllLogs();
            return;
        }

        if (this.logBatchTimer) return;

        this.logBatchTimer = setTimeout(() => {
            this.renderLogBatch();
            this.logBatchTimer = null;
        }, this.logBatchInterval);
    }

    renderLogBatch() {
        if (this.logBatch.length === 0) return;

        const fragment = document.createDocumentFragment();
        const shouldScroll = this.isUserAtBottom();

        this.logBatch.forEach(log => {
            if (this.shouldShowLog(log)) {
                const line = this.createLogLineElement(log);
                fragment.appendChild(line);
            }
        });

        this.terminalContent.appendChild(fragment);

        if (shouldScroll) {
            this.scrollToBottom();
        }

        this.logBatch = [];
    }

    isUserAtBottom() {
        const { scrollTop, scrollHeight, clientHeight } = this.terminalContent;
        return scrollHeight - scrollTop - clientHeight < this.autoScrollThreshold;
    }

    scrollToBottom(behavior = 'auto') {
        this.terminalContent.scrollTo({
            top: this.terminalContent.scrollHeight,
            behavior
        });
    }

    async persistLog(log) {
        try {
            await fetch(`/api/${this.instanceId}/logs`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(log)
            });
        } catch (error) {
            // Silent fail - don't block UI for logging
            console.error('[Dashboard] Failed to persist log:', error);
        }
    }

    async loadPersistedLogs(limit = 100) {
        try {
            const response = await fetch(`/api/${this.instanceId}/logs?limit=${limit}`);
            const data = await response.json();

            if (data.logs && data.logs.length > 0) {
                // Prepend persisted logs to current logs
                this.logs = data.logs.concat(this.logs);

                // Trim if too many
                if (this.logs.length > this.maxLogs) {
                    this.logs = this.logs.slice(-this.maxLogs);
                }

                // Re-render terminal
                this.renderAllLogs();
            }
        } catch (error) {
            console.error('[Dashboard] Failed to load persisted logs:', error);
        }
    }

    renderAllLogs() {
        const terminal = document.getElementById('terminalContent');
        if (!terminal) return;

        // Clear current content except welcome lines
        const welcomeLines = terminal.querySelectorAll('.terminal-welcome');
        terminal.innerHTML = '';
        welcomeLines.forEach(line => terminal.appendChild(line));

        // Render all logs that match filter (without auto-scroll for each line)
        this.logs.forEach(log => {
            if (this.shouldShowLog(log)) {
                const line = this.createLogLineElement(log);
                terminal.appendChild(line);
            }
        });

        // Auto-scroll to bottom once after rendering all
        terminal.scrollTo({
            top: terminal.scrollHeight,
            behavior: 'auto'
        });
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
        const line = this.createLogLineElement(log);
        this.terminalContent.appendChild(line);

        // Only auto-scroll if user is at bottom
        if (this.isUserAtBottom()) {
            this.terminalContent.scrollTo({
                top: this.terminalContent.scrollHeight,
                behavior: 'smooth'
            });
        }
    }

    createLogLineElement(log) {
        const line = document.createElement('div');
        line.className = `terminal-line alert-${log.type}`;
        line.style.whiteSpace = 'pre-wrap';

        const typeColors = {
            info: 'var(--accent-cyan)',
            data: 'var(--accent-cyan)',
            error: 'var(--accent-red)',
            warning: 'var(--accent-orange)',
            success: 'var(--accent-green)',
            connection: 'var(--accent-cyan)',
            control: 'var(--accent-orange)'
        };

        const message = String(log.message).replace(/\n/g, '<br>');

        line.innerHTML = `
            <span class="terminal-time">${log.timestamp}</span>
            <span class="terminal-type" style="color: ${typeColors[log.type] || 'var(--text-secondary)'}; flex-shrink: 0;">
                [${log.type.toUpperCase()}]
            </span>
            <span class="terminal-message" style="white-space: pre-wrap;">${message}</span>
        `;

        return line;
    }

    setLogFilter(filter) {
        this.logFilter = filter;

        // Update tabs
        document.querySelectorAll('.terminal-tabs .tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.filter === filter);
        });

        // Re-render logs
        this.renderAllLogs();
    }

    clearLogs() {
        this.logs = [];
        this.terminalContent.innerHTML = '';
    }

    togglePause() {
        this.isPaused = !this.isPaused;
        const btn = document.getElementById('pauseLogs');
        const icon = document.getElementById('pauseIcon');

        if (this.isPaused) {
            btn.style.color = 'var(--accent-orange)';
            icon.innerHTML = `
                <path d="M6 4L14 10L6 16V4Z" fill="currentColor"/>
            `;
        } else {
            btn.style.color = '';
            icon.innerHTML = `
                <rect x="4" y="3" width="3" height="10" rx="1" fill="currentColor"/>
                <rect x="9" y="3" width="3" height="10" rx="1" fill="currentColor"/>
            `;
        }
    }

    handleKeydown(e) {
        // ESC to focus terminal input
        if (e.key === 'Escape') {
            const input = document.getElementById('terminalInput');
            if (document.activeElement !== input) {
                input.focus();
                e.preventDefault();
            }
        }
    }

    showToast(type, title, message) {
        const toastContainer = document.getElementById('toastContainer');

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
                <div class="toast-title">${this.escapeHtml(title)}</div>
                <div class="toast-message">${this.escapeHtml(message)}</div>
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M3 3L11 11M11 3L3 11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
            </button>
        `;

        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('out');
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Audio Alert Configuration (Collapsible)
    async loadAudioAlertConfig() {
        try {
            // Load instance config
            const response = await fetch(`/api/instances/${this.instanceId}`);
            const data = await response.json();

            console.log('[Dashboard] Loading audio alert config:', data.instance);

            const rules = (data.instance && data.instance.audio_alerts && data.instance.audio_alerts.length > 0) ? data.instance.audio_alerts : [
                {keyword: 'ERROR', sound: 'error', audio_file_id: ''},
                {keyword: 'WARNING', sound: 'warning', audio_file_id: ''},
                {keyword: 'STOP', sound: 'stop', audio_file_id: ''},
                {keyword: '故障', sound: 'error', audio_file_id: ''},
                {keyword: '停止', sound: 'stop', audio_file_id: ''}
            ];

            const audioFiles = (data.instance && data.instance.audio_files) ? data.instance.audio_files : [];

            // Load audio alert match switch (default: false)
            this.audioAlertMatchEnabled = data.instance?.audio_alert_match_enabled === true;
            console.log('[Dashboard] Audio alert match enabled:', this.audioAlertMatchEnabled);

            this.audioAlertRules = rules;
            this.audioFiles = audioFiles;

            console.log('[Dashboard] Audio alert rules loaded:', rules);
            console.log('[Dashboard] Audio files loaded:', audioFiles);

            this.renderAlertPreview(rules);
            this.renderAudioAlertRules(rules);
            this.renderAudioFilesList(audioFiles);
        } catch (error) {
            console.error('Failed to load audio alert config:', error);
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

        container.innerHTML = rules.map((rule, index) => {
            // Build audio file options for this rule
            const audioFileOptions = (this.audioFiles || []).map(f =>
                `<option value="${f.id}" ${rule.audio_file_id === f.id ? 'selected' : ''}>${this.escapeHtml(f.name)}</option>`
            ).join('');

            return `
            <div class="alert-rule-item" style="padding: 0.75rem; background: var(--bg-tertiary); border-radius: 4px; margin-bottom: 0.5rem; font-size: 0.8125rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <strong style="color: var(--accent-cyan);">规则 ${index + 1}</strong>
                    <button onclick="window.dashboard.removeAudioAlertRule(${index})" style="background: transparent; border: none; color: var(--accent-red); cursor: pointer; font-size: 0.75rem;">删除</button>
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">关键词</label>
                    <input type="text" value="${this.escapeHtml(rule.keyword)}" onchange="window.dashboard.updateAlertRule(${index}, 'keyword', this.value)" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.5rem;">
                    <div>
                        <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">内置声音</label>
                        <select onchange="window.dashboard.updateAlertRule(${index}, 'sound', this.value)" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                            <option value="error" ${rule.sound === 'error' ? 'selected' : ''}>Error (高频)</option>
                            <option value="warning" ${rule.sound === 'warning' ? 'selected' : ''}>Warning (中频)</option>
                            <option value="stop" ${rule.sound === 'stop' ? 'selected' : ''}>Stop (低频)</option>
                            <option value="info" ${rule.sound === 'info' ? 'selected' : ''}>Info (提示)</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">自定义音频</label>
                        <select onchange="window.dashboard.updateAlertRule(${index}, 'audio_file_id', this.value)" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                            <option value="">-- 不使用 --</option>
                            ${audioFileOptions}
                        </select>
                    </div>
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">报警间隔 (分钟，0=不限制)</label>
                    <input type="number" min="0" max="1440" value="${rule.min_interval || 0}" onchange="window.dashboard.updateAlertRule(${index}, 'min_interval', parseInt(this.value) || 0)" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                </div>
                <button onclick="window.dashboard.testAlertRule(${index})" class="btn btn-secondary" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">测试</button>
            </div>
            `;
        }).join('');
    }

    async addAudioAlertRule() {
        const keyword = prompt('输入触发关键词 (如: ERROR, STOP):');
        if (!keyword) return;

        const sound = prompt('输入声音类型 (error/warning/stop/info):', 'error');
        if (!sound) return;

        try {
            const response = await fetch(`/api/instances/${this.instanceId}`);
            const data = await response.json();

            const alerts = (data.instance && data.instance.audio_alerts) || [];
            alerts.push({ keyword: keyword.toUpperCase(), sound, audio_file_id: '', min_interval: 0 });

            const updateResponse = await fetch(`/api/instances/${this.instanceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ audio_alerts: alerts })
            });

            if (updateResponse.ok) {
                this.showToast('success', '添加成功', `关键词 "${keyword}" 已添加`);
                this.loadAudioAlertConfig();
            }
        } catch (error) {
            console.error('Failed to add alert rule:', error);
            this.showToast('error', '添加失败', '无法保存规则');
        }
    }

    async removeAudioAlertRule(index) {
        if (!confirm('确定要删除这条告警规则吗?')) return;

        try {
            const response = await fetch(`/api/instances/${this.instanceId}`);
            const data = await response.json();

            const alerts = (data.instance && data.instance.audio_alerts) || [];
            alerts.splice(index, 1);

            const updateResponse = await fetch(`/api/instances/${this.instanceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ audio_alerts: alerts })
            });

            if (updateResponse.ok) {
                this.showToast('success', '删除成功', '规则已删除');
                this.loadAudioAlertConfig();
            }
        } catch (error) {
            console.error('Failed to remove alert rule:', error);
            this.showToast('error', '删除失败', '无法删除规则');
        }
    }

    testAlertSound(level, audioFileUrl = null) {
        this.playAlertSound(level, audioFileUrl);
    }

    async testAlertRule(index) {
        const rule = this.audioAlertRules[index];
        if (!rule) return;

        // Find audio file URL if specified
        let audioFileUrl = null;
        if (rule.audio_file_id && this.audioFiles) {
            const audioFile = this.audioFiles.find(f => f.id === rule.audio_file_id);
            if (audioFile) {
                audioFileUrl = audioFile.url;
            }
        }

        await this.playAlertSound(rule.sound, audioFileUrl);
    }

    async testFirstAlertRule() {
        // Test the first configured alert rule, or use default if none exists
        if (this.audioAlertRules && this.audioAlertRules.length > 0) {
            const rule = this.audioAlertRules[0];
            let audioFileUrl = null;
            if (rule.audio_file_id && this.audioFiles) {
                const audioFile = this.audioFiles.find(f => f.id === rule.audio_file_id);
                if (audioFile) {
                    audioFileUrl = audioFile.url;
                }
            }
            console.log('[Dashboard] Testing first alert rule:', { rule: rule.keyword, sound: rule.sound, fileUrl: audioFileUrl });
            await this.playAlertSound(rule.sound, audioFileUrl);
        } else {
            // Fallback to default error sound if no rules configured
            console.log('[Dashboard] No alert rules configured, playing default error sound');
            await this.playAlertSound('error');
        }
    }

    async updateAlertRule(index, field, value) {
        if (!this.audioAlertRules || !this.audioAlertRules[index]) {
            console.error('[Dashboard] Cannot update rule: rules not loaded or invalid index', { index, rules: this.audioAlertRules });
            return;
        }

        // Update local state
        this.audioAlertRules[index][field] = value;
        console.log('[Dashboard] Updated rule locally:', this.audioAlertRules[index]);

        // Save to server
        try {
            const response = await fetch(`/api/instances/${this.instanceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ audio_alerts: this.audioAlertRules })
            });

            if (response.ok) {
                const result = await response.json();
                console.log('[Dashboard] Rule saved to server:', result);
                this.showToast('success', '已保存', '规则已更新');

                // Reload config to ensure sync
                await this.loadAudioAlertConfig();
            } else {
                const error = await response.text();
                console.error('[Dashboard] Failed to save rule:', error);
                this.showToast('error', '保存失败', '无法保存规则');
            }
        } catch (error) {
            console.error('[Dashboard] Network error saving rule:', error);
            this.showToast('error', '保存失败', '网络错误');
        }
    }

    // Audio Files Management
    renderAudioFilesList(files) {
        const container = document.getElementById('audioFilesList');
        if (!container) return;

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
                    <span style="color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(file.name)}">${this.escapeHtml(file.name)}</span>
                </div>
                <div style="display: flex; gap: 0.5rem; flex-shrink: 0;">
                    <button onclick="window.dashboard.playAudioFile('${file.url}')" class="btn btn-secondary" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">播放</button>
                    <button onclick="window.dashboard.deleteAudioFile('${file.id}')" class="btn btn-danger" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">删除</button>
                </div>
            </div>
        `).join('');
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

                // If in settings panel (tempAudioFiles exists), add to temp state
                if (this.tempAudioFiles) {
                    this.tempAudioFiles.push({
                        id: result.file_id || `file_${Date.now()}`,
                        name: name,
                        url: result.url || `/audio/${this.instanceId}/${file.name}`
                    });
                    this.renderSettingsAudioFiles(this.tempAudioFiles);
                    // Also re-render alerts to update audio file dropdowns
                    this.renderSettingsAudioAlerts(this.tempAudioAlerts || []);
                } else {
                    this.loadAudioAlertConfig();
                }
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

        // If in settings panel (tempAudioFiles exists), remove from temp state only
        if (this.tempAudioFiles) {
            const index = this.tempAudioFiles.findIndex(f => f.id === fileId);
            if (index !== -1) {
                this.tempAudioFiles.splice(index, 1);
                this.renderSettingsAudioFiles(this.tempAudioFiles);
                // Also re-render alerts to update audio file dropdowns
                this.renderSettingsAudioAlerts(this.tempAudioAlerts || []);
                this.showToast('success', '已移除', '音频文件已从列表中移除');
            }
            return;
        }

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
            // Load current settings when opening
            this.loadSettingsPanel();
        }
    }

    async loadSettingsPanel() {
        try {
            const response = await fetch(`/api/instances/${this.instanceId}`);
            const data = await response.json();

            if (data.instance) {
                const instance = data.instance;
                console.log('[Dashboard] Loading settings, instance:', instance);

                // Load view UID
                const viewUidInput = document.getElementById('settingsViewUid');
                const viewLinkSpan = document.getElementById('settingsViewLink');

                // Handle view UID - auto-generate if not exists
                let currentUid = instance.view_uid;
                console.log('[Dashboard] Current view_uid from server:', currentUid);
                if (!currentUid) {
                    currentUid = this.generateUid();
                    console.log('[Dashboard] Generated new view_uid:', currentUid);
                }

                if (viewUidInput) {
                    viewUidInput.value = currentUid;
                    console.log('[Dashboard] Set viewUidInput value:', currentUid);
                }

                // Business view uses port 6010
                if (viewLinkSpan) {
                    const protocol = window.location.protocol;
                    const hostname = window.location.hostname;
                    const fullUrl = `${protocol}//${hostname}:6010/view/${currentUid}`;
                    viewLinkSpan.innerHTML = `<a href="${fullUrl}" target="_blank" style="color: var(--accent-cyan);">${fullUrl}</a>`;
                    console.log('[Dashboard] Set viewLinkSpan:', fullUrl);
                }

                // Load metrics mappings
                this.tempMetricsMappings = instance.metrics_mappings || [];
                this.renderSettingsMetricsList(this.tempMetricsMappings);

                // Load control buttons
                this.tempControlButtons = instance.control_buttons || [];
                this.renderSettingsControlButtons(this.tempControlButtons);

                // Load audio alerts
                this.tempAudioAlerts = instance.audio_alerts || [];
                this.tempAudioFiles = instance.audio_files || [];
                this.tempAudioAlertMatchEnabled = instance.audio_alert_match_enabled === true;
                this.renderSettingsAudioAlerts(this.tempAudioAlerts);
                this.renderSettingsAudioFiles(this.tempAudioFiles);
                this.renderAudioAlertMatchSwitch(this.tempAudioAlertMatchEnabled);

                // Bind add audio alert button (re-bind each time panel opens)
                const addAlertBtn = document.getElementById('settingsAddAudioAlertBtn');
                if (addAlertBtn) {
                    // Remove existing listeners to avoid duplicates
                    const newBtn = addAlertBtn.cloneNode(true);
                    addAlertBtn.parentNode.replaceChild(newBtn, addAlertBtn);
                    newBtn.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        this.addSettingsAudioAlert();
                    });
                }
            }
        } catch (error) {
            console.error('[Dashboard] Failed to load settings:', error);
        }
    }

    renderSettingsMetricsList(mappings) {
        const container = document.getElementById('settingsMetricsList');
        if (!container) return;

        if (mappings.length === 0) {
            container.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.875rem;">暂无指标映射配置</div>';
            return;
        }

        container.innerHTML = mappings.map((mapping, index) => `
            <div class="metric-mapping-item">
                <input type="text" placeholder="LA字段名" value="${this.escapeHtml(mapping.la_key || '')}" data-field="la_key" data-index="${index}">
                <input type="text" placeholder="显示名称" value="${this.escapeHtml(mapping.display_name || '')}" data-field="display_name" data-index="${index}">
                <input type="text" placeholder="单位" value="${this.escapeHtml(mapping.unit || '')}" data-field="unit" data-index="${index}" style="width: 60px;">
                <button onclick="window.dashboard.removeMetricsMapping(${index})" title="删除">删除</button>
            </div>
        `).join('');

        // Add change listeners
        container.querySelectorAll('input').forEach(input => {
            input.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                const field = e.target.dataset.field;
                this.updateMetricsMapping(index, field, e.target.value);
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

        container.innerHTML = buttons.map((btn, index) => `
            <div class="control-button-item">
                <input type="text" placeholder="标签" value="${this.escapeHtml(btn.label || '')}" data-field="label" data-index="${index}" title="按钮显示标签">
                <input type="text" placeholder="命令" value="${this.escapeHtml(btn.command || '')}" data-field="command" data-index="${index}" title="发送的命令">
                <select data-field="button_type" data-index="${index}" title="按钮类型">
                    <option value="command" ${btn.button_type === 'command' ? 'selected' : ''}>命令</option>
                    <option value="input" ${btn.button_type === 'input' ? 'selected' : ''}>输入</option>
                </select>
                <select data-field="color" data-index="${index}" title="按钮颜色">
                    <option value="green" ${btn.color === 'green' ? 'selected' : ''}>绿色</option>
                    <option value="red" ${btn.color === 'red' ? 'selected' : ''}>红色</option>
                    <option value="blue" ${btn.color === 'blue' ? 'selected' : ''}>蓝色</option>
                    <option value="orange" ${btn.color === 'orange' ? 'selected' : ''}>橙色</option>
                </select>
                <button onclick="window.dashboard.removeControlButton(${index})" title="删除" style="background: transparent; border: none; color: var(--accent-red); cursor: pointer; font-size: 0.75rem;">删除</button>
            </div>
        `).join('');

        // Add change listeners
        container.querySelectorAll('input, select').forEach(input => {
            input.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                const field = e.target.dataset.field;
                this.updateControlButton(index, field, e.target.value);
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

    // Settings Panel Audio Alerts Management
    renderSettingsAudioAlerts(rules) {
        const container = document.getElementById('settingsAlertConfigList');
        if (!container) return;

        if (rules.length === 0) {
            container.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted); font-size: 0.875rem;">暂无告警规则</div>';
            return;
        }

        // Get server IP (fallback to window.location.hostname)
        const serverIp = this.serverIp || window.location.hostname;
        const baseUrl = `http://${serverIp}:8000`;
        const viewUid = this.instanceConfig?.view_uid || '';

        container.innerHTML = rules.map((rule, index) => {
            const audioFileOptions = (this.tempAudioFiles || []).map(f =>
                `<option value="${f.id}" ${rule.audio_file_id === f.id ? 'selected' : ''}>${this.escapeHtml(f.name)}</option>`
            ).join('');

            // Generate API endpoint info
            const alertEndpoint = `${baseUrl}/api/${this.instanceId}/alert`;
            const viewUrl = viewUid ? `${baseUrl.replace(':8000', ':6010')}/view/${viewUid}` : '';

            // Generate curl example based on rule keyword
            const exampleMessage = `测试${rule.keyword || '告警'}触发`;
            const curlExample = `curl -X POST ${alertEndpoint} \\\
  -H "Content-Type: application/json" \\\
  -d '{"message":"${exampleMessage}","level":"${rule.sound || 'error'}"}'`;

            // Generate GET example
            const getExample = `${alertEndpoint}?message=${encodeURIComponent(exampleMessage)}&level=${rule.sound || 'error'}`;

            return `
            <div class="alert-rule-item" style="padding: 0.75rem; background: var(--bg-tertiary); border-radius: 4px; margin-bottom: 0.5rem; font-size: 0.8125rem;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <strong style="color: var(--accent-cyan);">规则 ${index + 1}</strong>
                    <button onclick="window.dashboard.removeSettingsAudioAlert(${index})" style="background: transparent; border: none; color: var(--accent-red); cursor: pointer; font-size: 0.75rem;">删除</button>
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">关键词</label>
                    <input type="text" value="${this.escapeHtml(rule.keyword || '')}" data-field="keyword" data-index="${index}" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.5rem;">
                    <div>
                        <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">内置声音</label>
                        <select data-field="sound" data-index="${index}" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                            <option value="error" ${rule.sound === 'error' ? 'selected' : ''}>Error (高频)</option>
                            <option value="warning" ${rule.sound === 'warning' ? 'selected' : ''}>Warning (中频)</option>
                            <option value="stop" ${rule.sound === 'stop' ? 'selected' : ''}>Stop (低频)</option>
                            <option value="info" ${rule.sound === 'info' ? 'selected' : ''}>Info (提示)</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">自定义音频</label>
                        <select data-field="audio_file_id" data-index="${index}" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                            <option value="">-- 不使用 --</option>
                            ${audioFileOptions}
                        </select>
                    </div>
                </div>
                <div style="margin-bottom: 0.5rem;">
                    <label style="font-size: 0.6875rem; color: var(--text-muted); display: block; margin-bottom: 0.25rem;">报警间隔 (分钟，0=不限制)</label>
                    <input type="number" min="0" max="1440" value="${rule.min_interval || 0}" data-field="min_interval" data-index="${index}" style="width: 100%; padding: 0.375rem; font-size: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary);">
                </div>

                <!-- API Endpoint Info -->
                <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px solid var(--border-subtle);">
                    <div style="font-size: 0.6875rem; color: var(--text-muted); margin-bottom: 0.25rem;">告警接收地址</div>
                    <div style="display: flex; gap: 0.25rem; margin-bottom: 0.5rem;">
                        <input type="text" value="${alertEndpoint}" readonly style="flex: 1; padding: 0.25rem 0.5rem; font-size: 0.6875rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-secondary); font-family: monospace;"
                            onclick="this.select();"
                            title="点击复制">
                        <button onclick="navigator.clipboard.writeText('${alertEndpoint}'); window.dashboard.showToast('地址已复制', 'success');" class="btn btn-secondary" style="font-size: 0.6875rem; padding: 0.25rem 0.5rem;">复制</button>
                    </div>
                    ${viewUrl ? `
                    <div style="font-size: 0.6875rem; color: var(--text-muted); margin-bottom: 0.25rem;">业务视图地址</div>
                    <div style="display: flex; gap: 0.25rem; margin-bottom: 0.5rem;">
                        <input type="text" value="${viewUrl}" readonly style="flex: 1; padding: 0.25rem 0.5rem; font-size: 0.6875rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-secondary); font-family: monospace;"
                            onclick="this.select();"
                            title="点击复制">
                        <button onclick="navigator.clipboard.writeText('${viewUrl}'); window.dashboard.showToast('地址已复制', 'success');" class="btn btn-secondary" style="font-size: 0.6875rem; padding: 0.25rem 0.5rem;">复制</button>
                    </div>
                    ` : ''}

                    <!-- Collapsible Request Examples -->
                    <div style="margin-top: 0.5rem;">
                        <div onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'; this.querySelector('span').style.transform = this.nextElementSibling.style.display === 'none' ? 'rotate(0deg)' : 'rotate(90deg)';" style="cursor: pointer; display: flex; align-items: center; gap: 0.25rem; font-size: 0.6875rem; color: var(--accent-cyan); user-select: none;">
                            <span style="display: inline-block; transition: transform 0.2s;">▶</span>
                            请求示例
                        </div>
                        <div style="display: none; margin-top: 0.5rem;">
                            <div style="font-size: 0.625rem; color: var(--text-muted); margin-bottom: 0.25rem;">POST (JSON)</div>
                            <div style="position: relative; margin-bottom: 0.5rem;">
                                <pre style="margin: 0; padding: 0.5rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; font-size: 0.625rem; color: var(--text-secondary); overflow-x: auto; white-space: pre-wrap; word-break: break-all;">${this.escapeHtml(curlExample)}</pre>
                                <button onclick="navigator.clipboard.writeText(\`${curlExample.replace(/\\/g, '\\\\').replace(/`/g, '\\`')}\`); window.dashboard.showToast('curl命令已复制', 'success');" class="btn btn-secondary" style="position: absolute; top: 0.25rem; right: 0.25rem; font-size: 0.625rem; padding: 0.125rem 0.375rem;">复制</button>
                            </div>
                            <div style="font-size: 0.625rem; color: var(--text-muted); margin-bottom: 0.25rem;">GET (URL)</div>
                            <div style="position: relative; margin-bottom: 0.5rem;">
                                <pre style="margin: 0; padding: 0.5rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; font-size: 0.625rem; color: var(--text-secondary); overflow-x: auto; white-space: pre-wrap; word-break: break-all;">${this.escapeHtml(getExample)}</pre>
                                <button onclick="navigator.clipboard.writeText('${getExample}'); window.dashboard.showToast('URL已复制', 'success');" class="btn btn-secondary" style="position: absolute; top: 0.25rem; right: 0.25rem; font-size: 0.625rem; padding: 0.125rem 0.375rem;">复制</button>
                            </div>
                        </div>
                    </div>
                </div>

                <button onclick="window.dashboard.testSettingsAlertRule(${index})" class="btn btn-secondary" style="font-size: 0.75rem; padding: 0.25rem 0.5rem; margin-top: 0.5rem;">测试</button>
            </div>
            `;
        }).join('');

        // Add change listeners
        container.querySelectorAll('input, select').forEach(input => {
            input.addEventListener('change', (e) => {
                const index = parseInt(e.target.dataset.index);
                const field = e.target.dataset.field;
                const value = field === 'min_interval' ? parseInt(e.target.value) || 0 : e.target.value;
                this.updateSettingsAudioAlert(index, field, value);
            });
        });
    }

    renderAudioAlertMatchSwitch(enabled) {
        const container = document.getElementById('settingsAlertConfigList');
        if (!container) return;

        // Insert the switch at the beginning of the container
        const switchHtml = `
            <div class="alert-match-switch" style="padding: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 4px; margin-bottom: 1rem;">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <div style="font-size: 0.875rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem;">启用关键词匹配</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted);">
                            ${enabled ? '仅匹配关键词的消息会触发声音' : '所有消息都会触发声音（无需匹配关键词）'}
                        </div>
                    </div>
                    <label class="switch" style="position: relative; display: inline-block; width: 44px; height: 24px;">
                        <input type="checkbox" id="audioAlertMatchSwitch" ${enabled ? 'checked' : ''} style="opacity: 0; width: 0; height: 0;">
                        <span style="position: absolute; cursor: pointer; inset: 0; background: ${enabled ? 'var(--accent-cyan)' : 'var(--border-subtle)'}; border-radius: 24px; transition: 0.3s;">
                            <span style="position: absolute; content: ''; height: 18px; width: 18px; left: ${enabled ? '22px' : '3px'}; bottom: 3px; background: white; border-radius: 50%; transition: 0.3s;"></span>
                        </span>
                    </label>
                </div>
            </div>
        `;

        // Check if the switch already exists
        const existingSwitch = container.querySelector('.alert-match-switch');
        if (existingSwitch) {
            existingSwitch.outerHTML = switchHtml;
        } else {
            container.insertAdjacentHTML('afterbegin', switchHtml);
        }

        // Add change listener
        const switchInput = document.getElementById('audioAlertMatchSwitch');
        if (switchInput) {
            switchInput.addEventListener('change', (e) => {
                this.tempAudioAlertMatchEnabled = e.target.checked;
                // Re-render to update the UI
                this.renderAudioAlertMatchSwitch(this.tempAudioAlertMatchEnabled);
            });
        }
    }

    renderSettingsAudioFiles(files) {
        const container = document.getElementById('settingsAudioFilesList');
        if (!container) return;

        if (files.length === 0) {
            container.innerHTML = '<div style="padding: 0.75rem; text-align: center; color: var(--text-muted); font-size: 0.8125rem;">暂无自定义音频文件</div>';
            return;
        }

        container.innerHTML = files.map((file, index) => `
            <div class="audio-file-item" style="display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.75rem; background: var(--bg-secondary); border-radius: 4px; margin-bottom: 0.5rem; font-size: 0.8125rem;">
                <div style="display: flex; align-items: center; gap: 0.5rem; overflow: hidden;">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style="flex-shrink: 0; color: var(--accent-cyan);">
                        <path d="M8 2V14M2 8H14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                    </svg>
                    <span style="color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(file.name)}">${this.escapeHtml(file.name)}</span>
                </div>
                <div style="display: flex; gap: 0.5rem; flex-shrink: 0;">
                    <button class="btn btn-secondary" onclick="window.dashboard.playAudioFile('${file.url}')" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">播放</button>
                    <button class="btn btn-danger" onclick="window.dashboard.deleteAudioFile('${file.id}')" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">删除</button>
                </div>
            </div>
        `).join('');
    }

    addSettingsAudioAlert() {
        const keyword = prompt('输入触发关键词 (如: ERROR, STOP):');
        if (!keyword) return;

        if (!this.tempAudioAlerts) {
            this.tempAudioAlerts = [];
        }
        this.tempAudioAlerts.push({
            keyword: keyword,
            sound: 'error',
            min_interval: 0,
            audio_file_id: ''
        });
        this.renderSettingsAudioAlerts(this.tempAudioAlerts);
    }

    removeSettingsAudioAlert(index) {
        if (this.tempAudioAlerts) {
            this.tempAudioAlerts.splice(index, 1);
            this.renderSettingsAudioAlerts(this.tempAudioAlerts);
        }
    }

    updateSettingsAudioAlert(index, field, value) {
        if (this.tempAudioAlerts && this.tempAudioAlerts[index]) {
            this.tempAudioAlerts[index][field] = value;
        }
    }

    testSettingsAlertRule(index) {
        if (this.tempAudioAlerts && this.tempAudioAlerts[index]) {
            const rule = this.tempAudioAlerts[index];
            this.playAlertSound(rule.sound);
        }
    }

    regenerateViewUid() {
        const newUid = this.generateUid();
        const viewUidInput = document.getElementById('settingsViewUid');
        if (viewUidInput) {
            viewUidInput.value = newUid;
        }
        this.updateSettingsViewLink(null, newUid);
    }

    generateUid() {
        return Array.from({length: 16}, () =>
            'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'[Math.floor(Math.random() * 62)]
        ).join('');
    }

    updateViewLink(uid) {
        this.updateSettingsViewLink(uid);
    }

    updateSettingsViewLink(uid) {
        const viewLinkSpan = document.getElementById('settingsViewLink');
        const viewUidInput = document.getElementById('settingsViewUid');

        if (!viewLinkSpan) return;

        const currentUid = uid || viewUidInput?.value || this.generateUid();
        // Business view uses port 6010
        const protocol = window.location.protocol;
        const hostname = window.location.hostname;
        const fullUrl = `${protocol}//${hostname}:6010/view/${currentUid}`;

        viewLinkSpan.innerHTML = `<a href="${fullUrl}" target="_blank" style="color: var(--accent-cyan);">${fullUrl}</a>`;
    }

    copyViewLink() {
        const input = document.getElementById('viewLinkInput');
        if (input && input.value && input.value !== '未配置') {
            input.select();
            document.execCommand('copy');
            this.showToast('success', '已复制', '业务视图链接已复制到剪贴板');
        } else {
            this.showToast('warning', '无法复制', '请先配置业务视图');
        }
    }

    /**
     * Sync current configuration to business view via WebSocket broadcast
     */
    async syncConfigToBusinessView() {
        try {
            // Get current instance config
            const response = await fetch(`/api/instances/${this.instanceId}`);
            const data = await response.json();

            if (!data.instance) {
                this.showToast('error', '同步失败', '无法获取实例配置');
                return;
            }

            const config = {
                type: 'config_sync',
                payload: {
                    metrics_mappings: data.instance.metrics_mappings || [],
                    audio_alerts: data.instance.audio_alerts || [],
                    audio_files: data.instance.audio_files || [],
                    control_buttons: data.instance.control_buttons || [],
                    updated_at: new Date().toISOString()
                }
            };

            // Send via WebSocket if connected
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify(config));
                this.showToast('success', '配置已同步', '业务视图将接收最新配置');
                console.log('[Dashboard] Config synced to business view:', config);
            } else {
                this.showToast('error', '同步失败', 'WebSocket 未连接，请先连接控制台');
            }
        } catch (error) {
            console.error('[Dashboard] Failed to sync config:', error);
            this.showToast('error', '同步失败', '网络错误或服务器无响应');
        }
    }

    async saveSettings() {
        try {
            const viewUid = document.getElementById('settingsViewUid')?.value || '';

            const updates = {
                view_uid: viewUid,
                metrics_mappings: this.tempMetricsMappings || [],
                control_buttons: this.tempControlButtons || [],
                audio_alerts: this.tempAudioAlerts || [],
                audio_files: this.tempAudioFiles || [],
                audio_alert_match_enabled: this.tempAudioAlertMatchEnabled === true
            };

            const response = await fetch(`/api/instances/${this.instanceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });

            if (response.ok) {
                this.showToast('success', '保存成功', '设置已保存');
                this.toggleSettingsPanel();
                // Update local config without reloading
                await this.loadAudioAlertConfig();
                this.initViewLink();
            } else {
                const error = await response.text();
                this.showToast('error', '保存失败', error);
            }
        } catch (error) {
            console.error('[Dashboard] Failed to save settings:', error);
            this.showToast('error', '保存失败', '网络错误');
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Global functions for collapsible UI
function toggleAlertConfig() {
    const content = document.getElementById('alertConfigContent');
    const icon = document.getElementById('collapseIcon');
    if (!content) return;

    const isVisible = content.style.display !== 'none';
    content.style.display = isVisible ? 'none' : 'block';
    if (icon) {
        icon.style.transform = isVisible ? 'rotate(0deg)' : 'rotate(180deg)';
    }
}

function expandAlertConfig() {
    const preview = document.getElementById('alertRulesPreview');
    const full = document.getElementById('alertConfigFull');
    const btn = document.getElementById('expandAlertConfigBtn');

    if (preview) preview.style.display = 'none';
    if (full) full.style.display = 'block';
    if (btn) btn.style.display = 'none';
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new DashboardManager();
});
