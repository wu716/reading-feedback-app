/**
 * Self-talk 音频播放器（循环次数 / 循环时长 + 播放统计）
 */
(function () {
    const state = {
        selfTalkId: null,
        audio: null,
        blobUrl: null,
        loadTimer: null,
        autoPlayed: false,
        loopMode: 'once',
        loopsDone: 0,
        sessionStart: 0,
        totalListenedSec: 0,
        playStart: 0,
        timeLimitSec: 0,
        targetLoops: 3,
        targetMinutes: 10,
        wheelCount: null,
        wheelTime: null,
        stopTimer: null,
        sessionReported: false,
        unloadBound: false,
    };

    function formatTime(sec) {
        const s = Math.max(0, Math.floor(sec));
        const m = Math.floor(s / 60);
        const r = s % 60;
        return `${m}:${String(r).padStart(2, '0')}`;
    }

    function accumulateListenTime() {
        if (state.playStart && state.audio && !state.audio.paused) {
            const now = performance.now();
            state.totalListenedSec += (now - state.playStart) / 1000;
            state.playStart = now;
        }
    }

    function getListenSeconds() {
        accumulateListenTime();
        let sec = state.totalListenedSec;
        if (state.audio && state.audio.currentTime > 0) {
            sec = Math.max(sec, state.audio.currentTime);
        }
        return Math.max(0, Math.round(sec));
    }

    function canLogPlayback() {
        return getListenSeconds() >= 1 || state.loopsDone >= 1;
    }

    function mediaAudioUrl(selfTalkId) {
        const token = localStorage.getItem('authToken') || '';
        return `/api/self_talks/${selfTalkId}/audio?token=${encodeURIComponent(token)}`;
    }

    function clearLoadTimer() {
        if (state.loadTimer) {
            clearTimeout(state.loadTimer);
            state.loadTimer = null;
        }
    }

    function notifyPlaybackLogged() {
        window.dispatchEvent(new CustomEvent('selftalk-playback-logged'));
        if (typeof loadTodayDashboard === 'function') {
            loadTodayDashboard();
        }
    }

    function buildPlaybackBody(segmentLoops) {
        return {
            self_talk_id: state.selfTalkId,
            duration_seconds: Math.max(1, getListenSeconds()),
            loops_completed: segmentLoops ?? Math.max(1, state.loopsDone),
            loop_mode: state.loopMode,
            loop_target: state.loopMode === 'count' ? state.targetLoops
                : state.loopMode === 'time' ? state.targetMinutes * 60 : null,
        };
    }

    async function reportPlayback(options = {}) {
        if (state.sessionReported && !options.allowAnother) return false;
        if (!state.selfTalkId) return false;

        const sec = getListenSeconds();
        if (sec < 1 && state.loopsDone < 1) return false;

        const token = localStorage.getItem('authToken');
        if (!token) return false;

        const body = buildPlaybackBody(options.segmentLoops);
        try {
            const res = await fetch('/api/self_talks/playback-log', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(body),
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                console.error('播放记录上报失败', res.status, err.detail || res.statusText);
                return false;
            }
            state.sessionReported = !options.resetAfter;
            if (options.resetAfter) {
                state.totalListenedSec = 0;
                state.playStart = state.audio && !state.audio.paused ? performance.now() : 0;
            }
            setStatus('已记录播放统计');
            notifyPlaybackLogged();
            return true;
        } catch (e) {
            console.warn('播放记录上报失败', e);
            return false;
        }
    }

    function tryKeepaliveReport() {
        if (!canLogPlayback() || state.sessionReported || !state.selfTalkId) return;
        const token = localStorage.getItem('authToken');
        if (!token) return;
        fetch('/api/self_talks/playback-log', {
            method: 'POST',
            keepalive: true,
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(buildPlaybackBody(1)),
        }).catch(() => {});
    }

    function bindPageHide() {
        if (state.unloadBound) return;
        state.unloadBound = true;
        window.addEventListener('pagehide', tryKeepaliveReport);
    }

    function ensureDock() {
        if (document.getElementById('stPlayerDock')) return;
        const dock = document.createElement('div');
        dock.id = 'stPlayerDock';
        dock.className = 'st-player-dock';
        dock.innerHTML = `
            <div class="st-player-card">
                <div class="st-player-header">
                    <span class="st-player-title" id="stPlayerTitle">Self-talk 播放</span>
                    <button type="button" class="st-player-close" id="stPlayerClose" aria-label="关闭">×</button>
                </div>
                <div class="st-player-visual" id="stPlayerVisual">
                    <div class="st-player-bar"></div><div class="st-player-bar"></div>
                    <div class="st-player-bar"></div><div class="st-player-bar"></div><div class="st-player-bar"></div>
                </div>
                <div class="st-player-progress-wrap">
                    <div class="st-player-progress"><div class="st-player-progress-fill" id="stProgressFill"></div></div>
                    <div class="st-player-time"><span id="stTimeCurrent">0:00</span><span id="stTimeTotal">0:00</span></div>
                </div>
                <div class="st-player-controls">
                    <button type="button" class="st-player-btn-sub" id="stPlayerStop">停止</button>
                    <button type="button" class="st-player-btn-main" id="stPlayerPlay">▶</button>
                    <button type="button" class="st-player-btn-sub" id="stPlayerLoopHint">单次</button>
                </div>
                <div class="st-player-loop">
                    <div class="st-loop-tabs">
                        <button type="button" class="st-loop-tab active" data-mode="once">单次</button>
                        <button type="button" class="st-loop-tab" data-mode="count">循环次数</button>
                        <button type="button" class="st-loop-tab" data-mode="time">循环时长</button>
                    </div>
                    <div class="st-loop-pickers">
                        <div class="st-loop-picker-wrap hidden" id="wrapLoopCount">
                            <div class="st-loop-picker-label">次数</div>
                            <div id="wheelLoopCount"></div>
                        </div>
                        <div class="st-loop-picker-wrap hidden" id="wrapLoopTime">
                            <div class="st-loop-picker-label">分钟</div>
                            <div id="wheelLoopTime"></div>
                        </div>
                    </div>
                </div>
                <div class="st-player-status" id="stPlayerStatus">选择循环方式后点击播放</div>
            </div>
        `;

        document.body.appendChild(dock);
        bindPageHide();

        document.getElementById('stPlayerClose').onclick = () => closePlayer(true);
        document.getElementById('stPlayerStop').onclick = () => closePlayer(true);
        document.getElementById('stPlayerPlay').onclick = togglePlay;

        document.querySelectorAll('.st-loop-tab').forEach((tab) => {
            tab.onclick = () => setLoopMode(tab.dataset.mode);
        });
    }

    function initWheels() {
        if (!state.wheelCount) {
            state.wheelCount = new WheelPicker('#wheelLoopCount', {
                min: 1, max: 99, value: 3,
                onChange: (v) => { state.targetLoops = v; updateLoopHint(); },
            });
        }
        if (!state.wheelTime) {
            state.wheelTime = new WheelPicker('#wheelLoopTime', {
                min: 1, max: 120, value: 10, suffix: '分',
                onChange: (v) => { state.targetMinutes = v; updateLoopHint(); },
            });
        }
    }

    function setLoopMode(mode) {
        state.loopMode = mode;
        document.querySelectorAll('.st-loop-tab').forEach((t) => {
            t.classList.toggle('active', t.dataset.mode === mode);
        });
        document.getElementById('wrapLoopCount').classList.toggle('hidden', mode !== 'count');
        document.getElementById('wrapLoopTime').classList.toggle('hidden', mode !== 'time');
        updateLoopHint();
    }

    function updateLoopHint() {
        const el = document.getElementById('stPlayerLoopHint');
        if (!el) return;
        if (state.loopMode === 'once') el.textContent = '单次';
        else if (state.loopMode === 'count') el.textContent = `${state.targetLoops}次`;
        else el.textContent = `${state.targetMinutes}分钟`;
    }

    function openDock() {
        ensureDock();
        initWheels();
        setLoopMode(state.loopMode);
        document.getElementById('stPlayerDock').classList.add('open');
    }

    async function closePlayer(logSession) {
        if (logSession && state.selfTalkId && canLogPlayback() && !state.sessionReported) {
            await reportPlayback();
        }

        const dock = document.getElementById('stPlayerDock');
        if (dock) dock.classList.remove('open', 'paused');

        clearLoadTimer();
        if (state.audio) {
            state.audio.pause();
            state.audio.onended = null;
            state.audio.ontimeupdate = null;
            state.audio.onerror = null;
            state.audio.oncanplay = null;
            state.audio.onloadedmetadata = null;
            state.audio.removeAttribute('src');
            try { state.audio.load(); } catch (e) { /* ignore */ }
            if (state.audio.parentNode) {
                state.audio.parentNode.removeChild(state.audio);
            }
        }
        if (state.stopTimer) {
            clearInterval(state.stopTimer);
            state.stopTimer = null;
        }
        if (state.blobUrl) {
            URL.revokeObjectURL(state.blobUrl);
            state.blobUrl = null;
        }
        state.audio = null;
        state.loopsDone = 0;
        state.totalListenedSec = 0;
        state.playStart = 0;
        state.sessionReported = false;
    }

    function shouldContinue() {
        if (state.loopMode === 'once') return false;
        if (state.loopMode === 'count') return state.loopsDone < state.targetLoops;
        if (state.loopMode === 'time') {
            return getListenSeconds() < state.targetMinutes * 60;
        }
        return false;
    }

    async function onTrackEnded() {
        accumulateListenTime();
        state.loopsDone += 1;
        const continuing = shouldContinue();

        if (state.loopMode === 'count' || state.loopMode === 'once') {
            await reportPlayback({ segmentLoops: 1, resetAfter: continuing, allowAnother: true });
        } else if (!continuing) {
            await reportPlayback({ allowAnother: true });
        }

        if (continuing) {
            state.audio.currentTime = 0;
            state.playStart = performance.now();
            await state.audio.play();
            setStatus(`第 ${state.loopsDone + 1} 遍播放中…`);
            return;
        }

        setStatus('播放完成');
        document.getElementById('stPlayerDock')?.classList.add('paused');
        document.getElementById('stPlayerPlay').textContent = '▶';
    }

    function setStatus(msg) {
        const el = document.getElementById('stPlayerStatus');
        if (el) el.textContent = msg;
    }

    function updateProgress() {
        if (!state.audio || !state.audio.duration) return;
        const cur = state.audio.currentTime;
        const dur = state.audio.duration;
        const pct = dur ? (cur / dur) * 100 : 0;
        const fill = document.getElementById('stProgressFill');
        if (fill) fill.style.width = `${pct}%`;
        document.getElementById('stTimeCurrent').textContent = formatTime(cur);
        document.getElementById('stTimeTotal').textContent = formatTime(dur);

        if (state.playStart && state.audio && !state.audio.paused) {
            const now = performance.now();
            state.totalListenedSec += (now - state.playStart) / 1000;
            state.playStart = now;
        }

        if (state.loopMode === 'time' && getListenSeconds() >= state.targetMinutes * 60) {
            state.audio.onended = null;
            state.audio.pause();
            onTrackEnded();
        }
    }

    async function togglePlay() {
        if (!state.audio) return;
        const btn = document.getElementById('stPlayerPlay');
        const dock = document.getElementById('stPlayerDock');
        if (state.audio.paused) {
            if (state.loopsDone === 0 && state.totalListenedSec === 0) {
                state.sessionStart = Date.now();
            }
            state.playStart = performance.now();
            if (state.loopMode === 'time' && !state.stopTimer) {
                state.stopTimer = setInterval(() => {
                    if (!state.audio || state.audio.paused) return;
                    updateProgress();
                }, 500);
            }
            await state.audio.play();
            dock.classList.remove('paused');
            btn.textContent = '⏸';
            setStatus('播放中…');
        } else {
            state.audio.pause();
            dock.classList.add('paused');
            btn.textContent = '▶';
            setStatus('已暂停');
            updateProgress();
            if (canLogPlayback()) {
                await reportPlayback({ segmentLoops: 1, resetAfter: true, allowAnother: true });
            }
        }
    }

    window.openSelfTalkPlayer = async function (selfTalkId) {
        const token = localStorage.getItem('authToken');
        if (!token) {
            alert('请先登录');
            return;
        }
        await closePlayer(false);
        state.selfTalkId = selfTalkId;
        state.loopsDone = 0;
        state.totalListenedSec = 0;
        state.loopMode = 'once';
        state.sessionReported = false;
        state.autoPlayed = false;

        openDock();
        setStatus('加载音频…');
        document.getElementById('stPlayerTitle').textContent = `Self-talk #${selfTalkId}`;

        const audio = document.createElement('audio');
        audio.setAttribute('playsinline', 'true');
        audio.setAttribute('webkit-playsinline', 'true');
        audio.preload = 'auto';
        audio.controls = false;
        audio.style.display = 'none';
        document.getElementById('stPlayerDock').appendChild(audio);
        state.audio = audio;

        const markReady = () => {
            clearLoadTimer();
            const dur = audio.duration;
            if (dur && Number.isFinite(dur)) {
                document.getElementById('stTimeTotal').textContent = formatTime(dur);
            }
        };

        audio.onended = onTrackEnded;
        audio.ontimeupdate = updateProgress;
        audio.onloadedmetadata = markReady;
        audio.oncanplay = async () => {
            markReady();
            if (state.autoPlayed || state.selfTalkId !== selfTalkId) return;
            state.autoPlayed = true;
            try {
                await togglePlay();
            } catch (playErr) {
                console.warn('自动播放被拦截，请手动点击播放', playErr);
                setStatus('已就绪，点击播放');
            }
        };
        audio.onerror = () => {
            clearLoadTimer();
            const code = audio.error ? audio.error.code : 0;
            setStatus(code === 4 ? '当前格式无法播放' : '音频加载失败，请稍后重试');
        };

        clearLoadTimer();
        state.loadTimer = setTimeout(() => {
            if (state.selfTalkId !== selfTalkId) return;
            if (!audio.duration || !Number.isFinite(audio.duration)) {
                setStatus('加载超时，请关闭后重试');
            }
        }, 12000);

        audio.src = mediaAudioUrl(selfTalkId);
        audio.load();
    };

    window.playAudio = function (selfTalkId) {
        openSelfTalkPlayer(selfTalkId);
    };
})();
