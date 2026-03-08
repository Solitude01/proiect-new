/**
 * Audio Management System
 * Handles audio unlock for browser policy compliance, keyword matching,
 * audio queue management, and volume control.
 */

class AudioManager {
    constructor() {
        this.context = null;
        this.isUnlocked = false;
        this.isMuted = false;
        this.volume = 0.5;
        this.queue = [];
        this.isPlaying = false;
        this.sounds = new Map();

        // Default alert configurations
        this.alertConfigs = [
            { keyword: 'ERROR', sound: 'alert_error', priority: 3 },
            { keyword: 'WARNING', sound: 'alert_warn', priority: 2 },
            { keyword: 'STOP', sound: 'alert_stop', priority: 3 },
            { keyword: 'ALERT', sound: 'alert_warn', priority: 2 },
            { keyword: 'CRITICAL', sound: 'alert_error', priority: 3 }
        ];

        // Initialize from localStorage
        this.loadSettings();
    }

    /**
     * Initialize AudioContext (must be called after user interaction)
     */
    async initialize() {
        if (this.isUnlocked) return true;

        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            this.context = new AudioContext();

            // Resume if suspended (browser autoplay policy)
            if (this.context.state === 'suspended') {
                await this.context.resume();
            }

            // Create oscillator beep sounds (no external files needed)
            this.generateSounds();

            this.isUnlocked = true;
            console.log('[Audio] Context unlocked');
            return true;
        } catch (error) {
            console.error('[Audio] Failed to initialize:', error);
            return false;
        }
    }

    /**
     * Generate synthetic sounds using Web Audio API
     * This avoids needing external audio files
     */
    generateSounds() {
        // Error alert - high pitched, urgent
        this.sounds.set('alert_error', this.createToneBuffer(880, 0.3, 'square', [1, 0.5, 1, 0.5, 1]));

        // Warning alert - medium tone
        this.sounds.set('alert_warn', this.createToneBuffer(440, 0.5, 'sawtooth', [1, 0.8, 0.6, 0.4, 0.2]));

        // Stop alert - low tone
        this.sounds.set('alert_stop', this.createToneBuffer(220, 0.6, 'sawtooth', [1, 0.3, 0.8, 0.3, 1]));

        // Info/Notification - pleasant beep
        this.sounds.set('alert_info', this.createToneBuffer(660, 0.2, 'sine', [0, 0.8, 1, 0.8, 0]));
    }

    /**
     * Create a tone buffer with envelope
     */
    createToneBuffer(frequency, duration, type, envelope) {
        const sampleRate = this.context.sampleRate;
        const buffer = this.context.createBuffer(1, sampleRate * duration, sampleRate);
        const data = buffer.getChannelData(0);

        const samplesPerSegment = data.length / (envelope.length - 1);

        for (let i = 0; i < data.length; i++) {
            const segment = Math.floor(i / samplesPerSegment);
            const segmentProgress = (i % samplesPerSegment) / samplesPerSegment;
            const amp1 = envelope[segment] || 0;
            const amp2 = envelope[segment + 1] || 0;
            const amplitude = amp1 + (amp2 - amp1) * segmentProgress;

            // Generate waveform
            const t = i / sampleRate;
            let sample = 0;

            switch (type) {
                case 'sine':
                    sample = Math.sin(2 * Math.PI * frequency * t);
                    break;
                case 'square':
                    sample = Math.sin(2 * Math.PI * frequency * t) >= 0 ? 1 : -1;
                    break;
                case 'sawtooth':
                    sample = 2 * (t * frequency - Math.floor(t * frequency + 0.5));
                    break;
            }

            // Apply envelope and soften the attack
            const attack = Math.min(1, i / (sampleRate * 0.01));
            data[i] = sample * amplitude * attack;
        }

        return buffer;
    }

    /**
     * Load external audio file
     */
    async loadAudioFile(url) {
        if (!this.context) return null;

        try {
            // Check cache
            if (this.sounds.has(url)) {
                return this.sounds.get(url);
            }

            const response = await fetch(url);
            const arrayBuffer = await response.arrayBuffer();
            const audioBuffer = await this.context.decodeAudioData(arrayBuffer);

            // Cache the buffer
            this.sounds.set(url, audioBuffer);
            return audioBuffer;
        } catch (error) {
            console.error('[Audio] Failed to load audio file:', error);
            return null;
        }
    }

    /**
     * Play a sound from the generated buffers or external file
     */
    async playSound(soundName, audioFileUrl = null) {
        // Ensure context is unlocked
        if (!this.isUnlocked) {
            console.warn('[Audio] Context not unlocked, trying to initialize...');
            await this.initialize();
        }

        if (!this.context) {
            console.error('[Audio] No audio context available');
            return;
        }

        if (this.isMuted) {
            console.log('[Audio] Audio is muted');
            return;
        }

        // Resume context if suspended
        if (this.context.state === 'suspended') {
            await this.context.resume();
        }

        console.log(`[Audio] Playing sound: ${soundName}, fileUrl: ${audioFileUrl}`);

        // If audio file URL provided, play external file
        if (audioFileUrl) {
            const buffer = await this.loadAudioFile(audioFileUrl);
            if (buffer) {
                console.log('[Audio] Playing custom audio file:', audioFileUrl);
                return this.playBuffer(buffer);
            }
            console.warn('[Audio] Failed to load audio file, falling back to generated sound');
            // Fallback to generated sound if file fails
        }

        // Play generated sound
        const buffer = this.sounds.get(soundName) || this.sounds.get('alert_error');
        if (!buffer) {
            console.warn(`[Audio] Sound not found: ${soundName}`);
            return;
        }

        console.log('[Audio] Playing generated sound:', soundName);
        return this.playBuffer(buffer);
    }

    /**
     * Play an audio buffer
     */
    async playBuffer(buffer) {
        const source = this.context.createBufferSource();
        const gainNode = this.context.createGain();

        source.buffer = buffer;
        gainNode.gain.value = this.volume;

        source.connect(gainNode);
        gainNode.connect(this.context.destination);

        source.start(0);

        return new Promise(resolve => {
            source.onended = resolve;
        });
    }

    /**
     * Check message for keywords and play appropriate alerts
     */
    async checkAndPlay(message) {
        if (!this.isUnlocked || this.isMuted) return;

        const text = typeof message === 'string' ? message : JSON.stringify(message);
        const upperText = text.toUpperCase();

        // Find matching alerts
        const matches = [];
        for (const config of this.alertConfigs) {
            if (upperText.includes(config.keyword)) {
                matches.push(config);
            }
        }

        if (matches.length === 0) return;

        // Sort by priority (highest first)
        matches.sort((a, b) => b.priority - a.priority);

        // Add to queue
        this.queue.push(...matches.map(m => m.sound));

        // Process queue
        await this.processQueue();
    }

    /**
     * Process the audio queue
     */
    async processQueue() {
        if (this.isPlaying || this.queue.length === 0) return;

        this.isPlaying = true;

        while (this.queue.length > 0) {
            const soundName = this.queue.shift();
            await this.playSound(soundName);

            // Small delay between sounds
            await new Promise(resolve => setTimeout(resolve, 100));
        }

        this.isPlaying = false;
    }

    /**
     * Set volume (0-1)
     */
    setVolume(value) {
        this.volume = Math.max(0, Math.min(1, value));
        this.saveSettings();
    }

    /**
     * Toggle mute
     */
    toggleMute() {
        this.isMuted = !this.isMuted;
        this.saveSettings();
        return this.isMuted;
    }

    /**
     * Get mute state
     */
    get isAudioMuted() {
        return this.isMuted;
    }

    /**
     * Save settings to localStorage
     */
    saveSettings() {
        try {
            localStorage.setItem('la_audio_settings', JSON.stringify({
                volume: this.volume,
                isMuted: this.isMuted
            }));
        } catch (e) {
            // Ignore localStorage errors
        }
    }

    /**
     * Load settings from localStorage
     */
    loadSettings() {
        try {
            const saved = localStorage.getItem('la_audio_settings');
            if (saved) {
                const settings = JSON.parse(saved);
                this.volume = settings.volume ?? 0.5;
                this.isMuted = settings.isMuted ?? false;
            }
        } catch (e) {
            // Ignore localStorage errors
        }
    }

    /**
     * Add custom alert configuration
     */
    addAlertConfig(keyword, soundName, priority = 1) {
        this.alertConfigs.push({ keyword: keyword.toUpperCase(), sound: soundName, priority });
    }

    /**
     * Test audio system
     */
    async test() {
        if (!this.isUnlocked) {
            console.warn('[Audio] Context not unlocked');
            return false;
        }

        await this.playSound('alert_info');
        return true;
    }
}

// Create global instance
window.audioManager = new AudioManager();
