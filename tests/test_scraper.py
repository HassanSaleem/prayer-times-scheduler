from datetime import datetime
from unittest.mock import MagicMock

import pytest
import pytz

import scraper


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


# ---- get_api_times ----

def test_get_api_times_missing_key(monkeypatch):
    monkeypatch.delenv("LPT_API_KEY", raising=False)
    assert scraper.get_api_times() is None


def test_get_api_times_request_failure(monkeypatch):
    monkeypatch.setenv("LPT_API_KEY", "test-key")
    monkeypatch.setattr(scraper.requests, "get", lambda url: FakeResponse(500))
    assert scraper.get_api_times() is None


def test_get_api_times_success(monkeypatch):
    monkeypatch.setenv("LPT_API_KEY", "test-key")
    api_data = {
        "fajr": "05:12",
        "dhuhr": "13:01",
        "asr_2": "17:45",
        "magrib": "19:30",
        "isha": "21:00",
    }
    monkeypatch.setattr(scraper.requests, "get", lambda url: FakeResponse(200, api_data))

    times = scraper.get_api_times()

    assert times == {
        "fajr": {"time": "05:12"},
        "zuhr": {"time": "13:01"},
        "asr_2_mithl": {"time": "17:45"},
        "maghrib": {"time": "19:30"},
        "isha": {"time": "21:00"},
    }


# ---- schedule_with_qstash ----

@pytest.fixture
def qstash_env(monkeypatch):
    monkeypatch.setenv("QSTASH_TOKEN", "qstash-token")
    monkeypatch.setenv("SMARTTHINGS_TOKEN", "smartthings-token")
    monkeypatch.setenv("DEVICE_ID", "device-123")
    monkeypatch.setenv("QSTASH_URL", "https://qstash.example.com")


def test_schedule_with_qstash_missing_env(monkeypatch):
    monkeypatch.delenv("QSTASH_TOKEN", raising=False)
    mock_qstash_cls = MagicMock()
    monkeypatch.setattr(scraper, "QStash", mock_qstash_cls)

    scraper.schedule_with_qstash({"fajr": {"time": "05:00"}})

    mock_qstash_cls.assert_not_called()


def test_schedule_with_qstash_skips_past_and_schedules_future(monkeypatch, qstash_env):
    uk_tz = pytz.timezone("Europe/London")
    fixed_now = uk_tz.localize(datetime(2026, 1, 1, 12, 0, 0))

    fake_datetime = MagicMock(wraps=datetime)
    fake_datetime.now.return_value = fixed_now
    monkeypatch.setattr(scraper, "datetime", fake_datetime)

    mock_client = MagicMock()
    mock_client.message.publish_json.return_value = MagicMock(message_id="msg-1")
    monkeypatch.setattr(scraper, "QStash", MagicMock(return_value=mock_client))

    times = {
        "fajr": {"time": "05:00"},  # already passed relative to fixed_now
        "isha": {"time": "18:30"},  # still upcoming
    }

    scraper.schedule_with_qstash(times)

    mock_client.message.publish_json.assert_called_once()
    _, kwargs = mock_client.message.publish_json.call_args

    expected_time = fixed_now.replace(hour=18, minute=30, second=0, microsecond=0)
    assert kwargs["not_before"] == int(expected_time.timestamp())
    assert kwargs["url"] == "https://api.smartthings.com/v1/devices/device-123/commands"
    assert kwargs["headers"] == {"Upstash-Forward-Authorization": "Bearer smartthings-token"}


def test_schedule_with_qstash_handles_publish_exception(monkeypatch, qstash_env, capsys):
    uk_tz = pytz.timezone("Europe/London")
    fixed_now = uk_tz.localize(datetime(2026, 1, 1, 12, 0, 0))

    fake_datetime = MagicMock(wraps=datetime)
    fake_datetime.now.return_value = fixed_now
    monkeypatch.setattr(scraper, "datetime", fake_datetime)

    mock_client = MagicMock()
    mock_client.message.publish_json.side_effect = Exception("boom")
    monkeypatch.setattr(scraper, "QStash", MagicMock(return_value=mock_client))

    scraper.schedule_with_qstash({"isha": {"time": "18:30"}})

    captured = capsys.readouterr()
    assert "Failed to schedule ISHA" in captured.out
