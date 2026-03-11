const CLASS_COLORS = {};
function getColor(cls) {
    if (!CLASS_COLORS[cls]) {
        const hue = (cls.charCodeAt(0) * 47 + cls.charCodeAt(cls.length - 1) * 31) % 360;
        CLASS_COLORS[cls] = `hsl(${hue}, 70%, 55%)`;
    }
    return CLASS_COLORS[cls];
}

const feed = document.getElementById('feed');
const placeholder = document.getElementById('placeholder');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const detList = document.getElementById('detection-list');
const fpsEl = document.getElementById('fps');
const objCountEl = document.getElementById('obj-count');
const classCountEl = document.getElementById('class-count');

let ws, frameCount = 0, lastFpsTime = Date.now();

function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws/detect-all`);

    ws.onopen = () => {
        statusDot.className = 'status-dot live';
        statusText.textContent = 'Live';
    };

    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);

        if (msg.type === 'frame') {
            feed.src = 'data:image/jpeg;base64,' + msg.data;
            feed.style.display = 'block';
            placeholder.style.display = 'none';

            frameCount++;
            const now = Date.now();
            if (now - lastFpsTime >= 1000) {
                fpsEl.textContent = frameCount;
                frameCount = 0;
                lastFpsTime = now;
            }
        }

        if (msg.detections !== undefined) {
            updateDetections(msg.detections);
        }
    };

    ws.onclose = () => {
        statusDot.className = 'status-dot';
        statusText.textContent = 'Reconnecting...';
        setTimeout(connect, 2000);
    };

    ws.onerror = () => ws.close();
}

function buildDetItem(cls, info) {
    const color = getColor(cls);
    const confPct = Math.round(info.maxConf * 100);

    const item = document.createElement('div');
    item.className = 'det-item';

    const nameDiv = document.createElement('div');
    nameDiv.className = 'det-name';

    const colorDot = document.createElement('div');
    colorDot.className = 'det-color';
    colorDot.style.background = color;

    const clsSpan = document.createElement('span');
    clsSpan.textContent = cls;

    nameDiv.appendChild(colorDot);
    nameDiv.appendChild(clsSpan);

    const rightDiv = document.createElement('div');
    rightDiv.className = 'det-right';

    const confSpan = document.createElement('span');
    confSpan.className = 'det-conf';
    confSpan.textContent = confPct + '%';

    const countSpan = document.createElement('span');
    countSpan.className = 'det-count';
    countSpan.textContent = String(info.count);

    rightDiv.appendChild(confSpan);
    rightDiv.appendChild(countSpan);

    item.appendChild(nameDiv);
    item.appendChild(rightDiv);
    return item;
}

function updateDetections(detections) {
    const groups = {};
    detections.forEach(d => {
        if (!groups[d.cls]) groups[d.cls] = { count: 0, maxConf: 0 };
        groups[d.cls].count++;
        groups[d.cls].maxConf = Math.max(groups[d.cls].maxConf, d.conf);
    });

    const sorted = Object.entries(groups).sort((a, b) => b[1].count - a[1].count);
    objCountEl.textContent = detections.length;
    classCountEl.textContent = sorted.length;

    while (detList.firstChild) detList.removeChild(detList.firstChild);

    if (sorted.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No objects detected';
        detList.appendChild(empty);
        return;
    }

    sorted.forEach(([cls, info]) => detList.appendChild(buildDetItem(cls, info)));
}

setInterval(() => { if (ws && ws.readyState === WebSocket.OPEN) ws.send('ping'); }, 10000);
connect();
