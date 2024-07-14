import requests
import time
from dotenv import load_dotenv
import os
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pprint

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WerosterClient:
    def __init__(self, start_date=None, end_date=None):
        # Calculate a default initial date from now
        default_start_date = datetime.now() - relativedelta(months=2)
        
        # Set start_date if not provided
        if start_date is None:
            start_date = default_start_date
        
        # Use the provided end_date only if start_date is provided and before end_date
        if start_date and end_date and start_date < end_date:
            self.end_date = end_date
        else:
            self.end_date = datetime.now()
        
        self.start_date = start_date
        
        self.base_url = "https://rch.weroster.com.au"
        self.api_root = f"{self.base_url}/api/v1"
        self.email = os.getenv('EMAIL')
        self.password = os.getenv('PASSWORD')
        self.access_token = None
        self.refresh_token = None
        self.session = requests.Session()
        self.registrars = {}
        self.events = {}
        self.calendar_data = None
        self.request_delay = 1
        self.designations_to_include = ['registrar']
        self.names_to_exclude = ['---unassigned---']
        self.session.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-AU,en-GB;q=0.9,en-US;q=0.8,en=q=0.7",
            "Cache-Control": "no-cache",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.base_url,
            "Pragma": "no-cache",
            "Referer": f"{self.base_url}/user/login?redirect={self.base_url}/",
            "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        })

    def login(self):
        login_url = f"{self.api_root}/login"
        payload = {
            "email": self.email,
            "password": self.password
        }
        response = self.session.post(login_url, data=payload)
        logger.info("Login response status code: %s", response.status_code)
        
        if response.status_code == 200:
            try:
                data = response.json()
                self.access_token = data['access_token']
                self.refresh_token = data['refresh_token']
                logger.info("Login successful.")
                self.update_headers_with_auth()
            except requests.exceptions.JSONDecodeError as e:
                logger.error("JSON decode error: %s", e)
                logger.error("Response content: %s", response.content)
        else:
            logger.error("Login failed with status code: %s", response.status_code)
            logger.error("Error message: %s", response.text)

    def refresh_token(self):
        refresh_url = f"{self.api_root}/refresh"
        payload = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token
        }
        response = self.session.post(refresh_url, data=payload)
        logger.info("Refresh token response status code: %s", response.status_code)
        
        if response.status_code == 200:
            try:
                data = response.json()
                self.access_token = data['access_token']
                self.refresh_token = data['refresh_token']
                logger.info("Token refresh successful.")
                self.update_headers_with_auth()
            except requests.exceptions.JSONDecodeError as e:
                logger.error("JSON decode error: %s", e)
                logger.error("Response content: %s", response.content)
        else:
            logger.error("Token refresh failed with status code: %s", response.status_code)
            logger.error("Error message: %s", response.text)

    def update_headers_with_auth(self):
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "Cookie": f"roster_access_token={self.access_token}; roster_refresh_token={self.refresh_token}"
        })

    def _get_calendar_data(self, start_date, end_date):
        calendar_url = f"{self.api_root}/roster/events/by-range"
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "_": int(time.time() * 1000)  # Current timestamp in milliseconds
        }
        response = self.session.get(calendar_url, params=params)
        
        if response.status_code == 401:
            logger.info("Access token expired, refreshing token.")
            self.refresh_token()
            response = self.session.get(calendar_url, params=params)

        if response.status_code == 200:
            logger.info("Authenticated request successful.")
            return response.json()
        else:
            logger.error("Authenticated request failed with status code: %s", response.status_code)
            logger.error("Error message: %s", response.text)
            logger.debug("Request URL: %s", response.url)
            logger.debug("Request Headers: %s", response.request.headers)
            return None
    
    def set_date_range(self, start_date, end_date):
        if start_date < end_date:
            self.start_date = start_date
            self.end_date = end_date
        else:
            logger.error(f"Start {start_date} must be before end {end_date}")

    def generate_weeks(self):
        start_date = self.start_date
        end_date = self.end_date

        # Adjust the start date to the previous Monday if it's not already a Monday
        if start_date.weekday() != 0:
            start_date -= timedelta(days=start_date.weekday())

        weeks = []
        current_date = start_date

        while current_date <= end_date:
            week_start = current_date
            week_end = week_start + timedelta(days=6)

            if week_end > end_date:
                week_end = end_date

            weeks.append((week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d")))
            current_date = week_end + timedelta(days=1)

        return weeks
    
    def parse_events(self, data):
        events = []
        
        for event in data['events']:
            staff = []
            for person in event['staff']:
                person_details = {
                    'name': person['display_name'],
                    'designation': person['designation']['name']
                }
                staff.append(person_details)
            
            event_details = {
                'name': event['name'],
                'date': event['date'],
                'start_time': datetime.strptime(event['start_time'], "%Y-%m-%d %H:%M:%S"),
                'end_time': datetime.strptime(event['end_time'], "%Y-%m-%d %H:%M:%S"),
                'session': event['session'],
                'location': event['location']['name'],
                'staff': staff
            }
            
            events.append(event_details)
        
        return events
    
    def get_registrar_list_counts(self, data):
        events = self.parse_events(data)

        for event in events:
            event_name = event['name']
            for person in event['staff']:
                name = person['name']
                if person['designation'].lower() not in self.designations_to_include:
                    continue
                if name.lower() in self.names_to_exclude:
                    continue
                if name not in self.registrars:
                    self.registrars[name] = {event_name: 1}
                else:
                    self.registrars[name][event_name] = self.registrars[name].get(event_name, 0) + 1

        return self.registrars
    
    def get_event_registrar_counts(self, data):
        events = self.parse_events(data)

        for event in events:
            event_name = event['name']
            for person in event['staff']:
                registrar_name = person['name']
                if person['designation'].lower() not in self.designations_to_include:
                    continue
                if registrar_name.lower() in self.names_to_exclude:
                    continue
                if event_name not in self.events:
                    self.events[event_name] = {registrar_name: 1}
                else:
                    self.events[event_name][registrar_name] = self.events[event_name].get(registrar_name, 0) + 1

        return self.events

    def populate_calendar_data(self):
        weeks = self.generate_weeks()
        calendar_data = []
        
        for start, end in weeks:
            week_data = self._get_calendar_data(start, end)
            if week_data is None:  # Failed fetch
                break
            calendar_data.append(week_data)

            # Delay time between requests
            time.sleep(self.request_delay)
        
        self.calendar_data = calendar_data
        return calendar_data
    
    def assemble_registrar_events(self):
        if not self.access_token:
            logger.error("Must be logged in")
            return None
        
        if not self.calendar_data:
            self.populate_calendar_data()

        for week_data in self.calendar_data:
            self.get_registrar_list_counts(week_data)

        self.registrars = dict(sorted(self.registrars.items()))

        return self.registrars
    
    def assemble_events_with_registrar_counts(self):
        if not self.access_token:
            logger.error("Must be logged in")
            return None
        
        if not self.calendar_data:
            self.populate_calendar_data()

        for week_data in self.calendar_data:
            self.get_event_registrar_counts(week_data)

        self.events = dict(sorted(self.events.items()))

        return self.events
    
    def close_connection(self):
        self.session.close()
        logger.info("Session closed.")

if __name__ == "__main__":
    client = WerosterClient()
    client.login()
    client.populate_calendar_data()
    registrars = client.assemble_registrar_events()
    print(registrars)
    client.close_connection()
