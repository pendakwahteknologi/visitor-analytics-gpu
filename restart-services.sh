#!/bin/bash
# Restart all visitor-stat services at midnight
# Created: 2026-02-06

LOG_FILE="/home/adilhidayat/visitor-stat/logs/restart.log"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting scheduled restart..." >> "$LOG_FILE"

# Restart visitor-stat service
sudo systemctl restart visitor-stat
sleep 5

# Check if service is running
if systemctl is-active --quiet visitor-stat; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - visitor-stat restarted successfully" >> "$LOG_FILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: visitor-stat failed to restart" >> "$LOG_FILE"
fi

# Clean up old log entries (keep last 1000 lines)
tail -1000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Scheduled restart complete" >> "$LOG_FILE"
