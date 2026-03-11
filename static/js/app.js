class CCTVApp {
    constructor() {
        this.ws = null;
        this.isStreaming = false;
        this.cctvConnected = false;
        this.statsInterval = null;
        this.periodStatsInterval = null;
        this.clockInterval = null;
        this.reconnectAttempts = 0;

        // API key (optional — for programmatic access; browser uses session cookie)
        const meta = document.querySelector('meta[name="api-key"]');
        this.apiKey = meta ? meta.getAttribute('content') : '';

        // DOM elements
        this.videoFeed = document.getElementById('video-feed');
        this.noFeed = document.getElementById('no-feed');
        this.noFeedText = document.getElementById('no-feed-text');
        this.noFeedSubtext = document.getElementById('no-feed-subtext');
        this.statusText = document.getElementById('status-text');
        this.liveDot = document.querySelector('.live-dot');

        this.btnResetStats = document.getElementById('btn-reset-stats');
        this.btnDownloadReport = document.getElementById('btn-download-report');

        this.confidenceSlider = document.getElementById('confidence-slider');
        this.confidenceValue = document.getElementById('confidence-value');
        this.genderToggle = document.getElementById('gender-toggle');

        // Stats elements - Today
        this.totalVisitors = document.getElementById('total-visitors');
        this.currentPeople = document.getElementById('current-people');
        this.fpsValue = document.getElementById('fps-value');
        this.maleCount = document.getElementById('male-count');
        this.femaleCount = document.getElementById('female-count');
        this.unknownCount = document.getElementById('unknown-count');
        this.malePercent = document.getElementById('male-percent');
        this.femalePercent = document.getElementById('female-percent');
        this.unknownPercent = document.getElementById('unknown-percent');

        // Period stats elements
        this.weekTotal = document.getElementById('week-total');
        this.weekMale = document.getElementById('week-male');
        this.weekFemale = document.getElementById('week-female');
        this.weekUnknown = document.getElementById('week-unknown');
        this.monthTotal = document.getElementById('month-total');
        this.monthMale = document.getElementById('month-male');
        this.monthFemale = document.getElementById('month-female');
        this.monthUnknown = document.getElementById('month-unknown');
        this.alltimeTotal = document.getElementById('alltime-total');
        this.alltimeMale = document.getElementById('alltime-male');
        this.alltimeFemale = document.getElementById('alltime-female');
        this.alltimeUnknown = document.getElementById('alltime-unknown');

        // Period age stats elements
        this.weekAgeChildren = document.getElementById('week-age-children');
        this.weekAgeTeens = document.getElementById('week-age-teens');
        this.weekAgeYoung = document.getElementById('week-age-young');
        this.weekAgeAdults = document.getElementById('week-age-adults');
        this.weekAgeSeniors = document.getElementById('week-age-seniors');

        this.monthAgeChildren = document.getElementById('month-age-children');
        this.monthAgeTeens = document.getElementById('month-age-teens');
        this.monthAgeYoung = document.getElementById('month-age-young');
        this.monthAgeAdults = document.getElementById('month-age-adults');
        this.monthAgeSeniors = document.getElementById('month-age-seniors');

        this.alltimeAgeChildren = document.getElementById('alltime-age-children');
        this.alltimeAgeTeens = document.getElementById('alltime-age-teens');
        this.alltimeAgeYoung = document.getElementById('alltime-age-young');
        this.alltimeAgeAdults = document.getElementById('alltime-age-adults');
        this.alltimeAgeSeniors = document.getElementById('alltime-age-seniors');

        // Age stats elements
        this.ageChildren = document.getElementById('age-children');
        this.ageTeens = document.getElementById('age-teens');
        this.ageYoungAdults = document.getElementById('age-young-adults');
        this.ageAdults = document.getElementById('age-adults');
        this.ageSeniors = document.getElementById('age-seniors');

        // Person capture elements
        this.personCapturesBody = document.getElementById('person-captures-body');
        this.personCapturesEmpty = document.getElementById('person-captures-empty');
        this.personCaptureCount = document.getElementById('person-capture-count');

        // Time elements
        this.currentTime = document.getElementById('current-time');
        this.currentDate = document.getElementById('current-date');

        this.init();
    }

    /**
     * Build fetch headers with API key if configured.
     */
    _headers(extra = {}) {
        const h = { 'Content-Type': 'application/json', ...extra };
        if (this.apiKey) h['X-API-Key'] = this.apiKey;
        return h;
    }

    /**
     * Safely set text content (prevents XSS — never use innerHTML for dynamic data).
     */
    _setText(el, value) {
        if (el) el.textContent = value;
    }

    init() {
        this.bindEvents();
        this.initMobileTabs();
        this.loadSettings();
        this.startStatsPolling();
        this.startPeriodStatsPolling();
        this.startClock();
        this.connectWebSocket();
        this.loadFaceCaptures();
        this.loadPersonCaptures();
    }

    initMobileTabs() {
        const tabs = document.querySelectorAll('.mobile-tab');
        if (!tabs.length) return;

        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const targetId = tab.dataset.target;

                // Update tab active state
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');

                // Show/hide sections
                const videoSection = document.getElementById('video-section');
                const statsSection = document.getElementById('stats-section');

                if (targetId === 'video-section') {
                    videoSection && videoSection.classList.remove('tab-hidden');
                    statsSection && statsSection.classList.add('tab-hidden');
                } else {
                    statsSection && statsSection.classList.remove('tab-hidden');
                    videoSection && videoSection.classList.add('tab-hidden');
                }

                // Scroll to top when switching tabs
                window.scrollTo({ top: 0, behavior: 'smooth' });
            });
        });
    }

    bindEvents() {
        this.btnResetStats.addEventListener('click', () => this.resetStats());
        this.btnDownloadReport.addEventListener('click', () => this.downloadReport());

        this.confidenceSlider.addEventListener('input', (e) => {
            this._setText(this.confidenceValue, parseFloat(e.target.value).toFixed(2));
        });

        this.confidenceSlider.addEventListener('change', (e) => {
            this.updateSettings({ confidence: parseFloat(e.target.value) });
        });

        this.genderToggle.addEventListener('change', (e) => {
            this.updateSettings({ enable_gender: e.target.checked });
        });
    }

    startClock() {
        const updateClock = () => {
            const now = new Date();

            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');
            this._setText(this.currentTime, `${hours}:${minutes}:${seconds}`);

            const options = {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            };
            this._setText(this.currentDate, now.toLocaleDateString('en-MY', options));
        };

        updateClock();
        this.clockInterval = setInterval(updateClock, 1000);
    }

    _checkAuth(response) {
        if (response.status === 401) {
            window.location.href = 'login';
            return false;
        }
        return true;
    }

    async loadSettings() {
        try {
            const response = await fetch('settings', { headers: this._headers() });
            if (!this._checkAuth(response)) return;
            const settings = await response.json();

            this.confidenceSlider.value = settings.confidence;
            this._setText(this.confidenceValue, settings.confidence.toFixed(2));
            this.genderToggle.checked = settings.enable_gender;
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    }

    async updateSettings(settings) {
        try {
            await fetch('settings', {
                method: 'POST',
                headers: this._headers(),
                body: JSON.stringify(settings)
            });
        } catch (error) {
            console.error('Failed to update settings:', error);
        }
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        // Build WS URL relative to current page path (works behind reverse proxy)
        const basePath = window.location.pathname.replace(/\/?$/, '/');
        let wsUrl = `${protocol}//${window.location.host}${basePath}ws/stream`;
        // API key only needed for programmatic access; browser sends session cookie automatically
        if (this.apiKey) wsUrl += `?api_key=${encodeURIComponent(this.apiKey)}`;

        this.setStatus('connecting', 'CONNECTING...');

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.isStreaming = true;
            this.reconnectAttempts = 0;
        };

        this.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);

                if (message.type === 'frame') {
                    if (this.cctvConnected) {
                        this.videoFeed.src = `data:image/jpeg;base64,${message.data}`;
                    }
                } else if (message.type === 'status') {
                    this.handleCCTVStatus(message.data);
                } else if (message.type === 'face_capture') {
                    this.prependFaceTile(message.data);
                } else if (message.type === 'person_capture') {
                    this.prependPersonTile(message.data);
                }
            } catch (error) {
                console.error('Error processing WebSocket message:', error);
            }
        };

        this.ws.onclose = () => {
            this.isStreaming = false;
            this.videoFeed.classList.remove('active');
            this.noFeed.classList.remove('hidden');

            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);

            this.setStatus('disconnected', `RECONNECTING IN ${Math.ceil(delay/1000)}s...`);

            setTimeout(() => {
                this.connectWebSocket();
            }, delay);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.setStatus('disconnected', 'CONNECTION ERROR');
        };
    }

    handleCCTVStatus(status) {
        const { state, message } = status;

        if (state === 'connected') {
            this.cctvConnected = true;
            this.setStatus('connected', 'LIVE');
            this.videoFeed.classList.add('active');
            this.noFeed.classList.add('hidden');
        } else if (state === 'disconnected') {
            this.cctvConnected = false;
            this.videoFeed.src = '';
            this.videoFeed.classList.remove('active');
            this.noFeed.classList.remove('hidden');
            this._setText(this.noFeedText, 'Camera Disconnected');
            this._setText(this.noFeedSubtext, message || 'Connection lost');
            this.setStatus('disconnected', 'DISCONNECTED');
        } else if (state === 'reconnecting') {
            this.cctvConnected = false;
            this.videoFeed.src = '';
            this.videoFeed.classList.remove('active');
            this.noFeed.classList.remove('hidden');
            this._setText(this.noFeedText, 'Reconnecting...');
            this._setText(this.noFeedSubtext, message || 'Please wait');
            this.setStatus('disconnected', 'RECONNECTING');
        } else if (state === 'connecting') {
            this.cctvConnected = false;
            this._setText(this.noFeedText, 'Connecting to Camera...');
            this._setText(this.noFeedSubtext, 'Please wait');
            this.setStatus('connecting', 'CONNECTING');
        }
    }

    setStatus(state, text) {
        this._setText(this.statusText, text);

        if (state === 'connected') {
            this.liveDot.classList.add('active');
        } else {
            this.liveDot.classList.remove('active');
        }
    }

    startStatsPolling() {
        this.fetchStats();
        this.statsInterval = setInterval(() => this.fetchStats(), 1000);
    }

    startPeriodStatsPolling() {
        this.fetchPeriodStats();
        this.periodStatsInterval = setInterval(() => this.fetchPeriodStats(), 10000);
    }

    async fetchStats() {
        try {
            const response = await fetch('stats', { headers: this._headers() });
            if (!this._checkAuth(response)) return;
            const stats = await response.json();

            this._setText(this.currentPeople, stats.current.total_people || 0);
            this._setText(this.fpsValue, stats.current.fps || 0);

            const todaySaved = stats.today_saved || {};
            const totalToday = todaySaved.total_visitors || 0;
            const maleTotal = todaySaved.male || 0;
            const femaleTotal = todaySaved.female || 0;
            const unknownTotal = todaySaved.unknown || 0;
            const totalGenderDetected = maleTotal + femaleTotal + unknownTotal;

            this._setText(this.totalVisitors, totalToday);
            this._setText(this.maleCount, maleTotal);
            this._setText(this.femaleCount, femaleTotal);
            this._setText(this.unknownCount, unknownTotal);

            if (totalGenderDetected > 0) {
                this._setText(this.malePercent, `${((maleTotal / totalGenderDetected) * 100).toFixed(1)}%`);
                this._setText(this.femalePercent, `${((femaleTotal / totalGenderDetected) * 100).toFixed(1)}%`);
                this._setText(this.unknownPercent, `${((unknownTotal / totalGenderDetected) * 100).toFixed(1)}%`);
            } else {
                this._setText(this.malePercent, '0%');
                this._setText(this.femalePercent, '0%');
                this._setText(this.unknownPercent, '0%');
            }

            const ageGroups = todaySaved.age_groups || {};
            this._setText(this.ageChildren, ageGroups['Children'] || 0);
            this._setText(this.ageTeens, ageGroups['Teens'] || 0);
            this._setText(this.ageYoungAdults, ageGroups['Young Adults'] || 0);
            this._setText(this.ageAdults, ageGroups['Adults'] || 0);
            this._setText(this.ageSeniors, ageGroups['Seniors'] || 0);
        } catch (error) {
            // Silent fail for stats polling
        }
    }

    async fetchPeriodStats() {
        try {
            const hdrs = this._headers();
            const [weeklyRes, monthlyRes, alltimeRes] = await Promise.all([
                fetch('stats/weekly', { headers: hdrs }),
                fetch('stats/monthly', { headers: hdrs }),
                fetch('stats/all-time', { headers: hdrs })
            ]);

            if (!this._checkAuth(weeklyRes) || !this._checkAuth(monthlyRes) || !this._checkAuth(alltimeRes)) return;

            const weekly = await weeklyRes.json();
            const monthly = await monthlyRes.json();
            const alltime = await alltimeRes.json();

            // Weekly
            this._setText(this.weekTotal, weekly.total_visitors || 0);
            this._setText(this.weekMale, weekly.male || 0);
            this._setText(this.weekFemale, weekly.female || 0);
            this._setText(this.weekUnknown, weekly.unknown || 0);

            const weekAge = weekly.age_groups || {};
            this._setText(this.weekAgeChildren, weekAge['Children'] || 0);
            this._setText(this.weekAgeTeens, weekAge['Teens'] || 0);
            this._setText(this.weekAgeYoung, weekAge['Young Adults'] || 0);
            this._setText(this.weekAgeAdults, weekAge['Adults'] || 0);
            this._setText(this.weekAgeSeniors, weekAge['Seniors'] || 0);

            // Monthly
            this._setText(this.monthTotal, monthly.total_visitors || 0);
            this._setText(this.monthMale, monthly.male || 0);
            this._setText(this.monthFemale, monthly.female || 0);
            this._setText(this.monthUnknown, monthly.unknown || 0);

            const monthAge = monthly.age_groups || {};
            this._setText(this.monthAgeChildren, monthAge['Children'] || 0);
            this._setText(this.monthAgeTeens, monthAge['Teens'] || 0);
            this._setText(this.monthAgeYoung, monthAge['Young Adults'] || 0);
            this._setText(this.monthAgeAdults, monthAge['Adults'] || 0);
            this._setText(this.monthAgeSeniors, monthAge['Seniors'] || 0);

            // All-time
            this._setText(this.alltimeTotal, alltime.total_visitors || 0);
            this._setText(this.alltimeMale, alltime.male || 0);
            this._setText(this.alltimeFemale, alltime.female || 0);
            this._setText(this.alltimeUnknown, alltime.unknown || 0);

            const alltimeAge = alltime.age_groups || {};
            this._setText(this.alltimeAgeChildren, alltimeAge['Children'] || 0);
            this._setText(this.alltimeAgeTeens, alltimeAge['Teens'] || 0);
            this._setText(this.alltimeAgeYoung, alltimeAge['Young Adults'] || 0);
            this._setText(this.alltimeAgeAdults, alltimeAge['Adults'] || 0);
            this._setText(this.alltimeAgeSeniors, alltimeAge['Seniors'] || 0);
        } catch (error) {
            console.error('Failed to fetch period stats:', error);
        }
    }

    async resetStats() {
        if (confirm('Reset today\'s visitor statistics?')) {
            try {
                await fetch('reset-stats', { method: 'POST', headers: this._headers() });

                this._setText(this.totalVisitors, '0');
                this._setText(this.maleCount, '0');
                this._setText(this.femaleCount, '0');
                this._setText(this.unknownCount, '0');
                this._setText(this.malePercent, '0%');
                this._setText(this.femalePercent, '0%');
                this._setText(this.unknownPercent, '0%');

                this._setText(this.ageChildren, '0');
                this._setText(this.ageTeens, '0');
                this._setText(this.ageYoungAdults, '0');
                this._setText(this.ageAdults, '0');
                this._setText(this.ageSeniors, '0');

                this.fetchPeriodStats();
            } catch (error) {
                console.error('Failed to reset stats:', error);
                alert('Failed to reset statistics');
            }
        }
    }
    downloadReport() {
        window.location.href = 'stats/export/pdf';
    }

    buildFaceTile(capture) {
        const tile = document.createElement('div');
        tile.className = 'face-tile ' + (capture.gender === 'Male' ? 'male' : 'female');

        const img = document.createElement('img');
        img.className = 'face-tile-img';
        img.src = capture.url;
        img.alt = 'Face';
        img.onerror = function() { this.style.opacity = '0.3'; };

        const info = document.createElement('div');
        info.className = 'face-tile-info';

        const genderEl = document.createElement('div');
        genderEl.className = 'face-tile-gender';
        genderEl.textContent = capture.gender;

        const ageEl = document.createElement('div');
        ageEl.className = 'face-tile-age';
        ageEl.textContent = capture.age != null
            ? capture.age + 'y \u00B7 ' + (capture.age_group || '')
            : (capture.age_group || '');

        const visitorEl = document.createElement('div');
        visitorEl.className = 'face-tile-visitor';
        if (capture.visitor_id != null) {
            visitorEl.textContent = 'Visitor #' + capture.visitor_id;
            if (capture.is_new_visitor) {
                const badge = document.createElement('span');
                badge.className = 'face-new-badge';
                badge.textContent = 'NEW';
                visitorEl.appendChild(badge);
            }
        } else {
            visitorEl.textContent = 'Unconfirmed';
            visitorEl.classList.add('face-unconfirmed');
        }

        const timeEl = document.createElement('div');
        timeEl.className = 'face-tile-time';
        timeEl.textContent = new Date(capture.timestamp * 1000).toLocaleTimeString();

        info.appendChild(genderEl);
        info.appendChild(ageEl);
        info.appendChild(visitorEl);
        info.appendChild(timeEl);
        tile.appendChild(img);
        tile.appendChild(info);
        return tile;
    }

    prependFaceTile(capture, silent = false) {
        const body = document.getElementById('face-captures-body');
        const empty = document.getElementById('face-captures-empty');
        if (empty) empty.remove();

        body.insertBefore(this.buildFaceTile(capture), body.firstChild);

        // Rolling window: keep max 20 tiles
        while (body.children.length > 20) {
            body.removeChild(body.lastChild);
        }

        if (!silent) {
            const counter = document.getElementById('face-capture-count');
            if (counter) counter.textContent = parseInt(counter.textContent || '0') + 1;
        }
    }

    async loadFaceCaptures() {
        try {
            const resp = await fetch('/faces', { headers: this._headers() });
            if (!resp.ok) return;
            const captures = await resp.json();
            // API returns newest-first; reverse so prepend builds correct top-to-bottom order
            [...captures].reverse().forEach(c => this.prependFaceTile(c, true));
            const counter = document.getElementById('face-capture-count');
            if (counter && captures.length) counter.textContent = captures.length;
        } catch (e) {
            console.warn('Could not load face captures:', e);
        }
    }

    buildPersonTile(capture) {
        const tile = document.createElement('div');
        const genderClass = (capture.gender || '').toLowerCase();
        tile.className = `person-tile ${genderClass}`;

        const img = document.createElement('img');
        img.className = 'person-tile-img';
        img.src = capture.url;
        img.alt = capture.gender || 'Person';
        img.loading = 'lazy';

        const info = document.createElement('div');
        info.className = 'person-tile-info';

        const genderEl = document.createElement('div');
        genderEl.className = 'person-tile-gender';
        this._setText(genderEl, capture.gender || '?');

        const ageEl = document.createElement('div');
        ageEl.className = 'person-tile-age';
        this._setText(ageEl, capture.age ? `${capture.age}y` : '');

        info.appendChild(genderEl);
        info.appendChild(ageEl);
        tile.appendChild(img);
        tile.appendChild(info);
        return tile;
    }

    prependPersonTile(capture, silent = false) {
        const body = document.getElementById('person-captures-body');
        const empty = document.getElementById('person-captures-empty');
        if (empty) empty.remove();

        body.insertBefore(this.buildPersonTile(capture), body.firstChild);

        // Rolling window: keep max 20 tiles
        while (body.children.length > 20) {
            body.removeChild(body.lastChild);
        }

        if (!silent) {
            const counter = document.getElementById('person-capture-count');
            if (counter) counter.textContent = parseInt(counter.textContent || '0') + 1;
        }
    }

    async loadPersonCaptures() {
        try {
            const resp = await fetch('/persons', { headers: this._headers() });
            if (!resp.ok) return;
            const captures = await resp.json();
            // API returns newest-first; reverse so prepend builds correct order
            [...captures].reverse().forEach(c => this.prependPersonTile(c, true));
            const counter = document.getElementById('person-capture-count');
            if (counter && captures.length) counter.textContent = captures.length;
        } catch (e) {
            console.warn('Could not load person captures:', e);
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new CCTVApp();
});
