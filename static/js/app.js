class CCTVApp {
    constructor() {
        this.ws = null;
        this.isStreaming = false;
        this.cctvConnected = false;  // Track CCTV connection separately
        this.statsInterval = null;
        this.periodStatsInterval = null;
        this.clockInterval = null;
        this.reconnectAttempts = 0;

        // DOM elements
        this.videoFeed = document.getElementById('video-feed');
        this.noFeed = document.getElementById('no-feed');
        this.noFeedText = document.getElementById('no-feed-text');
        this.noFeedSubtext = document.getElementById('no-feed-subtext');
        this.statusText = document.getElementById('status-text');
        this.liveDot = document.querySelector('.live-dot');

        this.btnResetStats = document.getElementById('btn-reset-stats');

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

        // Time elements
        this.currentTime = document.getElementById('current-time');
        this.currentDate = document.getElementById('current-date');

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadSettings();
        this.startStatsPolling();
        this.startPeriodStatsPolling();
        this.startClock();
        // Auto-connect on load
        this.connectWebSocket();
    }

    bindEvents() {
        this.btnResetStats.addEventListener('click', () => this.resetStats());

        this.confidenceSlider.addEventListener('input', (e) => {
            this.confidenceValue.textContent = parseFloat(e.target.value).toFixed(2);
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

            // Format time
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');
            this.currentTime.textContent = `${hours}:${minutes}:${seconds}`;

            // Format date
            const options = {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric'
            };
            this.currentDate.textContent = now.toLocaleDateString('en-MY', options);
        };

        updateClock();
        this.clockInterval = setInterval(updateClock, 1000);
    }

    async loadSettings() {
        try {
            const response = await fetch('/settings');
            const settings = await response.json();

            this.confidenceSlider.value = settings.confidence;
            this.confidenceValue.textContent = settings.confidence.toFixed(2);
            this.genderToggle.checked = settings.enable_gender;
        } catch (error) {
            console.error('Failed to load settings:', error);
        }
    }

    async updateSettings(settings) {
        try {
            await fetch('/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
        } catch (error) {
            console.error('Failed to update settings:', error);
        }
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/stream`;

        this.setStatus('connecting', 'CONNECTING...');

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.isStreaming = true;
            this.reconnectAttempts = 0;
            // Don't set status to LIVE yet - wait for CCTV connection status
        };

        this.ws.onmessage = (event) => {
            try {
                // Parse JSON message
                const message = JSON.parse(event.data);

                if (message.type === 'frame') {
                    // Only update video if CCTV is connected
                    if (this.cctvConnected) {
                        this.videoFeed.src = `data:image/jpeg;base64,${message.data}`;
                    }
                } else if (message.type === 'status') {
                    // Handle connection status update
                    this.handleCCTVStatus(message.data);
                }
            } catch (error) {
                console.error('Error processing WebSocket message:', error);
            }
        };

        this.ws.onclose = () => {
            this.isStreaming = false;
            this.videoFeed.classList.remove('active');
            this.noFeed.classList.remove('hidden');

            // Always auto-reconnect with exponential backoff
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
            // CCTV is connected - show live feed
            this.cctvConnected = true;
            this.setStatus('connected', 'LIVE');
            this.videoFeed.classList.add('active');
            this.noFeed.classList.add('hidden');
        } else if (state === 'disconnected') {
            // CCTV is disconnected - clear video and show overlay
            this.cctvConnected = false;
            this.videoFeed.src = '';  // Clear stale frame
            this.videoFeed.classList.remove('active');
            this.noFeed.classList.remove('hidden');
            this.noFeedText.textContent = 'Camera Disconnected';
            this.noFeedSubtext.textContent = message || 'Connection lost';
            this.setStatus('disconnected', 'DISCONNECTED');
        } else if (state === 'reconnecting') {
            // CCTV is reconnecting
            this.cctvConnected = false;
            this.videoFeed.src = '';  // Clear stale frame
            this.videoFeed.classList.remove('active');
            this.noFeed.classList.remove('hidden');
            this.noFeedText.textContent = 'Reconnecting...';
            this.noFeedSubtext.textContent = message || 'Please wait';
            this.setStatus('disconnected', 'RECONNECTING');
        } else if (state === 'connecting') {
            // CCTV is connecting
            this.cctvConnected = false;
            this.noFeedText.textContent = 'Connecting to Camera...';
            this.noFeedSubtext.textContent = 'Please wait';
            this.setStatus('connecting', 'CONNECTING');
        }
    }

    setStatus(state, text) {
        this.statusText.textContent = text;

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
        // Update period stats every 10 seconds
        this.periodStatsInterval = setInterval(() => this.fetchPeriodStats(), 10000);
    }

    async fetchStats() {
        try {
            const response = await fetch('/stats');
            const stats = await response.json();

            // Current stats
            this.currentPeople.textContent = stats.current.total_people || 0;
            this.fpsValue.textContent = stats.current.fps || 0;

            // Today's visitors from saved data
            const todaySaved = stats.today_saved || {};
            const totalToday = todaySaved.total_visitors || 0;
            const maleTotal = todaySaved.male || 0;
            const femaleTotal = todaySaved.female || 0;
            const unknownTotal = todaySaved.unknown || 0;
            const totalGenderDetected = maleTotal + femaleTotal + unknownTotal;

            this.totalVisitors.textContent = totalToday;
            this.maleCount.textContent = maleTotal;
            this.femaleCount.textContent = femaleTotal;
            this.unknownCount.textContent = unknownTotal;

            // Calculate percentages
            if (totalGenderDetected > 0) {
                const malePercent = ((maleTotal / totalGenderDetected) * 100).toFixed(1);
                const femalePercent = ((femaleTotal / totalGenderDetected) * 100).toFixed(1);
                const unknownPercent = ((unknownTotal / totalGenderDetected) * 100).toFixed(1);
                this.malePercent.textContent = `${malePercent}%`;
                this.femalePercent.textContent = `${femalePercent}%`;
                this.unknownPercent.textContent = `${unknownPercent}%`;
            } else {
                this.malePercent.textContent = '0%';
                this.femalePercent.textContent = '0%';
                this.unknownPercent.textContent = '0%';
            }

            // Update age group stats from saved data
            const ageGroups = todaySaved.age_groups || {};
            this.ageChildren.textContent = ageGroups['Children'] || 0;
            this.ageTeens.textContent = ageGroups['Teens'] || 0;
            this.ageYoungAdults.textContent = ageGroups['Young Adults'] || 0;
            this.ageAdults.textContent = ageGroups['Adults'] || 0;
            this.ageSeniors.textContent = ageGroups['Seniors'] || 0;
        } catch (error) {
            // Silent fail for stats polling
        }
    }

    async fetchPeriodStats() {
        try {
            // Fetch all period stats
            const [weeklyRes, monthlyRes, alltimeRes] = await Promise.all([
                fetch('/stats/weekly'),
                fetch('/stats/monthly'),
                fetch('/stats/all-time')
            ]);

            const weekly = await weeklyRes.json();
            const monthly = await monthlyRes.json();
            const alltime = await alltimeRes.json();

            // Update weekly stats
            this.weekTotal.textContent = weekly.total_visitors || 0;
            this.weekMale.textContent = weekly.male || 0;
            this.weekFemale.textContent = weekly.female || 0;
            this.weekUnknown.textContent = weekly.unknown || 0;

            // Weekly age groups
            const weekAge = weekly.age_groups || {};
            this.weekAgeChildren.textContent = weekAge['Children'] || 0;
            this.weekAgeTeens.textContent = weekAge['Teens'] || 0;
            this.weekAgeYoung.textContent = weekAge['Young Adults'] || 0;
            this.weekAgeAdults.textContent = weekAge['Adults'] || 0;
            this.weekAgeSeniors.textContent = weekAge['Seniors'] || 0;

            // Update monthly stats
            this.monthTotal.textContent = monthly.total_visitors || 0;
            this.monthMale.textContent = monthly.male || 0;
            this.monthFemale.textContent = monthly.female || 0;
            this.monthUnknown.textContent = monthly.unknown || 0;

            // Monthly age groups
            const monthAge = monthly.age_groups || {};
            this.monthAgeChildren.textContent = monthAge['Children'] || 0;
            this.monthAgeTeens.textContent = monthAge['Teens'] || 0;
            this.monthAgeYoung.textContent = monthAge['Young Adults'] || 0;
            this.monthAgeAdults.textContent = monthAge['Adults'] || 0;
            this.monthAgeSeniors.textContent = monthAge['Seniors'] || 0;

            // Update all-time stats
            this.alltimeTotal.textContent = alltime.total_visitors || 0;
            this.alltimeMale.textContent = alltime.male || 0;
            this.alltimeFemale.textContent = alltime.female || 0;
            this.alltimeUnknown.textContent = alltime.unknown || 0;

            // All-time age groups
            const alltimeAge = alltime.age_groups || {};
            this.alltimeAgeChildren.textContent = alltimeAge['Children'] || 0;
            this.alltimeAgeTeens.textContent = alltimeAge['Teens'] || 0;
            this.alltimeAgeYoung.textContent = alltimeAge['Young Adults'] || 0;
            this.alltimeAgeAdults.textContent = alltimeAge['Adults'] || 0;
            this.alltimeAgeSeniors.textContent = alltimeAge['Seniors'] || 0;
        } catch (error) {
            console.error('Failed to fetch period stats:', error);
        }
    }

    async resetStats() {
        if (confirm('Reset today\'s visitor statistics?')) {
            try {
                await fetch('/reset-stats', { method: 'POST' });

                // Reset today's display immediately
                this.totalVisitors.textContent = '0';
                this.maleCount.textContent = '0';
                this.femaleCount.textContent = '0';
                this.unknownCount.textContent = '0';
                this.malePercent.textContent = '0%';
                this.femalePercent.textContent = '0%';
                this.unknownPercent.textContent = '0%';

                // Reset age stats
                this.ageChildren.textContent = '0';
                this.ageTeens.textContent = '0';
                this.ageYoungAdults.textContent = '0';
                this.ageAdults.textContent = '0';
                this.ageSeniors.textContent = '0';

                // Refresh period stats
                this.fetchPeriodStats();
            } catch (error) {
                console.error('Failed to reset stats:', error);
                alert('Failed to reset statistics');
            }
        }
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new CCTVApp();
});
