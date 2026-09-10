import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

def get_todays_begins_times():
    url = "https://www.eastlondonmosque.org.uk/prayer-times"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    
    table = soup.find("table")
    if not table:
        return None
    
    # Force UK timezone
    uk_tz = pytz.timezone('Europe/London')
    today = datetime.now(uk_tz)
    today_day = str(today.day)
    
    for row in table.find_all("tr"):
        cols = [td.text.strip() for td in row.find_all(["td", "th"])]
        
        if cols and cols[0] == today_day:
            return {
                "fajr": {"time": cols[1], "is_pm": False},
                "zuhr": {"time": cols[4], "is_pm": True},
                "asr_2_mithl": {"time": cols[7], "is_pm": True},
                "maghrib": {"time": cols[9], "is_pm": True},
                "isha": {"time": cols[11], "is_pm": True}
            }
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