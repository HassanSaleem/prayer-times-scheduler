import os
import subprocess
import base64
import logging
from datetime import datetime
import pytz
import requests
from qstash import QStash

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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

    if not client_id or not client_secret or not refresh_token:
        logger.error("Missing one or more required environment variables: ST_CLIENT_ID, ST_CLIENT_SECRET, ST_REFRESH_TOKEN")
        raise ValueError("SmartThings credentials missing from environment.")

    credentials = f"{client_id.strip()}:{client_secret.strip()}"
    encoded_credentials = base64.b64encode(credentials.encode("ascii")).decode("ascii").strip()

    token_url = "https://api.smartthings.com/v1/oauth/token"
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id
    }

    logger.info("Attempting to exchange refresh token for a new SmartThings access token...")

    logger.info(f"Client ID length: {len(client_id) if client_id else 0}")
    logger.info(f"Client Secret length: {len(client_secret) if client_secret else 0}")
    logger.info(f"Encoded Basic Auth header preview: {encoded_credentials[:10]}...")
    response = requests.post(token_url, headers=headers, data=payload)

    logger.info(f"SmartThings token response status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        access_token = data.get("access_token")
        new_refresh_token = data.get("refresh_token")
        
        logger.info("Successfully generated new SmartThings access token.")
        if new_refresh_token and new_refresh_token != refresh_token:
            logger.info("New refresh token received. Automatically updating GitHub Secret...")
            repo = os.environ.get("REPO_NAME")
            gh_token = os.environ.get("GH_TOKEN")
            
            if repo and gh_token:
                try:
                    # Automatically update the GitHub Actions secret with the rotated token
                    subprocess.run(
                        ["gh", "secret", "set", "ST_REFRESH_TOKEN", "--body", new_refresh_token, "--repo", repo],
                        check=True,
                        env={**os.environ, "GH_TOKEN": gh_token}
                    )
                    logger.info("Successfully updated ST_REFRESH_TOKEN secret in GitHub!")
                except Exception as e:
                    logger.warning(f"Failed to auto-update GitHub secret: {e}")
            
        return access_token
    else:
        logger.error(f"Token refresh failed. Response text: {repr(response.text)}")
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
