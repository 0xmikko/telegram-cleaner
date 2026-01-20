"""Tests for the TUI functionality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from telegram_cleaner import load_chats_from_json, save_chats_to_json


class TestLoadChatsFromJson:
    """Tests for the load_chats_from_json function."""

    def test_loads_valid_json_file(self, tmp_path: Path):
        """Should load chats from a valid JSON file."""
        data = [
            {"id": 123, "name": "John Doe", "type": "user", "last_message_date": "2025-06-15T10:30:00"},
            {"id": 456, "name": "Test Channel", "type": "channel", "last_message_date": "2025-05-01T08:00:00"},
        ]
        json_path = tmp_path / "chats.json"
        json_path.write_text(json.dumps(data))

        result = load_chats_from_json(json_path)

        assert len(result) == 2
        assert result[0]["name"] == "John Doe"
        assert result[1]["name"] == "Test Channel"

    def test_raises_error_for_missing_file(self, tmp_path: Path):
        """Should raise FileNotFoundError for missing file."""
        json_path = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            load_chats_from_json(json_path)

    def test_raises_error_for_invalid_json(self, tmp_path: Path):
        """Should raise error for invalid JSON."""
        json_path = tmp_path / "invalid.json"
        json_path.write_text("not valid json {")

        with pytest.raises(json.JSONDecodeError):
            load_chats_from_json(json_path)

    def test_returns_empty_list_for_empty_array(self, tmp_path: Path):
        """Should return empty list for empty JSON array."""
        json_path = tmp_path / "empty.json"
        json_path.write_text("[]")

        result = load_chats_from_json(json_path)

        assert result == []


class TestSaveChatsToJson:
    """Tests for the save_chats_to_json function."""

    def test_saves_chats_to_file(self, tmp_path: Path):
        """Should save chats to a JSON file."""
        data = [
            {"id": 123, "name": "John Doe", "type": "user"},
            {"id": 456, "name": "Test Channel", "type": "channel"},
        ]
        json_path = tmp_path / "chats.json"

        save_chats_to_json(json_path, data)

        result = json.loads(json_path.read_text())
        assert len(result) == 2
        assert result[0]["name"] == "John Doe"

    def test_overwrites_existing_file(self, tmp_path: Path):
        """Should overwrite existing file content."""
        json_path = tmp_path / "chats.json"
        json_path.write_text('[{"id": 999, "name": "Old"}]')

        new_data = [{"id": 123, "name": "New"}]
        save_chats_to_json(json_path, new_data)

        result = json.loads(json_path.read_text())
        assert len(result) == 1
        assert result[0]["name"] == "New"

    def test_saves_empty_list(self, tmp_path: Path):
        """Should save empty list correctly."""
        json_path = tmp_path / "chats.json"

        save_chats_to_json(json_path, [])

        result = json.loads(json_path.read_text())
        assert result == []
