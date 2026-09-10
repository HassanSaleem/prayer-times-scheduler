import os
import requests
from datetime import datetime
import pytz

def get_api_times():
    lpt_key = os.environ.get("LPT_API_KEY")
    if not lpt_key:
        print("Missing LPT_API_KEY in environment variables.")
        return None
        
    # Call the API for today's times in 24-hour format
    url = f"https://www.londonprayertimes.com/api/times/?format=json&24hours=true&key={lpt_key}"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"API request failed with status: {response.status_code}")
        return None
        
    data = response.json()
    
    # Map the JSON response keys to our script.
    # Note: The API returns 'asr' (Shafi'i) and 'asr_2' (Hanafi). 
    # Using 'asr_2' since ELM generally follows Hanafi.
    return {
        "fajr": {"time": data.get("fajr")},
        "zuhr": {"time": data.get("dhuhr")},
        "asr_2_mithl": {"time": data.get("asr_2")}, 
        "maghrib": {"time": data.get("magrib")}, # API spells it without the 'h'
        "isha": {"time": data.get("isha")}
    }

def schedule_with_qstash(times):
    qstash_token = os.environ.get("QSTASH_TOKEN")
    smartthings_token = os.environ.get("SMARTTHINGS_TOKEN")
    device_id = os.environ.get("DEVICE_ID")

    if not all([qstash_token, smartthings_token, device_id]):
        print("Missing required environment variables (QStash or SmartThings).")
        return

    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    # 1. Read your region-specific URL from environment variables (or fall back to the global one)
    qstash_base_url = os.environ.get("QSTASH_URL", "https://qstash-eu-central-1.upstash.io")
    target_url = f"https://api.smartthings.com/v1/devices/{device_id}/commands"
    qstash_publish_url = f"{qstash_base_url}/v2/publish/{target_url}"
    payload = {"commands": [{"component": "main", "capability": "switch", "command": "on"}]}

    for prayer, data in times.items():
        if not data["time"]:
            continue
            
        hour, minute = map(int, data["time"].split(':'))
        prayer_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if prayer_time <= now:
            print(f"Skipping {prayer.upper()} ({data['time']}) - Time has already passed.")
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
    times = get_api_times()
    if not times:
        print("Failed to fetch timetable from API.")
        return

    print("Successfully fetched times from API:")
    for p, t in times.items():
        print(f"  {p.upper()}: {t['time']}")

    schedule_with_qstash(times)

if __name__ == "__main__":
    main()
