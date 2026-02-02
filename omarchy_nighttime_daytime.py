#!/usr/bin/env python3
import os
import sys
import time
import random
import datetime
import math
import subprocess
import glob
import urllib.request
import json

# --- Configuration ---
LATITUDE = None
LONGITUDE = None

THEME_DIR = os.path.expanduser("~/.local/share/omarchy/themes")
THEME_SET_CMD = os.path.expanduser("~/.local/share/omarchy/bin/omarchy-theme-set")
CHECK_INTERVAL = 60  # Check every minute

# --- Helpers ---
def get_location_from_ip():
    print("Attempting to detect location via IP...")
    try:
        # Use a timeout to avoid hanging if offline
        with urllib.request.urlopen("http://ip-api.com/json/", timeout=5) as url:
            data = json.loads(url.read().decode())
            if data['status'] == 'success':
                lat = data['lat']
                lon = data['lon']
                city = data.get('city', 'Unknown')
                country = data.get('country', 'Unknown')
                print(f"Location detected: {city}, {country} ({lat}, {lon})")
                return lat, lon
    except Exception as e:
        print(f"Could not automatically detect location: {e}")
    return None

def parse_iso6709(coord_str):
    """
    Parses ISO 6709 coordinates like -3652+17446 (DDMM[SS]±DDDMM[SS])
    Returns (latitude, longitude) as floats.
    """
    try:
        # This format is ±DDMM[SS]±DDDMM[SS]
        # Latitude is first 5 or 7 chars (e.g. -3652 or -365200)
        # We need to find the second '+' or '-' which starts the longitude
        
        # Longitude starts at the second sign (skipping the first char)
        sign_idx = -1
        for i in range(1, len(coord_str)):
            if coord_str[i] in ['+', '-']:
                sign_idx = i
                break
        
        if sign_idx == -1: return None
        
        lat_part = coord_str[:sign_idx]
        lon_part = coord_str[sign_idx:]
        
        def parse_part(part):
            # Sign is part[0]
            sign = 1 if part[0] == '+' else -1
            val = part[1:]
            if len(val) == 4 or len(val) == 5: # DDMM or DDDMM
                deg = int(val[:-2])
                min = int(val[-2:])
                return sign * (deg + min/60.0)
            elif len(val) == 6 or len(val) == 7: # DDMMSS or DDDMMSS
                deg = int(val[:-4])
                min = int(val[-4:-2])
                sec = int(val[-2:])
                return sign * (deg + min/60.0 + sec/3600.0)
            return 0.0

        return parse_part(lat_part), parse_part(lon_part)
    except:
        return None

def get_system_timezone():
    try:
        out = subprocess.check_output(['timedatectl', 'show', '-p', 'Timezone', '--value'], 
                                    stderr=subprocess.DEVNULL).decode().strip()
        if out: return out
    except:
        pass
    if os.path.exists('/etc/timezone'):
        try:
            with open('/etc/timezone', 'r') as f:
                return f.read().strip()
        except: pass
    return None

def get_fallback_location():
    tz_name = get_system_timezone()
    if tz_name:
        tab_path = "/usr/share/zoneinfo/zone1970.tab"
        if os.path.exists(tab_path):
            try:
                with open(tab_path, 'r') as f:
                    for line in f:
                        if line.startswith('#') or not line.strip(): continue
                        parts = line.split('\t')
                        if len(parts) >= 3 and parts[2].strip() == tz_name:
                            coords = parse_iso6709(parts[1])
                            if coords:
                                print(f"Found coordinates for timezone '{tz_name}' in system database: {coords}")
                                return coords
            except Exception as e:
                print(f"Error reading timezone database: {e}")

    # Ultimate fallback: offset-based calculation
    try:
        local_time = datetime.datetime.now().astimezone()
        local_offset = local_time.utcoffset()
        offset_hours = local_offset.total_seconds() / 3600.0 if local_offset else 0
        lon = (offset_hours * 15.0 + 180) % 360 - 180
        print(f"Using generic fallback (UTC{offset_hours:+.1f}): 0.0, {lon}")
        return 0.0, lon
    except:
        return 0.0, 0.0

# --- Sun Calculation ---
def force_range(v, max_v):
    if v < 0:
        return v + max_v
    elif v >= max_v:
        return v - max_v
    return v

def days_since_j2000(date):
    return (date - datetime.datetime(2000, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)).total_seconds() / 86400.0

def get_sun_times(date_obj, lat, lon):
    # Simple algorithm to calculate sunrise and sunset
    # Based on: http://edwilliams.org/sunrise_sunset_algorithm.htm
    
    # 1. first calculate the day of the year
    N = date_obj.timetuple().tm_yday
    
    # 2. convert the longitude to hour value and calculate an approximate time
    lngHour = lon / 15.0
    
    times = {}
    for event in ['sunrise', 'sunset']:
        if event == 'sunrise':
            t = N + ((6.0 - lngHour) / 24.0)
        else:
            t = N + ((18.0 - lngHour) / 24.0)
            
        # 3. calculate the Sun's mean anomaly
        M = (0.9856 * t) - 3.289
        
        # 4. calculate the Sun's true longitude
        L = M + (1.916 * math.sin(math.radians(M))) + (0.020 * math.sin(math.radians(2 * M))) + 282.634
        L = force_range(L, 360.0)
        
        # 5a. calculate the Sun's right ascension
        RA = math.degrees(math.atan(0.91764 * math.tan(math.radians(L))))
        RA = force_range(RA, 360.0)
        
        # 5b. right ascension value needs to be in the same quadrant as L
        Lquadrant  = (math.floor(L/90.0)) * 90.0
        RAquadrant = (math.floor(RA/90.0)) * 90.0
        RA = RA + (Lquadrant - RAquadrant)
        
        # 5c. right ascension value needs to be converted into hours
        RA = RA / 15.0
        
        # 6. calculate the Sun's declination
        sinDec = 0.39782 * math.sin(math.radians(L))
        cosDec = math.cos(math.asin(sinDec))
        
        # 7a. calculate the Sun's local hour angle
        zenith = 90.833 # Official
        cosH = (math.cos(math.radians(zenith)) - (sinDec * math.sin(math.radians(lat)))) / (cosDec * math.cos(math.radians(lat)))
        
        if cosH >  1:
            return None # The sun never rises on this location (on the specified date)
        if cosH < -1:
            return None # The sun never sets on this location (on the specified date)
            
        # 7b. finish calculating H and convert into hours
        if event == 'sunrise':
            H = 360.0 - math.degrees(math.acos(cosH))
        else:
            H = math.degrees(math.acos(cosH))
            
        H = H / 15.0
        
        # 8. calculate local mean time of rising/setting
        T = H + RA - (0.06571 * t) - 6.622
        
        # 9. adjust back to UTC
        UT = T - lngHour
        UT = force_range(UT, 24.0)
        
        # Convert UT to local time
        # This part is tricky without pytz, relying on system local time offset
        # We will return UTC datetime and let caller handle conversion if needed
        # Actually, let's just return UTC datetime objects
        
        seconds = UT * 3600.0
        event_dt_utc = datetime.datetime(date_obj.year, date_obj.month, date_obj.day, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
        times[event] = event_dt_utc

    return times

# --- Theme Management ---
def get_themes():
    themes = {'light': [], 'dark': []}
    if not os.path.exists(THEME_DIR):
        return themes
    
    for item in os.listdir(THEME_DIR):
        path = os.path.join(THEME_DIR, item)
        if os.path.isdir(path):
            if os.path.exists(os.path.join(path, "light.mode")):
                themes['light'].append(item)
            else:
                themes['dark'].append(item)
    return themes

def set_random_theme(mode, themes, dry_run=False):
    options = themes.get(mode, [])
    if not options:
        print(f"No themes found for mode: {mode}")
        return False
    
    choice = random.choice(options)
    print(f"Switching to {mode} theme: {choice}")
    
    if dry_run:
        return True

    try:
        subprocess.run([THEME_SET_CMD, choice], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error setting theme: {e}")
        return False
    except FileNotFoundError:
        print(f"Theme command not found: {THEME_SET_CMD}")
        return False

# --- Systemd Management ---
SERVICE_NAME = "omarchy-nighttime-daytime.service"
SERVICE_FILE_PATH = os.path.expanduser(f"~/.config/systemd/user/{SERVICE_NAME}")

def get_service_content():
    script_path = os.path.abspath(__file__)
    # We want the service to run unbuffered so logs appear immediately
    return f"""[Unit]
Description=Omarchy-Nighttime-Daytime Theme Switcher
After=graphical-session.target

[Service]
ExecStart={sys.executable} -u {script_path}
Restart=on-failure
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""

def run_systemctl(args):
    try:
        cmd = ["systemctl", "--user"] + args
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Systemctl command failed: {e}")
        return False

def install_service():
    print(f"Installing systemd service to {SERVICE_FILE_PATH}...")
    os.makedirs(os.path.dirname(SERVICE_FILE_PATH), exist_ok=True)
    
    with open(SERVICE_FILE_PATH, "w") as f:
        f.write(get_service_content())
    
    print("Reloading systemd daemon...")
    run_systemctl(["daemon-reload"])
    print("Enabling and starting service...")
    run_systemctl(["enable", "--now", SERVICE_NAME])
    print("Service installed and started.")

def uninstall_service():
    print("Stopping service...")
    run_systemctl(["stop", SERVICE_NAME])
    print("Disabling service...")
    run_systemctl(["disable", SERVICE_NAME])
    
    if os.path.exists(SERVICE_FILE_PATH):
        print(f"Removing service file {SERVICE_FILE_PATH}...")
        os.remove(SERVICE_FILE_PATH)
        run_systemctl(["daemon-reload"])
    
    print("Killing any remaining processes...")
    try:
        # Kill any process named omarchy_nighttime_daytime.py except this one
        subprocess.run(["pkill", "-f", os.path.basename(__file__)], check=False)
    except Exception as e:
        print(f"Error killing processes: {e}")
        
    print("Service uninstalled and stopped.")

# --- Main Logic ---
def get_current_state():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_times = get_sun_times(now_utc, LATITUDE, LONGITUDE)
    
    if not today_times:
        return 'day' 

    sunrise = today_times['sunrise']
    sunset = today_times['sunset']
    
    if sunrise < sunset:
        if sunrise <= now_utc <= sunset:
            return 'day'
        else:
            return 'night'
    else:
        if sunset <= now_utc <= sunrise:
            return 'night'
        else:
            return 'day'

def main():
    global LATITUDE, LONGITUDE

    # Handle management commands first (before logging setup)
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ["install", "enable", "up", "setup"]:
            install_service()
            return
        elif cmd in ["disable", "down", "remove", "uninstall"]:
            uninstall_service()
            return

    # Redirect stdout and stderr to a log file
    log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "omarchy_nighttime_daytime.log")
    try:
        log_file = open(log_file_path, "a", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    except Exception as e:
        print(f"Failed to open log file: {e}")

    dry_run = '--dry-run' in sys.argv
    one_shot = '--one-shot' in sys.argv
    no_ip = '--no-ip' in sys.argv
    print(f"\n--- {datetime.datetime.now()} ---")
    
    # Attempt to detect location
    loc = None
    if not no_ip:
        loc = get_location_from_ip()
    else:
        print("Skipping IP detection (--no-ip flag set).")

    if loc:
        LATITUDE, LONGITUDE = loc
    else:
        LATITUDE, LONGITUDE = get_fallback_location()

    print(f"Omarchy-Nighttime-Daytime Service Started. Location: {LATITUDE}, {LONGITUDE}")
    
    themes = get_themes()
    print(f"Found {len(themes['light'])} light themes and {len(themes['dark'])} dark themes.")

    # Show today's sun times once
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    today_times = get_sun_times(now_utc, LATITUDE, LONGITUDE)
    if today_times:
        # Convert to local time for display (rough estimate using current system offset)
        local_offset = datetime.datetime.now().astimezone().utcoffset()
        sr_local = today_times['sunrise'] + local_offset
        ss_local = today_times['sunset'] + local_offset
        print(f"Today's Sunrise: {sr_local.strftime('%H:%M:%S')}")
        print(f"Today's Sunset:  {ss_local.strftime('%H:%M:%S')}")
    
    last_state = None
    
    while True:
        try:
            current_state = get_current_state()
            
            if current_state != last_state:
                print(f"State change detected: {last_state} -> {current_state}")
                theme_mode = 'light' if current_state == 'day' else 'dark'
                set_random_theme(theme_mode, themes, dry_run)
                last_state = current_state
            
            if one_shot:
                break

            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            print("Exiting...")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            time.sleep(CHECK_INTERVAL) # Wait before retrying

if __name__ == "__main__":
    main()
