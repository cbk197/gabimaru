

```bash
#### ****need to do first**** fill your telebot token in checkin_misa_bot.py at line 631 and login amisapp.misa.vn on firefox 
### run file setup.sh to install bot
./setup.sh

#### or manual install follow steps below
# 1. Clone & Enter Directory
cd solo_checkin_bot

# 2. Setup Virtual Environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Dependencies
pip install -r requirements.txt
playwright install chromium

# 4. Configure Background Daemon
### change path in file com.checkinbot.telegrambot.plist for compatiable with your mac
cp com.checkinbot.telegrambot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.checkinbot.telegrambot.plist
launchctl start com.checkin_misa_bot.telebot

# 5. Check if running
launchctl list | grep tele

# --- OPTIONAL: Run these IF you encounter package errors on Python 3.12+ ---
# pip install "urllib3<2"
# pip install "setuptools<70.0.0"
# curl -sL "https://raw.githubusercontent.com/python/cpython/3.12/Lib/imghdr.py" -o venv/lib/$(ls venv/lib | grep python | head -n 1)/site-packages/imghdr.py

### unload and reload bot by launchctl if update code.
launchctl unload ~/Library/LaunchAgents/com.checkinbot.telegrambot.plist
launchctl load ~/Library/LaunchAgents/com.checkinbot.telegrambot.plist
launchctl start com.checkin_misa_bot.telebot
launchctl list | grep tele