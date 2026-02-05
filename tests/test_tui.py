"""Tests for the TUI functionality."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from telegram_cleaner import (
    add_to_keep_list,
    load_chats_from_json,
    load_keep_list,
    remove_from_keep_list,
    save_chats_to_json,
)


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


class TestLoadKeepList:
    """Tests for the load_keep_list function."""

    def test_returns_empty_set_for_missing_file(self, tmp_path: Path):
        """Should return empty set if keep file doesn't exist."""
        keep_path = tmp_path / "keep.json"

        result = load_keep_list(keep_path)

        assert result == set()

    def test_loads_ids_from_existing_file(self, tmp_path: Path):
        """Should load chat IDs from existing keep file."""
        keep_path = tmp_path / "keep.json"
        data = [
            {"id": 123, "name": "Chat 1"},
            {"id": 456, "name": "Chat 2"},
        ]
        keep_path.write_text(json.dumps(data))

        result = load_keep_list(keep_path)

        assert result == {123, 456}

    def test_handles_invalid_json(self, tmp_path: Path):
        """Should return empty set for invalid JSON."""
        keep_path = tmp_path / "keep.json"
        keep_path.write_text("invalid json {")

        result = load_keep_list(keep_path)

        assert result == set()

    def test_skips_entries_without_id(self, tmp_path: Path):
        """Should skip entries that don't have an id field."""
        keep_path = tmp_path / "keep.json"
        data = [
            {"id": 123, "name": "Chat 1"},
            {"name": "Chat without ID"},
            {"id": 456, "name": "Chat 2"},
        ]
        keep_path.write_text(json.dumps(data))

        result = load_keep_list(keep_path)

        assert result == {123, 456}


class TestAddToKeepList:
    """Tests for the add_to_keep_list function."""

    def test_creates_file_if_not_exists(self, tmp_path: Path):
        """Should create keep file if it doesn't exist."""
        keep_path = tmp_path / "keep.json"
        chat = {"id": 123, "name": "Test Chat"}

        add_to_keep_list(chat, keep_path)

        assert keep_path.exists()
        result = json.loads(keep_path.read_text())
        assert len(result) == 1
        assert result[0]["id"] == 123

    def test_appends_to_existing_file(self, tmp_path: Path):
        """Should append chat to existing keep file."""
        keep_path = tmp_path / "keep.json"
        existing = [{"id": 100, "name": "Existing"}]
        keep_path.write_text(json.dumps(existing))

        chat = {"id": 123, "name": "New Chat"}
        add_to_keep_list(chat, keep_path)

        result = json.loads(keep_path.read_text())
        assert len(result) == 2
        assert result[0]["id"] == 100
        assert result[1]["id"] == 123

    def test_does_not_add_duplicate(self, tmp_path: Path):
        """Should not add chat if ID already exists in keep list."""
        keep_path = tmp_path / "keep.json"
        existing = [{"id": 123, "name": "Existing"}]
        keep_path.write_text(json.dumps(existing))

        chat = {"id": 123, "name": "Duplicate"}
        add_to_keep_list(chat, keep_path)

        result = json.loads(keep_path.read_text())
        assert len(result) == 1
        assert result[0]["name"] == "Existing"

    def test_handles_corrupted_file(self, tmp_path: Path):
        """Should handle corrupted keep file gracefully."""
        keep_path = tmp_path / "keep.json"
        keep_path.write_text("corrupted {")

        chat = {"id": 123, "name": "New Chat"}
        add_to_keep_list(chat, keep_path)

        result = json.loads(keep_path.read_text())
        assert len(result) == 1
        assert result[0]["id"] == 123


class TestRemoveFromKeepList:
    """Tests for the remove_from_keep_list function."""

    def test_removes_chat_by_id(self, tmp_path: Path):
        """Should remove chat with matching ID from keep list."""
        keep_path = tmp_path / "keep.json"
        data = [
            {"id": 123, "name": "Chat 1"},
            {"id": 456, "name": "Chat 2"},
            {"id": 789, "name": "Chat 3"},
        ]
        keep_path.write_text(json.dumps(data))

        remove_from_keep_list(456, keep_path)

        result = json.loads(keep_path.read_text())
        assert len(result) == 2
        assert result[0]["id"] == 123
        assert result[1]["id"] == 789

    def test_does_nothing_if_id_not_found(self, tmp_path: Path):
        """Should not modify file if ID is not in keep list."""
        keep_path = tmp_path / "keep.json"
        data = [{"id": 123, "name": "Chat 1"}]
        keep_path.write_text(json.dumps(data))

        remove_from_keep_list(999, keep_path)

        result = json.loads(keep_path.read_text())
        assert len(result) == 1
        assert result[0]["id"] == 123

    def test_handles_missing_file(self, tmp_path: Path):
        """Should not raise error if file doesn't exist."""
        keep_path = tmp_path / "keep.json"

        remove_from_keep_list(123, keep_path)

        assert not keep_path.exists()

    def test_handles_empty_file(self, tmp_path: Path):
        """Should handle empty keep list."""
        keep_path = tmp_path / "keep.json"
        keep_path.write_text("[]")

        remove_from_keep_list(123, keep_path)

        result = json.loads(keep_path.read_text())
        assert result == []

    def test_removes_last_chat(self, tmp_path: Path):
        """Should handle removing the only chat in list."""
        keep_path = tmp_path / "keep.json"
        data = [{"id": 123, "name": "Only Chat"}]
        keep_path.write_text(json.dumps(data))

        remove_from_keep_list(123, keep_path)

        result = json.loads(keep_path.read_text())
        assert result == []
