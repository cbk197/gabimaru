# Solo Checkin Bot

## Prerequisites
- Login to `amisapp.misa.vn` on Firefox.
- Create a Telegram bot and add its token in a `.env` file (copy `.env_tmp` to `.env` and fill it in).

## Installation

### Automatic Installation
Run the setup script to install the bot automatically:
```bash
./setup.sh
```

### Manual Installation
If you prefer to install manually, follow these steps:

**1. Clone & Enter Directory**
```bash
cd solo_checkin_bot
```

**2. Setup Virtual Environment**
```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Install Dependencies**
```bash
pip install -r requirements.txt
playwright install chromium
```

**4. Configure Background Daemon**
*Note: Change the paths in `com.checkinbot.telegrambot.plist` to be compatible with your Mac before running these commands.*
```bash
cp com.checkinbot.telegrambot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.checkinbot.telegrambot.plist
launchctl start com.checkinbot.telegrambot
```

**5. Check if running**
```bash
launchctl list | grep tele
```

## Maintenance & Troubleshooting

### Reloading the Bot
If you update the code, unload and reload the bot using `launchctl`:
```bash
launchctl unload ~/Library/LaunchAgents/com.checkinbot.telegrambot.plist
launchctl load ~/Library/LaunchAgents/com.checkinbot.telegrambot.plist
launchctl start com.checkinbot.telegrambot
launchctl list | grep tele
```

### Optional: Python 3.12+ Issues
Run these commands ONLY if you encounter package errors on Python 3.12+:
```bash
pip install "urllib3<2"
pip install "setuptools<70.0.0"
curl -sL "https://raw.githubusercontent.com/python/cpython/3.12/Lib/imghdr.py" -o venv/lib/$(ls venv/lib | grep python | head -n 1)/site-packages/imghdr.py
```