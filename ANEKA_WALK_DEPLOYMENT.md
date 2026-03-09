# Aneka Walk Visitor Monitoring System

## Deployment Guide for Mall Display

---

## System Information

**Location**: Aneka Walk, Shah Alam
**Purpose**: Real-time visitor counting and gender analytics
**Display**: Large screen/monitor in public area
**Version**: 2.0.0
**Innovation Credit**: Bahagian Transformasi Digital

---

## Access Information

### Web Interface

**URL**: http://10.0.50.203:8000

**Browser Requirements**:
- Modern browser (Chrome, Firefox, Edge, Safari)
- JavaScript enabled
- WebSocket support

### Display Recommendations

**Optimal Setup**:
- Screen Size: 32" or larger
- Resolution: 1920x1080 (Full HD) or higher
- Orientation: Landscape
- Mounting: Eye level or above
- Viewing Distance: 2-5 meters

---

## Quick Start Guide

### 1. Open Dashboard

1. Open browser on display device
2. Navigate to: `http://10.0.50.203:8000`
3. Wait for dashboard to load
4. Press F11 for fullscreen mode (recommended)

### 2. Start Monitoring

1. Click **"Start Monitoring"** button (green)
2. Wait 2-3 seconds for connection
3. Video feed will appear
4. Status indicator will show **"LIVE"** (green)

### 3. Configure Settings

**Gender Detection**:
- Check/uncheck "Enable Gender Detection"
- Enabled: Shows male/female breakdown
- Disabled: Only counts total visitors

**Detection Confidence**:
- Adjust slider (0.30 - 0.90)
- Higher = fewer false positives
- Lower = catches more people
- Recommended: 0.50

---

## Dashboard Overview

### Header Section

```
┌─────────────────────────────────────────────────────────┐
│ ANEKA WALK          Visitor Monitoring      18:45:23   │
│ Shah Alam          System [●LIVE]       Friday, Jan 31  │
└─────────────────────────────────────────────────────────┘
```

**Left**: Mall branding
**Center**: System title and status
**Right**: Real-time clock and date

### Main Display Area

**Video Feed**:
- Live CCTV stream
- Bounding boxes around detected people
- Color-coded by gender (if enabled)
- FPS indicator (top-right corner)

**Control Panel** (below video):
- Start/Stop monitoring buttons
- Gender detection toggle
- Confidence threshold slider

### Statistics Panel (Right Side)

**Today's Visitors** (Blue gradient card):
- Total visitor count for the day
- Large prominent display
- Resets at midnight or manually

**Current Count**:
- People currently in camera view
- Updates in real-time

**Gender Distribution** (if enabled):
- Male count + percentage (Blue)
- Female count + percentage (Pink)
- Percentages add up to 100%

**Innovation Credit**:
- "Inovasi oleh"
- "Bahagian Transformasi Digital"

---

## Daily Operations

### Morning Setup

1. **Power On Display**
   - Turn on monitor
   - Open browser to dashboard

2. **Start Monitoring**
   - Click "Start Monitoring"
   - Verify video feed is live
   - Check FPS is 12-15

3. **Reset Yesterday's Stats** (if needed)
   - Click reset icon (🔄) on "Today's Visitors" card
   - Confirm reset
   - Verify counts return to 0

### During Operation

**Normal Operation**:
- Status: "LIVE" (green indicator)
- FPS: 12-15 (green badge)
- Video: Smooth stream
- Stats: Updating every second

**If Connection Lost**:
- Status changes to "OFFLINE" (red)
- Auto-reconnect attempts after 3 seconds
- If fails, click "Stop" then "Start Monitoring"

### Evening Shutdown (Optional)

1. Click "Stop Monitoring"
2. Note down final statistics (if needed)
3. Close browser or leave running overnight

---

## Understanding Statistics

### "Today's Visitors"

**What it shows**: Cumulative count of all detections

**Important Notes**:
- This is NOT unique visitors
- Same person walking by multiple times = multiple counts
- Useful for traffic flow analysis
- Higher numbers indicate busier periods

**Interpretation**:
```
100 visitors = Very quiet (early morning)
500 visitors = Moderate traffic
1000+ visitors = Busy period (afternoon/evening)
5000+ visitors = Very busy day
```

### "People in View"

**What it shows**: Current count in camera frame

**Use cases**:
- Real-time occupancy
- Queue management
- Crowding alerts

### "Gender Distribution"

**What it shows**: Male vs Female breakdown

**Accuracy**:
- 80-90% with clear facial visibility
- Works with hijab (facial features, not hair)
- "Unknown" when face not clear

**Use cases**:
- Marketing demographics
- Product placement decisions
- Store layout optimization

---

## Troubleshooting

### Video Feed Not Showing

**Problem**: Black screen or "No Live Feed"

**Solutions**:
1. Check "Start Monitoring" was clicked
2. Verify Status shows "LIVE"
3. Check CCTV camera at 172.31.0.71 is powered on
4. Try Stop → Start Monitoring
5. Refresh browser page (F5)

### Low FPS (Below 10)

**Problem**: Laggy video, low FPS number

**Solutions**:
1. Disable gender detection temporarily
2. Reduce detection confidence to 0.5
3. Check server CPU usage
4. Restart monitoring session

### Statistics Not Updating

**Problem**: Numbers frozen, not changing

**Solutions**:
1. Check internet connection
2. Open browser console (F12) for errors
3. Refresh page
4. Restart monitoring

### Gender Detection Not Working

**Problem**: All showing as "Unknown"

**Solutions**:
1. Ensure "Enable Gender Detection" is checked
2. Check people are facing camera
3. Verify lighting conditions
4. May be normal if faces not visible

---

## Best Practices

### Camera Positioning

✓ **Good**:
- Front-facing to capture faces
- 2-4 meters height
- Clear view of walking path
- Good lighting

✗ **Avoid**:
- Top-down angle (can't see faces)
- Backlit positions (against windows)
- Too far (>10 meters)
- Obstructed views

### Display Positioning

✓ **Good**:
- Eye level or slightly above
- Away from direct sunlight
- Visible to staff, not necessarily public
- Protected from tampering

### Monitoring Schedule

**Recommended**:
- Start: 9:00 AM (before mall opens)
- Stop: 11:00 PM (after mall closes)
- Reset: Daily at midnight or 9:00 AM

**Automated** (future):
- Schedule via cron jobs
- Auto-reset at specified time
- Email daily reports

---

## Performance Expectations

### Normal Operation

| Metric | Expected Value |
|--------|---------------|
| FPS | 12-15 |
| CPU Usage | 40-60% |
| Memory | ~2GB |
| Bandwidth | 2-3 Mbps |
| Latency | <500ms |

### Visitor Counts (Typical)

| Time Period | Expected Count |
|-------------|---------------|
| 10:00-12:00 | 500-1000 |
| 12:00-14:00 | 1500-2500 (lunch) |
| 14:00-17:00 | 800-1500 |
| 17:00-20:00 | 2000-3500 (dinner) |
| 20:00-22:00 | 1000-1500 |

*Varies by mall traffic patterns*

---

## Data Privacy & Compliance

### PDPA Compliance (Malaysia)

✓ **System Compliance**:
- No video recording
- No face storage
- Real-time analysis only
- Anonymous statistics

✓ **Required**:
- Privacy notice signage
- Purpose disclosure
- Contact for inquiries

### Recommended Signage

```
┌─────────────────────────────────────┐
│  VISITOR MONITORING IN OPERATION    │
│                                     │
│  For mall analytics purposes only   │
│  No personal data is stored         │
│                                     │
│  Contact: [Management Contact]      │
└─────────────────────────────────────┘
```

---

## Support & Maintenance

### Server Information

**Location**: Ubuntu Server (10.0.50.203)
**Service**: Runs automatically on boot
**Logs**: `/home/adilhidayat/visitor-stat/logs/server.log`

### Restart Service

```bash
# SSH to server
ssh adilhidayat@10.0.50.203

# Restart service
cd /home/adilhidayat/visitor-stat
pkill -f "uvicorn main:app"
./run.sh &
```

### Check Status

```bash
# Via command line
curl http://10.0.50.203:8000/health

# Expected response:
# {"status":"healthy","cctv_connected":true,"streaming":true}
```

### View Statistics

```bash
# Get current stats
curl http://10.0.50.203:8000/stats | python3 -m json.tool
```

---

## Contact Information

**Technical Support**:
Bahagian Transformasi Digital

**System Issues**:
- Connection problems
- Statistics not recording
- Performance degradation

**Requests**:
- Feature additions
- Report generation
- Integration with other systems

---

## Appendix

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| F11 | Toggle fullscreen |
| F5 | Refresh page |
| Ctrl+Shift+I | Open developer tools |
| Esc | Exit fullscreen |

### Browser Recommendations

**Best**: Chrome (latest)
**Good**: Firefox, Edge (latest)
**Avoid**: Internet Explorer

### Network Requirements

- Stable LAN connection
- Access to 10.0.50.203:8000
- Access to 172.31.0.71:554 (CCTV)
- No proxy or firewall blocking

---

**Document Version**: 1.0
**Last Updated**: 2026-01-31
**System Version**: 2.0.0
**Location**: Aneka Walk, Shah Alam
