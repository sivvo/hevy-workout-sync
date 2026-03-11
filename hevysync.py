import csv
import sys
import argparse
import logging
import requests
#import requests_random_user_agent
import os
import re
import sqlite3
import json
import time
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from collections import defaultdict

LOG = logging.getLogger('hevy-sync')
FORMATTER = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

def setup():
    parser = argparse.ArgumentParser(prog="hevy-sync.log",
                                        description='Sync between Hevy AI and local file, analyse, and generate workouts')
    parser.add_argument('--getworkouts', action='store_true', dest="getworkouts", help="Sync workouts. Set --workoutmode to new or full", required=False)
    parser.add_argument("--user", action="store", dest="user", help="Specify the user name, will be used for all file prefixes", required=True)
    parser.add_argument("--version", action="version", version="%(prog)s v0.1alpha")
    parser.add_argument('--verbose', action='store_true', dest="verbose", help="Turn on verbose mode")

    args = parser.parse_args()

    LOG = logging.getLogger('hevy-sync')
    FORMATTER = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

    file_hdlr = logging.FileHandler('hevy-sync.log')
    file_hdlr.setFormatter(FORMATTER)

    console_hdlr = logging.StreamHandler()
    console_hdlr.setFormatter(FORMATTER)

    if args.verbose:
        LOG.setLevel(logging.DEBUG)
        file_hdlr.setLevel(logging.DEBUG)
        console_hdlr.setLevel(logging.DEBUG)
        LOG.debug("Verbose mode enabled: Logging level set to DEBUG")
    else:
        LOG.setLevel(logging.INFO) 
        file_hdlr.setLevel(logging.WARNING)
        console_hdlr.setLevel(logging.INFO)

    LOG.addHandler(file_hdlr)
    LOG.addHandler(console_hdlr)
    return args

class HevySync:
    API_KEY = ''
    save_path = ''
    csv_file = ''
    searchdate = ''

    def __init__(self, username: str ="default"):
        LOG.info(f"HevyDownloader class created ")
        load_dotenv()
        self.API_KEY = os.getenv("HEVY_API_KEY")
        self.save_path = os.getenv("SAVE_PATH")
        self.body_weight = float(os.getenv('BODY_WEIGHT', '0').strip())

        self.category_map = {
    # --- LEGS ---
    'squat': 'Legs', 'lunge': 'Legs', 'leg press': 'Legs', 'leg extension': 'Legs', 
    'leg curl': 'Legs', 'calf': 'Legs', 'glute': 'Legs', 'hip': 'Legs', 
    'deadlift': 'Legs', 'rdl': 'Legs', 'stiff-legged': 'Legs', 'swing': 'Legs',
    "Wall Sit": "Legs", "Dumbbell Step Up": "Legs", "Step Up": "Legs", "Barbell Step Up": "Legs",
    "1-Step Box Jump": "Legs", "Box Jump": "Legs", 'sled push': 'Legs',

    # --- GLUTES ---
    'hip thrust': 'Glutes', 'glute bridge': 'Glutes', 'kickback': 'Glutes',
    "Balance Trainer Reverse Hyperextension": "Glutes", "Stability Ball Hyperextension": "Glutes",
    "Dumbbell Good Morning": "Glutes", "Kettlebell Good Morning": "Glutes", "Good Morning (Barbell)": "Glutes",
    "Cable Pull Through": "Glutes", "Single Leg Kickback": "Glutes", 

    # --- CHEST ---
    'bench press': 'Chest', 'chest press': 'Chest', 'push up': 'Chest', 
    'fly': 'Chest', 'hammerstrength chest': 'Chest', 'pec': 'Chest',
    "Floor Press (Dumbbell)": "Chest", "Single Arm Cable Press": "Chest",

    # --- BACK ---
    'row': 'Back', 'pull up': 'Back', 'chin up': 'Back', 'lat pulldown': 'Back', 
    'back extension': 'Back', 'superman': 'Back', 'bird dog': 'Back', 'pullover': 'Back',
    "Prone W’s": "Back", "Prone T’s": "Back", "Prone Y’s": "Back", "Rack Pulls": "Back",
    "Reverse Grip Pull Down": "Back",

    # --- SHOULDERS ---
    'overhead press': 'Shoulders', 'shoulder press': 'Shoulders', 'lateral raise': 'Shoulders', 
    'front raise': 'Shoulders', 'rear delt': 'Shoulders', 'face pull': 'Shoulders', 'shrug': 'Shoulders',
    "Half Kneeling DB Press": "Shoulders", "Arnold Press (Dumbbell)": "Shoulders", "Landmine Press": "Shoulders",
    "Front Plate Raise": "Shoulders", "Forward Arm Circle": "Shoulders", "Db Trap Raise": "Shoulders", 
    "Face Down Plate Neck Resistance": "Shoulders", "Kettlebell Jerk": "Shoulders",

    # --- ARMS ---
    'bicep': 'Arms', 'curl': 'Arms', 'tricep': 'Arms', 'pushdown': 'Arms', 
    'dip': 'Arms', 'skull crusher': 'Arms', 'hammer curl': 'Arms',
    "Skullcrusher (Dumbbell)": "Arms", "Dumbbell Kickbacks": "Arms", "Battle Ropes": "Arms",
    "Cable Bicep Curl": "Arms", "Cable Tricep Extension": "Arms",

    # --- Core ---
    'plank': 'Core', 'crunch': 'Core', 'leg raise': 'Core', 'russian twist': 'Core', 'abs': 'Core',
    "Balance Trainer Braced Bicycle Kicks": "Core","Balance Trainer Braced Frog Kicks": "Core",
    "Balance Trainer Mountain Climber": "Core","Balance Trainer Lying Toe Taps": "Core","Cable Wood Chop (Low to High)": "Core",
    "Kettlebell Sit Up and Press": "Core","Cross Body Mountain Climber": "Core","Standing Cable Core Twist": "Core",
    "Knee Raise Parallel Bars": "Core","Cable Twist (Up to down)": "Core","Vertical Knee Raise": "Core",
    "Hanging Knee Raise": "Core","Scissor Crossover Kick": "Core","Alternating Heel Touch": "Core",
    "Dumbbell Side Bend": "Core","Cable Wood Chop": "Core","Flutter Kicks": "Core","Scissor Kick": "Core",
    "Toe Touchers": "Core","Kettlebell Halo": "Core","Leg Pull-In": "Core","Ab Wheel": "Core","Dead Bug": "Core","Sit Up": "Core",
    "Bear Crawl": "Core", "Iron Cross": "Core",

    # --- Grip ---
    'farmers walk': 'Grip', 'carry': 'Grip', 'dead hang': 'Grip', "Single Arm Bottoms-up Kettlebell Press": "Grip", 
    "Climbing": "Grip",

    # --- CARDIO & WARM UP ---
    'walking': 'Cardio', 'treadmill': 'Cardio', "Aerobics": "Cardio",  "Spinning": "Cardio",
    "Scuba Diving": "Cardio", "Rowing Machine": "Cardio", "Elliptical Trainer": "Cardio", 

    "Butt Scoot": "Warm Up", "Airplane": "Warm Up", "Cat Cow": "Warm Up", "Stretching": "Warm Up",
    "Foam Roll Hamstrings": "Warm Up", 'warm up': 'Warm Up',

        }

        if self.API_KEY is None:
            LOG.critical("API Key is missing! Check your .env file.")
            sys.exit(1)

        self.username = username
        self.base_url = "https://api.hevyapp.com/v1"
        self.headers = {
            "api-key": self.API_KEY,
            "Accept": "application/json"
        }

        if self.save_path: #save path has been set
            self.csv_file = os.path.join(self.save_path, username, "-hevy_stats.csv")
            self.db = os.path.join(self.save_path, username, "-hevy.db")
        else:
            LOG.warning(f"SAVE_PATH not set in .env. Using current folder")
            self.csv_file = f"{username}-hevy_stats.csv"
            self.db = f"{username}-hevy.db"
        LOG.debug(f"Saving CSV output to: {self.csv_file}")
        LOG.debug(f"Saving DB output to: {self.db}")
        
        self.conn = sqlite3.connect(self.db, check_same_thread=False)
        self._create_tables()
        self._seed_exercise_mapping()
        self._create_analytics_view()

    # Setup methods
    def _create_analytics_view(self) -> None:
        self.conn.execute("DROP VIEW IF EXISTS v_workout_analytics")
        
        view_query = """
        CREATE VIEW v_workout_analytics AS
        WITH flattened_sets AS (
            SELECT 
                w.hevy_id,
                w.start_time,
                w.end_time,
                w.title AS workout_name,
                w.routine_id,
                ej.value ->> '$.title' AS exercise_name,
                ej.value ->> '$.notes' AS exercise_notes,
                (sj.key + 1) AS set_index,
                CAST(sj.value ->> '$.weight_kg' AS FLOAT) AS raw_weight,
                CAST(sj.value ->> '$.reps' AS INTEGER) AS reps,
                CAST(sj.value ->> '$.distance_meters' AS FLOAT) AS distance_meters,
                CAST(sj.value ->> '$.duration_seconds' AS FLOAT) AS duration_seconds,
                CAST(sj.value ->> '$.rpe' AS FLOAT) AS rpe,
                sj.value ->> '$.custom_metric' AS custom_metric,
                sj.value ->> '$.type' AS set_type
            FROM workouts w,
                json_each(w.raw_json, '$.exercises') ej,
                json_each(ej.value, '$.sets') sj
        )
        SELECT 
            f.start_time,
            
            -- NEW: Time Dimensions
            strftime('%Y-W%W', f.start_time) AS week_year,   -- e.g., '2026-W01'
            CASE strftime('%w', f.start_time)
                WHEN '0' THEN 'Sunday'
                WHEN '1' THEN 'Monday'
                WHEN '2' THEN 'Tuesday'
                WHEN '3' THEN 'Wednesday'
                WHEN '4' THEN 'Thursday'
                WHEN '5' THEN 'Friday'
                WHEN '6' THEN 'Saturday'
            END AS day_of_week,
            strftime('%H', f.start_time) AS hour_of_day,    -- Useful for 'Time of Day' analysis
            
            f.end_time,
            f.workout_name,
            f.exercise_name,
            f.exercise_notes,
            COALESCE(m.muscle_group, 'Other') AS muscle_group,
            f.set_index,
            f.raw_weight AS weight_kg,
            f.reps,
            f.distance_meters,
            f.duration_seconds,
            f.rpe,
            f.custom_metric,
            f.set_type AS type,
            
            -- Full Master Volume Logic
            CASE 
                WHEN COALESCE(f.distance_meters, 0) > 0 THEN 
                    CASE WHEN COALESCE(f.raw_weight, 0) = 0 THEN f.distance_meters ELSE (f.raw_weight * f.distance_meters) END
                WHEN (f.exercise_name LIKE '%Pull Up%' OR f.exercise_name LIKE '%Dip%' OR f.exercise_name LIKE '%Chin Up%') THEN 
                    ((81.0 + COALESCE(f.raw_weight, 0)) * COALESCE(f.reps, 0))
                WHEN COALESCE(f.raw_weight, 0) = 0 AND COALESCE(f.reps, 0) > 0 THEN (81.0 * f.reps)
                WHEN COALESCE(f.raw_weight, 0) = 0 AND COALESCE(f.duration_seconds, 0) > 0 THEN f.duration_seconds
                ELSE 
                    (CASE 
                        WHEN f.routine_id IS NULL AND (f.exercise_name LIKE '%Dumbbell%' OR f.exercise_name LIKE '%DB%') 
                        THEN (COALESCE(f.raw_weight, 0) * 2) * COALESCE(f.reps, 0) 
                        ELSE COALESCE(f.raw_weight, 0) * COALESCE(f.reps, 0) 
                    END)
            END AS volume
        FROM flattened_sets f
        LEFT JOIN exercise_mapping m ON f.exercise_name = m.exercise_name;
        """
        self.conn.execute(view_query)
        self.conn.commit()
      
    def _create_tables(self) -> None:
        query = """
        CREATE TABLE IF NOT EXISTS workouts (
            hevy_id TEXT PRIMARY KEY,
            start_time DATETIME,
            end_time DATETIME,
            created_at DATETIME,
            updated_at DATETIME,
            routine_id CHAR(36),
            title TEXT,
            raw_json TEXT
        );
        """
        self.conn.execute(query)
        self.conn.commit()
        # metadata table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        self.conn.commit()

        # exercise mapping table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS exercise_mapping (
            exercise_name TEXT PRIMARY KEY,
            muscle_group TEXT
            )
        """)
        self.conn.commit()

        # exercise templates table
        # TODO - this might replace the custom exercise_mapping table we made earlier
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS exercise_templates (
            id TEXT PRIMARY KEY,
            title TEXT,
            type TEXT, 
            primary_muscle_group TEXT, 
            secondary_muscle_groups TEXT, 
            equipment TEXT, 
            is_custom BOOLEAN
            )
        """)
        self.conn.commit()

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS routine_folders (
            id TEXT PRIMARY KEY,
            index_no INTEGER,
            title TEXT,
            updated_at DATETIME,
            created_at DATETIME
            )
        """)
        self.conn.commit()

        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS routines (
            id TEXT,
            title TEXT,
            folder_id TEXT,
            updated_at DATETIME,
            created_at DATETIME,
            exercise_template_id TEXT,
            exercise_title TEXT,
            exercise_notes TEXT,
            exercise_index INTEGER,
            superset_id TEXT,
            set_data TEXT,
            rest_seconds INTEGER,
            PRIMARY KEY (id, exercise_index)
        )
        """)
        self.conn.commit()

    def _seed_exercise_mapping(self) -> None:
        """Checks for exercises in the JSON that aren't in the mapping table yet."""
        cursor = self.conn.execute("""
            SELECT DISTINCT json_each.value ->> '$.title' 
            FROM workouts, json_each(raw_json, '$.exercises')
            WHERE json_each.value ->> '$.title' NOT IN (SELECT exercise_name FROM exercise_mapping)
        """)
        new_exercises = [row[0] for row in cursor.fetchall()]
        
        if new_exercises:
            LOG.info(f"Found {len(new_exercises)} new exercises. Mapping to muscle groups")
            for name in new_exercises:
                category = self.get_category(name)            
                LOG.info(f"Mapping exercise '{name}' to category '{category}'")
                self.conn.execute("INSERT INTO exercise_mapping (exercise_name, muscle_group) VALUES (?, ?)", 
                                (name, category))
            self.conn.commit()        

    # Helper/Utility functions
    def find_active_routine_folder(self) -> tuple | None:
        """Finds the most relevant routine folder based on the current date.
        That means the title (YYYY-MM) closest to today's date.        
        """
        cursor = self.conn.execute("SELECT id, title FROM routine_folders")
        folders = cursor.fetchall()
        if not folders:
            LOG.warning("No routine folders found in the database.")
            return None

        today = datetime.now()
        closest_entry = min(
            folders, 
            key=lambda x: abs(today - datetime.strptime(x[1], '%Y-%m'))
        )
        LOG.info(f"Found {len(folders)} folders.")
        LOG.info(f"Active routine folder ID: {closest_entry[0]} (Title: {closest_entry[1]})")
        return (closest_entry[0], closest_entry[1])

    def _clean(self, val):
        # Helper to turn None into an empty string and ensure no tuples
        if val is None:
            return 0
        # If it accidentally became a tuple, take the first element
        if isinstance(val, tuple):
            return val[0] if val[0] is not None else 0
        return val

    def _format_date_string(self, date_str: str) -> str:
        if not date_str:
            return ""
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            return date_str # Return original if it's not a valid date

    def _increment_timestamp_by_microsecond(self, ts_string: str) -> str:
        """
        Increments an ISO timestamp by 1 microsecond to prevent 
        duplicate retrieval from 'greater-than-or-equal-to' APIs.
        """
        clean_ts = ts_string.replace('Z', '+00:00')
        dt = datetime.fromisoformat(clean_ts)
        # Add 1 millisecond (1000 microseconds) 
        incremented_dt = dt + timedelta(milliseconds=1) 

        # Format with 3 decimal places manually to be safe
        main_part = incremented_dt.strftime('%Y-%m-%dT%H:%M:%S')
        millis = incremented_dt.strftime('%f')[:3]
    
        return f"{main_part}.{millis}Z"

    # General methods
    def _save_to_file(self) -> None:
        """
        Exports the processed analytical view to CSV.
        All transformation logic now lives in the SQLite View 'v_workout_analytics'.
        """
        LOG.debug("Entering _save_to_file method")
        
        # We select specific columns to ensure the CSV header matches the data exactly
        query = """
            SELECT 
                start_time, end_time, workout_name, exercise_name, exercise_notes, 
                muscle_group, set_index, weight_kg, reps, distance_meters, 
                duration_seconds, rpe, custom_metric, type, volume 
            FROM v_workout_analytics 
            ORDER BY start_time DESC
        """

        try:
            cursor = self.conn.execute(query)
            rows = cursor.fetchall()
            
            if not rows:
                LOG.info("No data found in v_workout_analytics for export")
                return

            with open(self.csv_file, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow([
                    "start_time", "end_time", "workout", "exercise", "exercise_notes", 
                    "muscle_group", "set_index", "weight_kg", "reps", "distance_meters", 
                    "duration_seconds", "rpe", "custom_metric", "type", "volume"
                ])
                
                writer.writerows(rows)
                line_counter = len(rows)

            LOG.info(f"Export complete. Lines written: {line_counter}")
            
        except Exception as e:
            LOG.error(f"Error creating CSV file: {e}")
        
        # Note: Removed self.conn.close() to keep the connection alive for other tasks
        return

    def _make_get_request(self, endpoint: str, params =None):
        """
        Internal helper to handle all API GET communication.
        Returns JSON data if successful, None if it fails.
        """
        url = f"{self.base_url}/{endpoint}"
        try:
            LOG.debug(f"Requesting: {url} with params: {params}")    
            # Use a timeout so the script doesn't hang forever if the API is slow
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            # This triggers an error for 4xx or 5xx status codes
            response.raise_for_status()
            response = response.json()
            LOG.debug(f"Remote response: {response}")
            return response
        except requests.exceptions.HTTPError as http_err:
            LOG.error(f"HTTP error occurred: {http_err} - {response.text}")
        except requests.exceptions.ConnectionError:
            LOG.error("Failed to connect to the Hevy API. Check your internet.")
        except requests.exceptions.Timeout:
            LOG.error("The request timed out.")
        except requests.exceptions.RequestException as err:
            LOG.error(f"An unexpected error occurred: {err}")
        
        return None

    def _make_post_request(self, endpoint: str, params =None):
        """
        Internal helper to handle all API POST communication.
        Returns JSON data if successful, None if it fails.
        """
        url = f"{self.base_url}/{endpoint}"
        try:
            LOG.debug(f"POSTING: {url} with params: {params}")    
            # Use a timeout so the script doesn't hang forever if the API is slow
            response = requests.post(url, headers=self.headers, json=params, timeout=10)
            # This triggers an error for 4xx or 5xx status codes
            response.raise_for_status()
            response = response.json()
            LOG.debug(f"Remote response: {response}")
            return response
        except requests.exceptions.HTTPError as http_err:
            LOG.error(f"HTTP error occurred: {http_err} - {response.text}")
        except requests.exceptions.ConnectionError:
            LOG.error("Failed to connect to the Hevy API. Check your internet.")
        except requests.exceptions.Timeout:
            LOG.error("The request timed out.")
        except requests.exceptions.RequestException as err:
            LOG.error(f"An unexpected error occurred: {err}")
        
        return None

    def _get_last_sync_time(self):
        """Returns the ISO timestamp of the last successful sync, or None if first time."""
        cursor = self.conn.execute("SELECT value FROM metadata WHERE key = 'last_sync_at'")
        row = cursor.fetchone()
        return row[0] if row else None

    def _update_last_sync_time(self, timestamp) -> None:
        """Updates the sync marker to the latest event time received."""
        # need to increment the timestamp cuz hevy is doing >= on the 'since' timestamp
        ammendedTimeStamp = self._increment_timestamp_by_microsecond(timestamp)
        LOG.info(f"setting new marker: {ammendedTimeStamp} - was {timestamp}")
        query = "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_sync_at', ?)"
        self.conn.execute(query, (ammendedTimeStamp,))
        self.conn.commit()

    def get_category(self, exercise_name: str) -> str:

        """Matches an exercise name to a category using the keyword map."""
        name_lower = exercise_name.lower()
        for keyword, category in self.category_map.items():
            if keyword.lower() in name_lower:
                return category
        return 'Other'  # Fallback for unique exercises   
    
    def _save_workout(self, workout_data) -> None:
        """Saves a new workout or updates an existing one."""
        query = """
        INSERT OR REPLACE INTO workouts (hevy_id, start_time, end_time, created_at, updated_at, routine_id, title, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        # We store the full JSON response in one column so we don't lose any detail
        # This is going to duplicate all of the other fields - is that desirable?
        self.conn.execute(query, (
            workout_data['id'],
            workout_data['start_time'],
            workout_data['end_time'],
            workout_data['created_at'],
            workout_data['updated_at'],
            workout_data['routine_id'],
            workout_data['title'],
            json.dumps(workout_data)
        ))
        self.conn.commit()
        LOG.debug(f"Saved workout {workout_data['id']} to database.")

    def _delete_workout(self, workout_id: str) -> None:
        """Handles the 'deleted' event type."""
        self.conn.execute("DELETE FROM workouts WHERE hevy_id = ?", (workout_id,))
        self.conn.commit()
        LOG.info(f"Deleted workout {workout_id} from database.")
    
    def _get_all_historical_workouts(self, endpoint: str, pageSize: int) -> list:
        all_results = []
        page = 1
        while True:
            LOG.info(f"Fetching page {page} of history...")
            data = self._make_get_request(endpoint, params={"page": page, "pageSize": pageSize})
            LOG.debug(f"response: {data}")
            if not data or not data.get('workouts'):
                break
            all_results.extend(data['workouts'])
            # Check if there's a next page (Hevy uses page/page_count in response)
            if page >= data.get('page_count', 1):
                break
            page += 1
        return all_results

    def sync_workouts(self) -> None:
        LOG.info("syncing workouts")
        page = 1 # we always start at page 1
        pageSize = 10 #default - 10 pages

        last_sync = self._get_last_sync_time()
        # On first run, last_sync will be None, this should trigger a complete run
        if last_sync is None:
            endpoint = "workouts"
            LOG.info("syncing all workouts")
            all_results = self._get_all_historical_workouts(endpoint, pageSize)
            if all_results:
                LOG.info(f"Iterating through results to save them")
                for workout in all_results:
                    LOG.debug(f"workout: {workout}")
                    self._save_workout(workout)

                newest_workout = all_results[0] # newest is first
                newest_timestamp = newest_workout['updated_at']
                LOG.info(f"newest workout: {newest_workout} timestamp: {newest_timestamp}")
                self._update_last_sync_time(newest_timestamp)
                LOG.info(f"Full sync complete. Imported {len(all_results)} workouts.")
        else:
            #run_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            endpoint = "workouts/events"
            LOG.info(f"get new workouts since {last_sync}")
            params = {"page": page, "pageSize": pageSize, "since": last_sync}
            events_data = self._make_get_request(endpoint, params)
            #LOG.info(f"events_data: {events_data}")
            if not events_data or 'events' not in events_data:
                LOG.info("No new events to sync.")
                return

            events = events_data['events']
            for event in reversed(events):
                etype = event['type']
                workout = event['workout']
                if etype in ['created', 'updated']:
                    LOG.debug(f"found a new or modified workout: {workout}")
                    self._save_workout(workout)
                elif etype == 'deleted':
                    LOG.info("found a deletion event: {workout['id']}")
                    self._delete_workout(workout['id'])
            if events:
                #let's get the latest time from the hevy API
                timestamp = events[0]["workout"]["updated_at"]
            # we can use system time to set the last check
            LOG.info(f"Sync complete")
            self._update_last_sync_time(timestamp)

    def _save_exercise(self, exercise_data) -> None:
        """Saves a new exercise or updates an existing one."""
        query = """
        INSERT OR REPLACE INTO exercise_templates (id, title, type, primary_muscle_group, secondary_muscle_groups, equipment, is_custom)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        self.conn.execute(query, (
            exercise_data['id'],
            exercise_data['title'],
            exercise_data['type'],
            exercise_data['primary_muscle_group'],
            json.dumps(exercise_data['secondary_muscle_groups']),
            exercise_data['equipment'],
            int(exercise_data['is_custom'])        
         ))
        self.conn.commit()
        LOG.debug(f"Saved exercise {exercise_data['id']} to database.")

    def sync_exercises(self) -> None:
        """ 
        periodic sync of exercises from Hevy API so that 
        we have access to the exercise ID's for generating workouts later.
        This creates/updates the exercise_templates table in the local DB. 
        We will need to pass this table to the LLM API later on when it's 
        time to generate new workouts because the exercise ID's are required
        """
        LOG.info("syncing exercises")
        endpoint = "exercise_templates"
        page = 1
        pageSize = 100
        while True:
            LOG.info(f"Fetching page {page} of exercises...")
            data = self._make_get_request(endpoint, params={"page": page, "pageSize": pageSize})
            LOG.debug(f"response: {data}")
            if not data or not data.get('exercise_templates'):
                break
            for exercise in data['exercise_templates']:
                LOG.debug(f"exercise: {exercise}")
                self._save_exercise(exercise)

            # Check if there's a next page (Hevy uses page/page_count in response)
            if page >= data.get('page_count', 1):
                break
            page += 1

    """ TODO: Think about method for deleting routines that are no longer listed here  """
    def _save_routine_folder(self, folder_data) -> None:
        """Saves a new routine folder or updates an existing one."""
        query = """
        INSERT OR REPLACE INTO routine_folders (id, index_no, title, updated_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """
        self.conn.execute(query, (
            folder_data['id'],
            folder_data['index'],
            folder_data['title'],
            folder_data['updated_at'],
            folder_data['created_at'],
         ))
        self.conn.commit()
        LOG.debug(f"Saved routine folder {folder_data['id']} to database.")

    def backup_current_routine(self):    
        """ 
        We need to POST the current routine to Hevy API under a new name in order to create a backup
        We'll use a fixed format naming convention so we can find it later: backup_YYYY-MM
        We also need to amend the index so that the backup doesn't appear at the top of the workout list
        But the HEVY api doesn't give us a way to set the index, so annoyingly it is going to appear at the top....
        """

        """
        Create a routine_folder: POST /routine_folders
        """
        current_workout_folder_id, current_workout_folder_name = self.find_active_routine_folder()

        endpoint = "routine_folders"
        # We need the title of the main workload that we're backing up already

        post_data = {
            "routine_folder": {
            "title": f"{current_workout_folder_name}-backup"
            }
        }

        response = self._make_post_request(endpoint, post_data)        
        if response is not None:
            LOG.info(f"Created new routine folder: { response['routine_folder']['id'] }")
            new_folder_id = response['routine_folder']['id']
            #new_folder_id = 2202930

            # Now we have our new routine ID, this is where we need to save the routine

            # do we need to find the current folder id? after all, routines only has the active/recent 
            query = "SELECT * FROM routines WHERE folder_id = ?"
            cursor = self.conn.execute(query, (current_workout_folder_id,))
            routines = cursor.fetchall() # do all at once, or row by row?
            payloads = self.create_hevy_post_payloads(routines, new_folder_id)

            #LOG.info(f"payloads: {payloads}")
            #LOG.info(f"{routines}")
            for payload in payloads:
                response = self._make_post_request("routines", params=payload)
                
                if response and isinstance(response, dict):
                    # The log shows 'routine' is a LIST inside the dictionary
                    routine_list = response.get('routine', [])
                    
                    if isinstance(routine_list, list) and len(routine_list) > 0:
                        # Grab the first (and only) routine object in the list
                        routine_data = routine_list[0]
                        new_routine_id = routine_data.get('id')
                        
                        LOG.info(f"✅ Successfully backed up: {payload['routine']['title']} (New ID: {new_routine_id})")
                    else:
                        LOG.error(f"❌ Response 'routine' key was not a list or was empty: {response}")
                else:
                    LOG.error(f"❌ Failed to backup routine or unexpected response format: {payload['routine']['title']}")
                
                time.sleep(0.5)

    def create_hevy_post_payloads(self, rows, target_folder_id):
        LOG.info("creating hevy post payloads from routine rows")
        routines_map = defaultdict(list)

        for row in rows:
            routines_map[row[0]].append(row)            
        all_payloads = []

        #for r_id, r_rows in routines_map.items():
        for r_id, r_rows in reversed(list(routines_map.items())):
            routine_title = r_rows[0][1]         
            payload = {
                "routine": {
                    "title": routine_title,
                    "folder_id": target_folder_id, 
                    "notes": "", 
                    "exercises": []
                }
            }

            for row in r_rows:
                ex_template_id = row[5]
                ex_notes       = row[7]
                ex_index       = row[8] 
                superset_id    = row[9]
                raw_sets       = json.loads(row[10]) 
                rest_seconds   = row[11]

                # Clean sets: Strip 'index' and 'None' values
                cleaned_sets = []
                for s in raw_sets:
                    cleaned_set = {k: v for k, v in s.items() if k != 'index' and v is not None}
                    cleaned_sets.append(cleaned_set)

                exercise = {
                    "exercise_template_id": ex_template_id,
                    "superset_id": superset_id,
                    "rest_seconds": rest_seconds,
                    "notes": ex_notes,
                    "sets": cleaned_sets,
                    "_sort_index": ex_index # Temporary for sorting
                }
                payload["routine"]["exercises"].append(exercise)

            # Sort exercises by the temporary index
            payload["routine"]["exercises"].sort(key=lambda x: x["_sort_index"])
            
            # Final exercise cleanup
            for ex in payload["routine"]["exercises"]:
                ex.pop("_sort_index", None)
                # Clean up None values at exercise level
                if ex.get("superset_id") is None:
                    ex.pop("superset_id", None)

            all_payloads.append(payload)

        return all_payloads

    def _save_routine(self, routine_data) -> None:
        """Saves a new routine or updates an existing one.
        TODO: Need to think about the primary key here - is it just routine ID, or do we need to
        include exercise ID and set index to make it unique?
        Think about Saturdays: I have weighed sled pull 2x but they are different exercises in the same routine.
        """

        """
        We have a folder ID (that is what we're going to match against target_id to know we're on the right workout folder
        routines:
            exercises:
                index
                title
                notes
                exercise_template_id
                superset_id
                sets:
                    index
                    type
                    weight_kg
                    reps
                    distance_meters
                    duration_seconds                
                    custom_metric
                rest_seconds
        """

        id = routine_data['id']
        title = routine_data['title']
        folder_id = routine_data['folder_id']
        updated_at = routine_data['updated_at']
        created_at = routine_data['created_at']
        for exercise in routine_data['exercises']:
            exercise_template_id = exercise['exercise_template_id']
            exercise_title = exercise['title']
            exercise_notes = exercise['notes']
            exercise_index = exercise['index']
            superset_id = exercise['superset_id']
            set_data = json.dumps(exercise['sets'])
            rest_seconds = exercise['rest_seconds']
            query = """
            INSERT OR REPLACE INTO routines (id, title, folder_id, updated_at, created_at, exercise_template_id, exercise_title, exercise_notes, exercise_index, superset_id, set_data, rest_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self.conn.execute(query, (
                id, 
                title,
                folder_id,
                updated_at,
                created_at,
                exercise_template_id,
                exercise_title,
                exercise_notes,
                exercise_index,
                superset_id,
                set_data,
                rest_seconds
            ))
            self.conn.commit()
            LOG.debug(f"Saved routine {routine_data['id']} to database.")

    def sync_routines(self) -> None:
        # get routine_folders
        # use the title to figure out which one we want to use
        # then get the routines for that folder
        LOG.info("syncing workout folders")

        endpoint = "routine_folders"
        page = 1 # we always start at page 1
        pageSize = 10 #default - 10 pages

        params = {"page": page, "pageSize": pageSize}
        data = self._make_get_request(endpoint, params)
        # TODO: Handle pagination if needed
        # We're not going through multiple pages... we need to make sure if many workout folders exist that it's newest to oldest
        # Otherwise, we might miss some!
        LOG.debug(f"response: {data}")
        # Let's get all the folders, and then decide which one to use
        # We'll save them all locally in the DB anyway
        folders = []
        if not data or not data.get('routine_folders'):
            LOG.info("No folders found.")
            return
        for folder in data['routine_folders']:
            LOG.debug(f"folder: {folder}")
            folders.append(folder)
            self._save_routine_folder(folder)    
        #key=lambda x: abs(today - datetime.strptime(x['title'], '%Y-%m'))        
        #TODO - check that find_active_routine_folder() is being called correctly - it probably won't return 2 variables
        target_id, name = self.find_active_routine_folder()
        if target_id is None:
            LOG.warning("No active routine folder found.")
            return
        else:
            LOG.info(f"syncing routines for folder ID: {target_id}")
            endpoint = f"routines"
            page = 1
            pageSize = 10
            routine_data = self._make_get_request(endpoint, params={"page": page, "pageSize": pageSize})
            if not routine_data or 'routines' not in routine_data:
                LOG.warning("No routine information found.")
                return
            for routine in routine_data['routines']:
                LOG.debug(f"routine: {routine}")
                if routine['folder_id'] == target_id:
                    LOG.info(f"Saving routine {routine['title']} from target folder")
                    self._save_routine(routine)
                else:
                    LOG.debug(f"Skipping routine {routine['title']} from non-target folder")
       
    
def webhook_handler(event, context):
    """
    TODO Placeholder for future webhook handling logic.
    This function will process incoming webhook events from Hevy.
    """


if __name__ == '__main__':
    args = setup()
    #yyyymmdd_regex = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    hevydownloader = HevySync(args.user)

    if args.getworkouts:
        """ We're going to be downloading from Hevy API to local log """
        #hevydownloader.sync_workouts()
        #hevydownloader._save_to_file() # TEMPORARY DIRECT CALL
        #hevydownloader.sync_exercises()    
        hevydownloader.sync_routines() # Think about when to call things like this routine
        #hevydownloader.backup_current_routine()