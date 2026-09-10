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

def trigger_smartthings():
    url = f"https://api.smartthings.com/v1/devices/{os.environ['DEVICE_ID']}/commands"
    headers = {
        "Authorization": f"Bearer {os.environ['SMARTTHINGS_TOKEN']}",
        "Content-Type": "application/json",
    }
    payload = {
        "commands": [{"component": "main", "capability": "switch", "command": "on"}]
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"SmartThings API Response: {response.status_code}")

def main():
    times = get_todays_begins_times()
    if not times:
        print("Failed to scrape timetable.")
        return

    uk_tz = pytz.timezone('Europe/London')
    now = datetime.now(uk_tz)
    
    for prayer, data in times.items():
        # Parse 12-hour string to 24-hour datetime
        hour, minute = map(int, data["time"].split(':'))
        if data["is_pm"] and hour != 12:
            hour += 12
            
        prayer_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # Calculate time difference in minutes
        diff_minutes = (now - prayer_time).total_seconds() / 60
        
        # If the prayer time occurred within the last 5 minutes, trigger the webhook
        if 0 <= diff_minutes < 5:
            print(f"Triggering Routine for {prayer.upper()} (Time: {data['time']})")
            trigger_smartthings()
            # Turn switch off immediately so it's ready for the next trigger
            # (Assuming you didn't set up an auto-off timer in SmartThings)
            return 
            
    print(f"Current time ({now.strftime('%H:%M')}) does not match any prayer times.")

if __name__ == "__main__":
    main()