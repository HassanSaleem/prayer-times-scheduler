import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import re

def get_todays_begins_times():
    url = "https://www.londonprayertimes.com/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Website rejected request with status code: {response.status_code}")
        return None
        
    text = BeautifulSoup(response.text, "html.parser").get_text(separator=" ")
    times = {}
    
    # Strictly look for HH:MM format (digits only) next to the prayer names
    prayers = {
        "fajr": r'Fajr\s+(\d{1,2}:\d{2})',
        "zuhr": r'Dhuhr\s+(\d{1,2}:\d{2})',
        "asr_2_mithl": r'Asr\s+(\d{1,2}:\d{2})',
        "maghrib": r'Maghrib\s+(\d{1,2}:\d{2})',
        "isha": r'Isha\s+(\d{1,2}:\d{2})'
    }
    
    for prayer, pattern in prayers.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            times[prayer] = {"time": match.group(1)}
            
    return times

def schedule_with_qstash(times):
    qstash_token = os.environ.get("QSTASH_TOKEN")
    smartthings_token = os.environ.get("SMARTTHINGS_TOKEN")
    device_id = os.environ.get("DEVICE_ID")

    if not all([qstash_token, smartthings_token, device_id]):
        print("Missing required environment variables. Check your GitHub Secrets!")
        return

    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    target_url = f"https://api.smartthings.com/v1/devices/{device_id}/commands"
    qstash_publish_url = f"https://qstash.upstash.io/v2/publish/{target_url}"
    payload = {"commands": [{"component": "main", "capability": "switch", "command": "on"}]}

    for prayer, data in times.items():
        try:
            hour, minute = map(int, data["time"].split(':'))
        except ValueError:
            print(f"Skipping {prayer.upper()} - Invalid time format: {data['time']}")
            continue
            
        prayer_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if prayer_time <= now:
            print(f"Skipping {prayer.upper()} ({data['time']}) - Time has already passed today.")
            continue

        unix_timestamp = int(prayer_time.timestamp())
        headers = {
            "Authorization": f"Bearer {qstash_token}",
            "Upstash-Not-Before": str(unix_timestamp), 
            "Upstash-Forward-Authorization": f"Bearer {smartthings_token}",
            "Content-Type": "application/json"
        }

        response = requests.post(qstash_publish_url, headers=headers, json=payload)
        if response.status_code in [200, 201]:
            print(f"✅ Scheduled {prayer.upper()} at {prayer_time.strftime('%H:%M %Z')} (UNIX: {unix_timestamp})")
        else:
            print(f"❌ Failed to schedule {prayer.upper()}: Status {response.status_code}")

def main():
    times = get_todays_begins_times()
    if not times or len(times) == 0:
        print("Failed to scrape timetable.")
        return

    print("Successfully scraped times:")
    for p, t in times.items():
        print(f"  {p.upper()}: {t['time']}")

    schedule_with_qstash(times)

if __name__ == "__main__":
    main()
