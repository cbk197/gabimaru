#!/bin/bash
set -e

echo "=========================================="
echo "    MISA Check-in Bot Setup Script        "
echo "=========================================="

# 1. Base paths
# Get the absolute path of the directory containing this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "[*] Project directory: $DIR"

# 2. Setup python virtual environment
echo "[*] Setting up virtual environment..."
if [ ! -d "$DIR/venv" ]; then
    python3 -m venv "$DIR/venv"
    echo "    Created new venv."
else
    echo "    venv already exists."
fi

# 3. Install packages
echo "[*] Installing dependencies..."
"$DIR/venv/bin/pip" install --upgrade pip -q
"$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" -q

echo "[*] Installing Playwright Chromium browser..."
"$DIR/venv/bin/playwright" install chromium

# 4. Read and update the plist file dynamically
PLIST_FILE="$DIR/com.checkinbot.telegrambot.plist"
echo "[*] Updating plist paths in: $PLIST_FILE"

cat <<EOF > "$PLIST_FILE"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.checkinbot.telegrambot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-s</string>
        <string>$DIR/venv/bin/python3</string>
        <string>$DIR/checkin_misa_bot.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$DIR/</string>
    <key>StandardOutPath</key>
    <string>/dev/null</string>
    <key>StandardErrorPath</key>
    <string>/dev/null</string>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# 5. Copy the plist to LaunchAgents
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS_DIR"

TARGET_PLIST="$LAUNCH_AGENTS_DIR/com.checkinbot.telegrambot.plist"
echo "[*] Copying plist to macOS LaunchAgents..."
cp "$PLIST_FILE" "$TARGET_PLIST"

# 6. Load the agent
echo "[*] Unloading any existing bot agent..."
launchctl unload "$TARGET_PLIST" 2>/dev/null || true

echo "[*] Starting the bot agent..."
launchctl load "$TARGET_PLIST"
launchctl start com.checkinbot.telegrambot

echo "=========================================="
echo "✅ Setup Complete!"
echo "The MISA Check-in Bot is now running in the background."
echo "Logs will be written to: $DIR/logfile.log"
echo "You can view the logs anytime by running:"
echo "    tail -f $DIR/logfile.log"
echo "=========================================="
