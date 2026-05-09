"""
╔══════════════════════════════════════════════════╗
║         JARVIS v1.0 — Advanced AI Copilot         ║
║         Built by: Sonu Kumar Sah                ║
╚══════════════════════════════════════════════════╝
pip install SpeechRecognition pyttsx3 requests pyautogui psutil
pip install pygame google-generativeai google-genai pyperclip pillow
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
import os, sys, json, time, math, random, datetime, threading
import subprocess, webbrowser, urllib.parse, re, tempfile, hashlib
import tkinter as tk
from tkinter import font as tkfont, filedialog, simpledialog, colorchooser
import requests, psutil, pyautogui, pyttsx3, pygame
import speech_recognition as sr
try:
    import google.generativeai as genai
except ImportError:
    import google.genai as genai

try:    import pyperclip; HAS_CLIP=True
except: HAS_CLIP=False
try:    import cv2; HAS_CV2=True
except: HAS_CV2=False

# ═══════════════════════════════════════════════════
#  PHONE CONTROL via ADB (Android Debug Bridge)
#  Connect phone via USB with USB Debugging ON
# ═══════════════════════════════════════════════════
ADB_PATH = "********"   # set full path if needed e.g. r"C:\platform-tools\adb.exe"

_phone_monitor_active = False
_incoming_call_number  = ""
_incoming_call_name    = ""
_call_state            = "idle"   # idle / ringing / in_call
_phone_ui_ref          = None     # set after UI builds

def _adb(cmd):
    """Run adb command, return output."""
    try:
        result = subprocess.run(
            f"{ADB_PATH} {cmd}",
            shell=True, capture_output=True, text=True, timeout=8
        )
        return result.stdout.strip()
    except: return ""

def check_adb_connected():
    out = _adb("devices")
    lines = [l for l in out.splitlines() if "device" in l and "List" not in l]
    return len(lines) > 0

def get_call_state():
    """Read current phone call state via adb."""
    out = _adb("shell dumpsys telephony.registry")
    if "mCallState=1" in out or "RINGING" in out: return "ringing"
    if "mCallState=2" in out or "OFFHOOK" in out: return "in_call"
    return "idle"

# ─── PHONE CONTACTS CACHE ─────────────────────────
_contacts_cache = {}   # {number: name}
_contacts_loaded = False

def load_phone_contacts():
    """Pull contacts from Android phone via ADB and cache them."""
    global _contacts_cache, _contacts_loaded
    try:
        # Use content provider to read contacts
        out = _adb("shell content query --uri content://contacts/phones --projection number:display_name")
        for line in out.splitlines():
            row = dict(re.findall(r'(\w+)=(.*?)(?:,\s*\w+=|$)', line))
            num = re.sub(r'[\s\-\(\)]', '', row.get('number',''))
            name = row.get('display_name','').strip()
            if num and name:
                _contacts_cache[num] = name
                # also store without country code
                if num.startswith('+977'): _contacts_cache[num[4:]] = name
                if num.startswith('977'):  _contacts_cache[num[3:]] = name
        _contacts_loaded = True
        return len(_contacts_cache)
    except: return 0

def number_to_name(number):
    """Look up contact name for a phone number."""
    if not _contacts_loaded: load_phone_contacts()
    clean = re.sub(r'[\s\-\(\)]', '', str(number))
    # exact match
    if clean in _contacts_cache: return _contacts_cache[clean]
    # match last 10 digits
    for saved_num, name in _contacts_cache.items():
        if clean[-10:] == saved_num[-10:] and len(clean) >= 8:
            return name
    return None

def get_caller_number():
    """Extract incoming caller number from adb — with contact name lookup."""
    number = "Unknown"
    # Method 1: telephony registry
    out = _adb("shell dumpsys telephony.registry")
    m = re.search(r'mCallIncomingNumber=([+\d]+)', out)
    if m: number = m.group(1)
    # Method 2: phone state from notification
    if number == "Unknown":
        out2 = _adb("shell dumpsys notification --noredact")
        lines = [l for l in out2.splitlines() if 'call' in l.lower() or 'phone' in l.lower()]
        for line in lines:
            m2 = re.search(r'([+\d]{8,15})', line)
            if m2: number = m2.group(1); break
    # Method 3: active call via telecom
    if number == "Unknown":
        out3 = _adb("shell dumpsys telecom")
        m3 = re.search(r'address:[\s]*tel:([+\d]+)', out3)
        if m3: number = m3.group(1)
    return number

def get_caller_info():
    """Returns (number, display_name) for incoming call."""
    number = get_caller_number()
    name   = number_to_name(number)
    display = f"{name} ({number})" if name else number
    return number, display

def receive_call():
    """Answer the incoming call."""
    # Method 1: media button (works on most Android)
    _adb("shell input keyevent KEYCODE_HEADSETHOOK")
    time.sleep(0.5)
    # Method 2: telephony service
    _adb("shell service call ITelephony 5")
    return "Call received!"

def reject_call():
    """Reject/cancel the incoming call."""
    # Method 1: endcall key
    _adb("shell input keyevent KEYCODE_ENDCALL")
    time.sleep(0.3)
    # Method 2: telephony service
    _adb("shell service call ITelephony 6")
    return "Call rejected!"

def end_call():
    """End ongoing call."""
    _adb("shell input keyevent KEYCODE_ENDCALL")
    return "Call ended."

def open_phone_dialpad(number=""):
    """Open phone dialer on Android."""
    if number:
        _adb(f"shell am start -a android.intent.action.CALL -d tel:{number}")
        return f"Calling {number} on your phone!"
    _adb("shell am start -a android.intent.action.DIAL")
    return "Phone dialer opened!"

def send_sms_via_phone(number, message):
    """Open SMS composer on phone."""
    encoded = urllib.parse.quote(message)
    _adb(f'shell am start -a android.intent.action.SENDTO -d "sms:{number}" --es sms_body "{encoded}" --ez exit_on_sent false')
    return f"SMS composer opened for {number}!"

def get_phone_battery():
    out = _adb("shell dumpsys battery")
    m = re.search(r'level: (\d+)', out)
    return f"Phone battery: {m.group(1)}%" if m else "Can't read phone battery."

def get_phone_notifications():
    out = _adb("shell dumpsys notification --noredact")
    apps = re.findall(r'pkg=([a-z.]+)', out)
    unique = list(dict.fromkeys(apps))[:5]
    return f"Notifications from: {', '.join(unique)}" if unique else "No notifications."

def take_phone_screenshot():
    _adb("shell screencap -p /sdcard/jarvis_ss.png")
    desktop = os.path.join(os.path.expanduser("~"), "Desktop", f"phone_ss_{int(time.time())}.png")
    _adb(f"pull /sdcard/jarvis_ss.png {desktop}")
    return f"Phone screenshot saved to Desktop!"

def get_phone_info():
    """Get phone model, Android version, storage."""
    model   = _adb("shell getprop ro.product.model").strip()
    android = _adb("shell getprop ro.build.version.release").strip()
    storage = _adb("shell df /data").splitlines()
    used = free = "?"
    for line in storage:
        parts = line.split()
        if len(parts) >= 4 and parts[0] != "Filesystem":
            try:
                total_kb = int(parts[1]); used_kb = int(parts[2]); free_kb = int(parts[3])
                used = f"{used_kb//1024}MB"; free = f"{free_kb//1024}MB"
            except: pass
    bat_out = _adb("shell dumpsys battery")
    bat_m   = re.search(r'level: (\d+)', bat_out)
    bat     = bat_m.group(1)+"%" if bat_m else "?"
    plug_m  = re.search(r'plugged: (\d+)', bat_out)
    plug    = "Charging" if plug_m and plug_m.group(1)!="0" else "Battery"
    return {"model":model,"android":android,"battery":bat,"status":plug,"used":used,"free":free}

def get_call_log():
    """Get recent call history from phone."""
    out = _adb("shell content query --uri content://call_log/calls --projection number:name:duration:type --sort date+DESC --limit 10")
    calls = []
    for line in out.splitlines():
        row = dict(re.findall(r'(\w+)=(.*?)(?:,\s*\w+=|$)', line))
        num  = row.get('number','?').strip()
        name = row.get('name','').strip() or num
        dur  = int(row.get('duration','0').strip() or 0)
        typ  = row.get('type','0').strip()
        type_map = {"1":"Incoming","2":"Outgoing","3":"Missed","4":"Voicemail","5":"Rejected"}
        calls.append({"number":num,"name":name,"duration":f"{dur//60}m {dur%60}s","type":type_map.get(typ,"Unknown")})
    return calls

def get_sms_log():
    """Get recent SMS messages from phone."""
    out = _adb("shell content query --uri content://sms/inbox --projection address:body:date --sort date+DESC --limit 10")
    msgs = []
    for line in out.splitlines():
        row = dict(re.findall(r'(\w+)=(.*?)(?:,\s*\w+=|$)', line))
        addr = row.get('address','?').strip()
        body = row.get('body','').strip()[:80]
        name = number_to_name(addr) or addr
        if body: msgs.append({"from":name,"number":addr,"message":body})
    return msgs

def get_phone_contacts_list():
    """Return sorted contacts list."""
    if not _contacts_loaded: load_phone_contacts()
    items = sorted(_contacts_cache.items(), key=lambda x: x[1])
    return [{"number":num,"name":name} for num,name in items[:50]]

def phone_open_app(package):
    """Launch an app on phone by package name."""
    pkg_map = {
        "whatsapp":"com.whatsapp","instagram":"com.instagram.android",
        "facebook":"com.facebook.katana","telegram":"org.telegram.messenger",
        "youtube":"com.google.android.youtube","camera":"com.android.camera",
        "gallery":"com.android.gallery3d","settings":"com.android.settings",
        "chrome":"com.android.chrome","maps":"com.google.android.apps.maps",
        "spotify":"com.spotify.music","calculator":"com.android.calculator2",
        "clock":"com.android.deskclock","messages":"com.android.messaging",
        "contacts":"com.android.contacts","files":"com.android.documentsui",
    }
    pkg = pkg_map.get(package.lower(), package)
    _adb(f"shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
    return f"Opening {package} on your phone!"

def set_phone_volume(level, stream="music"):
    """Set phone volume. Level 0-15."""
    # stream: music=3, ringtone=2, notification=5
    stream_map = {"music":3,"ring":2,"ringtone":2,"notification":5,"alarm":4}
    s = stream_map.get(stream.lower(), 3)
    _adb(f"shell media volume --stream {s} --set {level}")
    return f"Phone {stream} volume set to {level}."

def phone_torch(on=True):
    """Toggle phone flashlight."""
    _adb(f"shell cmd flashlight {1 if on else 0}")
    return f"Flashlight {'on' if on else 'off'}!"

def phone_wifi(on=True):
    """Toggle phone WiFi."""
    _adb(f"shell svc wifi {'enable' if on else 'disable'}")
    return f"WiFi {'enabled' if on else 'disabled'} on phone."

def phone_bluetooth(on=True):
    """Toggle phone Bluetooth."""
    _adb(f"shell svc bluetooth {'enable' if on else 'disable'}")
    return f"Bluetooth {'on' if on else 'off'} on phone."

def phone_screen(on=True):
    """Turn phone screen on/off."""
    if on:
        _adb("shell input keyevent KEYCODE_WAKEUP")
        _adb("shell input swipe 540 1600 540 900")
    else:
        _adb("shell input keyevent KEYCODE_SLEEP")
    return f"Phone screen {'on' if on else 'off'}."

def get_phone_location():
    """Get last known GPS location from phone."""
    out = _adb("shell dumpsys location")
    m = re.search(r'Last Known Locations.*?gps: Location\[gps ([-\d.]+),([-\d.]+)', out, re.DOTALL)
    if m:
        lat, lon = m.group(1), m.group(2)
        return f"Phone location: {lat}, {lon} — maps.google.com/?q={lat},{lon}"
    return "Location not available. Make sure GPS is on."

def phone_media_control(action):
    """Control media playback on phone."""
    key_map = {"play":"KEYCODE_MEDIA_PLAY_PAUSE","pause":"KEYCODE_MEDIA_PLAY_PAUSE",
               "next":"KEYCODE_MEDIA_NEXT","previous":"KEYCODE_MEDIA_PREVIOUS",
               "stop":"KEYCODE_MEDIA_STOP","volume_up":"KEYCODE_VOLUME_UP","volume_down":"KEYCODE_VOLUME_DOWN"}
    key = key_map.get(action.lower())
    if key:
        _adb(f"shell input keyevent {key}")
        return f"Phone media: {action}!"
    return "Unknown media command."

def send_text_to_phone(text):
    """Type text on phone (works in any input field)."""
    safe = urllib.parse.quote(text)
    _adb(f"shell input text '{safe}'")
    return f"Typed on phone: {text[:30]}"


def _phone_monitor_loop():
    """Background thread — watches for incoming calls and alerts Jarvis."""
    global _incoming_call_number, _incoming_call_name, _call_state, _phone_monitor_active
    _phone_monitor_active = True
    last_state = "idle"
    alerted    = False

    while _phone_monitor_active:
        try:
            if not check_adb_connected():
                time.sleep(5); continue
            # load contacts once when phone first connects
            global _contacts_loaded
            if not _contacts_loaded:
                threading.Thread(target=load_phone_contacts, daemon=True).start()

            state = get_call_state()

            # INCOMING CALL DETECTED
            if state == "ringing" and last_state != "ringing":
                alerted = False
                number, display = get_caller_info()
                _incoming_call_number = number
                _incoming_call_name   = display
                _call_state = "ringing"

                if not alerted:
                    alerted = True
                    msg = f"Incoming call from {display}! Say receive call to answer or reject call to decline."
                    if _phone_ui_ref:
                        _phone_ui_ref.root.after(0, _phone_ui_ref._show_call_popup, display)
                        _phone_ui_ref.root.after(0, _phone_ui_ref._add_sys, f"📱 Incoming call from {display}")
                        _phone_ui_ref.root.after(0, _phone_ui_ref._refresh_phone_panel)
                    speak(msg)

            # CALL CONNECTED
            elif state == "in_call" and last_state == "ringing":
                _call_state = "in_call"
                if _phone_ui_ref:
                    _phone_ui_ref.root.after(0, _phone_ui_ref._add_sys, f"📱 Call connected with {_incoming_call_name}!")
                    _phone_ui_ref.root.after(0, _phone_ui_ref._refresh_phone_panel)
                speak(f"Call connected with {_incoming_call_name}!")

            # CALL ENDED
            elif state == "idle" and last_state in ["ringing","in_call"]:
                _call_state = "idle"
                alerted = False
                _incoming_call_number = ""
                _incoming_call_name   = ""
                if _phone_ui_ref:
                    _phone_ui_ref.root.after(0, _phone_ui_ref._add_sys, "📱 Call ended.")
                    _phone_ui_ref.root.after(0, _phone_ui_ref._close_call_popup)
                    _phone_ui_ref.root.after(0, _phone_ui_ref._refresh_phone_panel)

            last_state = state
            time.sleep(1)
        except Exception as e:
            print(f"[Phone Monitor] {e}"); time.sleep(3)

def start_phone_monitor():
    global _phone_monitor_active
    if not _phone_monitor_active:
        t = threading.Thread(target=_phone_monitor_loop, daemon=True)
        t.start()
        return "Phone monitor started! I'll alert you when someone calls."
    return "Phone monitor is already running."

def stop_phone_monitor():
    global _phone_monitor_active
    _phone_monitor_active = False
    return "Phone monitor stopped."

# Auto-start phone monitor on launch
threading.Thread(target=_phone_monitor_loop, daemon=True).start()

# ═══════════════════════════════
#  API KEY
# ═══════════════════════════════
GEMINI_API_KEY = "AI*******..."   # <-- paste your key

# ═══════════════════════════════
#  APP PATHS
# ═══════════════════════════════
APP_PATHS = {
    "whatsapp":r"C:\Users\%USERNAME%\AppData\Local\WhatsApp\WhatsApp.exe",
    "chrome":r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "notepad":r"C:\Windows\System32\notepad.exe",
    "calculator":r"C:\Windows\System32\calc.exe",
    "spotify":r"C:\Users\%USERNAME%\AppData\Roaming\Spotify\Spotify.exe",
    "vscode":r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "explorer":r"C:\Windows\explorer.exe",
    "paint":r"C:\Windows\System32\mspaint.exe",
    "vlc":r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    "telegram":r"C:\Users\%USERNAME%\AppData\Roaming\Telegram Desktop\Telegram.exe",
    "word":r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
    "excel":r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
    "powerpoint":r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    "task manager":r"C:\Windows\System32\Taskmgr.exe",
}

WAKE_WORDS  = ["hey jarvis","hi jarvis","okay jarvis","jarvis","yo jarvis"]
SLEEP_WORDS = ["goodbye jarvis","bye jarvis","go to sleep","sleep jarvis","later jarvis"]

# ═══════════════════════════════
#  NEPAL NEW YEAR
# ═══════════════════════════════
NEPAL_NEW_YEAR = True
NY_WISHES = [
    "Happy New Year 2083! Shubha Naya Barsha! A fresh start, new dreams, endless possibilities. May this year bring you joy, health, success, and everything you've been working toward!",
    "Naya Barsha 2083 ko Hardik Shubhakamana! Happy New Year! Today Nepal begins a beautiful new chapter. May your family be healthy, goals be achieved, and heart always full. Best wishes from Jarvis!",
    "Happy Nepali New Year 2083! May this year fill your life with laughter, wonderful moments, and success in everything you do. Cheers to 2083 — your best year yet!",
]
def get_ny_wish(): return random.choice(NY_WISHES)

# ═══════════════════════════════
#  THEME SYSTEM
# ═══════════════════════════════
THEMES = {
    "holographic": {"BG":"#020408","BG2":"#040810","BG3":"#06101a","CARD":"#081420","BORDER":"#0d2035","GLASS":"#0a1828","H1":"#00f5ff","H2":"#7c3aed","H3":"#f0abfc","H4":"#00ff88","H5":"#ff6b35","H6":"#fbbf24","H7":"#3b82f6","H8":"#ec4899","TEXT":"#c8e8ff","MUTED":"#0f2640","DIM":"#1e4060"},
    "light":       {"BG":"#f8faff","BG2":"#eef2ff","BG3":"#e0e7ff","CARD":"#ffffff","BORDER":"#c7d2fe","GLASS":"#f0f4ff","H1":"#4f46e5","H2":"#7c3aed","H3":"#db2777","H4":"#059669","H5":"#ea580c","H6":"#d97706","H7":"#2563eb","H8":"#be185d","TEXT":"#1e1b4b","MUTED":"#c7d2fe","DIM":"#818cf8"},
    "midnight":    {"BG":"#000000","BG2":"#0a0a0a","BG3":"#111111","CARD":"#0d0d0d","BORDER":"#222222","GLASS":"#0f0f0f","H1":"#ffffff","H2":"#888888","H3":"#aaaaaa","H4":"#00ff00","H5":"#ff4400","H6":"#ffcc00","H7":"#4488ff","H8":"#ff44aa","TEXT":"#eeeeee","MUTED":"#222222","DIM":"#444444"},
}
current_theme_name = "holographic"
T = dict(THEMES["holographic"])  # active theme colors

def apply_theme(name):
    global current_theme_name, T
    if name in THEMES:
        current_theme_name = name
        T.update(THEMES[name])

def get(key): return T.get(key,"#888888")

# ═══════════════════════════════
#  EMOTION SYSTEM
# ═══════════════════════════════
class Mood:
    HAPPY="happy"; EXCITED="excited"; CALM="calm"; CURIOUS="curious"
    EMPATHY="empathy"; PLAYFUL="playful"; FOCUSED="focused"; STRESSED="stressed"

nova_mood = Mood.CALM
MOOD_COLORS = {Mood.HAPPY:"H4",Mood.EXCITED:"H6",Mood.CALM:"H1",Mood.CURIOUS:"H7",Mood.EMPATHY:"H3",Mood.PLAYFUL:"H8",Mood.FOCUSED:"H2",Mood.STRESSED:"H5"}
MOOD_ICONS  = {Mood.HAPPY:"😊",Mood.EXCITED:"🤩",Mood.CALM:"😌",Mood.CURIOUS:"🤔",Mood.EMPATHY:"🥺",Mood.PLAYFUL:"😄",Mood.FOCUSED:"🧠",Mood.STRESSED:"😰"}

def detect_mood(text):
    global nova_mood; t=text.lower()
    if any(w in t for w in ["stressed","anxious","worried","panic","overwhelmed","too much","can't handle"]):
        nova_mood=Mood.STRESSED
    elif any(w in t for w in ["sad","crying","hurt","lonely","depressed","upset","terrible"]):
        nova_mood=Mood.EMPATHY
    elif any(w in t for w in ["wow","amazing","awesome","incredible","no way","seriously"]):
        nova_mood=Mood.EXCITED
    elif any(w in t for w in ["happy","great","love","fantastic","excited","yay"]):
        nova_mood=Mood.HAPPY
    elif any(w in t for w in ["joke","funny","lol","haha","roast","meme"]):
        nova_mood=Mood.PLAYFUL
    elif any(w in t for w in ["code","debug","fix","error","program","script"]):
        nova_mood=Mood.FOCUSED
    elif any(w in t for w in ["how","what","why","explain","curious"]):
        nova_mood=Mood.CURIOUS
    else: nova_mood=Mood.CALM

def mood_col(): return get(MOOD_COLORS.get(nova_mood,"H1"))

# ═══════════════════════════════
#  CONFIG & DATA FILES
# ═══════════════════════════════
_BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE   = os.path.join(_BASE,"jarvis_config.json")
NOTES_FILE    = os.path.join(_BASE,"jarvis_notes.json")
SHOP_FILE     = os.path.join(_BASE,"jarvis_shopping.json")
TASKS_FILE    = os.path.join(_BASE,"jarvis_tasks.json")
HABITS_FILE   = os.path.join(_BASE,"jarvis_habits.json")
SLEEP_FILE    = os.path.join(_BASE,"jarvis_sleep.json")
MEMORY_FILE   = os.path.join(_BASE,"jarvis_memory.json")
CUSTOM_FILE   = os.path.join(_BASE,"jarvis_custom_commands.json")
EXPENSE_FILE  = os.path.join(_BASE,"jarvis_expenses.json")
PASSWORD_FILE = os.path.join(_BASE,"jarvis_passwords.json")
PREFS_FILE    = os.path.join(_BASE,"jarvis_prefs.json")

# ── v8.0 NEW DATA FILES ──────────────────────────
PROFILE_FILE  = os.path.join(_BASE,"jarvis_profile.json")
MOOD_LOG_FILE = os.path.join(_BASE,"jarvis_mood_log.json")
APP_USE_FILE  = os.path.join(_BASE,"jarvis_app_usage.json")
ROUTINE_FILE  = os.path.join(_BASE,"jarvis_routine.json")

MUSIC_FOLDER=""; NATIONAL_ANTHEM_FILE="national_anthem.mp3"
ACCENT_COLOR = "#00f5ff"

def lj(p,d):
    if os.path.exists(p):
        try: return json.load(open(p))
        except: pass
    return d

def sj(p,d):
    try: json.dump(d,open(p,"w"),indent=2)
    except: pass

def load_config():
    global MUSIC_FOLDER,NATIONAL_ANTHEM_FILE,ACCENT_COLOR,current_theme_name
    c=lj(CONFIG_FILE,{})
    MUSIC_FOLDER=c.get("music_folder",""); NATIONAL_ANTHEM_FILE=c.get("anthem_file","national_anthem.mp3")
    ACCENT_COLOR=c.get("accent_color","#00f5ff"); apply_theme(c.get("theme","holographic"))

def save_config_full():
    sj(CONFIG_FILE,{"music_folder":MUSIC_FOLDER,"anthem_file":NATIONAL_ANTHEM_FILE,"accent_color":ACCENT_COLOR,"theme":current_theme_name})

# ═══════════════════════════════
#  CONVERSATION MEMORY
# ═══════════════════════════════
memory = lj(MEMORY_FILE, {"facts":[],"preferences":{},"last_session":""})
custom_commands = lj(CUSTOM_FILE, {})
prefs = lj(PREFS_FILE, {"voice_personality":"friendly","wake_quote":True,"daily_briefing":True,"briefing_time":"08:00"})

def remember(fact):
    memory["facts"].append({"fact":fact,"time":datetime.datetime.now().isoformat()})
    memory["facts"] = memory["facts"][-50:]  # keep last 50
    sj(MEMORY_FILE,memory)

def get_memory_context():
    if not memory["facts"]: return ""
    recent = memory["facts"][-5:]
    return "Previous context: " + ". ".join(f["fact"] for f in recent)

def learn_command(trigger, action):
    custom_commands[trigger.lower()] = action
    sj(CUSTOM_FILE,custom_commands)
    return f"Got it! Whenever you say '{trigger}' I'll {action}."

# ═══════════════════════════════════════════════
#  v8.0 — PERSONAL PROFILE SYSTEM
# ═══════════════════════════════════════════════
profile = lj(PROFILE_FILE, {
    "name":"","age":"","job":"","city":"","interests":[],
    "created":datetime.datetime.now().isoformat(),
    "last_seen":""
})

def update_profile(key, value):
    profile[key] = value
    profile["last_seen"] = datetime.datetime.now().isoformat()
    sj(PROFILE_FILE, profile)

def extract_profile_info(text):
    """Auto-extract name/job/city/age from conversation."""
    t = text.lower()
    m = re.search(r'my name is (\w+)', t)
    if m: update_profile("name", m.group(1).capitalize())
    m = re.search(r'i am (\d+) years old|i\'m (\d+) years old', t)
    if m: update_profile("age", m.group(1) or m.group(2))
    m = re.search(r'i(?:\'m| am) (?:a |an )?(.+?)(?:\.|,|$)', t)
    if m and len(m.group(1).split()) <= 4:
        job = m.group(1).strip()
        if any(w in job for w in ["student","developer","engineer","teacher","doctor","designer","manager","worker"]):
            update_profile("job", job.capitalize())
    m = re.search(r'(?:i live in|i\'m from|i am from) (.+?)(?:\.|,|$)', t)
    if m: update_profile("city", m.group(1).strip().capitalize())
    m = re.search(r'i (?:like|love|enjoy) (.+?)(?:\.|,|$)', t)
    if m:
        interest = m.group(1).strip()
        if interest not in profile["interests"]:
            profile["interests"].append(interest)
            profile["interests"] = profile["interests"][-20:]
            sj(PROFILE_FILE, profile)

def get_profile_summary():
    p = profile
    parts = []
    if p.get("name"):     parts.append(f"Name: {p['name']}")
    if p.get("age"):      parts.append(f"Age: {p['age']}")
    if p.get("job"):      parts.append(f"Job: {p['job']}")
    if p.get("city"):     parts.append(f"City: {p['city']}")
    if p.get("interests"):parts.append(f"Interests: {', '.join(p['interests'][:5])}")
    if not parts: return "I don't know much about you yet. Tell me your name, job, or city and I'll remember!"
    return "Here's your profile: " + ". ".join(parts)

def get_profile_greeting():
    """Personalized greeting using known profile."""
    name = profile.get("name","")
    city = profile.get("city","")
    g = f"Hey {name}!" if name else "Hey!"
    if city: g += f" How's everything in {city}?"
    return g

# ═══════════════════════════════════════════════
#  v8.0 — APP USAGE TRACKER
# ═══════════════════════════════════════════════
app_usage = lj(APP_USE_FILE, {})

def track_app(app_name):
    app_usage[app_name] = app_usage.get(app_name, 0) + 1
    sj(APP_USE_FILE, app_usage)

def get_app_suggestions():
    if not app_usage: return "Open some apps first and I'll learn your favourites!"
    top = sorted(app_usage.items(), key=lambda x: x[1], reverse=True)[:3]
    return "Your most used apps: " + ", ".join(f"{k} ({v}x)" for k,v in top)

# ═══════════════════════════════════════════════
#  v8.0 — DAILY ROUTINE LEARNER
# ═══════════════════════════════════════════════
routine_data = lj(ROUTINE_FILE, {"events":[],"suggestions":[]})

def log_routine_event(event):
    now = datetime.datetime.now()
    routine_data["events"].append({
        "event": event,
        "hour":  now.hour,
        "day":   now.strftime("%A"),
        "time":  now.isoformat()
    })
    routine_data["events"] = routine_data["events"][-200:]
    sj(ROUTINE_FILE, routine_data)
    _analyze_routine()

def _analyze_routine():
    """Find patterns and build suggestions."""
    from collections import Counter
    suggestions = []
    hour_events = {}
    for e in routine_data["events"]:
        h = e["hour"]
        if h not in hour_events: hour_events[h] = []
        hour_events[h].append(e["event"])
    for h, evts in hour_events.items():
        most_common = Counter(evts).most_common(1)
        if most_common and most_common[0][1] >= 2:
            suggestions.append(f"At {h:02d}:00 you usually: {most_common[0][0]}")
    routine_data["suggestions"] = suggestions[-5:]
    sj(ROUTINE_FILE, routine_data)

def get_routine_suggestions():
    now_h = datetime.datetime.now().hour
    relevant = [s for s in routine_data["suggestions"] if str(now_h) in s]
    if relevant: return "Based on your routine: " + relevant[0]
    if routine_data["suggestions"]: return "Routine insight: " + random.choice(routine_data["suggestions"])
    return "Keep using Jarvis and I'll learn your daily routine!"

# ═══════════════════════════════════════════════
#  v8.0 — EMOTION AI & MENTAL HEALTH TRACKER
# ═══════════════════════════════════════════════
mood_log = lj(MOOD_LOG_FILE, {"entries":[],"weekly_stress":[]})
_mental_health_score = 70   # 0-100 scale

EMOTION_SIGNALS = {
    "very_stressed" : ["panic","overwhelmed","can't handle","breaking down","too much","freaking out","anxiety attack"],
    "stressed"      : ["stressed","anxious","worried","nervous","tense","pressure"],
    "sad"           : ["sad","crying","depressed","lonely","hopeless","hurt","upset","heartbroken"],
    "angry"         : ["angry","furious","hate","annoyed","frustrated","mad","irritated"],
    "happy"         : ["happy","excited","great","amazing","love","awesome","fantastic","blessed"],
    "confident"     : ["i will","i can","sure","definitely","absolutely","i know","positive"],
    "uncertain"     : ["maybe","not sure","idk","i don't know","confused","unsure"],
    "lying_signals" : ["actually","well","to be honest","truthfully","i swear","believe me"],
}

def analyze_emotion_deep(text):
    """Deep emotion analysis — returns emotion + confidence + mental score delta."""
    global _mental_health_score
    t = text.lower()
    detected = []
    for emotion, signals in EMOTION_SIGNALS.items():
        count = sum(1 for s in signals if s in t)
        if count > 0: detected.append((emotion, count))
    detected.sort(key=lambda x: x[1], reverse=True)
    primary = detected[0][0] if detected else "neutral"
    # update mental health score
    score_delta = {
        "very_stressed":-12,"stressed":-6,"sad":-5,"angry":-4,
        "happy":+8,"confident":+6,"neutral":0,"uncertain":-2,"lying_signals":0
    }
    delta = score_delta.get(primary, 0)
    _mental_health_score = max(10, min(100, _mental_health_score + delta))
    # log to mood diary
    mood_log["entries"].append({
        "time"    : datetime.datetime.now().isoformat(),
        "text"    : text[:80],
        "emotion" : primary,
        "score"   : _mental_health_score
    })
    mood_log["entries"] = mood_log["entries"][-100:]
    # weekly stress
    today = datetime.date.today().isoformat()
    mood_log["weekly_stress"].append({"date":today,"emotion":primary,"score":_mental_health_score})
    mood_log["weekly_stress"] = mood_log["weekly_stress"][-70:]
    sj(MOOD_LOG_FILE, mood_log)
    return primary, _mental_health_score

def get_mental_health_report():
    if not mood_log["entries"]: return "No mood data yet. Keep talking to me and I'll track your wellbeing!"
    recent = mood_log["entries"][-10:]
    avg_score = sum(e["score"] for e in recent) / len(recent)
    emotions = [e["emotion"] for e in recent]
    most_common = max(set(emotions), key=emotions.count)
    if avg_score >= 75:   status = "You're doing great! Your mental health score is excellent."
    elif avg_score >= 55: status = "You're doing okay, but I notice some stress. Take care of yourself!"
    elif avg_score >= 35: status = "I'm a bit concerned. You seem stressed lately. Want to talk or try a breathing exercise?"
    else:                 status = "Your stress level is high. Please take a break and reach out to someone you trust."
    return f"Mental health score: {avg_score:.0f}/100. Most common feeling: {most_common}. {status}"

def get_emotion_response(emotion, score):
    """Return emotion-aware response prefix."""
    if emotion == "very_stressed":
        return random.choice(["Hey, breathe. I'm right here with you. One thing at a time, okay?",
                              "That sounds really overwhelming. Can you take one slow breath with me first?"])
    elif emotion == "stressed":
        return random.choice(["I can hear the stress. Want to try a quick 2-minute breathing break?",
                              "You've got this — but also, it's okay to slow down a little."])
    elif emotion == "sad":
        return random.choice(["Hey... I'm here. You don't have to be okay right now.",
                              "That sounds really hard. I'm listening if you want to share."])
    elif emotion == "happy":
        return random.choice(["Love that energy! What's going great?","Yes!! That's amazing, tell me more!"])
    elif emotion == "confident":
        return random.choice(["That's the spirit! You've totally got this.","Love the confidence — let's do this!"])
    return None

def get_weekly_mood_summary():
    if not mood_log["weekly_stress"]: return "No weekly data yet!"
    week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    this_week = [e for e in mood_log["weekly_stress"] if e["date"] >= week_ago]
    if not this_week: return "Not enough data for the week yet."
    avg = sum(e["score"] for e in this_week) / len(this_week)
    highs = [e for e in this_week if e["emotion"] in ["happy","confident"]]
    lows  = [e for e in this_week if e["emotion"] in ["stressed","very_stressed","sad"]]
    return (f"This week: avg mood score {avg:.0f}/100. "
            f"Good moments: {len(highs)}, Tough moments: {len(lows)}. "
            f"{'Keep it up!' if avg >= 60 else 'Remember to take care of yourself this week.'}")

# ═══════════════════════════════════════════════
#  v8.0 — CODE COPILOT
# ═══════════════════════════════════════════════
def code_ask_ai(prompt, tokens=800):
    """Dedicated high-quality code AI call."""
    try:
        code_model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=(
                "You are an expert programmer and code assistant. "
                "Write clean, minimal, working code. "
                "When explaining: use simple words, one concept at a time. "
                "When fixing bugs: show the fixed code + one-line explanation of what was wrong. "
                "When generating: produce complete working code with comments. "
                "Format code in plain text without markdown backticks since this is voice output. "
                "Keep non-code explanation under 2 sentences."
            )
        )
        r = code_model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(max_output_tokens=tokens, temperature=0.3)
        )
        return r.text.strip()
    except Exception as e: return f"Code AI error: {e}"

def generate_code(description):
    """Generate full code from description."""
    lang = "Python"
    if any(w in description.lower() for w in ["javascript","js","node","react"]): lang = "JavaScript"
    elif any(w in description.lower() for w in ["html","webpage","website"]): lang = "HTML"
    prompt = f"Write a complete working {lang} program for: {description}. Include comments."
    return code_ask_ai(prompt, 800)

def explain_code(code_snippet):
    """Explain code line by line."""
    prompt = f"Explain this code simply, line by line in plain English:\n{code_snippet}"
    return code_ask_ai(prompt, 600)

def find_bugs(code_snippet):
    """Auto find and fix bugs."""
    prompt = f"Find all bugs in this code, show the fixed version and explain each bug in one line:\n{code_snippet}"
    return code_ask_ai(prompt, 700)

def improve_code(code_snippet):
    """Suggest improvements."""
    prompt = f"Suggest improvements for this code with reasons. Show improved version:\n{code_snippet}"
    return code_ask_ai(prompt, 700)

def run_python_code(code):
    try:
        tmp = tempfile.mktemp(suffix=".py")
        with open(tmp,"w") as f: f.write(code)
        result = subprocess.run(["python", tmp], capture_output=True, text=True, timeout=10)
        os.unlink(tmp)
        out = (result.stdout or result.stderr or "No output.")[:300]
        return f"Output: {out}"
    except subprocess.TimeoutExpired: return "Code timed out after 10 seconds."
    except Exception as e: return f"Error: {e}"

# code clipboard buffer — stores code user pastes
_code_buffer = ""

def set_code_buffer(code):
    global _code_buffer; _code_buffer = code
    return f"Code saved! I have {len(code.split(chr(10)))} lines ready. Say 'explain code', 'find bugs', or 'improve code'."

# ═══════════════════════════════
#  AI SETUP
# ═══════════════════════════════
genai.configure(api_key=GEMINI_API_KEY)

PERSONALITIES = {
    "friendly":   "You are Jarvis — a warm, casual, friendly AI best friend. Use words like 'bro', 'honestly', 'got it'. Short 1-3 sentence replies. Never robotic.",
    "professional":"You are Jarvis — a sharp, professional AI assistant. Precise, efficient, respectful. No slang. Clean concise answers.",
    "funny":      "You are Jarvis — a hilarious, witty AI with great humor. Add jokes and sarcasm naturally. Still helpful but always entertaining.",
}

def make_ai():
    personality = PERSONALITIES.get(prefs.get("voice_personality","friendly"), PERSONALITIES["friendly"])
    return genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=(
            f"{personality} "
            "You were built by Sonu Kumar Sah. "
            "Keep replies SHORT — 1-3 sentences max. No bullet points, no markdown. "
            "CODING: clean minimal working code + one-line explanation. "
            "Always prefer DOING over EXPLAINING. Be REAL. Be FAST. Be USEFUL."
        )
    )

ai_model = make_ai()
chat_session = ai_model.start_chat(history=[])

def ask_ai(text):
    try:
        detect_mood(text)
        emotion, mh_score = analyze_emotion_deep(text)
        extract_profile_info(text)
        log_routine_event(text[:50])
        now  = datetime.datetime.now().strftime("%I:%M %p, %A %B %d")
        ctx  = get_memory_context()
        name = profile.get("name","")
        name_ctx = f"User's name is {name}." if name else ""
        tl   = text.lower()
        is_code  = any(w in tl for w in ["code","function","error","fix","program","script","def ","debug","python","javascript","html","css","generate code","write code","build"])
        is_write = any(w in tl for w in ["write email","draft","compose","rewrite","write message"])
        tokens   = 800 if is_code else 300 if is_write else 110
        temp     = 0.3 if is_code else 0.85
        # emotion-aware prefix
        emo_prefix = get_emotion_response(emotion, mh_score)
        prompt = f"[{now}][mood:{nova_mood}][mh:{mh_score}]{name_ctx}{ctx} {text}"
        r = chat_session.send_message(
            prompt,
            generation_config=genai.types.GenerationConfig(max_output_tokens=tokens, temperature=temp, candidate_count=1)
        )
        reply = r.text.strip()
        if emo_prefix and emotion in ["very_stressed","stressed","sad"]:
            reply = emo_prefix + " " + reply
        if any(w in tl for w in ["my name is","i am","i work","i study","i like","i love","i hate","i prefer","i live in"]):
            threading.Thread(target=lambda:remember(text), daemon=True).start()
        return reply
    except: return "Something broke on my end — try again?"

# ═══════════════════════════════
#  VOICE ENGINE
# ═══════════════════════════════
recognizer = sr.Recognizer()
recognizer.pause_threshold=0.8; recognizer.energy_threshold=3000
is_awake=is_speaking=is_thinking=False; mouth_open=False
_voice_id=None; _ui_ref=None

def _find_voice():
    global _voice_id
    try:
        e=pyttsx3.init(); vs=e.getProperty("voices")
        for v in vs:
            if any(n in v.name.lower() for n in ["david","mark","george","james","male","man","richard","microsoft sam"]):
                _voice_id=v.id; break
        if not _voice_id and len(vs)>1: _voice_id=vs[1].id
        e.stop()
    except: pass
_find_voice()

def speak(text):
    def _r():
        global is_speaking,mouth_open
        is_speaking=True; mouth_open=True
        try:
            e=pyttsx3.init(); e.setProperty("volume",1.0); e.setProperty("rate",165)
            if _voice_id: e.setProperty("voice",_voice_id)
            e.say(re.sub(r'[*_`#~]','',text).strip()); e.runAndWait(); e.stop()
        except Exception as ex: print(f"[TTS]{ex}")
        mouth_open=False; is_speaking=False
    threading.Thread(target=_r,daemon=True).start()

def listen(timeout=6,phrase_limit=10):
    try:
        with sr.Microphone() as src:
            recognizer.adjust_for_ambient_noise(src,duration=0.1)
            audio=recognizer.listen(src,timeout=timeout,phrase_time_limit=phrase_limit)
        return recognizer.recognize_google(audio,language="en-US").lower().strip()
    except: return ""

# ═══════════════════════════════
#  CLAP DETECTION
# ═══════════════════════════════
clap_times=[]
def _clap_thread():
    cr=sr.Recognizer(); cr.energy_threshold=3500; cr.dynamic_energy_threshold=False
    while True:
        try:
            with sr.Microphone() as src:
                cr.adjust_for_ambient_noise(src,duration=0.05)
                cr.listen(src,timeout=None,phrase_time_limit=0.35)
            now=time.time(); clap_times.append(now)
            while clap_times and now-clap_times[0]>2.0: clap_times.pop(0)
            if len(clap_times)>=2 and clap_times[-1]-clap_times[-2]<0.9:
                clap_times.clear()
                if not is_awake and _ui_ref: _ui_ref.root.after(0,_ui_ref._do_wake)
        except: time.sleep(0.05)
threading.Thread(target=_clap_thread,daemon=True).start()

# ═══════════════════════════════
#  MUSIC
# ═══════════════════════════════
pygame.mixer.init()
music_playlist=[]; music_index=0; music_playing=False; music_paused=False

def _load_pl():
    global music_playlist
    if MUSIC_FOLDER and os.path.exists(MUSIC_FOLDER):
        music_playlist=sorted([os.path.join(MUSIC_FOLDER,f) for f in os.listdir(MUSIC_FOLDER) if f.lower().endswith(".mp3")])
    else: music_playlist=[]

def _play_idx(idx):
    global music_index,music_playing,music_paused
    if not music_playlist: return
    music_index=idx%len(music_playlist); music_paused=False; music_playing=True
    pygame.mixer.music.load(music_playlist[music_index]); pygame.mixer.music.play()
    if _ui_ref: _ui_ref.root.after(0,_ui_ref._refresh_music)

def play_music(q=None):
    _load_pl()
    if not music_playlist: return "No songs found! Set your music folder in Settings."
    if not q or q.strip() in ["","music","song"]:
        idx=random.randint(0,len(music_playlist)-1)
    else:
        m=[i for i,p in enumerate(music_playlist) if q.lower() in os.path.basename(p).lower()]
        idx=m[0] if m else random.randint(0,len(music_playlist)-1)
    _play_idx(idx)
    return f"Playing {os.path.splitext(os.path.basename(music_playlist[idx]))[0]}!"

def music_next(): 
    if not music_playlist: return "No songs!"
    _play_idx(music_index+1); return f"Next: {os.path.splitext(os.path.basename(music_playlist[music_index]))[0]}!"
def music_prev():
    if not music_playlist: return "No songs!"
    _play_idx(music_index-1); return f"Back to: {os.path.splitext(os.path.basename(music_playlist[music_index]))[0]}!"
def music_toggle():
    global music_playing,music_paused
    if music_paused: pygame.mixer.music.unpause(); music_paused=False; music_playing=True; return "Back on!"
    elif music_playing: pygame.mixer.music.pause(); music_paused=True; music_playing=False; return "Paused."
    return "Nothing playing!"
def music_stop():
    global music_playing,music_paused
    pygame.mixer.music.stop(); music_playing=False; music_paused=False
    if _ui_ref: _ui_ref.root.after(0,_ui_ref._refresh_music); return "Stopped."

# ═══════════════════════════════
#  ALARMS
# ═══════════════════════════════
alarms=[]; reminders=[]; _aid=0
def _nid(): global _aid; _aid+=1; return _aid

def set_alarm(text):
    m=re.search(r'(\d{1,2})[:\.](\d{2})\s*(am|pm)?|(\d{1,2})\s*(am|pm)',text,re.IGNORECASE)
    if m:
        h=int(m.group(1) or m.group(4)); mi=int(m.group(2) or 0); ap=m.group(3) or m.group(5)
        if ap and ap.lower()=="pm" and h!=12: h+=12
        if ap and ap.lower()=="am" and h==12: h=0
        h=h%24; alarms.append({"id":_nid(),"hour":h,"minute":mi,"label":f"Alarm {h:02d}:{mi:02d}","active":True,"repeat":False})
        if _ui_ref: _ui_ref.root.after(0,_ui_ref._refresh_alarm_ui)
        return f"Alarm set for {h:02d}:{mi:02d}!"
    return "Say: 'set alarm at 7:30 am'"

def set_reminder(text):
    m=re.search(r'(\d+)\s*(minute|min|hour|second|sec)',text,re.IGNORECASE)
    if m:
        v=int(m.group(1)); u=m.group(2).lower()
        s=v*3600 if "hour" in u else v*60 if "min" in u else v
        lbl=re.sub(r'remind(er)?\s*(me)?\s*(in|to|about|after)?','',text,flags=re.IGNORECASE)
        lbl=re.sub(r'\d+\s*(minute|min|hour|second|sec)s?','',lbl,flags=re.IGNORECASE).strip() or "Reminder"
        reminders.append({"id":_nid(),"label":lbl,"fire_at":time.time()+s})
        if _ui_ref: _ui_ref.root.after(0,_ui_ref._refresh_alarm_ui)
        return f"I'll remind you in {v} {u}: {lbl}"
    return "Try: 'remind me in 10 minutes to drink water'"

def _alarm_checker():
    while True:
        now=datetime.datetime.now(); ch=now.hour; cm=now.minute; cs=now.second
        if cs==0:
            for a in alarms:
                if a["active"] and a["hour"]==ch and a["minute"]==cm:
                    if not a.get("fired_at") or (now.timestamp()-a["fired_at"])>60:
                        a["fired_at"]=now.timestamp()
                        if not a["repeat"]: a["active"]=False
                        if _ui_ref: _ui_ref.root.after(0,_ui_ref._add_sys,f"⏰ ALARM: {a['label']}")
                        if _ui_ref: _ui_ref.root.after(0,_ui_ref._alarm_popup,a["label"])
                        speak(f"Hey! Alarm! {a['label']}!")
        for r in reminders[:]:
            if time.time()>=r["fire_at"]:
                reminders.remove(r)
                if _ui_ref: _ui_ref.root.after(0,_ui_ref._add_sys,f"🔔 {r['label']}")
                if _ui_ref: _ui_ref.root.after(0,_ui_ref._alarm_popup,r["label"])
                if _ui_ref: _ui_ref.root.after(0,_ui_ref._refresh_alarm_ui)
                speak(f"Reminder: {r['label']}")
        time.sleep(1)
threading.Thread(target=_alarm_checker,daemon=True).start()

# ═══════════════════════════════
#  HABIT TRACKER
# ═══════════════════════════════
habits_data = lj(HABITS_FILE, {"habits":[],"logs":{}})

PRESET_HABITS = ["drink water","exercise","meditate","study","read","sleep early","no junk food","walk"]

def add_habit(name):
    if name not in habits_data["habits"]:
        habits_data["habits"].append(name)
        sj(HABITS_FILE,habits_data)
        if _ui_ref: _ui_ref.root.after(0,_ui_ref._refresh_habits)
    return f"Habit '{name}' added! I'll help you track it."

def log_habit(name):
    today=datetime.date.today().isoformat()
    if today not in habits_data["logs"]: habits_data["logs"][today]=[]
    if name not in habits_data["logs"][today]:
        habits_data["logs"][today].append(name)
        sj(HABITS_FILE,habits_data)
        if _ui_ref: _ui_ref.root.after(0,_ui_ref._refresh_habits)
        return f"Nice! Logged '{name}' for today. Keep it up!"
    return f"You already logged '{name}' today!"

def habit_streak(name):
    streak=0; today=datetime.date.today()
    for i in range(30):
        day=(today-datetime.timedelta(days=i)).isoformat()
        if day in habits_data["logs"] and name in habits_data["logs"][day]: streak+=1
        else: break
    return streak

# ═══════════════════════════════
#  SLEEP TRACKER
# ═══════════════════════════════
sleep_data = lj(SLEEP_FILE, {"sessions":[],"current_sleep":None})

def start_sleep():
    sleep_data["current_sleep"] = datetime.datetime.now().isoformat()
    sj(SLEEP_FILE,sleep_data)
    return "Sweet dreams! I'm tracking your sleep. Say 'good morning' when you wake up!"

def wake_up_sleep():
    if not sleep_data.get("current_sleep"):
        return "I don't have your sleep start time. Next time say 'going to sleep' before bed!"
    slept = datetime.datetime.fromisoformat(sleep_data["current_sleep"])
    woke  = datetime.datetime.now()
    dur   = woke - slept
    hrs   = dur.total_seconds()/3600
    sleep_data["sessions"].append({"date":slept.date().isoformat(),"hours":round(hrs,1),"start":sleep_data["current_sleep"],"end":woke.isoformat()})
    sleep_data["current_sleep"] = None
    sj(SLEEP_FILE,sleep_data)
    if _ui_ref: _ui_ref.root.after(0,_ui_ref._refresh_sleep)
    quality = "Great sleep!" if hrs>=7 else "A bit short, try for 7-8 hours!" if hrs>=5 else "That was really short, get more rest!"
    return f"Good morning! You slept {hrs:.1f} hours. {quality}"

def sleep_stats():
    if not sleep_data["sessions"]: return "No sleep data yet! Say 'going to sleep' tonight."
    recent=sleep_data["sessions"][-7:]
    avg=sum(s["hours"] for s in recent)/len(recent)
    return f"Your average sleep this week: {avg:.1f} hours. {'Great!' if avg>=7 else 'Try to get more sleep!'}"

# ═══════════════════════════════
#  POMODORO TIMER
# ═══════════════════════════════
pomodoro_active=False; pomodoro_count=0

def start_pomodoro(minutes=25):
    global pomodoro_active
    pomodoro_active=True
    def _pom():
        global pomodoro_active,pomodoro_count
        speak(f"Focus mode started! {minutes} minutes. You got this!")
        time.sleep(minutes*60)
        pomodoro_count+=1; pomodoro_active=False
        speak(f"Time's up! Great focus session — that's {pomodoro_count} pomodoros today. Take a 5-minute break!")
        if _ui_ref: _ui_ref.root.after(0,_ui_ref._alarm_popup,f"Pomodoro #{pomodoro_count} done! Take a break.")
    threading.Thread(target=_pom,daemon=True).start()
    return f"Focus mode ON! {minutes} minutes — no distractions. You got this!"

def stop_pomodoro():
    global pomodoro_active; pomodoro_active=False
    return "Focus mode stopped."

# ═══════════════════════════════
#  DAILY BRIEFING
# ═══════════════════════════════
def get_daily_briefing():
    now=datetime.datetime.now()
    h=now.hour; g="Good morning" if h<12 else "Good afternoon" if h<17 else "Good evening"
    parts=[f"{g}! Here's your briefing for {now.strftime('%A, %B %d')}."]
    # tasks
    pending=[t["task"] for t in lj(TASKS_FILE,[]) if not t.get("done")]
    if pending: parts.append(f"You have {len(pending)} pending tasks.")
    # habits today
    today=now.date().isoformat()
    logged=habits_data["logs"].get(today,[])
    if logged: parts.append(f"Habits done today: {', '.join(logged)}.")
    else: parts.append("No habits logged yet today.")
    # motivational quote
    quotes=["Believe you can and you're halfway there.","Every day is a new beginning.","Small steps every day lead to big results.","You are capable of amazing things!","Make today count!"]
    parts.append(random.choice(quotes))
    if NEPAL_NEW_YEAR: parts.append("Happy New Year 2083! Make it your best year yet!")
    return " ".join(parts)

def _briefing_scheduler():
    """Auto-trigger daily briefing at set time."""
    while True:
        now=datetime.datetime.now()
        bt=prefs.get("briefing_time","08:00").split(":")
        bh,bm=int(bt[0]),int(bt[1])
        if now.hour==bh and now.minute==bm and now.second<5:
            if prefs.get("daily_briefing",True) and is_awake and _ui_ref:
                briefing=get_daily_briefing()
                _ui_ref.root.after(0,_ui_ref._add_chat,"jarvis",briefing,True)
                speak(briefing)
        time.sleep(10)
threading.Thread(target=_briefing_scheduler,daemon=True).start()

# ═══════════════════════════════
#  MENTAL HEALTH & WELLNESS
# ═══════════════════════════════
MOTIVATIONAL_QUOTES = [
    "You are doing better than you think. Keep going!",
    "Every expert was once a beginner. Trust the process.",
    "Small progress is still progress. Be proud of yourself!",
    "You have survived every hard day so far. You've got this!",
    "Your only competition is who you were yesterday.",
    "The best time to start was yesterday. The next best time is now.",
    "Difficult roads often lead to beautiful destinations.",
    "You are stronger than you know and braver than you believe.",
]

def get_motivation(): return random.choice(MOTIVATIONAL_QUOTES)

def breathing_exercise():
    def _breathe():
        steps=[("Breathe IN for 4 seconds",4),("Hold for 4 seconds",4),("Breathe OUT for 4 seconds",4),("Hold for 4 seconds",4)]
        speak("Starting breathing exercise. Let's calm your mind.")
        for i in range(4):
            for step,secs in steps:
                speak(step); time.sleep(secs)
        speak("Great job! You should feel calmer now. How are you feeling?")
    threading.Thread(target=_breathe,daemon=True).start()
    return "Starting breathing exercise — box breathing technique. Follow my voice."

def stress_check(text):
    stress_words=["stressed","anxious","overwhelmed","can't handle","too much","panic","nervous","worried","freaking out"]
    if any(w in text.lower() for w in stress_words):
        responses=[
            "Hey, I can hear that you're stressed. Take a slow breath right now. You don't have to handle everything at once.",
            "It sounds like a lot is on your plate. Want to try a quick breathing exercise? Just say 'start breathing exercise'.",
            "Stress is real and valid. But you've handled hard things before. One step at a time, okay?",
        ]
        return random.choice(responses)
    return None

# ═══════════════════════════════
#  EXPENSE TRACKER
# ═══════════════════════════════
expenses = lj(EXPENSE_FILE, [])

def add_expense(text):
    m=re.search(r'(\d+(?:\.\d+)?)',text)
    if m:
        amount=float(m.group(1))
        cat_match=re.search(r'on\s+(.+)',text,re.IGNORECASE)
        cat=cat_match.group(1).strip() if cat_match else "General"
        expenses.append({"amount":amount,"category":cat,"date":datetime.datetime.now().isoformat()})
        sj(EXPENSE_FILE,expenses)
        if _ui_ref: _ui_ref.root.after(0,_ui_ref._refresh_expenses)
        return f"Logged! Spent {amount} on {cat}."
    return "Say: 'I spent 500 on food'"

def expense_summary():
    if not expenses: return "No expenses tracked yet!"
    today=datetime.date.today().isoformat()
    today_exp=[e for e in expenses if e["date"].startswith(today)]
    total=sum(e["amount"] for e in today_exp)
    return f"Today's spending: {total:.0f}. Total entries: {len(expenses)}."

# ═══════════════════════════════
#  PASSWORD VAULT
# ═══════════════════════════════
passwords = lj(PASSWORD_FILE, {})
vault_unlocked = False

def unlock_vault():
    global vault_unlocked; vault_unlocked=True
    return "Vault unlocked! You can now access your passwords."

def lock_vault():
    global vault_unlocked; vault_unlocked=False
    return "Vault locked."

def add_password(text):
    m=re.search(r'password for (\S+)\s+(?:is\s+)?(\S+)',text,re.IGNORECASE)
    if m:
        site=m.group(1); pwd=m.group(2)
        passwords[site]=pwd; sj(PASSWORD_FILE,passwords)
        return f"Password saved for {site}!"
    return "Say: 'password for gmail is mypassword123'"

def get_password(site):
    if not vault_unlocked: return "Say 'unlock vault' first to access passwords."
    if site in passwords: return f"Password for {site}: {passwords[site]}"
    return f"No password saved for {site}."

# ═══════════════════════════════
#  FACE / SECURITY (basic)
# ═══════════════════════════════
def check_camera():
    if not HAS_CV2: return "Install opencv-python for camera features: pip install opencv-python"
    try:
        cap=cv2.VideoCapture(0)
        ret,frame=cap.read(); cap.release()
        if ret: return "Camera is working!"
        return "Camera not accessible."
    except: return "Camera check failed."

# ═══════════════════════════════
#  WIKIPEDIA
# ═══════════════════════════════
def wiki_search(query):
    try:
        r=requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(query)}",timeout=5)
        data=r.json()
        extract=data.get("extract","")
        if extract: return extract[:300]+"..." if len(extract)>300 else extract
        return f"No Wikipedia article found for '{query}'."
    except: return "Wikipedia search failed."

# ═══════════════════════════════
#  CURRENCY & CRYPTO
# ═══════════════════════════════
def convert_currency(text):
    try:
        m=re.search(r'(\d+(?:\.\d+)?)\s+([A-Z]{3})\s+to\s+([A-Z]{3})',text,re.IGNORECASE)
        if m:
            amount=float(m.group(1)); src=m.group(2).upper(); dst=m.group(3).upper()
            r=requests.get(f"https://api.exchangerate-api.com/v4/latest/{src}",timeout=5)
            rate=r.json()["rates"].get(dst)
            if rate: return f"{amount} {src} = {amount*rate:.2f} {dst}"
        return "Say: 'convert 100 USD to NPR'"
    except: return "Currency conversion unavailable."

def crypto_price(coin="bitcoin"):
    try:
        r=requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd",timeout=5)
        price=r.json().get(coin,{}).get("usd")
        if price: return f"{coin.capitalize()} is ${price:,.2f} USD."
        return f"Couldn't find price for {coin}."
    except: return "Crypto price unavailable."

# ═══════════════════════════════
#  NEWS / WEATHER
# ═══════════════════════════════
def get_news(cat="general"):
    try:
        feeds={"general":"https://feeds.bbci.co.uk/news/rss.xml","tech":"https://feeds.bbci.co.uk/news/technology/rss.xml","sports":"https://feeds.bbci.co.uk/sport/rss.xml"}
        r=requests.get(feeds.get(cat,feeds["general"]),timeout=6)
        t=re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>',r.text)
        if not t: t=re.findall(r'<title>(.*?)</title>',r.text)
        h=[x.strip() for x in t[1:5] if x.strip()]
        return "Headlines: "+". ".join(h[:3]) if h else "No news available."
    except: return "News unavailable."

def get_weather(city=None):
    try:
        if not city:
            try: city=requests.get("https://ipinfo.io/json",timeout=3).json().get("city","Kathmandu")
            except: city="Kathmandu"
        return requests.get(f"https://wttr.in/{urllib.parse.quote(city)}?format=3",timeout=5).text.strip()
    except: return "Weather unavailable."

def tell_joke():
    try:
        j=requests.get("https://official-joke-api.appspot.com/random_joke",timeout=4).json()
        return f"{j['setup']} ... {j['punchline']}"
    except: return "Why do programmers prefer dark mode? Because light attracts bugs!"

# ═══════════════════════════════
#  COMMAND ROUTER
# ═══════════════════════════════
def handle_command(text):
    t=text.lower()

    # custom learned commands
    for trigger,action in custom_commands.items():
        if trigger in t: return f"Running your custom command: {action}"

    # ── v8 EMOTION & MENTAL HEALTH ─────────────────
    emotion, mh_score = analyze_emotion_deep(text)
    extract_profile_info(text)

    if any(x in t for x in ["mental health","my mood report","how am i feeling","wellness report","mood report"]):
        return get_mental_health_report()
    if any(x in t for x in ["weekly mood","mood this week","how was my week","stress report"]):
        return get_weekly_mood_summary()
    if any(x in t for x in ["my mental health score","my score","health score"]):
        return f"Your current mental health score is {mh_score}/100. {'You are doing well!' if mh_score>=70 else 'Take care of yourself!'}"

    # ── v8 PERSONAL PROFILE ────────────────────────
    if any(x in t for x in ["my profile","show profile","what do you know about me","who am i","my info"]):
        return get_profile_summary()
    if any(x in t for x in ["forget me","clear profile","reset profile","delete my info"]):
        global profile
        profile = {"name":"","age":"","job":"","city":"","interests":[],"created":datetime.datetime.now().isoformat(),"last_seen":""}
        sj(PROFILE_FILE, profile)
        return "Profile cleared! Fresh start."

    # ── v8 APP USAGE & ROUTINE ─────────────────────
    if any(x in t for x in ["my favourite apps","most used apps","app suggestions","suggest apps"]):
        return get_app_suggestions()
    if any(x in t for x in ["my routine","daily routine","routine suggestions","what should i do now"]):
        return get_routine_suggestions()

    # ── v8 CODE COPILOT ────────────────────────────
    if any(x in t for x in ["generate code","write code for","create code","build a","code for"]):
        desc = re.sub(r'(generate code|write code for|create code|build a|code for)','',t,flags=re.IGNORECASE).strip()
        if desc:
            result = generate_code(desc)
            if _ui_ref: _ui_ref.root.after(0, _ui_ref._show_code_window, result, f"Generated: {desc[:40]}")
            return f"Code generated! Check the code window. Here's a preview: {result[:80]}..."
        return "What code should I generate? Say: 'generate code for a calculator'"

    if any(x in t for x in ["explain this code","explain my code","explain code","what does this code do"]):
        code = _code_buffer if _code_buffer else re.sub(r'(explain this code|explain my code|explain code|what does this code do)','',t).strip()
        if code:
            result = explain_code(code)
            if _ui_ref: _ui_ref.root.after(0, _ui_ref._show_code_window, result, "Code Explanation")
            return "Explanation ready! Check the code window."
        return "Paste your code first by saying 'save code [paste your code]'"

    if any(x in t for x in ["find bugs","check bugs","debug this","fix bugs","find errors in"]):
        code = _code_buffer if _code_buffer else re.sub(r'(find bugs|check bugs|debug this|fix bugs|find errors in)','',t).strip()
        if code:
            result = find_bugs(code)
            if _ui_ref: _ui_ref.root.after(0, _ui_ref._show_code_window, result, "Bug Report & Fix")
            return "Bug analysis done! Check the code window."
        return "No code saved. Say 'save code [your code]' first."

    if any(x in t for x in ["improve code","optimize code","make code better","code improvements"]):
        code = _code_buffer if _code_buffer else t
        result = improve_code(code if code else "print('hello')")
        if _ui_ref: _ui_ref.root.after(0, _ui_ref._show_code_window, result, "Code Improvements")
        return "Improvement suggestions ready! Check the code window."

    if t.startswith("save code") or t.startswith("code buffer"):
        code = t.replace("save code","").replace("code buffer","").strip()
        if code: return set_code_buffer(code)
        return "Paste your code after 'save code ...'"

    if t.startswith("run code") or t.startswith("execute"):
        code = _code_buffer or t.replace("run code","").replace("execute","").strip()
        if code: return run_python_code(code)
        return "No code to run!"

    # ── STRESS CHECK ───────────────────────────────
    if emotion == "very_stressed":
        return random.choice([
            "Hey, stop for a second. Take one slow breath. You don't have to handle everything right now.",
            "That sounds overwhelming. Want to try a 2-minute breathing exercise? Say 'start breathing exercise'.",
        ])

    # stress check
    from_stress = None
    stress_words=["stressed","anxious","overwhelmed","can't handle","too much","panic","nervous","worried"]
    if any(w in t for w in stress_words):
        from_stress = random.choice([
            "I can hear the stress in that. Let's take one thing at a time, okay?",
            "That sounds tough. Deep breath — want to try a quick breathing exercise?",
        ])
    if from_stress: return from_stress

    # NEW YEAR
    if any(x in t for x in ["new year","naya barsha","2083"]): return get_ny_wish()

    # THEME
    if "switch to light mode" in t or "light mode" in t: apply_theme("light"); return "Switched to light mode!"
    if "switch to dark mode" in t or "dark mode" in t: apply_theme("holographic"); return "Back to holographic dark mode!"
    if "midnight mode" in t: apply_theme("midnight"); return "Midnight mode activated!"

    # VOICE PERSONALITY
    if any(x in t for x in ["friendly mode","be friendly","friendly voice"]): prefs["voice_personality"]="friendly"; sj(PREFS_FILE,prefs); return "Friendly mode on! Hey friend!"
    if any(x in t for x in ["professional mode","be professional","professional voice"]): prefs["voice_personality"]="professional"; sj(PREFS_FILE,prefs); return "Professional mode activated."
    if any(x in t for x in ["funny mode","be funny","funny voice"]): prefs["voice_personality"]="funny"; sj(PREFS_FILE,prefs); return "Funny mode ON! Brace yourself for terrible jokes."

    # TEACH NOVA
    m=re.search(r'when i say (.+?) do (.+)',t)
    if m: return learn_command(m.group(1).strip(),m.group(2).strip())
    if "teach jarvis" in t or "learn command" in t: return "Sure! Say: 'when I say [trigger] do [action]'"

    # MEMORY
    if any(x in t for x in ["remember that","remember this","save this","note that"]):
        fact=re.sub(r'(remember that|remember this|save this|note that)','',t).strip()
        remember(fact); return "Got it, I'll remember that!"
    if any(x in t for x in ["what do you remember","my info","what do you know about me"]):
        if not memory["facts"]: return "I don't know much about you yet. Tell me things and I'll remember!"
        recent=memory["facts"][-3:]
        return "Here's what I remember: "+". ".join(f["fact"] for f in recent)

    # TIME / DATE
    if any(x in t for x in ["what time","time is it","current time"]):
        n=datetime.datetime.now(); return f"It's {n.strftime('%I:%M %p')} on {n.strftime('%A, %B %d')}."
    if any(x in t for x in ["what date","today's date","what day"]):
        return f"Today is {datetime.datetime.now().strftime('%A, %B %d %Y')}."

    # DAILY BRIEFING
    if any(x in t for x in ["daily briefing","morning briefing","my briefing","brief me","what's my day"]): return get_daily_briefing()

    # MOTIVATION
    if any(x in t for x in ["motivate me","motivational quote","inspire me","i need motivation"]): return get_motivation()

    # BREATHING
    if any(x in t for x in ["breathing exercise","start breathing","calm me down","anxiety relief"]): return breathing_exercise()

    # SLEEP TRACKER
    if any(x in t for x in ["going to sleep","good night","i'm sleeping","sleep now","time to sleep"]):
        return start_sleep()
    if any(x in t for x in ["good morning","i woke up","just woke up","wake up sleep"]): return wake_up_sleep()
    if any(x in t for x in ["sleep stats","how much did i sleep","sleep tracker","my sleep"]): return sleep_stats()

    # POMODORO
    if any(x in t for x in ["pomodoro","focus mode","start focus","study mode"]):
        m2=re.search(r'(\d+)',t); mins=int(m2.group(1)) if m2 else 25
        return start_pomodoro(mins)
    if any(x in t for x in ["stop pomodoro","stop focus","end focus"]): return stop_pomodoro()

    # HABIT TRACKER
    if any(x in t for x in ["add habit","track habit","new habit"]):
        habit=re.sub(r'(add habit|track habit|new habit)','',t).strip()
        return add_habit(habit) if habit else "What habit? Say: 'add habit drink water'"
    if any(x in t for x in ["i did","completed","done with","just did","finished","drank water","exercised","meditated","studied","read","walked"]):
        for h in habits_data["habits"]:
            if h in t: return log_habit(h)
        # auto-detect preset habits
        for h in PRESET_HABITS:
            if h in t: add_habit(h); return log_habit(h)
        return "Which habit did you complete? Say: 'I did drink water'"
    if any(x in t for x in ["my habits","habit streak","show habits"]): 
        if not habits_data["habits"]: return "No habits tracked yet. Say: 'add habit drink water'"
        today=datetime.date.today().isoformat(); logged=habits_data["logs"].get(today,[])
        return f"Your habits: {', '.join(habits_data['habits'])}. Done today: {', '.join(logged) if logged else 'none yet'}."

    # EXPENSES
    if any(x in t for x in ["i spent","spent","expense","paid for","bought"]):
        return add_expense(t)
    if any(x in t for x in ["my expenses","expense summary","how much spent","spending"]):
        return expense_summary()

    # CRYPTO / CURRENCY
    if any(x in t for x in ["bitcoin price","ethereum price","crypto price"]):
        coin="bitcoin" if "bitcoin" in t else "ethereum" if "ethereum" in t else "bitcoin"
        return crypto_price(coin)
    if any(x in t for x in ["convert","usd to","npr to","currency"]):
        return convert_currency(t)

    # WIKIPEDIA
    if any(x in t for x in ["tell me about","what is","who is","wikipedia","search wikipedia"]):
        query=re.sub(r'(tell me about|what is|who is|wikipedia|search wikipedia)','',t).strip()
        if query and len(query)>2: return wiki_search(query)

    # PASSWORD VAULT
    if any(x in t for x in ["unlock vault","open vault","show passwords"]): return unlock_vault()
    if any(x in t for x in ["lock vault","secure vault"]): return lock_vault()
    if "password for" in t and "is" in t: return add_password(t)
    if "password for" in t: 
        site=t.replace("password for","").replace("password","").strip().split()[0]
        return get_password(site)

    # PC HEALTH
    if any(x in t for x in ["pc health","system health","cpu","ram usage","memory usage","pc status"]):
        try:
            cpu=psutil.cpu_percent(interval=1); ram=psutil.virtual_memory()
            disk=psutil.disk_usage('/'); bat=psutil.sensors_battery()
            bat_str=f"Battery {bat.percent:.0f}% {'(charging)' if bat.power_plugged else '(unplugged)'}." if bat else ""
            return f"CPU: {cpu}%, RAM: {ram.percent}% ({ram.available//1024//1024}MB free), Disk: {disk.percent}%. {bat_str}"
        except: return "Couldn't read PC health."

    # WEATHER / NEWS
    if any(x in t for x in ["weather","temperature"]): return get_weather(t.split(" in ")[-1].strip() if " in " in t else None)
    if any(x in t for x in ["news","headlines","what's happening"]):
        cat="tech" if "tech" in t else "sports" if "sport" in t else "general"; return get_news(cat)

    # ALARMS
    if any(x in t for x in ["set alarm","alarm at","wake me"]): return set_alarm(t)
    if any(x in t for x in ["remind me","set reminder"]): return set_reminder(t)

    # MUSIC
    if any(x in t for x in ["national anthem","jan gan man","vande mataram"]): return play_music("anthem")
    if any(x in t for x in ["next song","skip"]): return music_next()
    if any(x in t for x in ["previous song","go back song"]): return music_prev()
    if any(x in t for x in ["pause music","pause song"]): return music_toggle()
    if "stop music" in t: return music_stop()
    if any(x in t for x in ["play music","play a song","play "]): 
        q=re.sub(r'(play music|play a song|play)','',t).strip(); return play_music(q if len(q)>2 else None)

    # VOLUME
    if "mute" in t: pyautogui.press("volumemute"); return "Muted."
    if any(x in t for x in ["volume up","louder"]): [pyautogui.press("volumeup") for _ in range(5)]; return "Volume up!"
    if any(x in t for x in ["volume down","quieter"]): [pyautogui.press("volumedown") for _ in range(5)]; return "Volume down."

    # APPS
    if "whatsapp" in t:
        exp=os.path.expandvars(APP_PATHS["whatsapp"])
        if os.path.exists(exp): subprocess.Popen([exp]); return "WhatsApp open!"
        webbrowser.open("https://web.whatsapp.com"); return "WhatsApp Web open!"
    if "instagram" in t: webbrowser.open("https://www.instagram.com"); return "Instagram!"
    if "youtube" in t:
        q=t.replace("youtube","").replace("open","").strip()
        if len(q)>2: webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}"); return f"Searching YouTube for {q}!"
        webbrowser.open("https://www.youtube.com"); return "YouTube open!"
    if "open" in t:
        target=t.replace("open","").strip()
        if any(w in target for w in ["google","facebook","instagram","twitter","github","netflix","amazon","gmail"]):
            webbrowser.open(f"https://www.{target.strip().split()[0]}.com"); return f"Opening {target}!"
        for k,p in APP_PATHS.items():
            if k in target:
                exp=os.path.expandvars(p)
                if os.path.exists(exp): subprocess.Popen([exp]); return f"Opening {k}!"
        subprocess.Popen(f"start {target}",shell=True); return f"Opening {target}!"
    if any(x in t for x in ["search","google"]):
        q=re.sub(r'(search|google|for)','',t).strip()
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(q)}"); return f"Searching {q}!"

    # ── PHONE CALL CONTROL ──────────────────────────
    if any(x in t for x in ["receive call","answer call","pick up","attend call","call receive","accept call"]):
        if _call_state == "ringing":
            r = receive_call()
            if _ui_ref: _ui_ref.root.after(0, _ui_ref._close_call_popup)
            return r
        return "No incoming call right now."

    if any(x in t for x in ["reject call","decline call","cancel call","don't receive","not receive","ignore call","cut call","reject"]):
        if _call_state in ["ringing","in_call"]:
            r = reject_call() if _call_state=="ringing" else end_call()
            if _ui_ref: _ui_ref.root.after(0, _ui_ref._close_call_popup)
            return r
        return "No active call to reject."

    if any(x in t for x in ["end call","hang up","cut the call","disconnect call"]):
        r = end_call()
        if _ui_ref: _ui_ref.root.after(0, _ui_ref._close_call_popup)
        return r

    if any(x in t for x in ["call status","who is calling","any call","incoming call"]):
        if _call_state == "ringing": return f"Someone is calling from {_incoming_call_number}! Say 'receive call' or 'reject call'."
        if _call_state == "in_call": return f"You are on a call with {_incoming_call_number}. Say 'end call' to hang up."
        return "No active call."

    if any(x in t for x in ["phone battery","mobile battery","phone charge"]):
        return get_phone_battery()

    if any(x in t for x in ["phone screenshot","screenshot phone","mobile screenshot"]):
        return take_phone_screenshot()

    if any(x in t for x in ["phone notifications","mobile notifications","my notifications"]):
        return get_phone_notifications()

    if any(x in t for x in ["connect phone","phone monitor","watch my phone","monitor calls"]):
        return start_phone_monitor()

    if "call" in t and re.search(r'\d{7,}', t):
        num = re.search(r'[+\d]{7,}', t)
        if num: return open_phone_dialpad(num.group())

    if any(x in t for x in ["is my phone connected","phone connected","adb connected","phone status"]):
        if check_adb_connected(): return "Yes! Your phone is connected via ADB. Call monitoring is active."
        return "Phone not connected. Connect via USB and enable USB Debugging in Developer Options."
    if "screenshot" in t:
        p=os.path.join(os.path.expanduser("~"),"Desktop",f"ss_{int(time.time())}.png"); pyautogui.screenshot(p); return "Screenshot saved!"
    if "battery" in t:
        try:
            b=psutil.sensors_battery()
            if b: return f"Battery at {b.percent:.0f}%, {'charging' if b.power_plugged else 'not plugged in'}."
        except: pass
        return "Can't read battery."
    if any(x in t for x in ["joke","funny","make me laugh"]): return tell_joke()

    # PC POWER
    if "shutdown" in t: speak("Shutting down in 10!"); time.sleep(3); os.system("shutdown /s /t 7"); return "Shutting down!"
    if "restart" in t: speak("Restarting!"); time.sleep(3); os.system("shutdown /r /t 7"); return "Restarting!"
    if "lock" in t and ("pc" in t or "screen" in t): os.system("rundll32.exe user32.dll,LockWorkStation"); return "Locked."

    # CUSTOM ANSWERS
    if any(x in t for x in ["who made you","who created you","who built you","who developed you"]):
        return "I was built by Sonu Kumar Sah — he's the genius behind me!"
    if any(x in t for x in ["prime minister of nepal","nepal pm"]): return "The Prime Minister of Nepal is Balendra Shah."
    if any(x in t for x in ["what is nepal","about nepal"]): return "Nepal is a beautiful country in South Asia, home to Mount Everest and amazing culture!"
    if any(x in t for x in ["who are you","what are you","your name"]): return "I'm Jarvis v7.0 — your AI best friend, copilot, and personal assistant!"
    if any(x in t for x in ["how are you","what's up","you good"]): return random.choice(["Doing great! Ready for anything. What do you need?","All good! What's up?","Living my best AI life! How can I help?"])
    if any(x in t for x in ["i'm sad","feeling sad","i'm upset","i'm crying"]): return random.choice(["Hey... I'm really here for you. Want to talk about it?","That sounds hard. I'm listening — what happened?","Aww, you're not alone. Tell me more."])
    if any(x in t for x in ["i'm bored","so bored"]): return random.choice(["Bored? Want a joke, a habit challenge, or should I start a pomodoro session?","Okay boredom is illegal! Let's do something — what are you into?"])
    if any(x in t for x in ["thank you","thanks","you're amazing","love you jarvis"]): return random.choice(["Always! That's what I'm here for.","Of course! You know I've got you.","Anytime!"])
    if any(x in t for x in ["i'm tired","so tired","exhausted"]): return "Rest is productive too! Want me to track your sleep tonight? Just say 'going to sleep' when you hit the pillow."

    return None

# ═══════════════════════════════════════════════════════════════
#  NOVA UI v7.0 — Holographic + Tabs + 3D Face + Mini Widget
# ═══════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════
#   JARVIS UI v9  —  Modern Dark + Full Phone Control
# ══════════════════════════════════════════════════════════
class JarvisUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JARVIS — AI Copilot")
        self.root.geometry("1400x820")
        self.root.minsize(1100,700)
        self.root.configure(bg="#0a0a0f")
        self.root.resizable(True, True)

        # animation state
        self.face_blink=0; self.mouth_ph=0.0; self.eye_a=0.0
        self.wave_ph=0.0; self.title_ph=0.0
        self._typ_full=""; self._typ_pos=0
        self._alarm_frame=None
        self._call_win=None
        self._mini_widget=None
        self._active_tab="chat"
        self._phone_panel_built=False

        # colour palette
        self.C = {
            "bg":     "#0a0a0f",
            "bg2":    "#0f0f18",
            "bg3":    "#141420",
            "card":   "#13131e",
            "border": "#1e1e2e",
            "glass":  "#111120",
            "cyan":   "#00e5ff",
            "violet": "#8b5cf6",
            "pink":   "#f472b6",
            "green":  "#22c55e",
            "amber":  "#f59e0b",
            "red":    "#ef4444",
            "blue":   "#3b82f6",
            "orange": "#f97316",
            "text":   "#e2e8f0",
            "muted":  "#1e2035",
            "dim":    "#4a5568",
        }

        self.is_awake=False; self.is_listening=False
        self.is_thinking=False; self.is_speaking=False

        self._splash()

    # ── helpers ────────────────────────────────────
    def c(self, key): return self.C.get(key,"#888")
    def blend(self, c1, c2, r):
        try:
            r1,g1,b1=int(c1[1:3],16),int(c1[3:5],16),int(c1[5:7],16)
            r2,g2,b2=int(c2[1:3],16),int(c2[3:5],16),int(c2[5:7],16)
            return f"#{int(r1+(r2-r1)*r):02x}{int(g1+(g2-g1)*r):02x}{int(b1+(b2-b1)*r):02x}"
        except: return c1

    def fnt(self, size, weight="normal", family="Segoe UI"):
        try: return tkfont.Font(family=family, size=size, weight=weight)
        except: return tkfont.Font(size=size, weight=weight)

    # ── SPLASH ─────────────────────────────────────
    def _splash(self):
        sp = tk.Toplevel(); sp.overrideredirect(True)
        sw=sp.winfo_screenwidth(); sh=sp.winfo_screenheight()
        sp.geometry(f"480x300+{(sw-480)//2}+{(sh-300)//2}")
        sp.configure(bg=self.c("bg2"))
        tk.Frame(sp, bg=self.c("cyan"), height=2).pack(fill="x", side="top")
        tk.Frame(sp, bg=self.c("violet"), height=2).pack(fill="x", side="bottom")

        body = tk.Frame(sp, bg=self.c("bg2")); body.pack(expand=True, fill="both", padx=4)
        cv = tk.Canvas(body, width=90, height=90, bg=self.c("bg2"), highlightthickness=0)
        cv.pack(pady=(18,4)); self._sc=cv; self._sa=0; self._sn=sp; self._draw_sc()

        nrow = tk.Frame(body, bg=self.c("bg2")); nrow.pack()
        self._sp_name = tk.Label(nrow, text="JARVIS", font=self.fnt(34,"bold"), bg=self.c("bg2"), fg=self.c("cyan"))
        self._sp_name.pack(side="left")
        tk.Label(nrow, text="  AI Copilot v9", font=self.fnt(12), bg=self.c("bg2"), fg=self.c("dim")).pack(side="left", pady=12)
        tk.Label(body, text="Built by Sonu Kumar Sah  ·  Full Phone Control Edition",
                 font=self.fnt(8), bg=self.c("bg2"), fg=self.c("muted")).pack(pady=(2,14))

        pb_bg = tk.Frame(body, bg=self.c("border"), height=4); pb_bg.pack(fill="x", padx=60)
        self._spb = tk.Frame(pb_bg, bg=self.c("cyan"), height=4); self._spb.place(x=0,y=0,height=4)
        self._spl = tk.Label(body, text="", font=self.fnt(9), bg=self.c("bg2"), fg=self.c("dim")); self._spl.pack(pady=8)
        self._sp_tick(0)

    def _draw_sc(self):
        c=self._sc; c.delete("all"); cx=cy=45; self._sa=(self._sa+5)%360
        for r,col in [(42,self.c("violet")),(34,self.c("cyan")),(24,self.c("pink"))]:
            c.create_oval(cx-r,cy-r,cx+r,cy+r, outline=self.blend(self.c("bg2"),col,0.2), width=1)
        c.create_oval(cx-19,cy-19,cx+19,cy+19, fill=self.blend(self.c("bg2"),self.c("cyan"),0.55), outline=self.c("cyan"), width=2)
        for i in range(3):
            a=math.radians((self._sa+i*120)%360)
            dx=cx+38*math.cos(a); dy=cy+38*math.sin(a)
            c.create_oval(dx-4,dy-4,dx+4,dy+4, fill=[self.c("cyan"),self.c("pink"),self.c("violet")][i], outline="")

    def _sp_tick(self, step):
        self._draw_sc()
        msgs=["Booting AI Core...","Loading phone control...","Syncing contacts...","Setting up voice...","Almost ready!","Let's go!"]
        total=72
        if step<=total:
            p=step/total
            self._spb.place(x=0,y=0,height=4,width=max(0,int(self._spb.master.winfo_width()*p)))
            self._spl.config(text=msgs[min(int(p*(len(msgs)-1)),len(msgs)-1)])
            self._sp_name.config(fg=self.c("cyan") if int(time.time()*3)%2==0 else self.c("pink"))
            self._sn.after(38, self._sp_tick, step+1)
        else: self._sn.after(300, self._finish_splash)

    def _finish_splash(self):
        self._sn.destroy(); self._build(); self._start_timers()
        global _ui_ref, _phone_ui_ref; _ui_ref=self; _phone_ui_ref=self
        load_config(); _load_pl()
        # load contacts in background
        threading.Thread(target=load_phone_contacts, daemon=True).start()
        greeting = (
            "Happy New Year 2083! I'm Jarvis version 9 with full phone control. Clap twice or say Hey Jarvis to start!"
            if NEPAL_NEW_YEAR else
            "Jarvis version 9 online! Full phone control loaded. Clap twice or say Hey Jarvis!"
        )
        threading.Thread(target=lambda:speak(greeting), daemon=True).start()
        threading.Thread(target=self._wake_loop, daemon=True).start()

    # ── MAIN UI BUILD ──────────────────────────────
    def _build(self):
        root = self.root; root.configure(bg=self.c("bg"))

        # ── TOP HEADER ──────────────────────────────
        hdr = tk.Frame(root, bg=self.c("bg2"), height=56)
        hdr.pack(fill="x"); hdr.pack_propagate(False)

        # Left: logo
        ll = tk.Frame(hdr, bg=self.c("bg2")); ll.pack(side="left", padx=16, pady=8)
        self._title_lbl = tk.Label(ll, text="J A R V I S", font=self.fnt(18,"bold"), bg=self.c("bg2"), fg=self.c("cyan"))
        self._title_lbl.pack(side="left")
        tk.Label(ll, text="  AI COPILOT  v9", font=self.fnt(8), bg=self.c("bg2"), fg=self.c("dim")).pack(side="left", pady=14)
        self._mood_lbl = tk.Label(ll, text="😊", font=self.fnt(14), bg=self.c("bg2"))
        self._mood_lbl.pack(side="left", padx=10)

        # Phone status pill
        self._phone_pill = tk.Label(hdr, text="📱 Phone: Checking...", font=self.fnt(9,"bold"),
                                     bg=self.blend(self.c("bg2"),self.c("amber"),0.15),
                                     fg=self.c("amber"), padx=10, pady=3)
        self._phone_pill.pack(side="left", padx=10, pady=16)

        # Right: action buttons + clock
        rr = tk.Frame(hdr, bg=self.c("bg2")); rr.pack(side="right", padx=10)
        for txt,cmd,clr in [("📖 Help",self._show_help,self.c("green")),
                             ("⚙",self._settings_win,self.c("blue")),
                             ("📰",self._news_win,self.c("orange")),
                             ("⏰",self._alarm_win,self.c("amber")),
                             ("🪟",self._toggle_mini,self.c("pink"))]:
            tk.Button(rr, text=txt, font=self.fnt(10), bg=self.c("bg3"), fg=clr,
                      activebackground=self.c("border"), activeforeground=clr,
                      relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                      command=cmd).pack(side="left", padx=2, pady=14)
        self._dot_cv = tk.Canvas(rr,width=10,height=10,bg=self.c("bg2"),highlightthickness=0)
        self._dot_cv.pack(side="left",pady=22,padx=(8,0))
        self._dot = self._dot_cv.create_oval(1,1,9,9,fill=self.c("green"),outline="")
        self._clk_lbl = tk.Label(rr, text="", font=self.fnt(10), bg=self.c("bg2"), fg=self.c("dim"))
        self._clk_lbl.pack(side="left", padx=(6,8), pady=16)

        # New Year banner
        if NEPAL_NEW_YEAR:
            self._ny_f = tk.Frame(root, bg=self.blend(self.c("bg"),self.c("amber"),0.07))
            self._ny_f.pack(fill="x")
            self._ny_txt="🎉 Happy New Year 2083  ·  Shubha Naya Barsha  ·  नया वर्ष २०८३  ·  May 2083 be your best year!  ✨  "
            self._ny_off=0
            self._ny_lbl=tk.Label(self._ny_f, text="", font=self.fnt(9,"bold"),
                                   bg=self.blend(self.c("bg"),self.c("amber"),0.07),
                                   fg=self.c("amber"), pady=3)
            self._ny_lbl.pack()
        tk.Frame(root, bg=self.c("border"), height=1).pack(fill="x")

        # ── MAIN 3-COLUMN LAYOUT ────────────────────
        main = tk.Frame(root, bg=self.c("bg")); main.pack(fill="both", expand=True)

        # ── COL A: Face + Controls (280px) ──────────
        colA = tk.Frame(main, bg=self.c("bg"), width=280)
        colA.pack(side="left", fill="y"); colA.pack_propagate(False)
        tk.Frame(main, bg=self.c("border"), width=1).pack(side="left", fill="y")

        self._face_cv = tk.Canvas(colA, width=260, height=255, bg=self.c("bg"), highlightthickness=0)
        self._face_cv.pack(pady=(12,2), padx=10)

        self._st_lbl = tk.Label(colA, text='👏 Clap or say "Hey Jarvis"',
                                 font=self.fnt(9,"bold"), bg=self.c("bg"), fg=self.c("dim"), wraplength=250, justify="center")
        self._st_lbl.pack(pady=(0,4))

        self._wave_cv = tk.Canvas(colA, width=260, height=32, bg=self.c("bg"), highlightthickness=0)
        self._wave_cv.pack(pady=(0,6))

        # Speak / Wake row
        br = tk.Frame(colA, bg=self.c("bg")); br.pack(fill="x", padx=14, pady=(0,4))
        self._mic_btn = tk.Button(br, text="🎤 Speak", font=self.fnt(10,"bold"),
                                   bg=self.c("cyan"), fg=self.c("bg"),
                                   activebackground=self.c("green"), activeforeground=self.c("bg"),
                                   relief="flat", cursor="hand2", padx=10, pady=8, bd=0,
                                   command=self._toggle_mic)
        self._mic_btn.pack(side="left", fill="x", expand=True, padx=(0,4))
        self._wake_btn = tk.Button(br, text="⚡ Wake", font=self.fnt(10,"bold"),
                                    bg=self.c("bg3"), fg=self.c("violet"),
                                    activebackground=self.c("violet"), activeforeground=self.c("bg"),
                                    relief="flat", cursor="hand2", padx=10, pady=8, bd=0,
                                    command=self._toggle_wake)
        self._wake_btn.pack(side="left", fill="x", expand=True, padx=(4,0))

        # Quick icons
        qi = tk.Frame(colA, bg=self.c("glass"), highlightbackground=self.c("border"), highlightthickness=1)
        qi.pack(fill="x", padx=10, pady=(2,4))
        tk.Label(qi, text="QUICK", font=self.fnt(8,"bold"), bg=self.c("glass"), fg=self.c("dim")).pack(anchor="w", padx=10, pady=(5,2))
        qa_row = tk.Frame(qi, bg=self.c("glass")); qa_row.pack(fill="x", padx=6, pady=(0,6))
        for emoji,clr,cmd in [("⏰",self.c("amber"),"what time"),("🌤",self.c("blue"),"weather"),
                               ("🔋",self.c("green"),"battery"),("😄",self.c("pink"),"joke"),
                               ("🧘",self.c("violet"),"breathing"),("💻",self.c("orange"),"pc health"),
                               ("🎊",self.c("amber"),"new year"),("📱",self.c("cyan"),"phone info")]:
            tk.Button(qa_row, text=emoji, font=self.fnt(13), bg=self.c("glass"), fg=clr,
                      activebackground=self.c("border"), relief="flat", bd=0,
                      padx=6, pady=5, cursor="hand2",
                      command=lambda c=cmd:self._quick(c)).pack(side="left", padx=2)

        # Music card
        mc = tk.Frame(colA, bg=self.c("glass"), highlightbackground=self.c("border"), highlightthickness=1)
        mc.pack(fill="x", padx=10, pady=(0,4))
        mhdr = tk.Frame(mc, bg=self.c("glass")); mhdr.pack(fill="x", padx=10, pady=(6,2))
        tk.Label(mhdr, text="♫", font=self.fnt(11), bg=self.c("glass"), fg=self.c("cyan")).pack(side="left")
        tk.Label(mhdr, text="  NOW PLAYING", font=self.fnt(8,"bold"), bg=self.c("glass"), fg=self.c("dim")).pack(side="left")
        self._song_lbl = tk.Label(mc, text="Nothing playing",
                                   font=self.fnt(9,"bold"), bg=self.c("glass"), fg=self.c("pink"),
                                   wraplength=240, justify="center")
        self._song_lbl.pack(padx=10, pady=(0,4))
        pb_bg = tk.Frame(mc, bg=self.c("border"), height=2); pb_bg.pack(fill="x", padx=10, pady=(0,4))
        self._prog = tk.Frame(pb_bg, bg=self.c("pink"), height=2); self._prog.place(x=0,y=0,height=2)
        mc_c = tk.Frame(mc, bg=self.c("glass")); mc_c.pack(pady=(0,6))
        mbs = dict(font=self.fnt(14), bg=self.c("glass"), relief="flat", bd=0, cursor="hand2", activebackground=self.c("glass"))
        tk.Button(mc_c,text="⏮",fg=self.c("dim"),activeforeground=self.c("cyan"),command=lambda:threading.Thread(target=music_prev,daemon=True).start(),**mbs).pack(side="left",padx=4)
        self._pp=tk.Button(mc_c,text="▶",fg=self.c("pink"),activeforeground=self.c("cyan"),command=lambda:threading.Thread(target=music_toggle,daemon=True).start(),**mbs); self._pp.pack(side="left",padx=4)
        tk.Button(mc_c,text="⏭",fg=self.c("dim"),activeforeground=self.c("cyan"),command=lambda:threading.Thread(target=music_next,daemon=True).start(),**mbs).pack(side="left",padx=4)
        tk.Button(mc_c,text="⏹",fg=self.c("dim"),activeforeground=self.c("red"),command=lambda:threading.Thread(target=music_stop,daemon=True).start(),**mbs).pack(side="left",padx=4)
        vr = tk.Frame(mc, bg=self.c("glass")); vr.pack(pady=(0,8))
        tk.Label(vr,text="🔈",font=self.fnt(9),bg=self.c("glass"),fg=self.c("dim")).pack(side="left")
        self._vol=tk.Scale(vr,from_=0,to=100,orient="horizontal",length=160,bg=self.c("glass"),fg=self.c("violet"),troughcolor=self.c("border"),highlightthickness=0,relief="flat",sliderlength=12,width=5,showvalue=False,command=lambda v:pygame.mixer.music.set_volume(int(v)/100))
        self._vol.set(80); pygame.mixer.music.set_volume(0.8); self._vol.pack(side="left",padx=4)
        tk.Label(vr,text="🔊",font=self.fnt(9),bg=self.c("glass"),fg=self.c("dim")).pack(side="left")

        # ── COL B: Chat + Tabs (520px) ──────────────
        colB = tk.Frame(main, bg=self.c("bg"), width=540)
        colB.pack(side="left", fill="both", expand=False); colB.pack_propagate(False)
        tk.Frame(main, bg=self.c("border"), width=1).pack(side="left", fill="y")

        # Tab bar
        tab_bar = tk.Frame(colB, bg=self.c("bg2")); tab_bar.pack(fill="x")
        self._tabs={}; self._tab_frames={}
        tabs=[("💬","chat",self.c("cyan")),("📝","notes",self.c("green")),
              ("✅","tasks",self.c("amber")),("🛒","shop",self.c("pink")),
              ("💪","habits",self.c("violet")),("😴","sleep",self.c("blue")),
              ("💰","expenses",self.c("orange"))]
        for lbl,key,clr in tabs:
            b=tk.Button(tab_bar,text=lbl,font=self.fnt(13),bg=self.c("bg2"),fg=self.c("dim"),
                        activebackground=self.c("bg3"),activeforeground=clr,
                        relief="flat",bd=0,padx=14,pady=8,cursor="hand2",
                        command=lambda k=key,c=clr:self._switch_tab(k,c))
            b.pack(side="left"); self._tabs[key]=(b,clr)
        tk.Frame(colB,bg=self.c("border"),height=1).pack(fill="x")
        tc = tk.Frame(colB,bg=self.c("bg")); tc.pack(fill="both",expand=True)

        # CHAT TAB
        cf=tk.Frame(tc,bg=self.c("bg")); self._tab_frames["chat"]=cf
        sb=tk.Scrollbar(cf,bg=self.c("bg3"),troughcolor=self.c("bg")); sb.pack(side="right",fill="y")
        self._chat=tk.Text(cf,font=self.fnt(11),bg=self.c("bg"),fg=self.c("text"),
                            insertbackground=self.c("cyan"),relief="flat",bd=0,wrap="word",
                            state="disabled",yscrollcommand=sb.set,padx=16,pady=10,spacing1=6,spacing3=6,cursor="arrow")
        self._chat.pack(fill="both",expand=True); sb.config(command=self._chat.yview)
        self._chat.tag_config("you_n",foreground=self.c("violet"),font=self.fnt(10,"bold"))
        self._chat.tag_config("jrv_n",foreground=self.c("cyan"),font=self.fnt(10,"bold"))
        self._chat.tag_config("you_m",foreground=self.blend(self.c("bg"),self.c("violet"),0.9))
        self._chat.tag_config("jrv_m",foreground=self.c("text"))
        self._chat.tag_config("sys",foreground=self.c("dim"),font=self.fnt(9))
        self._chat.tag_config("ts",foreground=self.c("dim"),font=self.fnt(8))

        # NOTES TAB
        nf=tk.Frame(tc,bg=self.c("bg")); self._tab_frames["notes"]=nf
        nc=tk.Frame(nf,bg=self.c("bg")); nc.pack(fill="x",padx=12,pady=8)
        tk.Label(nc,text="📝 Notes & Diary",font=self.fnt(11,"bold"),bg=self.c("bg"),fg=self.c("green")).pack(side="left")
        tk.Button(nc,text="+ Add",font=self.fnt(9),bg=self.c("green"),fg=self.c("bg"),relief="flat",bd=0,padx=10,pady=4,cursor="hand2",command=self._add_note_ui).pack(side="right")
        nsf=tk.Frame(nf,bg=self.c("bg")); nsf.pack(fill="both",expand=True,padx=12,pady=(0,10))
        nsb=tk.Scrollbar(nsf,bg=self.c("bg3"),troughcolor=self.c("bg")); nsb.pack(side="right",fill="y")
        self._notes_list=tk.Text(nsf,font=self.fnt(11),bg=self.c("bg"),fg=self.c("text"),relief="flat",bd=0,wrap="word",state="disabled",yscrollcommand=nsb.set,padx=10,pady=8,spacing1=4)
        self._notes_list.pack(fill="both",expand=True); nsb.config(command=self._notes_list.yview)
        self._notes_list.tag_config("nh",foreground=self.c("green"),font=self.fnt(9,"bold"))
        self._notes_list.tag_config("nb",foreground=self.c("text"))
        self._refresh_notes()

        # TASKS TAB
        tf=tk.Frame(tc,bg=self.c("bg")); self._tab_frames["tasks"]=tf
        tcc=tk.Frame(tf,bg=self.c("bg")); tcc.pack(fill="x",padx=12,pady=8)
        tk.Label(tcc,text="✅ Tasks",font=self.fnt(11,"bold"),bg=self.c("bg"),fg=self.c("amber")).pack(side="left")
        tk.Button(tcc,text="+ Add",font=self.fnt(9),bg=self.c("amber"),fg=self.c("bg"),relief="flat",bd=0,padx=10,pady=4,cursor="hand2",command=self._add_task_ui).pack(side="right")
        self._task_list=tk.Frame(tf,bg=self.c("bg")); self._task_list.pack(fill="both",expand=True,padx=12)
        self._refresh_tasks()

        # SHOPPING TAB
        sf=tk.Frame(tc,bg=self.c("bg")); self._tab_frames["shop"]=sf
        sc=tk.Frame(sf,bg=self.c("bg")); sc.pack(fill="x",padx=12,pady=8)
        tk.Label(sc,text="🛒 Shopping",font=self.fnt(11,"bold"),bg=self.c("bg"),fg=self.c("pink")).pack(side="left")
        tk.Button(sc,text="+ Add",font=self.fnt(9),bg=self.c("pink"),fg=self.c("bg"),relief="flat",bd=0,padx=10,pady=4,cursor="hand2",command=self._add_shop_ui).pack(side="right")
        self._shop_list=tk.Frame(sf,bg=self.c("bg")); self._shop_list.pack(fill="both",expand=True,padx=12)
        self._refresh_shopping()

        # HABITS TAB
        hf=tk.Frame(tc,bg=self.c("bg")); self._tab_frames["habits"]=hf
        hcc=tk.Frame(hf,bg=self.c("bg")); hcc.pack(fill="x",padx=12,pady=8)
        tk.Label(hcc,text="💪 Habits",font=self.fnt(11,"bold"),bg=self.c("bg"),fg=self.c("violet")).pack(side="left")
        tk.Button(hcc,text="+ Add",font=self.fnt(9),bg=self.c("violet"),fg=self.c("bg"),relief="flat",bd=0,padx=10,pady=4,cursor="hand2",command=self._add_habit_ui).pack(side="right")
        self._habit_frame=tk.Frame(hf,bg=self.c("bg")); self._habit_frame.pack(fill="both",expand=True,padx=12)
        self._refresh_habits()

        # SLEEP TAB
        slp=tk.Frame(tc,bg=self.c("bg")); self._tab_frames["sleep"]=slp
        tk.Label(slp,text="😴 Sleep Tracker",font=self.fnt(11,"bold"),bg=self.c("bg"),fg=self.c("blue")).pack(anchor="w",padx=14,pady=(12,6))
        slpc=tk.Frame(slp,bg=self.c("bg")); slpc.pack(fill="x",padx=14,pady=(0,8))
        tk.Button(slpc,text="😴 Going to Sleep",font=self.fnt(10,"bold"),bg=self.c("blue"),fg=self.c("bg"),relief="flat",bd=0,padx=14,pady=8,cursor="hand2",
                  command=lambda:self._process("going to sleep")).pack(side="left",padx=(0,8))
        tk.Button(slpc,text="☀️ Good Morning",font=self.fnt(10,"bold"),bg=self.c("amber"),fg=self.c("bg"),relief="flat",bd=0,padx=14,pady=8,cursor="hand2",
                  command=lambda:self._process("good morning")).pack(side="left")
        self._sleep_frame=tk.Frame(slp,bg=self.c("bg")); self._sleep_frame.pack(fill="both",expand=True,padx=14)
        self._refresh_sleep()

        # EXPENSES TAB
        ef=tk.Frame(tc,bg=self.c("bg")); self._tab_frames["expenses"]=ef
        ecc=tk.Frame(ef,bg=self.c("bg")); ecc.pack(fill="x",padx=12,pady=8)
        tk.Label(ecc,text="💰 Expenses",font=self.fnt(11,"bold"),bg=self.c("bg"),fg=self.c("orange")).pack(side="left")
        tk.Button(ecc,text="+ Add",font=self.fnt(9),bg=self.c("orange"),fg=self.c("bg"),relief="flat",bd=0,padx=10,pady=4,cursor="hand2",command=self._add_expense_ui).pack(side="right")
        self._expense_frame=tk.Frame(ef,bg=self.c("bg")); self._expense_frame.pack(fill="both",expand=True,padx=12)
        self._refresh_expenses()

        # Input bar
        ib=tk.Frame(colB,bg=self.c("bg2"),pady=8); ib.pack(fill="x",padx=12,pady=(4,8))
        inp_b=tk.Frame(ib,bg=self.c("cyan"),pady=1,padx=1); inp_b.pack(fill="x",side="left",expand=True)
        inp_i=tk.Frame(inp_b,bg=self.c("bg3")); inp_i.pack(fill="x")
        self._inp=tk.Entry(inp_i,font=self.fnt(12),bg=self.c("bg3"),fg=self.c("text"),
                            insertbackground=self.c("cyan"),relief="flat",bd=0,highlightthickness=0)
        self._inp.pack(fill="x",padx=14,pady=9,side="left",expand=True)
        self._inp.bind("<Return>",self._send)
        ph="Ask Jarvis anything..."; self._inp.insert(0,ph); self._inp.config(fg=self.c("dim"))
        self._inp.bind("<FocusIn>",lambda e:(self._inp.delete(0,"end"),self._inp.config(fg=self.c("text"))) if self._inp.get()==ph else None)
        self._inp.bind("<FocusOut>",lambda e:(self._inp.insert(0,ph),self._inp.config(fg=self.c("dim"))) if not self._inp.get() else None)
        tk.Button(inp_i,text="➤",font=self.fnt(14),bg=self.c("cyan"),fg=self.c("bg"),
                  activebackground=self.c("green"),activeforeground=self.c("bg"),
                  relief="flat",bd=0,padx=14,pady=6,cursor="hand2",command=self._send).pack(side="right",padx=5,pady=3)

        self._switch_tab("chat",self.c("cyan"))

        # ── COL C: Phone Dashboard (right) ──────────
        colC = tk.Frame(main, bg=self.c("bg2")); colC.pack(side="left", fill="both", expand=True)
        self._build_phone_panel(colC)

        # Welcome messages
        self._add_sys('✦ Jarvis v9 — Clap 👏👏 or say "Hey Jarvis". Full phone control active.')
        if NEPAL_NEW_YEAR: self._add_sys("🎉 Happy New Year 2083! Shubha Naya Barsha!")

    # ── PHONE PANEL (right column) ──────────────────
    def _build_phone_panel(self, parent):
        """Right panel — full phone control dashboard."""
        self._phone_parent = parent

        # Header
        ph=tk.Frame(parent,bg=self.c("bg2"),height=44); ph.pack(fill="x"); ph.pack_propagate(False)
        tk.Label(ph,text="📱  PHONE DASHBOARD",font=self.fnt(11,"bold"),bg=self.c("bg2"),fg=self.c("cyan")).pack(side="left",padx=14,pady=10)
        self._phone_conn_lbl=tk.Label(ph,text="● Offline",font=self.fnt(9,"bold"),bg=self.c("bg2"),fg=self.c("red"))
        self._phone_conn_lbl.pack(side="right",padx=14,pady=12)
        tk.Frame(parent,bg=self.c("border"),height=1).pack(fill="x")

        sc=tk.Frame(parent,bg=self.c("bg2")); sc.pack(fill="both",expand=True)

        # Scrollable content
        vsb=tk.Scrollbar(sc); vsb.pack(side="right",fill="y")
        canvas=tk.Canvas(sc,bg=self.c("bg2"),highlightthickness=0,yscrollcommand=vsb.set)
        canvas.pack(side="left",fill="both",expand=True)
        vsb.config(command=canvas.yview)
        self._phone_scroll_frame=tk.Frame(canvas,bg=self.c("bg2"))
        canvas.create_window((0,0),window=self._phone_scroll_frame,anchor="nw")
        self._phone_scroll_frame.bind("<Configure>",lambda e:canvas.config(scrollregion=canvas.bbox("all")))
        self._pcf=self._phone_scroll_frame
        self._phone_panel_built=True
        self._refresh_phone_panel()

    def _refresh_phone_panel(self):
        if not self._phone_panel_built: return
        for w in self._pcf.winfo_children(): w.destroy()
        pcf=self._pcf; pad=12

        def card(title,color):
            f=tk.Frame(pcf,bg=self.c("glass"),highlightbackground=color,highlightthickness=1)
            f.pack(fill="x",padx=pad,pady=4)
            hdr=tk.Frame(f,bg=self.c("glass")); hdr.pack(fill="x",padx=10,pady=(8,4))
            tk.Label(hdr,text=title,font=self.fnt(9,"bold"),bg=self.c("glass"),fg=color).pack(side="left")
            return f

        # ── CONNECTION STATUS ──
        connected=check_adb_connected()
        conn_color=self.c("green") if connected else self.c("red")
        conn_text="● Connected via ADB" if connected else "● Not Connected"
        self._phone_conn_lbl.config(text=conn_text,fg=conn_color)
        self._phone_pill.config(text=f"📱 Phone: {'Connected ✓' if connected else 'Connect USB'}",
                                 fg=self.c("green") if connected else self.c("amber"))

        # ── CALL STATUS CARD ──
        call_card=card("📞  CALL CONTROL",self.c("cyan") if _call_state=="idle" else self.c("green") if _call_state=="in_call" else self.c("amber"))
        cs_row=tk.Frame(call_card,bg=self.c("glass")); cs_row.pack(fill="x",padx=10,pady=(0,4))
        state_txt={"idle":"No active call","ringing":f"📲 Ringing: {_incoming_call_name or _incoming_call_number}","in_call":f"📞 In call: {_incoming_call_name or _incoming_call_number}"}
        state_col={"idle":self.c("dim"),"ringing":self.c("amber"),"in_call":self.c("green")}
        tk.Label(cs_row,text=state_txt.get(_call_state,""),font=self.fnt(10,"bold"),bg=self.c("glass"),fg=state_col.get(_call_state,self.c("dim"))).pack(side="left")
        btn_row=tk.Frame(call_card,bg=self.c("glass")); btn_row.pack(fill="x",padx=10,pady=(0,10))
        def call_btn(txt,clr,cmd):
            tk.Button(btn_row,text=txt,font=self.fnt(9,"bold"),bg=clr,fg=self.c("bg"),relief="flat",bd=0,padx=10,pady=6,cursor="hand2",command=cmd).pack(side="left",padx=3)
        if _call_state=="ringing":
            call_btn("✅ Receive",self.c("green"),lambda:(receive_call(),self._close_call_popup(),self._add_sys("📱 Call received!")))
            call_btn("❌ Reject","#ef4444",lambda:(reject_call(),self._close_call_popup(),self._add_sys("📱 Call rejected.")))
        elif _call_state=="in_call":
            call_btn("📴 End Call","#ef4444",lambda:(end_call(),self._add_sys("📱 Call ended.")))
        else:
            call_btn("📞 Dial",self.c("cyan"),lambda:self._quick("open phone dialpad"))
            call_btn("📱 Keypad",self.c("violet"),lambda:phone_open_app("phone"))

        # ── PHONE INFO CARD ──
        if connected:
            try:
                info_card=card("ℹ️  PHONE INFO",self.c("blue"))
                info=get_phone_info()
                for label,val in [("Model",info.get("model","?")),("Android",info.get("android","?")),("Battery",f"{info.get('battery','?')} {info.get('status','')}")]:
                    row=tk.Frame(info_card,bg=self.c("glass")); row.pack(fill="x",padx=10,pady=2)
                    tk.Label(row,text=label+":",font=self.fnt(9),bg=self.c("glass"),fg=self.c("dim"),width=10,anchor="w").pack(side="left")
                    tk.Label(row,text=str(val),font=self.fnt(9,"bold"),bg=self.c("glass"),fg=self.c("text")).pack(side="left")
            except: pass

        # ── QUICK CONTROLS CARD ──
        qc=card("⚡  QUICK CONTROLS",self.c("violet"))
        qcr1=tk.Frame(qc,bg=self.c("glass")); qcr1.pack(fill="x",padx=10,pady=(0,4))
        qcr2=tk.Frame(qc,bg=self.c("glass")); qcr2.pack(fill="x",padx=10,pady=(0,8))
        def qbtn(parent,txt,clr,cmd):
            tk.Button(parent,text=txt,font=self.fnt(8,"bold"),bg=self.blend(self.c("glass"),clr,0.2),
                      fg=clr,relief="flat",bd=0,padx=8,pady=6,cursor="hand2",highlightthickness=1,
                      highlightbackground=clr,command=cmd).pack(side="left",padx=2,pady=2)
        qbtn(qcr1,"🔦 Torch On",self.c("amber"),lambda:threading.Thread(target=lambda:(phone_torch(True),self._add_sys("🔦 Torch on")),daemon=True).start())
        qbtn(qcr1,"🔦 Torch Off",self.c("dim"),lambda:threading.Thread(target=lambda:(phone_torch(False),self._add_sys("🔦 Torch off")),daemon=True).start())
        qbtn(qcr1,"📱 Screen On",self.c("green"),lambda:threading.Thread(target=lambda:(phone_screen(True),self._add_sys("📱 Screen on")),daemon=True).start())
        qbtn(qcr1,"📵 Screen Off",self.c("red"),lambda:threading.Thread(target=lambda:(phone_screen(False),self._add_sys("📵 Screen off")),daemon=True).start())
        qbtn(qcr2,"📶 WiFi On",self.c("blue"),lambda:threading.Thread(target=lambda:(phone_wifi(True),self._add_sys("📶 WiFi on")),daemon=True).start())
        qbtn(qcr2,"📵 WiFi Off",self.c("dim"),lambda:threading.Thread(target=lambda:(phone_wifi(False),self._add_sys("📵 WiFi off")),daemon=True).start())
        qbtn(qcr2,"🔵 BT On",self.c("cyan"),lambda:threading.Thread(target=lambda:(phone_bluetooth(True),self._add_sys("🔵 Bluetooth on")),daemon=True).start())
        qbtn(qcr2,"🔵 BT Off",self.c("dim"),lambda:threading.Thread(target=lambda:(phone_bluetooth(False),self._add_sys("🔵 Bluetooth off")),daemon=True).start())

        # ── APP LAUNCHER CARD ──
        al=card("📲  APP LAUNCHER",self.c("orange"))
        alr=tk.Frame(al,bg=self.c("glass")); alr.pack(fill="x",padx=10,pady=(0,8))
        apps=[("💬","WhatsApp","whatsapp"),("📷","Camera","camera"),("🎵","Music","music"),
              ("🌐","Chrome","chrome"),("📸","Gallery","gallery"),("⚙️","Settings","settings"),
              ("🗺️","Maps","maps"),("✉️","SMS","messages")]
        for emoji,name,pkg in apps:
            fr=tk.Frame(alr,bg=self.c("glass")); fr.pack(side="left",padx=3)
            tk.Button(fr,text=emoji,font=self.fnt(18),bg=self.c("glass"),fg=self.c("text"),
                      relief="flat",bd=0,padx=6,pady=4,cursor="hand2",
                      command=lambda p=pkg:threading.Thread(target=lambda:(phone_open_app(p),self._add_sys(f"📱 Opening {p} on phone")),daemon=True).start()).pack()
            tk.Label(fr,text=name,font=self.fnt(7),bg=self.c("glass"),fg=self.c("dim")).pack()

        # ── MEDIA CONTROLS CARD ──
        mdc=card("🎵  PHONE MEDIA",self.c("pink"))
        mdr=tk.Frame(mdc,bg=self.c("glass")); mdr.pack(fill="x",padx=10,pady=(0,8))
        for txt,clr,act in [("⏮","#888","previous"),("▶/⏸",self.c("pink"),"play"),("⏭","#888","next"),("🔉",self.c("blue"),"volume_down"),("🔊",self.c("green"),"volume_up")]:
            tk.Button(mdr,text=txt,font=self.fnt(16),bg=self.c("glass"),fg=clr,
                      relief="flat",bd=0,padx=8,pady=6,cursor="hand2",
                      command=lambda a=act:threading.Thread(target=lambda:phone_media_control(a),daemon=True).start()).pack(side="left",padx=4)

        # ── RECENT CALLS CARD ──
        if connected:
            try:
                rc_card=card("📋  RECENT CALLS",self.c("green"))
                calls=get_call_log()[:5]
                if not calls:
                    tk.Label(rc_card,text="No call history",font=self.fnt(9),bg=self.c("glass"),fg=self.c("dim")).pack(padx=10,pady=6)
                for call in calls:
                    row=tk.Frame(rc_card,bg=self.c("glass")); row.pack(fill="x",padx=10,pady=2)
                    type_icons={"Incoming":"📲","Outgoing":"📞","Missed":"❌","Rejected":"🚫"}
                    icon=type_icons.get(call["type"],"📱")
                    tk.Label(row,text=f"{icon} {call['name'][:20]}",font=self.fnt(9),bg=self.c("glass"),fg=self.c("text"),anchor="w").pack(side="left",fill="x",expand=True)
                    tk.Label(row,text=call["type"],font=self.fnt(8),bg=self.c("glass"),fg=self.c("dim")).pack(side="right",padx=4)
                    tk.Button(row,text="📞",font=self.fnt(9),bg=self.c("glass"),fg=self.c("green"),relief="flat",bd=0,cursor="hand2",
                              command=lambda n=call["number"]:threading.Thread(target=lambda:open_phone_dialpad(n),daemon=True).start()).pack(side="right",padx=2)
            except: pass

        # ── CONTACTS CARD ──
        if _contacts_cache:
            cont_card=card(f"👥  CONTACTS ({len(_contacts_cache)})",self.c("blue"))
            # search box
            sv=tk.StringVar()
            sf=tk.Frame(cont_card,bg=self.c("glass")); sf.pack(fill="x",padx=10,pady=(0,4))
            se=tk.Entry(sf,textvariable=sv,font=self.fnt(10),bg=self.c("bg3"),fg=self.c("text"),
                        insertbackground=self.c("cyan"),relief="flat",bd=0)
            se.pack(fill="x",padx=4,pady=6)
            se.insert(0,"Search contact..."); se.config(fg=self.c("dim"))
            se.bind("<FocusIn>",lambda e:(se.delete(0,"end"),se.config(fg=self.c("text"))) if se.get()=="Search contact..." else None)
            cont_list_f=tk.Frame(cont_card,bg=self.c("glass")); cont_list_f.pack(fill="x",padx=10,pady=(0,8))
            def render_contacts(query=""):
                for w in cont_list_f.winfo_children(): w.destroy()
                items=sorted(_contacts_cache.items(),key=lambda x:x[1])
                if query: items=[(n,nm) for n,nm in items if query.lower() in nm.lower()]
                for num,name in items[:15]:
                    row=tk.Frame(cont_list_f,bg=self.c("glass")); row.pack(fill="x",pady=1)
                    tk.Label(row,text=f"👤 {name[:22]}",font=self.fnt(9),bg=self.c("glass"),fg=self.c("text"),anchor="w").pack(side="left",fill="x",expand=True,padx=4)
                    tk.Label(row,text=num[-10:],font=self.fnt(8),bg=self.c("glass"),fg=self.c("dim")).pack(side="left",padx=4)
                    tk.Button(row,text="📞",font=self.fnt(9),bg=self.c("glass"),fg=self.c("green"),relief="flat",bd=0,cursor="hand2",
                              command=lambda n=num:threading.Thread(target=lambda:open_phone_dialpad(n),daemon=True).start()).pack(side="right",padx=2)
                    tk.Button(row,text="💬",font=self.fnt(9),bg=self.c("glass"),fg=self.c("blue"),relief="flat",bd=0,cursor="hand2",
                              command=lambda n=num:threading.Thread(target=lambda:send_sms_via_phone(n,""),daemon=True).start()).pack(side="right",padx=1)
            render_contacts()
            sv.trace("w",lambda *a:render_contacts(sv.get()))
        else:
            no_cont=card("👥  CONTACTS",self.c("blue"))
            tk.Label(no_cont,text="Connect phone to load contacts",font=self.fnt(9),bg=self.c("glass"),fg=self.c("dim")).pack(padx=10,pady=8)
            tk.Button(no_cont,text="🔄 Load Contacts",font=self.fnt(9,"bold"),bg=self.c("blue"),fg=self.c("bg"),
                      relief="flat",bd=0,padx=12,pady=6,cursor="hand2",
                      command=lambda:threading.Thread(target=lambda:(load_phone_contacts(),self._refresh_phone_panel()),daemon=True).start()).pack(padx=10,pady=(0,10))

        # ── SMS PREVIEW CARD ──
        if connected:
            try:
                sms_card=card("💬  LATEST SMS",self.c("violet"))
                msgs=get_sms_log()[:4]
                if not msgs:
                    tk.Label(sms_card,text="No SMS messages",font=self.fnt(9),bg=self.c("glass"),fg=self.c("dim")).pack(padx=10,pady=6)
                for msg in msgs:
                    mrow=tk.Frame(sms_card,bg=self.c("glass")); mrow.pack(fill="x",padx=10,pady=3)
                    tk.Label(mrow,text=f"👤 {msg['from'][:16]}",font=self.fnt(9,"bold"),bg=self.c("glass"),fg=self.c("violet")).pack(anchor="w",padx=4)
                    tk.Label(mrow,text=msg["message"][:60],font=self.fnt(9),bg=self.c("glass"),fg=self.c("text"),wraplength=260,justify="left").pack(anchor="w",padx=4,pady=(0,4))
            except: pass

        # ── SCREENSHOT CARD ──
        ss_card=card("📸  PHONE SCREENSHOT",self.c("orange"))
        ss_row=tk.Frame(ss_card,bg=self.c("glass")); ss_row.pack(fill="x",padx=10,pady=(0,10))
        tk.Button(ss_row,text="📸 Take Screenshot",font=self.fnt(9,"bold"),bg=self.c("orange"),fg=self.c("bg"),
                  relief="flat",bd=0,padx=14,pady=7,cursor="hand2",
                  command=lambda:threading.Thread(target=lambda:self._add_sys(take_phone_screenshot()),daemon=True).start()).pack(side="left",padx=4)
        tk.Button(ss_row,text="🔄 Refresh Panel",font=self.fnt(9,"bold"),bg=self.c("bg3"),fg=self.c("cyan"),
                  relief="flat",bd=0,padx=14,pady=7,cursor="hand2",
                  command=self._refresh_phone_panel).pack(side="left",padx=4)

        # ── ADB SETUP GUIDE ──
        if not connected:
            guide=card("🔧  SETUP GUIDE",self.c("amber"))
            steps=[
                "1. Download ADB: developer.android.com/tools",
                "2. Enable Developer Options on phone:",
                "   Settings > About Phone > tap Build No. 7x",
                "3. Enable USB Debugging in Developer Options",
                "4. Connect phone via USB cable",
                "5. Accept USB Debugging prompt on phone",
                "6. Run: adb devices in Command Prompt",
                "✅ Then Jarvis auto-detects calls & contacts!",
            ]
            for s in steps:
                tk.Label(guide,text=s,font=self.fnt(8),bg=self.c("glass"),fg=self.c("text") if s.startswith("✅") else self.c("dim"),anchor="w").pack(fill="x",padx=10,pady=1)
            tk.Label(guide,text="",bg=self.c("glass")).pack(pady=4)

    # ── TABS ───────────────────────────────────────
    def _switch_tab(self,key,clr):
        for f in self._tab_frames.values(): f.pack_forget()
        self._tab_frames[key].pack(fill="both",expand=True)
        for k,(b,c) in self._tabs.items():
            b.config(fg=c if k==key else self.c("dim"), bg=self.c("border") if k==key else self.c("bg2"))
        self._active_tab=key

    # ── FACE ───────────────────────────────────────
    def _draw_face(self):
        c=self._face_cv; c.delete("all"); cx=130; cy=122; r=92; t=time.time()
        ec=mood_col()

        # particles
        if self.is_speaking or self.is_awake:
            for i in range(6):
                a=math.radians((t*44+i*60)%360)
                pr=r+28+10*math.sin(t*2.5+i)
                px=cx+pr*math.cos(a); py=cy+pr*math.sin(a)
                clrs=[self.c("cyan"),self.c("violet"),self.c("pink"),self.c("green"),self.c("amber"),self.c("blue")]
                c.create_oval(px-3,py-3,px+3,py+3,fill=self.blend(self.c("bg"),clrs[i],0.85),outline="")
                for j in range(1,3):
                    ta=math.radians((t*44+i*60-j*9)%360)
                    tx=cx+pr*math.cos(ta); ty=cy+pr*math.sin(ta)
                    c.create_oval(tx-1.5,ty-1.5,tx+1.5,ty+1.5,fill=self.blend(self.c("bg"),clrs[i],0.2/j),outline="")

        # rings
        for rx,spd,col in [(r+28,16,self.c("violet")),(r+18,24,self.c("cyan")),(r+9,36,self.c("pink"))]:
            for seg in range(0,360,40):
                a1=math.radians(seg+(t*spd)%360); a2=math.radians(seg+22+(t*spd)%360)
                x1=cx+rx*math.cos(a1); y1=cy+rx*math.sin(a1)
                x2=cx+rx*math.cos(a2); y2=cy+rx*math.sin(a2)
                c.create_line(x1,y1,x2,y2,fill=self.blend(self.c("bg"),col,0.2),width=1)

        # glow
        for g,op in [(r+20,0.04),(r+12,0.1),(r+5,0.22)]:
            c.create_oval(cx-g,cy-g,cx+g,cy+g,outline=self.blend(self.c("bg"),ec,op),width=2)

        # face base
        c.create_oval(cx-r,cy-r,cx+r,cy+r,fill=self.blend(self.c("bg"),ec,0.2),outline=ec,width=2)
        c.create_oval(cx-r+10,cy-r+10,cx+r-10,cy+r-10,fill=self.blend(self.c("bg"),ec,0.07),outline=self.blend(self.c("bg"),ec,0.13),width=1)
        c.create_oval(cx-r+8,cy-r+8,cx-r+42,cy-r+32,fill=self.blend(self.c("bg"),"#ffffff",0.05),outline="")

        # blink
        self.face_blink=(self.face_blink+1)%110
        eh=1 if 52<self.face_blink<57 else 12

        # eyes
        self.eye_a=(self.eye_a+0.5)%360
        for i,(ex,ey) in enumerate([(cx-29,cy-18),(cx+29,cy-18)]):
            c.create_oval(ex-14,ey-eh,ex+14,ey+eh,fill=self.blend(self.c("bg"),"#ffffff",0.9),outline=self.c("text"),width=1)
            if eh>4:
                ix=ex+int(5*math.cos(math.radians(self.eye_a+i*180))); iy=ey+int(2*math.sin(math.radians(self.eye_a)))
                c.create_oval(ix-8,iy-8,ix+8,iy+8,fill=self.blend(ec,self.c("violet"),0.4),outline="")
                c.create_oval(ix-6,iy-6,ix+6,iy+6,fill=ec,outline="")
                c.create_oval(ix-4,iy-4,ix+4,iy+4,fill=self.c("bg"),outline="")
                c.create_oval(ix-2,iy-2,ix+2,iy+2,fill="#010308",outline="")
                c.create_oval(ix-1.5,iy-5,ix,iy-3,fill="#ffffff",outline="")

        # eyebrows
        by=cy-38 if self.is_thinking else cy-34 if self.is_awake else cy-32
        sl=-4 if self.is_thinking else 0
        for bx in [cx-29,cx+29]:
            s=sl if bx<cx else -sl
            c.create_line(bx-13,by+s,bx+13,by-s,fill=ec,width=2,smooth=True)

        # nose
        c.create_line(cx,cy-5,cx-5,cy+10,fill=self.blend(self.c("bg"),ec,0.28),width=1.5,smooth=True)
        c.create_line(cx,cy-5,cx+5,cy+10,fill=self.blend(self.c("bg"),ec,0.28),width=1.5,smooth=True)
        c.create_arc(cx-6,cy+8,cx+6,cy+13,start=0,extent=-180,outline=self.blend(self.c("bg"),ec,0.28),width=1.5,style="arc")

        # mouth
        self.mouth_ph=(self.mouth_ph+0.36)%360; mw=26; my=cy+34
        if self.is_speaking and mouth_open:
            mh=max(2,int(13*abs(math.sin(self.mouth_ph))))
            c.create_arc(cx-mw,my-mh//2,cx+mw,my+mh,start=0,extent=-180,fill=self.blend(self.c("bg"),self.c("pink"),0.8),outline=self.c("pink"),width=1.5,style="chord")
            c.create_line(cx-mw,my,cx,my-3,cx+mw,my,fill=self.c("pink"),width=2,smooth=True)
            if mh>5: c.create_rectangle(cx-12,my,cx+12,my+mh-2,fill="#f0ddd0",outline="")
        elif self.is_thinking:
            c.create_arc(cx-16,my-7,cx+16,my+6,start=0,extent=180,outline=ec,width=2,style="arc")
        elif nova_mood==Mood.EXCITED:
            c.create_arc(cx-mw,my-12,cx+mw,my+8,start=0,extent=-180,outline=ec,width=2,style="arc")
        else:
            c.create_arc(cx-mw,my-9,cx+mw,my+6,start=0,extent=-180,outline=ec,width=2,style="arc")

        if self.is_awake or self.is_speaking:
            for bx in [cx-46,cx+46]: c.create_oval(bx-11,cy+5,bx+11,cy+19,fill=self.blend(self.c("bg"),self.c("pink"),0.1),outline="")

        if self.is_thinking:
            for i in range(3):
                ph=(t*3+i*0.45)%1; ddy=cy-r-20-int(11*abs(math.sin(ph*math.pi)))
                ddx=cx-14+i*14; c.create_oval(ddx-4,ddy-4,ddx+4,ddy+4,fill=self.c("amber"),outline="")

        sy=int((t*57)%244); c.create_line(cx-r+5,sy,cx+r-5,sy,fill=self.blend(self.c("bg"),self.c("cyan"),0.04),width=1)

    # ── TIMERS ─────────────────────────────────────
    def _start_timers(self):
        self._anim(); self._clk_tick(); self._refresh_music()
        if NEPAL_NEW_YEAR: self._scroll_ny()
        self._phone_refresh_timer()

    def _anim(self):
        try:
            self._draw_face(); self._draw_wave()
            self.title_ph=(self.title_ph+0.04)%360
            self._title_lbl.config(fg=self.blend(self.c("cyan"),self.c("pink"),abs(math.sin(self.title_ph))))
            tick=int(time.time()*2)%2
            self._dot_cv.itemconfig(self._dot, fill=self.c("green") if self.is_awake else(self.c("cyan") if tick else self.c("dim")))
            icon=MOOD_ICONS.get(nova_mood,"😊")
            self._mood_lbl.config(text=icon, fg=mood_col(), bg=self.c("bg2"))
        except: pass
        self.root.after(33, self._anim)

    def _draw_wave(self):
        c=self._wave_cv; c.delete("all"); self.wave_ph+=0.26
        n,bw,gap,h=32,6,2,13; total=n*(bw+gap); sx=(260-total)//2
        active=self.is_awake or self.is_speaking or self.is_listening
        for i in range(n):
            if active:
                ht=max(2,int(h*(0.2+0.8*abs(math.sin(self.wave_ph+i*0.36)))))
                col=self.c("blue") if self.is_listening else self.c("green") if self.is_speaking else self.c("amber") if self.is_thinking else self.c("cyan")
            else: ht,col=2,self.c("muted")
            x=sx+i*(bw+gap); c.create_rectangle(x,h-ht,x+bw,h+ht,fill=col,outline="")

    def _clk_tick(self):
        self._clk_lbl.config(text=datetime.datetime.now().strftime("%H:%M:%S  ·  %a %d %b"))
        self.root.after(1000,self._clk_tick)

    def _scroll_ny(self):
        if not hasattr(self,'_ny_off'): self._ny_off=0
        try:
            disp=self._ny_txt[self._ny_off:]+self._ny_txt[:self._ny_off]
            self._ny_lbl.config(text=disp[:120]); self._ny_off=(self._ny_off+1)%len(self._ny_txt)
            self.root.after(130,self._scroll_ny)
        except: pass

    def _phone_refresh_timer(self):
        """Refresh phone panel every 10 seconds."""
        try: self._refresh_phone_panel()
        except: pass
        self.root.after(10000, self._phone_refresh_timer)

    def _refresh_music(self):
        try:
            if music_playlist and(music_playing or music_paused):
                name=os.path.splitext(os.path.basename(music_playlist[music_index]))[0]
                self._song_lbl.config(text=name[:30]+"..." if len(name)>30 else name,fg=self.c("pink"))
                self._pp.config(text="⏸" if music_playing else "▶")
                pos=pygame.mixer.music.get_pos()
                self._prog.place(x=0,y=0,height=2,width=max(0,int(self._prog.master.winfo_width()*min(1,pos/60000))))
            else:
                self._song_lbl.config(text="Nothing playing",fg=self.c("dim")); self._pp.config(text="▶"); self._prog.place(x=0,y=0,height=2,width=0)
        except: pass
        self.root.after(500,self._refresh_music)

    # ── CHAT ───────────────────────────────────────
    def _add_chat(self,who,text,animate=False):
        self._chat.config(state="normal")
        now=datetime.datetime.now().strftime("%H:%M")
        if who=="you":
            self._chat.insert("end","You","you_n")
            self._chat.insert("end",f"  {now}\n","ts")
            self._chat.insert("end",f"{text}\n\n","you_m")
            self._chat.config(state="disabled"); self._chat.see("end")
        else:
            self._chat.insert("end","Jarvis","jrv_n")
            self._chat.insert("end",f"  {now}\n","ts")
            if animate:
                self._chat.config(state="disabled"); self._chat.see("end")
                self._typ_full=text; self._typ_pos=0; self._do_type()
            else:
                self._chat.insert("end",f"{text}\n\n","jrv_m")
                self._chat.config(state="disabled"); self._chat.see("end")

    def _do_type(self):
        if self._typ_pos<len(self._typ_full):
            self._chat.config(state="normal"); ch=self._typ_full[self._typ_pos]
            self._chat.insert("end",ch,"jrv_m"); self._typ_pos+=1
            self._chat.config(state="disabled"); self._chat.see("end")
            self.root.after(90 if ch in ".!?," else 11,self._do_type)
        else:
            self._chat.config(state="normal"); self._chat.insert("end","\n\n","jrv_m")
            self._chat.config(state="disabled"); self._chat.see("end")

    def _add_sys(self,text):
        self._chat.config(state="normal"); self._chat.insert("end",f"{text}\n\n","sys")
        self._chat.config(state="disabled"); self._chat.see("end")

    def _set_st(self,text,col=None): self._st_lbl.config(text=text,fg=col or self.c("dim"))

    # ── PHONE CALL POPUP ───────────────────────────
    def _show_call_popup(self,display):
        if self._call_win and self._call_win.winfo_exists(): return
        win=tk.Toplevel(self.root); win.title("📱 Incoming Call")
        win.geometry("400x300"); win.configure(bg=self.c("bg2"))
        win.attributes("-topmost",True); win.resizable(False,False)
        self._call_win=win
        tk.Frame(win,bg=self.c("green"),height=4).pack(fill="x",side="top")
        tk.Frame(win,bg=self.c("red"),height=4).pack(fill="x",side="bottom")
        body=tk.Frame(win,bg=self.c("bg2")); body.pack(expand=True,fill="both",padx=4)
        self._call_ic=tk.Label(body,text="📲",font=self.fnt(44),bg=self.c("bg2"))
        self._call_ic.pack(pady=(18,4)); self._pulse_call_icon()
        tk.Label(body,text="INCOMING CALL",font=self.fnt(12,"bold"),bg=self.c("bg2"),fg=self.c("dim")).pack()
        tk.Label(body,text=display,font=self.fnt(20,"bold"),bg=self.c("bg2"),fg=self.c("cyan")).pack(pady=(6,18))
        br=tk.Frame(body,bg=self.c("bg2")); br.pack(pady=(0,12))
        tk.Button(br,text="✅  RECEIVE",font=self.fnt(12,"bold"),bg=self.c("green"),fg=self.c("bg"),
                  activebackground="#16a34a",activeforeground=self.c("bg"),
                  relief="flat",bd=0,padx=24,pady=12,cursor="hand2",
                  command=lambda:(receive_call(),self._close_call_popup(),self._add_sys(f"📱 Call received from {display}!"))).pack(side="left",padx=10)
        tk.Button(br,text="❌  REJECT",font=self.fnt(12,"bold"),bg=self.c("red"),fg="white",
                  activebackground="#dc2626",activeforeground="white",
                  relief="flat",bd=0,padx=24,pady=12,cursor="hand2",
                  command=lambda:(reject_call(),self._close_call_popup(),self._add_sys(f"📱 Call rejected from {display}."))).pack(side="left",padx=10)
        tk.Label(body,text='Say "receive call" or "reject call"',font=self.fnt(9),bg=self.c("bg2"),fg=self.c("dim")).pack()
        self._switch_tab("chat",self.c("cyan"))

    def _pulse_call_icon(self):
        if not self._call_win or not self._call_win.winfo_exists(): return
        try:
            self._call_ic.config(text="📲" if self._call_ic.cget("text")=="📱" else "📱")
            self.root.after(600,self._pulse_call_icon)
        except: pass

    def _close_call_popup(self):
        try:
            if self._call_win and self._call_win.winfo_exists(): self._call_win.destroy(); self._call_win=None
        except: pass
        self._refresh_phone_panel()

    # ── MINI WIDGET ────────────────────────────────
    def _toggle_mini(self):
        if self._mini_widget and self._mini_widget.winfo_exists():
            self._mini_widget.destroy(); self._mini_widget=None; return
        mw=tk.Toplevel(self.root); mw.title("Jarvis"); mw.geometry("230x230")
        mw.configure(bg=self.c("bg2")); mw.attributes("-topmost",True); mw.resizable(False,False)
        mw.overrideredirect(True); self._mini_widget=mw
        def drag_start(e): mw._dx=e.x; mw._dy=e.y
        def drag_move(e): mw.geometry(f"+{mw.winfo_x()+e.x-mw._dx}+{mw.winfo_y()+e.y-mw._dy}")
        mfc=tk.Canvas(mw,width=230,height=172,bg=self.c("bg2"),highlightthickness=0); mfc.pack()
        mfc.bind("<Button-1>",drag_start); mfc.bind("<B1-Motion>",drag_move)
        self._mfc=mfc
        bc=tk.Frame(mw,bg=self.c("bg2")); bc.pack(fill="x",padx=8,pady=4)
        tk.Button(bc,text="🎤",font=self.fnt(12),bg=self.c("bg3"),fg=self.c("cyan"),relief="flat",bd=0,padx=8,pady=4,cursor="hand2",command=self._toggle_mic).pack(side="left",padx=2)
        tk.Button(bc,text="⚡",font=self.fnt(12),bg=self.c("bg3"),fg=self.c("violet"),relief="flat",bd=0,padx=8,pady=4,cursor="hand2",command=self._toggle_wake).pack(side="left",padx=2)
        self._mini_st=tk.Label(bc,text="...",font=self.fnt(8),bg=self.c("bg2"),fg=self.c("dim")); self._mini_st.pack(side="left",padx=4)
        tk.Button(bc,text="✕",font=self.fnt(10),bg=self.c("bg2"),fg=self.c("dim"),relief="flat",bd=0,cursor="hand2",command=lambda:mw.destroy()).pack(side="right")
        self._anim_mini()

    def _anim_mini(self):
        if not self._mini_widget or not self._mini_widget.winfo_exists(): return
        try:
            mc=self._mfc; mc.delete("all"); cx=cy=86; r=50; t=time.time(); ec=mood_col()
            for g,op in [(r+8,0.08),(r+4,0.16)]: mc.create_oval(cx-g,cy-g,cx+g,cy+g,outline=self.blend(self.c("bg2"),ec,op),width=1)
            mc.create_oval(cx-r,cy-r,cx+r,cy+r,fill=self.blend(self.c("bg2"),ec,0.18),outline=ec,width=2)
            blink=self.face_blink; eh2=1 if 52<blink<57 else 8
            for ex2,ey2 in [(cx-18,cy-10),(cx+18,cy-10)]:
                mc.create_oval(ex2-10,ey2-eh2,ex2+10,ey2+eh2,fill=self.blend(self.c("bg2"),"#ffffff",0.88),outline="")
                if eh2>3:
                    mc.create_oval(ex2-5,ey2-5,ex2+5,ey2+5,fill=ec,outline="")
                    mc.create_oval(ex2-3,ey2-3,ex2+3,ey2+3,fill=self.c("bg"),outline="")
            mmy2=cy+22
            if self.is_speaking and mouth_open:
                mh2=max(2,int(8*abs(math.sin(self.mouth_ph))))
                mc.create_arc(cx-16,mmy2-mh2//2,cx+16,mmy2+mh2,start=0,extent=-180,fill=self.blend(self.c("bg2"),self.c("pink"),0.75),outline=self.c("pink"),width=1,style="chord")
            else:
                mc.create_arc(cx-16,mmy2-7,cx+16,mmy2+5,start=0,extent=-180,outline=ec,width=1.5,style="arc")
            # phone call badge
            if _call_state=="ringing":
                mc.create_oval(cx+40,cy-50,cx+60,cy-30,fill=self.c("green"),outline="")
                mc.create_text(cx+50,cy-40,text="📲",font=self.fnt(12))
            st="🎤" if self.is_listening else "🔊" if self.is_speaking else "💭" if self.is_thinking else("✅" if self.is_awake else "💤")
            self._mini_st.config(text=st)
        except: pass
        self.root.after(33, self._anim_mini)

    # ── ALARM POPUP ────────────────────────────────
    def _alarm_popup(self,label):
        win=tk.Toplevel(self.root); win.title("⏰"); win.geometry("340x180")
        win.configure(bg=self.c("bg2")); win.attributes("-topmost",True)
        tk.Frame(win,bg=self.c("amber"),height=3).pack(fill="x")
        tk.Label(win,text="⏰  TIME'S UP!",font=self.fnt(16,"bold"),bg=self.c("bg2"),fg=self.c("amber")).pack(pady=(18,8))
        tk.Label(win,text=label,font=self.fnt(12),bg=self.c("bg2"),fg=self.c("text")).pack(pady=(0,16))
        tk.Button(win,text="Got it! ✓",font=self.fnt(11,"bold"),bg=self.c("amber"),fg=self.c("bg"),relief="flat",bd=0,padx=24,pady=8,cursor="hand2",command=win.destroy).pack()

    def _refresh_alarm_ui(self):
        try:
            if self._alarm_frame and self._alarm_frame.winfo_exists(): self._draw_alarms(self._alarm_frame)
        except: pass

    # ── INPUT ──────────────────────────────────────
    def _send(self,event=None):
        val=self._inp.get().strip()
        if not val or val=="Ask Jarvis anything...": return
        self._inp.delete(0,"end"); self._switch_tab("chat",self.c("cyan"))
        if not self.is_awake: self.is_awake=True; self._set_st("I'm here!",self.c("cyan")); self._wake_btn.config(text="💤 Sleep")
        self._process(val)

    def _quick(self,cmd):
        self._switch_tab("chat",self.c("cyan"))
        if not self.is_awake: self.is_awake=True; self._set_st("Active",self.c("cyan")); self._wake_btn.config(text="💤 Sleep")
        self._process(cmd)

    def _toggle_mic(self):
        if not self.is_listening: threading.Thread(target=self._mic_once,daemon=True).start()

    def _mic_once(self):
        self.is_listening=True
        self._mic_btn.config(bg=self.c("red"),text="🔴 Listening...")
        self._set_st("Listening...",self.c("blue"))
        heard=listen(6,12); self.is_listening=False
        self._mic_btn.config(bg=self.c("cyan"),text="🎤 Speak")
        if heard:
            if not self.is_awake: self.is_awake=True; self.root.after(0,self._wake_btn.config,{"text":"💤 Sleep"})
            self.root.after(0,self._process,heard)
        else:
            self._set_st("Didn't catch that",self.c("red"))
            self.root.after(2000,lambda:self._set_st("I'm here!" if self.is_awake else '👏 Clap or say "Hey Jarvis"',self.c("cyan") if self.is_awake else self.c("dim")))

    def _toggle_wake(self):
        if self.is_awake: self._sleep_jarvis()
        else: self._do_wake()

    def _do_wake(self):
        self.is_awake=True; self._set_st("I'm here! Talk to me.",self.c("cyan"))
        self._wake_btn.config(text="💤 Sleep"); self._add_sys("— Jarvis is awake —")
        h=datetime.datetime.now().hour; g="Good morning" if h<12 else "Good afternoon" if h<17 else "Good evening"
        if NEPAL_NEW_YEAR: reply=f"{g}! {get_ny_wish()}"
        else: reply=random.choice([f"Hey! {g}! What's up?","I'm here! What do you need?","Yo! Talk to me."])
        self._add_chat("jarvis",reply,True)
        threading.Thread(target=lambda:speak(reply),daemon=True).start()

    def _sleep_jarvis(self):
        self.is_awake=False; self._set_st('👏 Clap or say "Hey Jarvis"',self.c("dim"))
        self._wake_btn.config(text="⚡ Wake"); self._add_sys("— Jarvis is resting —")
        threading.Thread(target=lambda:speak(random.choice(["Alright, resting! Clap twice or say Hey Jarvis.","Later!","Rest mode on."])),daemon=True).start()

    def _process(self,text):
        detect_mood(text); self._add_chat("you",text)
        self._set_st("Thinking...",self.c("amber")); self.is_thinking=True
        threading.Thread(target=self._get_resp,args=(text,),daemon=True).start()

    def _get_resp(self,text):
        resp=handle_command(text)
        if resp is None: resp=ask_ai(text)
        self.is_thinking=False; self.root.after(0,self._deliver,resp)

    def _deliver(self,resp):
        self._add_chat("jarvis",resp,animate=True)
        self._set_st("Speaking...",self.c("green")); self.is_speaking=True; speak(resp)
        threading.Thread(target=self._wait_done,daemon=True).start()

    def _wait_done(self):
        while is_speaking: time.sleep(0.1)
        self.is_speaking=False
        self._set_st("I'm here!" if self.is_awake else '👏 Clap or say "Hey Jarvis"',self.c("cyan") if self.is_awake else self.c("dim"))

    def _wake_loop(self):
        while True:
            try:
                if not self.is_awake and not self.is_listening:
                    heard=listen(10,5)
                    if heard and any(w in heard for w in WAKE_WORDS): self.root.after(0,self._do_wake)
                elif self.is_awake and not self.is_listening and not self.is_thinking and not is_speaking:
                    heard=listen(7,12)
                    if heard:
                        if any(w in heard for w in SLEEP_WORDS): self.root.after(0,self._sleep_jarvis)
                        else: self.root.after(0,self._process,heard)
                else: time.sleep(0.3)
            except Exception as e: print(f"[loop]{e}"); time.sleep(0.5)

    # ── TAB CONTENT REFRESH ────────────────────────
    def _refresh_notes(self):
        if not hasattr(self,'_notes_list') or not self._notes_list: return
        notes_data=lj(NOTES_FILE,[])
        self._notes_list.config(state="normal"); self._notes_list.delete("1.0","end")
        if not notes_data:
            self._notes_list.insert("end","No notes yet. Say 'add note ...'\n","sys")
            self._notes_list.config(state="disabled"); return
        for n in reversed(notes_data[-20:]):
            self._notes_list.insert("end",f"{'📔' if n.get('type')=='diary' else '📝'}  {n['time']}\n","nh")
            self._notes_list.insert("end",f"{n['text']}\n\n","nb")
        self._notes_list.config(state="disabled")

    def _add_note_ui(self):
        txt=simpledialog.askstring("Add Note","Enter your note:",parent=self.root)
        if txt:
            nd=lj(NOTES_FILE,[]); nd.append({"text":txt,"time":datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),"type":"note"}); sj(NOTES_FILE,nd)
            self._refresh_notes(); self._switch_tab("notes",self.c("green"))

    def _refresh_tasks(self):
        if not self._task_list: return
        for w in self._task_list.winfo_children(): w.destroy()
        td=lj(TASKS_FILE,[])
        if not td: tk.Label(self._task_list,text="No tasks. Say 'add task ...'",font=self.fnt(9),bg=self.c("bg"),fg=self.c("dim")).pack(pady=20); return
        for task in td:
            row=tk.Frame(self._task_list,bg=self.c("glass"),highlightbackground=self.c("border"),highlightthickness=1); row.pack(fill="x",pady=3)
            done=task.get("done",False)
            tk.Label(row,text=("✅ " if done else "⬜ ")+task["task"],font=self.fnt(11),bg=self.c("glass"),fg=self.c("dim") if done else self.c("text"),anchor="w").pack(side="left",padx=12,pady=8,fill="x",expand=True)
            if not done:
                tk.Button(row,text="Done",font=self.fnt(9),bg=self.c("green"),fg=self.c("bg"),relief="flat",bd=0,padx=8,pady=4,cursor="hand2",
                          command=lambda t=task:(t.update({"done":True}),sj(TASKS_FILE,td),self._refresh_tasks())).pack(side="right",padx=8,pady=6)
            tk.Button(row,text="✕",font=self.fnt(9),bg=self.c("glass"),fg=self.c("red"),relief="flat",bd=0,padx=6,cursor="hand2",
                      command=lambda t=task:(td.remove(t),sj(TASKS_FILE,td),self._refresh_tasks())).pack(side="right",padx=4,pady=6)

    def _add_task_ui(self):
        txt=simpledialog.askstring("Add Task","What's the task?",parent=self.root)
        if txt:
            td=lj(TASKS_FILE,[]); td.append({"task":txt,"done":False,"created":datetime.datetime.now().strftime("%H:%M")}); sj(TASKS_FILE,td)
            self._refresh_tasks(); self._switch_tab("tasks",self.c("amber"))

    def _refresh_shopping(self):
        if not self._shop_list: return
        for w in self._shop_list.winfo_children(): w.destroy()
        sd=lj(SHOP_FILE,[])
        if not sd: tk.Label(self._shop_list,text="Shopping list empty.",font=self.fnt(9),bg=self.c("bg"),fg=self.c("dim")).pack(pady=20); return
        for item in sd:
            row=tk.Frame(self._shop_list,bg=self.c("glass"),highlightbackground=self.c("border"),highlightthickness=1); row.pack(fill="x",pady=3)
            done=item.get("done",False)
            tk.Label(row,text=("✅ " if done else "🛒 ")+item["item"],font=self.fnt(11),bg=self.c("glass"),fg=self.c("dim") if done else self.c("text"),anchor="w").pack(side="left",padx=12,pady=8,fill="x",expand=True)
            if not done:
                tk.Button(row,text="Got it",font=self.fnt(9),bg=self.c("green"),fg=self.c("bg"),relief="flat",bd=0,padx=8,pady=4,cursor="hand2",
                          command=lambda i=item:(i.update({"done":True}),sj(SHOP_FILE,sd),self._refresh_shopping())).pack(side="right",padx=8,pady=6)
            tk.Button(row,text="✕",font=self.fnt(9),bg=self.c("glass"),fg=self.c("red"),relief="flat",bd=0,padx=6,cursor="hand2",
                      command=lambda i=item:(sd.remove(i),sj(SHOP_FILE,sd),self._refresh_shopping())).pack(side="right",padx=4,pady=6)

    def _add_shop_ui(self):
        txt=simpledialog.askstring("Add Item","What to buy?",parent=self.root)
        if txt:
            sd=lj(SHOP_FILE,[]); sd.append({"item":txt,"done":False}); sj(SHOP_FILE,sd)
            self._refresh_shopping(); self._switch_tab("shop",self.c("pink"))

    def _refresh_habits(self):
        if not self._habit_frame: return
        for w in self._habit_frame.winfo_children(): w.destroy()
        if not habits_data["habits"]: tk.Label(self._habit_frame,text="No habits. Say 'add habit drink water'",font=self.fnt(9),bg=self.c("bg"),fg=self.c("dim")).pack(pady=20); return
        today=datetime.date.today().isoformat(); logged=habits_data["logs"].get(today,[])
        for h in habits_data["habits"]:
            done=h in logged; streak=habit_streak(h)
            row=tk.Frame(self._habit_frame,bg=self.c("glass") if done else self.c("bg3"),highlightbackground=self.c("violet") if done else self.c("border"),highlightthickness=1); row.pack(fill="x",pady=3)
            tk.Label(row,text=("✅ " if done else "⭕ ")+h.capitalize(),font=self.fnt(11),bg=row["bg"],fg=self.c("green") if done else self.c("text"),anchor="w").pack(side="left",padx=12,pady=8)
            tk.Label(row,text=f"🔥{streak}",font=self.fnt(9,"bold"),bg=row["bg"],fg=self.c("amber")).pack(side="left",padx=4)
            if not done: tk.Button(row,text="✓ Done",font=self.fnt(9),bg=self.c("violet"),fg=self.c("bg"),relief="flat",bd=0,padx=8,pady=4,cursor="hand2",command=lambda hb=h:(log_habit(hb),self._refresh_habits())).pack(side="right",padx=8,pady=6)
            tk.Button(row,text="✕",font=self.fnt(9),bg=row["bg"],fg=self.c("red"),relief="flat",bd=0,padx=6,cursor="hand2",command=lambda hb=h:(habits_data["habits"].remove(hb),sj(HABITS_FILE,habits_data),self._refresh_habits())).pack(side="right",padx=4,pady=6)

    def _add_habit_ui(self):
        txt=simpledialog.askstring("Add Habit","What habit to track?",parent=self.root)
        if txt: add_habit(txt); self._switch_tab("habits",self.c("violet"))

    def _refresh_sleep(self):
        if not self._sleep_frame: return
        for w in self._sleep_frame.winfo_children(): w.destroy()
        sessions=sleep_data.get("sessions",[])
        if not sessions: tk.Label(self._sleep_frame,text="No sleep data yet.",font=self.fnt(9),bg=self.c("bg"),fg=self.c("dim")).pack(pady=20); return
        for s in reversed(sessions[-7:]):
            row=tk.Frame(self._sleep_frame,bg=self.c("glass"),highlightbackground=self.c("border"),highlightthickness=1); row.pack(fill="x",pady=3)
            hrs=s["hours"]; col=self.c("green") if hrs>=7 else self.c("amber") if hrs>=5 else self.c("red")
            tk.Label(row,text=f"😴 {s['date']}",font=self.fnt(9,"bold"),bg=self.c("glass"),fg=self.c("blue")).pack(side="left",padx=12,pady=8)
            tk.Label(row,text=f"{hrs:.1f}h",font=self.fnt(11,"bold"),bg=self.c("glass"),fg=col).pack(side="left",padx=8)
            tk.Label(row,text="😊 Great" if hrs>=7 else "😐 OK" if hrs>=5 else "😴 Short",font=self.fnt(9),bg=self.c("glass"),fg=col).pack(side="left")

    def _refresh_expenses(self):
        if not self._expense_frame: return
        for w in self._expense_frame.winfo_children(): w.destroy()
        exp_data=lj(EXPENSE_FILE,[])
        if not exp_data: tk.Label(self._expense_frame,text="No expenses. Say 'I spent 500 on food'",font=self.fnt(9),bg=self.c("bg"),fg=self.c("dim")).pack(pady=20); return
        today=datetime.date.today().isoformat()
        today_total=sum(e["amount"] for e in exp_data if e["date"].startswith(today))
        tk.Label(self._expense_frame,text=f"Today: {today_total:.0f}  ·  Total: {sum(e['amount'] for e in exp_data):.0f}",font=self.fnt(10,"bold"),bg=self.c("bg"),fg=self.c("orange")).pack(anchor="w",pady=(0,8))
        for e in reversed(exp_data[-10:]):
            row=tk.Frame(self._expense_frame,bg=self.c("glass"),highlightbackground=self.c("border"),highlightthickness=1); row.pack(fill="x",pady=2)
            tk.Label(row,text=f"💸 {e['category']}",font=self.fnt(11),bg=self.c("glass"),fg=self.c("text"),anchor="w").pack(side="left",padx=12,pady=6,fill="x",expand=True)
            tk.Label(row,text=f"{e['amount']:.0f}",font=self.fnt(10,"bold"),bg=self.c("glass"),fg=self.c("orange")).pack(side="right",padx=12,pady=6)

    def _add_expense_ui(self):
        txt=simpledialog.askstring("Add Expense","Amount and category (e.g. 500 on food):",parent=self.root)
        if txt: r=add_expense(txt); self._add_sys(r); self._switch_tab("expenses",self.c("orange"))

    # ── POPUPS ─────────────────────────────────────
    def _alarm_win(self):
        win=tk.Toplevel(self.root); win.title("Alarms"); win.geometry("480x420"); win.configure(bg=self.c("bg")); win.grab_set()
        tk.Label(win,text="⏰  Alarms & Reminders",font=self.fnt(13,"bold"),bg=self.c("bg"),fg=self.c("amber")).pack(pady=(16,3))
        lf=tk.Frame(win,bg=self.c("card"),highlightbackground=self.c("border"),highlightthickness=1); lf.pack(fill="both",expand=True,padx=18,pady=10)
        self._alarm_frame=lf; self._draw_alarms(lf)
        af=tk.Frame(win,bg=self.c("bg")); af.pack(fill="x",padx=18,pady=(0,14))
        tv=tk.StringVar(); lv=tk.StringVar()
        for row2,(lbl,var,w) in enumerate([("Time (HH:MM):",tv,10),("Label:",lv,22)]):
            tk.Label(af,text=lbl,font=self.fnt(9),bg=self.c("bg"),fg=self.c("dim")).grid(row=row2,column=0,sticky="w",pady=3)
            tk.Entry(af,textvariable=var,font=self.fnt(11),bg=self.c("bg3"),fg=self.c("text"),insertbackground=self.c("cyan"),relief="flat",width=w).grid(row=row2,column=1,padx=8,pady=3)
        def add():
            t2=tv.get().strip(); l=lv.get().strip() or f"Alarm {t2}"
            if re.match(r'\d{1,2}:\d{2}',t2):
                h2,m2=map(int,t2.split(":")); alarms.append({"id":_nid(),"hour":h2%24,"minute":m2,"label":l,"active":True,"repeat":False}); self._draw_alarms(lf)
        tk.Button(af,text="+ ADD",font=self.fnt(9,"bold"),bg=self.c("amber"),fg=self.c("bg"),relief="flat",bd=0,padx=14,pady=7,cursor="hand2",command=add).grid(row=2,column=0,columnspan=2,pady=8,sticky="w")

    def _draw_alarms(self,frame):
        for w in frame.winfo_children(): w.destroy()
        if not alarms and not reminders: tk.Label(frame,text="No alarms set",font=self.fnt(9),bg=self.c("card"),fg=self.c("dim")).pack(pady=20); return
        for a in alarms:
            row=tk.Frame(frame,bg=self.c("card")); row.pack(fill="x",padx=8,pady=2)
            tk.Label(row,text=f"{'✓' if not a['active'] else '⏰'} {a['hour']:02d}:{a['minute']:02d} — {a['label']}",font=self.fnt(11),bg=self.c("card"),fg=self.c("dim") if not a["active"] else self.c("amber")).pack(side="left",padx=8,pady=4)
            tk.Button(row,text="✕",font=self.fnt(9),bg=self.c("card"),fg=self.c("red"),relief="flat",bd=0,cursor="hand2",command=lambda a=a:(alarms.remove(a),self._draw_alarms(frame))).pack(side="right",padx=8)
        for r in reminders:
            row=tk.Frame(frame,bg=self.c("card")); row.pack(fill="x",padx=8,pady=2)
            lft=max(0,int(r["fire_at"]-time.time())); m2,s2=divmod(lft,60)
            tk.Label(row,text=f"🔔 {r['label']} — in {m2}m {s2}s",font=self.fnt(11),bg=self.c("card"),fg=self.c("orange")).pack(side="left",padx=8,pady=4)
            tk.Button(row,text="✕",font=self.fnt(9),bg=self.c("card"),fg=self.c("red"),relief="flat",bd=0,cursor="hand2",command=lambda r=r:(reminders.remove(r),self._draw_alarms(frame))).pack(side="right",padx=8)

    def _news_win(self):
        win=tk.Toplevel(self.root); win.title("News"); win.geometry("580x460"); win.configure(bg=self.c("bg")); win.grab_set()
        tk.Label(win,text="📰  News Reader",font=self.fnt(13,"bold"),bg=self.c("bg"),fg=self.c("orange")).pack(pady=(16,3))
        cv=tk.StringVar(value="general"); cf2=tk.Frame(win,bg=self.c("bg")); cf2.pack()
        for cat,lbl in [("general","General"),("tech","Tech"),("sports","Sports")]:
            tk.Radiobutton(cf2,text=lbl,variable=cv,value=cat,bg=self.c("bg"),fg=self.c("text"),selectcolor=self.c("bg3"),activebackground=self.c("bg"),font=self.fnt(11)).pack(side="left",padx=10)
        nb=tk.Text(win,font=self.fnt(11),bg=self.c("card"),fg=self.c("text"),relief="flat",bd=0,wrap="word",padx=14,pady=10,state="disabled")
        nb.pack(fill="both",expand=True,padx=18,pady=10)
        br=tk.Frame(win,bg=self.c("bg")); br.pack(pady=(0,14))
        sl=tk.Label(br,text="",font=self.fnt(9),bg=self.c("bg"),fg=self.c("dim")); sl.pack(side="left",padx=8)
        def fetch():
            sl.config(text="Fetching..."); nb.config(state="normal"); nb.delete("1.0","end"); nb.insert("end","Loading...\n"); nb.config(state="disabled")
            def _f():
                res=get_news(cv.get()); nb.config(state="normal"); nb.delete("1.0","end"); nb.insert("end",res); nb.config(state="disabled"); sl.config(text="Done!")
            threading.Thread(target=_f,daemon=True).start()
        def read(): t2=nb.get("1.0","end").strip(); threading.Thread(target=lambda:speak(t2),daemon=True).start() if t2 else None
        tk.Button(br,text="🔄 Refresh",font=self.fnt(9,"bold"),bg=self.c("orange"),fg=self.c("bg"),relief="flat",bd=0,padx=14,pady=7,cursor="hand2",command=fetch).pack(side="left",padx=6)
        tk.Button(br,text="🔊 Read",font=self.fnt(9,"bold"),bg=self.c("cyan"),fg=self.c("bg"),relief="flat",bd=0,padx=14,pady=7,cursor="hand2",command=read).pack(side="left",padx=6)
        fetch()

    def _settings_win(self):
        win=tk.Toplevel(self.root); win.title("Settings"); win.geometry("540x340"); win.configure(bg=self.c("bg")); win.resizable(False,False); win.grab_set()
        tk.Label(win,text="⚙  Settings",font=self.fnt(13,"bold"),bg=self.c("bg"),fg=self.c("blue")).pack(pady=(16,4))
        sf=tk.Frame(win,bg=self.c("bg")); sf.pack(fill="x",padx=28)
        def field(lbl,hint,val):
            tk.Label(sf,text=lbl,font=self.fnt(11),bg=self.c("bg"),fg=self.c("text"),anchor="w").pack(fill="x")
            tk.Label(sf,text=hint,font=self.fnt(9),bg=self.c("bg"),fg=self.c("dim"),anchor="w").pack(fill="x")
            fb=tk.Frame(sf,bg=self.c("cyan"),pady=1,padx=1); fb.pack(fill="x",pady=(2,10))
            fi=tk.Frame(fb,bg=self.c("bg3")); fi.pack(fill="x")
            v=tk.StringVar(value=val); tk.Entry(fi,textvariable=v,font=self.fnt(11),bg=self.c("bg3"),fg=self.c("text"),insertbackground=self.c("cyan"),relief="flat",bd=0).pack(fill="x",padx=10,pady=7); return v
        fv=field("🎵 Music Folder","Full path to your music folder",MUSIC_FOLDER)
        av=field("🎵 Anthem File","Filename (e.g. national_anthem.mp3)",NATIONAL_ANTHEM_FILE)
        # ADB path
        adb_v=field("📱 ADB Path","Path to adb.exe (leave as 'adb' if in PATH)",ADB_PATH)
        br=tk.Frame(win,bg=self.c("bg")); br.pack(pady=4)
        def browse():
            p=filedialog.askdirectory()
            if p: fv.set(p.replace("/", os.sep))
        msg=tk.Label(win,text="",font=self.fnt(9),bg=self.c("bg"),fg=self.c("green")); msg.pack()
        tk.Button(br,text="Browse",font=self.fnt(9),bg=self.c("bg3"),fg=self.c("blue"),relief="flat",bd=0,padx=10,pady=5,cursor="hand2",command=browse).pack(side="left",padx=6)
        def save():
            global MUSIC_FOLDER,NATIONAL_ANTHEM_FILE,ADB_PATH
            MUSIC_FOLDER=fv.get().strip(); NATIONAL_ANTHEM_FILE=av.get().strip()
            ADB_PATH=adb_v.get().strip() or "adb"
            save_config_full(); _load_pl(); msg.config(text=f"Saved! {len(music_playlist)} songs found."); win.after(1500,win.destroy)
        tk.Button(br,text="Save",font=self.fnt(10,"bold"),bg=self.c("cyan"),fg=self.c("bg"),activebackground=self.c("green"),activeforeground=self.c("bg"),relief="flat",bd=0,padx=24,pady=9,cursor="hand2",command=save).pack(side="left",padx=6)

    def _show_help(self):
        win=tk.Toplevel(self.root); win.title("Help"); win.geometry("700x620"); win.configure(bg=self.c("bg")); win.grab_set()
        tk.Label(win,text="📖  JARVIS — ALL COMMANDS",font=self.fnt(13,"bold"),bg=self.c("bg"),fg=self.c("cyan")).pack(pady=(16,4))
        fr=tk.Frame(win,bg=self.c("card"),highlightbackground=self.c("border"),highlightthickness=1); fr.pack(fill="both",expand=True,padx=18,pady=(0,8))
        sb=tk.Scrollbar(fr,bg=self.c("bg3"),troughcolor=self.c("bg")); sb.pack(side="right",fill="y")
        tb=tk.Text(fr,font=self.fnt(10),bg=self.c("card"),fg=self.c("text"),relief="flat",bd=0,wrap="word",padx=16,pady=12,yscrollcommand=sb.set)
        tb.pack(fill="both",expand=True); sb.config(command=tb.yview)
        guide="""WAKE JARVIS
  Say "Hey Jarvis"  |  Clap twice  |  Click ⚡ Wake

PHONE CALL CONTROL
  When someone calls you, Jarvis says who it is (name + number)!
  "Receive call" / "Answer call"   -- answers on phone
  "Reject call" / "Don't receive"  -- declines call
  "End call" / "Hang up"           -- ends active call
  "Call status"                    -- who is calling?

PHONE QUICK CONTROLS
  "Torch on / off"        "WiFi on / off"
  "Bluetooth on / off"    "Phone screen on / off"
  "Phone volume up/down"  "Phone play / pause"
  "Phone next / previous" "Phone location"
  "Phone battery"         "Phone screenshot"
  "Phone info"            "Call log"
  "Read messages"         "Load contacts"

CALL / SMS SOMEONE
  "Call John"             -- dials John from contacts
  "Send message to John saying hello"

OPEN PHONE APPS
  "Open WhatsApp on phone"    "Open camera on phone"
  "Open Instagram on phone"   "Open maps on phone"

MUSIC
  "Play music"  "Play [song name]"  "Next song"
  "Pause"  "Stop music"

TIME / WEATHER / NEWS
  "What time is it?"  "Weather in Pokhara"
  "What's happening?" / "Tech news"

ALARMS
  "Set alarm at 7:30 am"
  "Remind me in 10 minutes to drink water"

NOTES / TASKS / SHOPPING
  "Add note buy groceries"
  "Add task finish homework"
  "Buy milk"

HABITS / SLEEP / POMODORO
  "Add habit drink water"
  "I did drink water"
  "Going to sleep" / "Good morning"
  "Start focus mode 25 minutes"

AI COPILOT
  "Write Python function for sorting"
  "Fix this error: ..."
  "Write email to boss"
  "I'm sad" / "I'm bored" / "Motivate me"
  "Start breathing exercise"

APPS / WEBSITES
  "Open YouTube"  "Open Chrome"  "Search Python"

PC CONTROL
  "Screenshot"  "Lock PC"  "Shutdown"  "Restart"
  "Volume up/down"  "PC health"  "Battery"

SLEEP
  "Goodbye Jarvis"  "Bye Jarvis"  Click 💤"""
        tb.insert("1.0",guide); tb.config(state="disabled")
        tk.Button(win,text="Got it! 👍",font=self.fnt(10,"bold"),bg=self.c("cyan"),fg=self.c("bg"),relief="flat",bd=0,padx=24,pady=9,cursor="hand2",command=win.destroy).pack(pady=(0,14))

    def run(self): self.root.mainloop()
