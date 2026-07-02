import logging
import json
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
import pytz
import random
import math
import threading
import platform
from datetime import datetime, time, timedelta

from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

import requests
import urllib3
from playwright.sync_api import sync_playwright

from get_misa_cookie import get_firefox_cookies

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)
cookies_lock = threading.RLock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_PATH = os.path.join(BASE_DIR, 'cookies.json')
STATUS_PATH = os.path.join(BASE_DIR, 'checkin_status.json')
ACTIVE_USERS_PATH = os.path.join(BASE_DIR, 'active_users.json')

# --- Utility Functions ---

def get_user_id_from_misa():
    """Dynamically fetches MISA User ID from API if missing, and caches it locally."""
    if os.path.exists(STATUS_PATH):
        try:
            with open(STATUS_PATH, 'r', encoding='utf-8') as f:
                status_data = json.load(f)
                if isinstance(status_data, dict) and status_data.get("misa_userid"):
                    return status_data["misa_userid"]
        except json.JSONDecodeError:
            pass

    if not os.path.exists(COOKIES_PATH):
        return None

    with open(COOKIES_PATH, 'r', encoding='utf-8') as f:
        try:
            cookies_list = json.load(f)
        except json.JSONDecodeError:
            return None

    cookie_dict = {}
    for c in cookies_list:
        if isinstance(c, dict) and 'name' in c and 'value' in c:
            cookie_dict[c['name']] = c['value']

    x_sessionid = cookie_dict.get('x-sessionid')
    x_tenantid = cookie_dict.get('x-tenantid')
    x_tenantsource = cookie_dict.get('x-tenantsource')
    x_culture = cookie_dict.get('x-culture')
    x_deviceid = cookie_dict.get('x-deviceid')

    url = "https://amisapp.misa.vn/APIS/EmployeesContactAPI/api/Employee/user-info"
    cookie_header_string = f"x-sessionid={x_sessionid}; x-tenantid={x_tenantid}; x-tenantsource={x_tenantsource}"

    headers = {
        'Host': 'amisapp.misa.vn',
        'DeviceType': 'Smartphone',
        'DeviceName': 'iPhone 11 Pro Max',
        'AppCode': 'System',
        'x-culture': x_culture,
        'x-sessionid': x_sessionid,
        'AppVersion': '97.4',
        'Accept': '*/*',
        'DeviceOS': 'IOS',
        'Accept-Language': 'en-VN;q=1.0, vi-VN;q=0.9',
        'Cookies': cookie_header_string,
        'DeviceId': x_deviceid,
        'User-Agent': 'MISA AMIS/97.4 (vn.com.misa.amis; build:2; iOS 26.2.0) Alamofire/5.11.1',
        'Connection': 'keep-alive',
        'OSVersion': '26.2',
        'Content-Type': 'application/json; charset=utf-8'
    }

    req_cookies = {
        'x-sessionid': x_sessionid,
        'x-tenantid': x_tenantid,
        'x-tenantsource': x_tenantsource
    }

    try:
        response = requests.get(url, headers=headers, cookies=req_cookies, verify=False)
        if response.status_code == 200:
            data = response.json()
            if data.get("Success"):
                user_info = data.get("Data", {})
                user_id = user_info.get("UserID") or user_info.get("ConvertID")
                if user_id:
                    status_data = {
                        "morning_checkin": False,
                        "evening_checkin": False,
                        "last_checkin_time": ""
                    }
                    if os.path.exists(STATUS_PATH):
                        try:
                            with open(STATUS_PATH, 'r', encoding='utf-8') as f:
                                loaded = json.load(f)
                                if isinstance(loaded, dict):
                                    status_data.update(loaded)
                        except json.JSONDecodeError:
                            pass
                    status_data["misa_userid"] = user_id
                    with open(STATUS_PATH, 'w', encoding='utf-8') as f:
                        json.dump(status_data, f, indent=4)
                    return user_id
    except Exception as e:
        logger.error(f"User API request failed: {e}")
        
    return None

def generate_random_point(lat, lng, radius):
    """Generates a random point within a radius around given coordinates."""
    x0 = lat
    y0 = lng
    rd = radius / 111300  # Convert radius from meters to degrees
    u = random.random()
    v = random.random()
    w = rd * math.sqrt(u)
    t = 2 * math.pi * v
    x = w * math.cos(t)
    y = w * math.sin(t)
    xp = x / math.cos(math.radians(y0))
    return xp + x0, y + y0

def load_cookies_dict():
    """Loads cookies from cookies.json and returns a dict of {name: value}."""
    user_cookies_list = []
    
    with cookies_lock:
        if os.path.exists(COOKIES_PATH):
            with open(COOKIES_PATH, 'r', encoding='utf-8') as f:
                try:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        user_cookies_list = next(iter(loaded.values())) if loaded else []
                    elif isinstance(loaded, list):
                        user_cookies_list = loaded
                except json.JSONDecodeError:
                    pass

    # Fallback: pull directly from Firefox if no cookies found
    if not user_cookies_list:
        try:
            user_cookies_list = get_firefox_cookies("amisapp.misa.vn")
        except Exception as e:
            logger.error(f"Failed to get cookies from Firefox: {e}")

    if not user_cookies_list:
        return None

    return {c['name']: c['value'] for c in user_cookies_list if isinstance(c, dict) and 'name' in c and 'value' in c}


def perform_misa_checkin(lat, lng, gps_name="Onsite Viettel"):
    """Performs the MISA checkin via direct HTTP request using stored cookies (no browser needed)."""
    cookie_dict = load_cookies_dict()
    if not cookie_dict:
        return False, "No cookies found. Use /refresh or log in to MISA on Firefox first."

    misa_userid = get_user_id_from_misa()
    if not misa_userid:
        return False, "Error: Could not determine MISA user ID. Try /refresh first."

    x_sessionid = cookie_dict.get('x-sessionid', '')
    x_culture = cookie_dict.get('x-culture', 'vi')
    x_deviceid = cookie_dict.get('x-deviceid', '')
    x_tenantid = cookie_dict.get('x-tenantid', '')
    x_tenantsource = cookie_dict.get('x-tenantsource', 'MISAStore')

    if not x_sessionid:
        return False, "Session cookie expired or missing. Use /refresh to renew."

    url = f'https://amisapp.misa.vn/APIS/TimekeeperAPI/api/TimeKeepingRemote/timekeeping-now-token?userId={misa_userid}'

    headers = {
        'Host': 'amisapp.misa.vn',
        'DeviceType': 'Smartphone',
        'AppCode': 'System',
        'DeviceName': 'iPhone 11 Pro Max',
        'x-culture': x_culture,
        'x-sessionid': x_sessionid,
        'AppVersion': '97.6',
        'Accept': '*/*',
        'DeviceOS': 'IOS',
        'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8',
        'Cookies': f'x-sessionid={x_sessionid}',
        'DeviceId': x_deviceid,
        'User-Agent': 'MISA AMIS/97.6 (vn.com.misa.amis; build:1; iOS 26.3.0) Alamofire/5.11.2',
        'Connection': 'keep-alive',
        'OSVersion': '26.2',
        'Content-Type': 'application/json'
    }

    req_cookies = {
        'x-sessionid': x_sessionid,
        'x-tenantid': x_tenantid,
        'x-tenantsource': x_tenantsource
    }

    validate_url = 'https://amisapp.misa.vn/APIS/TimekeeperAPI/api/TimeKeepingRemote/validate-working-shift'
    challenge_token = ""
    try:
        validate_res = requests.get(validate_url, headers=headers, cookies=req_cookies, verify=False)
        if validate_res.status_code == 200:
            val_data = validate_res.json()
            if val_data.get("Success"):
                challenge_token = val_data.get("Data", {}).get("ChallengeToken", "")
    except Exception as e:
        logger.warning(f"Failed to get challenge token: {e}")
    misa_key = "MISA-AMIS-TK-PROD-2025-x9VbN4mK8tL2wPc7YqH5RgF3JzS6aWdE"
    import base64
    responseToken = base64.b64encode(f"{challenge_token}_{misa_key}".encode()).decode()

    payload = {
        "IsRequireFaceIdentifi": False,
        "Longitude": lng,
        "Latitude": lat,
        "IsGPSFixed": True,
        "ResponseToken": responseToken,
        "IsWorkRemote": False,
        "TimeZone": "(UTC +07:00) Asia/Ho_Chi_Minh",
        "WorkingShiftID": 14408,
        "GPSName": gps_name,
        "IsMobile": True,
        "ApprovalName": "",
        "ApprovalToID": 0,
        "IsManagerConfirmTimekeeping": False,
        "ChallengeToken": challenge_token,
        "Documents": "[]",
        "WorkingShiftName": "Ca hành chính",
        "WorkingShiftCode": "HC"
    }

    try:
        response = requests.post(url, headers=headers, cookies=req_cookies, json=payload, verify=False)

        if response.status_code == 200 and response.json().get("Success") == True:
            # Save any new cookies returned by the API
            _update_cookies_from_response(response)
            return True, "success"
        else:
            return False, f"fail - Status Code: {response.status_code}, Response: {response.text}"
    except Exception as e:
        return False, f"fail - Exception occurred: {e}"


def _update_cookies_from_response(response):
    """Merges any Set-Cookie values from an API response back into cookies.json."""
    new_cookies = {}
    for r_cookie in response.cookies:
        new_cookies[r_cookie.name] = {
            "name": r_cookie.name,
            "value": r_cookie.value,
            "host": r_cookie.domain if r_cookie.domain else "amisapp.misa.vn",
            "path": r_cookie.path if r_cookie.path else "/"
        }

    if not new_cookies:
        return

    with cookies_lock:
        existing = []
        if os.path.exists(COOKIES_PATH):
            with open(COOKIES_PATH, 'r', encoding='utf-8') as f:
                try:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        existing = loaded
                except json.JSONDecodeError:
                    pass

        # Merge: overwrite existing cookies by name, append new ones
        existing_by_name = {c['name']: c for c in existing if isinstance(c, dict) and 'name' in c}
        existing_by_name.update(new_cookies)
        merged = list(existing_by_name.values())

        with open(COOKIES_PATH, 'w', encoding='utf-8') as f:
            json.dump(merged, f, indent=4)


# --- Bot Logic ---

def echo(update: Update, context: CallbackContext) -> None:
    """Echoes the user's message."""
    context.bot.send_message(
        update.message.chat_id,
        update.message.text,
        entities=update.message.entities
    )

def update_checkin_status(context):
    """Updates the check-in status in the JSON file."""
    vn_timezone = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(vn_timezone).time()
    morning_start = time(6, 0, tzinfo=vn_timezone)
    morning_end = time(9, 0, tzinfo=vn_timezone)
    evening_start = time(17, 0, tzinfo=vn_timezone)
    checkin_type = None

    if morning_start <= now <= morning_end:
        checkin_type = "morning"
    elif evening_start <= now:
        checkin_type = "evening"

    
    with open(STATUS_PATH, 'r+') as f:
        try:
            checkin_data = json.load(f)
        except json.JSONDecodeError:
            checkin_data = {}
            
        if "morning_checkin" not in checkin_data:
            checkin_data["morning_checkin"] = False
            checkin_data["evening_checkin"] = False
            checkin_data["last_checkin_time"] = str(datetime.now(vn_timezone))
                            
        if checkin_type == "morning":
            checkin_data["morning_checkin"] = True
        elif checkin_type == "evening":
            checkin_data["evening_checkin"] = True
        checkin_data["last_checkin_time"] = str(datetime.now(vn_timezone))
        f.seek(0)
        json.dump(checkin_data, f)
        f.truncate()

def handle_checkin(update: Update, context: CallbackContext, latitude, longitude, gps_name="Onsite Viettel"):
    """Handles immediate check-in requests."""
    success, message = perform_misa_checkin(latitude, longitude, gps_name)
    if success:
        update_checkin_status(context)
        context.bot.send_message(update.message.chat_id, f"MISA Check-in Success: {message}")
    else:
        context.bot.send_message(update.message.chat_id, f"MISA Check-in Failed: {message}")

def perform_checkin_callback(context: CallbackContext):
    """Callback function for scheduled check-ins."""
    job_context = context.job.context
    chat_id = job_context['chat_id']
    lat = job_context['lat']
    lng = job_context['lng']
    gps_name = job_context.get('gps_name', 'Onsite Viettel')
    success, message = perform_misa_checkin(lat, lng, gps_name)
    if success:
        update_checkin_status(context)
        context.bot.send_message(chat_id, f"Scheduled MISA check-in success! {message}")
    else:
        context.bot.send_message(chat_id, f"Scheduled MISA check-in failed: {message}")

def schedule_checkin(update: Update, context: CallbackContext, hour: int, minute: int, center_lat=21.016835297342254, center_lng=105.78426152398515, gps_name="Onsite Viettel"):
    """Schedules a check-in at a specified time."""
    chat_id = update.effective_chat.id

    lat, lng = generate_random_point(center_lat, center_lng, 50)

    if not (0 <= hour < 24 and 0 <= minute < 60):
        update.message.reply_text("Invalid time. Hour must be 0-23 and minute must be 0-59.")
        return

    vn_timezone = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(vn_timezone)
    current_hour = now.hour
    current_minute = now.minute

    if hour < current_hour or (hour == current_hour and minute < current_minute):
        update.message.reply_text("The specified time has already passed today. Please choose a future time.")
        return

    scheduled_time = time(hour, minute, tzinfo=vn_timezone)
    scheduled_datetime = datetime.combine(now.date(), scheduled_time, tzinfo=vn_timezone)
    time_difference = (scheduled_datetime - now).total_seconds()
    
    # Matches original bot implementation of a 7 minute offset
    context.job_queue.run_once(
        perform_checkin_callback,
        when=time_difference + 7*60,
        context={'chat_id': chat_id, 'lat': lat, 'lng': lng, 'gps_name': gps_name}
    )
    update.message.reply_text(f"MISA check-in scheduled for {scheduled_datetime.strftime('%Y-%m-%d %H:%M:%S')} (Vietnam time).")

def checkin_viettel(update: Update, context: CallbackContext) -> None:
    """Handles Viettel check-in commands using MISA login flow."""
    if len(context.args) == 0:
        lat, lng = generate_random_point(21.016835297342254, 105.78426152398515, 50)
        handle_checkin(update, context, lat, lng)
    elif len(context.args) == 1:
        try:
            hour = int(context.args[0])
            if 0 <= hour < 24:
                schedule_checkin(update, context, hour, 0)
            else:
                update.message.reply_text("Hour must be between 0 and 23.")
        except ValueError:
            update.message.reply_text("Invalid hour. Please use /viettel <hour>, e.g., /viettel 18")
    elif len(context.args) == 2:
        try:
            hour = int(context.args[0])
            minute = int(context.args[1])
            if 0 <= hour < 24 and 0 <= minute < 60:
                schedule_checkin(update, context, hour, minute)
            else:
                update.message.reply_text("Invalid time. Hour must be 0-23 and minute must be 0-59.")
        except ValueError:
            update.message.reply_text("Invalid time format. Please use /viettel <hour> <minute>, e.g., /viettel 18 30")
    else:
        update.message.reply_text("Too many arguments. Use /viettel, /viettel <hour>, or /viettel <hour> <minute>.")

def checkin_mobi(update: Update, context: CallbackContext) -> None:
    """Handles Mobifone check-in commands using MISA login flow."""
    MOBI_CENTER_LAT = 21.019731447886304
    MOBI_CENTER_LNG = 105.78436007613178
    MOBI_GPS_NAME = "Onsite Mobifone"

    if len(context.args) == 0:
        lat, lng = generate_random_point(MOBI_CENTER_LAT, MOBI_CENTER_LNG, 50)
        handle_checkin(update, context, lat, lng, MOBI_GPS_NAME)
    elif len(context.args) == 1:
        try:
            hour = int(context.args[0])
            if 0 <= hour < 24:
                schedule_checkin(update, context, hour, 0, MOBI_CENTER_LAT, MOBI_CENTER_LNG, MOBI_GPS_NAME)
            else:
                update.message.reply_text("Hour must be between 0 and 23.")
        except ValueError:
            update.message.reply_text("Invalid hour. Please use /mobi <hour>, e.g., /mobi 18")
    elif len(context.args) == 2:
        try:
            hour = int(context.args[0])
            minute = int(context.args[1])
            if 0 <= hour < 24 and 0 <= minute < 60:
                schedule_checkin(update, context, hour, minute, MOBI_CENTER_LAT, MOBI_CENTER_LNG, MOBI_GPS_NAME)
            else:
                update.message.reply_text("Invalid time. Hour must be 0-23 and minute must be 0-59.")
        except ValueError:
            update.message.reply_text("Invalid time format. Please use /mobi <hour> <minute>, e.g., /mobi 18 30")
    else:
        update.message.reply_text("Too many arguments. Use /mobi, /mobi <hour>, or /mobi <hour> <minute>.")

def checkin_vnpt(update: Update, context: CallbackContext) -> None:
    """Handles VNPT check-in commands using MISA login flow."""
    VNPT_CENTER_LAT = 21.01893485945844
    VNPT_CENTER_LNG = 105.80970278698703
    VNPT_GPS_NAME = "Onsite VNPT"

    if len(context.args) == 0:
        lat, lng = generate_random_point(VNPT_CENTER_LAT, VNPT_CENTER_LNG, 50)
        handle_checkin(update, context, lat, lng, VNPT_GPS_NAME)
    elif len(context.args) == 1:
        try:
            hour = int(context.args[0])
            if 0 <= hour < 24:
                schedule_checkin(update, context, hour, 0, VNPT_CENTER_LAT, VNPT_CENTER_LNG, VNPT_GPS_NAME)
            else:
                update.message.reply_text("Hour must be between 0 and 23.")
        except ValueError:
            update.message.reply_text("Invalid hour. Please use /vnpt <hour>, e.g., /vnpt 18")
    elif len(context.args) == 2:
        try:
            hour = int(context.args[0])
            minute = int(context.args[1])
            if 0 <= hour < 24 and 0 <= minute < 60:
                schedule_checkin(update, context, hour, minute, VNPT_CENTER_LAT, VNPT_CENTER_LNG, VNPT_GPS_NAME)
            else:
                update.message.reply_text("Invalid time. Hour must be 0-23 and minute must be 0-59.")
        except ValueError:
            update.message.reply_text("Invalid time format. Please use /vnpt <hour> <minute>, e.g., /vnpt 18 30")
    else:
        update.message.reply_text("Too many arguments. Use /vnpt, /vnpt <hour>, or /vnpt <hour> <minute>.")

def send_checkin_reminder(context: CallbackContext):
    """Sends reminders for morning and evening check-ins."""
    vn_timezone = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.now(vn_timezone).time()
    today = datetime.now(vn_timezone).weekday()
    if today == 5 or today == 6:  # Skip weekends
        return
    # Use naive times to match `now` (datetime.time() drops tzinfo); the hours/
    # minutes are already in VN time so no conversion is needed.
    morning_check_time = time(8, 50)
    evening_check_time = time(18, 10)

    # Default to "not checked in" when the status file is missing or unreadable,
    # so reminders still fire on a fresh day instead of being silently skipped.
    checkin_data = {}
    if os.path.exists(STATUS_PATH):
        with open(STATUS_PATH, 'r') as f:
            try:
                checkin_data = json.load(f)
            except json.JSONDecodeError:
                checkin_data = {}

    morning_checked_in = checkin_data.get("morning_checkin", False)
    evening_checked_in = checkin_data.get("evening_checkin", False)

    if 'active_users' in context.bot_data:
        for user_id in context.bot_data['active_users']:
            try:
                user_id_int = int(user_id)
                if now >= morning_check_time and not morning_checked_in:
                    context.bot.send_message(user_id_int, "Reminder: Please do morning check-in.")
                if now >= evening_check_time and not evening_checked_in:
                    context.bot.send_message(user_id_int, "Reminder: Please do evening check-in.")
            except ValueError:
                pass

def load_active_users():
    """Loads the persisted set of active users from disk."""
    if os.path.exists(ACTIVE_USERS_PATH):
        with open(ACTIVE_USERS_PATH, 'r') as f:
            try:
                return set(json.load(f))
            except json.JSONDecodeError:
                pass
    return set()

def save_active_users(active_users):
    """Persists the set of active users to disk."""
    with open(ACTIVE_USERS_PATH, 'w') as f:
        json.dump(list(active_users), f)

def track_active_user(update: Update, context: CallbackContext):
    """Tracks active users."""
    if update.effective_user is None:
        return
    user_id = str(update.effective_user.id)
    if 'active_users' not in context.bot_data:
        context.bot_data['active_users'] = set()
    if user_id not in context.bot_data['active_users']:
        context.bot_data['active_users'].add(user_id)
        save_active_users(context.bot_data['active_users'])

def reset_checkin_status():
    """Resets check-in status daily."""
    if os.path.exists(STATUS_PATH):
        with open(STATUS_PATH, 'r+') as f:
            try:
                checkin_data = json.load(f)
            except json.JSONDecodeError:
                checkin_data = {}
            if "morning_checkin" in checkin_data:
                checkin_data["morning_checkin"] = False
                checkin_data["evening_checkin"] = False
            f.seek(0)
            json.dump(checkin_data, f)
            f.truncate()

def perform_cookie_refresh(context_or_none=None):
    """Refreshes cookies by opening Playwright browser, loading existing cookies,
    letting the site refresh the session, and exporting updated cookies.
    Returns (success: bool, message: str).
    """
    user_cookies_list = []
    
    with cookies_lock:
        if os.path.exists(COOKIES_PATH):
            with open(COOKIES_PATH, 'r', encoding='utf-8') as f:
                try:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        user_cookies_list = next(iter(loaded.values())) if loaded else []
                    elif isinstance(loaded, list):
                        user_cookies_list = loaded
                except json.JSONDecodeError:
                    pass
                    
    # Single user fallback: pull right from firefox
    if not user_cookies_list:
        try:
            user_cookies_list = get_firefox_cookies("amisapp.misa.vn")
        except Exception as e:
            logger.error(f"Failed to auto-refresh because get_firefox_cookies failed: {e}")
            
    if not user_cookies_list:
        return False, "No cookies found. Please log in to MISA on Firefox first."
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pw_context = browser.new_context(ignore_https_errors=True)
            
            valid_pw_cookies = []
            for c in user_cookies_list:
                pc = {
                    "name": c.get("name"),
                    "value": c.get("value"),
                    "domain": c.get("host") or c.get("domain", "amisapp.misa.vn"),
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", True),
                    "httpOnly": c.get("httpOnly", False)
                }
                expiry = c.get('expiry') or c.get('expires')
                if expiry is not None:
                    try:
                        exp_val = float(expiry)
                        if exp_val > 1e11:
                            exp_val = exp_val / 1000.0
                        pc['expires'] = exp_val
                    except ValueError:
                        pass
                valid_pw_cookies.append(pc)
                
            if valid_pw_cookies:
                pw_context.add_cookies(valid_pw_cookies)
            
            page = pw_context.new_page()
            try:
                page.goto('https://amisapp.misa.vn', wait_until='networkidle', timeout=30000)
            except Exception:
                pass
                
            # Wait 5 seconds to ensure dynamic tracking cookies propagate fully 
            page.wait_for_timeout(5000)
            
            final_pw_cookies = pw_context.cookies()
            final_cookies_list = []
            for c in final_pw_cookies:
                fc = {
                    "name": c["name"],
                    "value": c["value"],
                    "host": c.get("domain", "amisapp.misa.vn"),
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", False),
                    "httpOnly": c.get("httpOnly", False)
                }
                if "expires" in c and c["expires"] > 0:
                    fc["expiry"] = int(float(c["expires"]) * 1000)
                final_cookies_list.append(fc)
                         
            with cookies_lock:
                with open(COOKIES_PATH, 'w', encoding='utf-8') as f:
                    json.dump(final_cookies_list, f, indent=4)
                    
            browser.close()
            logger.info("Successfully refreshed cookies via Playwright")
            return True, f"Cookies refreshed successfully ({len(final_cookies_list)} cookies saved)."
            
    except Exception as e:
        logger.error(f"Failed to refresh cookies: {e}")
        return False, f"Cookie refresh failed: {e}"


def perform_firefox_reload():
    """Reads cookies straight from the Firefox profile and overwrites cookies.json.
    Returns (success: bool, message: str).
    """
    try:
        firefox_cookies = get_firefox_cookies("amisapp.misa.vn")
    except Exception as e:
        logger.error(f"Failed to read cookies from Firefox: {e}")
        return False, f"Failed to read cookies from Firefox: {e}"

    if not firefox_cookies:
        return False, "No MISA cookies found in Firefox. Please log in to amisapp.misa.vn on Firefox first."

    with cookies_lock:
        with open(COOKIES_PATH, 'w', encoding='utf-8') as f:
            json.dump(firefox_cookies, f, indent=4)

    logger.info(f"Reloaded {len(firefox_cookies)} cookies from Firefox")
    return True, f"Reloaded {len(firefox_cookies)} cookies from Firefox (cookies.json overwritten)."


def perform_cookie_refresh_scheduled(context: CallbackContext):
    """Wrapper for scheduled cookie refresh job (adapts to job_queue signature)."""
    success, message = perform_cookie_refresh()
    if not success:
        logger.error(f"Scheduled cookie refresh failed: {message}")

def schedule_random_cookie_refresh(context: CallbackContext):
    """Triggers a random delay between 0 and 60 minutes for cookie refresh."""
    random_delay = random.randint(0, 3600)
    context.job_queue.run_once(
        perform_cookie_refresh_scheduled,
        when=random_delay
    )


def refresh_command(update: Update, context: CallbackContext) -> None:
    """Handles /refresh command - opens browser to refresh cookies."""
    update.message.reply_text("🔄 Refreshing cookies via browser... This may take ~30 seconds.")
    try:
        success, message = perform_cookie_refresh()
        if success:
            update.message.reply_text(f"✅ {message}")
        else:
            update.message.reply_text(f"❌ {message}")
    except Exception as e:
        update.message.reply_text(f"❌ Cookie refresh error: {e}")

def reload_firefox_command(update: Update, context: CallbackContext) -> None:
    """Handles /reload_firefox command - reloads cookies from Firefox, overwriting cookies.json."""
    update.message.reply_text("🦊 Reloading cookies from Firefox...")
    try:
        success, message = perform_firefox_reload()
        if success:
            update.message.reply_text(f"✅ {message}")
        else:
            update.message.reply_text(f"❌ {message}")
    except Exception as e:
        update.message.reply_text(f"❌ Firefox reload error: {e}")

def help_command(update: Update, context: CallbackContext) -> None:
    """Displays help information."""
    update.message.reply_text(
        "Welcome to the MISA Check-in Bot!\n\n"
        "Here's how to use the bot:\n"
        "1. Make sure you are logged into amisapp.misa.vn on Firefox.\n"
        "2. Check in at Viettel (MISA System):\n"
        "   - `/viettel` - Immediate check-in (direct HTTP, no browser).\n"
        "   - `/viettel <hour>` - Schedule check-in at <hour>:00.\n"
        "   - `/viettel <hour> <minute>` - Schedule check-in at <hour>:<minute>.\n\n"
        "3. Check in at Mobifone:\n"
        "   - `/mobi` - Immediate check-in at Mobifone.\n"
        "   - `/mobi <hour>` - Schedule check-in at <hour>:00.\n"
        "   - `/mobi <hour> <minute>` - Schedule check-in at <hour>:<minute>.\n\n"
        "4. Check in at VNPT:\n"
        "   - `/vnpt` - Immediate check-in at VNPT.\n"
        "   - `/vnpt <hour>` - Schedule check-in at <hour>:00.\n"
        "   - `/vnpt <hour> <minute>` - Schedule check-in at <hour>:<minute>.\n\n"
        "5. Cookie Management:\n"
        "   - `/refresh` - Manually refresh cookies via browser.\n"
        "   - `/reload_firefox` - Reload cookies directly from Firefox (overwrites current).\n"
        "   - Cookies auto-refresh daily between 7:00-8:00 AM.\n\n"
        "6. Reminders are sent at 8:50 and 18:10.\n\n"
        "Questions? Feel free to ask!",
        parse_mode=ParseMode.MARKDOWN
    )

def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message."""
    update.message.reply_text(
        "Welcome to the MISA Check-in Bot!\n"
        "Cookies are automatically fetched from your Firefox session.\n"
        "Use `/viettel` to check in via MISA system. "
        "For more information, use /help.",
        parse_mode=ParseMode.MARKDOWN
    )

def main() -> None:
    """Starts the bot."""
    updater = Updater(os.environ["TELEGRAM_BOT_TOKEN"])
    dispatcher = updater.dispatcher

    # Restore active users so reminders still fire after a restart, even before
    # any user sends a new message.
    dispatcher.bot_data['active_users'] = load_active_users()

    # Track users in a separate handler group: within one group only the first
    # matching handler runs, so a same-group tracker never sees commands — the
    # CommandHandlers consume them and reminders end up with no recipients.
    dispatcher.add_handler(MessageHandler(Filters.all, track_active_user), group=-1)

    # Command handlers
    dispatcher.add_handler(CommandHandler("viettel", checkin_viettel))
    dispatcher.add_handler(CommandHandler("mobi", checkin_mobi))
    dispatcher.add_handler(CommandHandler("vnpt", checkin_vnpt))
    dispatcher.add_handler(CommandHandler("refresh", refresh_command))
    dispatcher.add_handler(CommandHandler("reload_firefox", reload_firefox_command))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(~Filters.command, echo))

    # Job queue scheduling
    vn_timezone = pytz.timezone('Asia/Ho_Chi_Minh')
    updater.job_queue.run_daily(schedule_random_cookie_refresh, time=time(7, 0, tzinfo=vn_timezone))
    updater.job_queue.run_daily(send_checkin_reminder, time=time(8, 50, tzinfo=vn_timezone))
    updater.job_queue.run_daily(send_checkin_reminder, time=time(18, 10, tzinfo=vn_timezone))
    updater.job_queue.run_daily(lambda context: reset_checkin_status(), time=time(0, 0, tzinfo=vn_timezone))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
