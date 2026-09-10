import os
from datetime import datetime
import pytz
import requests
from qstash import QStash

def get_api_times():
    lpt_key = os.environ.get("LPT_API_KEY")
    if not lpt_key:
        print("Missing LPT_API_KEY in environment variables.")
        return None
        
    url = f"https://www.londonprayertimes.com/api/times/?format=json&24hours=true&key={lpt_key}"
    response = requests.get(url)
    
    if response.status_code != 200:
        print(f"API request failed with status: {response.status_code}")
        return None
        
    data = response.json()
    
    return {
        "fajr": {"time": data.get("fajr")},
        "zuhr": {"time": data.get("dhuhr")},
        "asr_2_mithl": {"time": data.get("asr_2")}, 
        "maghrib": {"time": data.get("magrib")},
        "isha": {"time": data.get("isha")}
    }

def schedule_with_qstash(times):
    qstash_token = os.environ.get("QSTASH_TOKEN")
    smartthings_token = os.environ.get("SMARTTHINGS_TOKEN")
    device_id = os.environ.get("DEVICE_ID")

    if not all([qstash_token, smartthings_token, device_id]):
        print("Missing required environment variables.")
        return

    # Initialize the official QStash client
    client = QStash(token=qstash_token)

    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)

    target_url = f"https://api.smartthings.com/v1/devices/{device_id}/commands"
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

        try:
            # Use the SDK's publish method with headers and delay/timestamp controls
            client.message.publish_json(
                url=target_url,
                body=payload,
                not_before=unix_timestamp,
                headers={
                    "Upstash-Forward-Authorization": f"Bearer {smartthings_token}"
                }
            )
            print(f"✅ Scheduled {prayer.upper()} at {prayer_time.strftime('%H:%M %Z')} (UNIX: {unix_timestamp})")
        except Exception as e:
            print(f"❌ Failed to schedule {prayer.upper()}: {e}")

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