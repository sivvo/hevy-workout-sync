import os
import sqlite3
import pytest
from hevysync import HevySync

# Ensure an API key is present so HevySync __init__ does not exit
os.environ.setdefault("HEVY_API_KEY", "test-api-key")
os.environ.setdefault("BODY_WEIGHT", "0")

def _clean_db_files(username):
    # Remove files that HevySync may create to avoid test pollution
    for suffix in (f"{username}-hevy.db", f"{username}-hevy_stats.csv"):
        try:
            os.remove(suffix)
        except FileNotFoundError:
            pass

def test_full_sync_calls_save_and_update():
    username = "testuser_fullsync"
    _clean_db_files(username)
    hs = HevySync(username)

    # Simulate first-run: no last sync
    hs._get_last_sync_time = lambda: None

    # Provide two workouts, newest first
    all_results = [
        {"id": "w_new", "updated_at": "2022-03-02T12:00:00Z", "start_time": None, "end_time": None, "created_at": None, "routine_id": None, "title": "Newest"},
        {"id": "w_old", "updated_at": "2022-01-01T12:00:00Z", "start_time": None, "end_time": None, "created_at": None, "routine_id": None, "title": "Old"}
    ]
    hs._get_all_historical_workouts = lambda endpoint, pageSize: all_results

    saved = []
    updated = []
    hs._save_workout = lambda workout: saved.append(workout["id"])
    hs._update_last_sync_time = lambda ts: updated.append(ts)

    hs.sync_workouts()

    assert saved == ["w_new", "w_old"]
    assert updated == ["2022-03-02T12:00:00Z"]

    _clean_db_files(username)

def test_no_new_events_when_make_request_returns_none():
    username = "testuser_nonevents"
    _clean_db_files(username)
    hs = HevySync(username)

    # Simulate existing last sync -> events path
    hs._get_last_sync_time = lambda: "2022-01-01T00:00:00Z"
    hs._make_get_request = lambda endpoint, params=None: None

    called_save = []
    called_update = []
    hs._save_workout = lambda w: called_save.append(w)
    hs._update_last_sync_time = lambda ts: called_update.append(ts)

    hs.sync_workouts()

    assert called_save == []
    assert called_update == []

    _clean_db_files(username)

def test_event_processing_calls_save_and_delete_and_updates_timestamp():
    username = "testuser_events"
    _clean_db_files(username)
    hs = HevySync(username)

    hs._get_last_sync_time = lambda: "2022-01-01T00:00:00Z"

    # Two events: first is created, second is deleted (original order)
    events = [
        {"type": "created", "workout": {"id": "w_created", "updated_at": "2022-02-01T10:00:00Z"}},
        {"type": "deleted", "workout": {"id": "w_deleted", "updated_at": "2022-02-02T11:00:00Z"}},
    ]
    hs._make_get_request = lambda endpoint, params=None: {"events": events}

    saved = []
    deleted = []
    updated = []
    hs._save_workout = lambda w: saved.append(w["id"])
    hs._delete_workout = lambda wid: deleted.append(wid)
    hs._update_last_sync_time = lambda ts: updated.append(ts)

    hs.sync_workouts()

    # The loop processes reversed(events): deleted then created
    assert deleted == ["w_deleted"]
    assert saved == ["w_created"]
    # The code sets timestamp = events[0]["workout"]["updated_at"] (first element of original list)
    assert updated == ["2022-02-01T10:00:00Z"]

    _clean_db_files(username)