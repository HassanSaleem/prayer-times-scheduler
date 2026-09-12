import os
import base64
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

def get_smartthings_access_token():
    client_id = os.environ.get("ST_CLIENT_ID")
    client_secret = os.environ.get("ST_CLIENT_SECRET")
    refresh_token = os.environ.get("ST_REFRESH_TOKEN")

    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    response = requests.post(
        "https://api.smartthings.com/v1/oauth/token",
        headers={
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id
        }
    )

    if response.status_code == 200:
        data = response.json()
        new_access_token = data.get("access_token")
        new_refresh_token = data.get("refresh_token")
        
        # Print out the new refresh token so you can update your GitHub secret if it rotates
        print(f"🔄 SmartThings Token Refreshed Successfully!")
        print(f"⚠️ NEW_REFRESH_TOKEN (Save this if running manually): {new_refresh_token}")
        
        return new_access_token
    else:
        raise Exception(f"HTTP {response.status_code} - Failed to refresh SmartThings token: {response.text}")

def schedule_with_qstash(times):
    qstash_token = os.environ.get("QSTASH_TOKEN")
    smartthings_token = get_smartthings_access_token()
    device_id = os.environ.get("DEVICE_ID")
    qstash_url = os.environ.get("QSTASH_URL")

    if not all([qstash_token, smartthings_token, device_id]):
        print("Missing required environment variables.")
        return

    # Initialize the official QStash client
    client = QStash(base_url=qstash_url, token=qstash_token)

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
            res = client.message.publish_json(
                url=target_url,
                body=payload,
                not_before=unix_timestamp,
                headers={
                    "Upstash-Forward-Authorization": f"Bearer {smartthings_token}"
                }
            )
            print(f"✅ Scheduled {prayer.upper()} at {prayer_time.strftime('%H:%M %Z')} (UNIX: {unix_timestamp}) (Message ID: {res.message_id})")
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
