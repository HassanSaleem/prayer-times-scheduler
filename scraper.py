import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

def get_todays_begins_times():
    # Using the official mirror for East London Mosque times (no Cloudflare blocking)
    url = "https://www.londonprayertimes.com/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Website rejected request with status code: {response.status_code}")
        return None
        
    soup = BeautifulSoup(response.text, "html.parser")
    
    # The site has a very simple table: Prayer | Start | Jama'ah
    table = soup.find("table")
    if not table:
        return None

    times = {}
    
    for row in table.find_all("tr"):
        cols = [td.text.strip() for td in row.find_all(["td", "th"])]
        
        # Match the prayer names in the first column
        if len(cols) >= 2:
            prayer_name = cols[0].lower()
            start_time = cols[1] # We want the 'Start' time, not the Jama'ah time
            
            if "fajr" in prayer_name:
                times["fajr"] = {"time": start_time, "is_pm": False}
            elif "dhuhr" in prayer_name:
                times["zuhr"] = {"time": start_time, "is_pm": True}
            elif "asr" in prayer_name:
                times["asr_2_mithl"] = {"time": start_time, "is_pm": True}
            elif "maghrib" in prayer_name:
                times["maghrib"] = {"time": start_time, "is_pm": True}
            elif "isha" in prayer_name:
                times["isha"] = {"time": start_time, "is_pm": True}

    if len(times) == 5:
        return times
    else:
        print(f"Only found {len(times)} prayers: {times}")
        return None

def schedule_with_qstash(times):
    # Load required tokens from GitHub Actions environment
    qstash_token = os.environ.get("QSTASH_TOKEN")
    smartthings_token = os.environ.get("SMARTTHINGS_TOKEN")
    device_id = os.environ.get("DEVICE_ID")

    if not all([qstash_token, smartthings_token, device_id]):
        print("Missing required environment variables (QSTASH_TOKEN, SMARTTHINGS_TOKEN, DEVICE_ID).")
        return

    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # QStash publisher URL pointing to your SmartThings API endpoint
    target_url = f"https://api.smartthings.com/v1/devices/{device_id}/commands"
    qstash_publish_url = f"https://qstash.upstash.io/v2/publish/{target_url}"
    
    # Payload to turn the Virtual Switch ON
    payload = {
        "commands": [{"component": "main", "capability": "switch", "command": "on"}]
    }

    for prayer, data in times.items():
        # Parse 12-hour string to 24-hour datetime
        hour, minute = map(int, data["time"].split(':'))
        if data["is_pm"] and hour != 12:
            hour += 12
            
        prayer_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Skip prayers that have already passed today
        if prayer_time <= now:
            print(f"Skipping {prayer.upper()} ({data['time']}) - Time has already passed.")
            continue

        # Convert the exact prayer time to a UNIX timestamp for QStash
        unix_timestamp = int(prayer_time.timestamp())

        headers = {
            "Authorization": f"Bearer {qstash_token}",
            "Upstash-Not-Before": str(unix_timestamp), # The exact second QStash will fire the webhook
            "Upstash-Forward-Authorization": f"Bearer {smartthings_token}",
            "Content-Type": "application/json"
        }

        # Send scheduling request to QStash
        response = requests.post(qstash_publish_url, headers=headers, json=payload)
        
        if response.status_code == 201 or response.status_code == 200:
            print(f"✅ Scheduled {prayer.upper()} at {prayer_time.strftime('%H:%M %Z')} (UNIX: {unix_timestamp})")
        else:
            print(f"❌ Failed to schedule {prayer.upper()}: Status {response.status_code}, Response: {response.text}")

def main():
    times = get_todays_begins_times()
    if not times:
        print("Failed to scrape timetable.")
        return

    schedule_with_qstash(times)

if __name__ == "__main__":
    main()
