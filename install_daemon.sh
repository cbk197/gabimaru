#!/bin/bash
# Installs the bot as a system LaunchDaemon so it starts at boot, without anyone logging in.
# Run as your normal user (not with sudo): ./install_daemon.sh
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
RUN_USER="$(id -un)"
LABEL="com.checkinbot.telegrambot"
AGENT_PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DAEMON_PLIST="/Library/LaunchDaemons/$LABEL.plist"
TMP_PLIST="$(mktemp)"

if [ "$EUID" -eq 0 ]; then
    echo "Run this as your normal user, not with sudo. It will ask for your password when needed."
    exit 1
fi

for f in "$DIR/venv/bin/python3" "$DIR/.env" "$DIR/checkin_misa_bot.py"; do
    if [ ! -e "$f" ]; then
        echo "Missing $f - run ./setup.sh and create .env first."
        exit 1
    fi
done

echo "[*] Removing old login-only LaunchAgent (if any)..."
launchctl unload "$AGENT_PLIST" 2>/dev/null || true
rm -f "$AGENT_PLIST"

echo "[*] Writing daemon plist (runs as $RUN_USER)..."
cat <<EOF > "$TMP_PLIST"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>UserName</key>
    <string>$RUN_USER</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-s</string>
        <string>$DIR/venv/bin/python3</string>
        <string>$DIR/checkin_misa_bot.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR/</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>$HOME</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/dev/null</string>
    <key>StandardErrorPath</key>
    <string>$DIR/error.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
</dict>
</plist>
EOF
plutil -lint "$TMP_PLIST" >/dev/null

echo "[*] Installing to $DAEMON_PLIST (needs your password)..."
sudo launchctl bootout "system/$LABEL" 2>/dev/null || true
sudo cp "$TMP_PLIST" "$DAEMON_PLIST"
sudo chown root:wheel "$DAEMON_PLIST"
sudo chmod 644 "$DAEMON_PLIST"
rm -f "$TMP_PLIST"

echo "[*] Starting daemon..."
sudo launchctl bootstrap system "$DAEMON_PLIST"
sleep 5

if sudo launchctl print "system/$LABEL" | grep -q "state = running"; then
    echo "=========================================="
    echo "✅ Bot is running and will start at every boot."
    echo "   Restart bot:  sudo launchctl kickstart -k system/$LABEL"
    echo "   Errors:       tail -f $DIR/error.log"
    echo "   Planned reboot (skips FileVault unlock screen): sudo fdesetup authrestart"
    echo "=========================================="
else
    echo "❌ Bot is not running. Last errors:"
    tail -20 "$DIR/error.log"
    exit 1
fi
