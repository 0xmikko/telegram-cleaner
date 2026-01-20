"""Tests for the collect command."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telethon.tl.types import Channel, User

from telegram_cleaner import (
    collect_inactive_chats,
    is_inactive,
    load_fresh_chats_cache,
    save_fresh_chats_cache,
)


class TestIsInactive:
    """Tests for the is_inactive helper function."""

    def test_returns_true_when_last_message_older_than_threshold(self):
        """Should return True when last message is older than months threshold."""
        old_date = datetime.now(UTC) - timedelta(days=200)
        assert is_inactive(old_date, months=6) is True

    def test_returns_false_when_last_message_recent(self):
        """Should return False when last message is within threshold."""
        recent_date = datetime.now(UTC) - timedelta(days=30)
        assert is_inactive(recent_date, months=6) is False

    def test_returns_true_when_date_is_none(self):
        """Should return True when date is None (no messages)."""
        assert is_inactive(None, months=6) is True

    def test_respects_custom_months_threshold(self):
        """Should use the custom months threshold."""
        four_months_ago = datetime.now(UTC) - timedelta(days=120)
        assert is_inactive(four_months_ago, months=3) is True
        assert is_inactive(four_months_ago, months=6) is False


def create_mock_user(user_id, first_name, last_name, username, phone, bot=False):
    """Create a mock User that passes isinstance checks."""
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = first_name
    user.last_name = last_name
    user.username = username
    user.phone = phone
    user.bot = bot
    return user


def create_mock_channel(channel_id, title, username, broadcast=True, participants_count=0):
    """Create a mock Channel that passes isinstance checks."""
    channel = MagicMock(spec=Channel)
    channel.id = channel_id
    channel.title = title
    channel.username = username
    channel.broadcast = broadcast
    channel.participants_count = participants_count
    return channel


class TestCollectInactiveChats:
    """Tests for the collect_inactive_chats function."""

    @pytest.fixture
    def mock_dialogs(self):
        """Create mock dialogs for testing."""
        now = datetime.now(UTC)
        old_date = now - timedelta(days=200)
        recent_date = now - timedelta(days=30)

        # Mock User dialog (inactive)
        old_user = create_mock_user(
            user_id=123,
            first_name="Old",
            last_name="User",
            username="olduser",
            phone="+1234567890",
        )

        old_dialog = MagicMock()
        old_dialog.id = 123
        old_dialog.entity = old_user
        old_dialog.date = old_date
        old_dialog.unread_count = 0

        # Mock User dialog (active)
        active_user = create_mock_user(
            user_id=456,
            first_name="Active",
            last_name="User",
            username="activeuser",
            phone=None,
        )

        active_dialog = MagicMock()
        active_dialog.id = 456
        active_dialog.entity = active_user
        active_dialog.date = recent_date
        active_dialog.unread_count = 5

        # Mock Channel dialog (inactive)
        old_channel = create_mock_channel(
            channel_id=789,
            title="Old Channel",
            username="oldchannel",
            broadcast=True,
            participants_count=100,
        )

        old_channel_dialog = MagicMock()
        old_channel_dialog.id = 789
        old_channel_dialog.entity = old_channel
        old_channel_dialog.date = old_date
        old_channel_dialog.unread_count = 10

        return [old_dialog, active_dialog, old_channel_dialog]

    @pytest.mark.asyncio
    async def test_collects_only_inactive_chats(self, mock_dialogs, tmp_path):
        """Should only collect chats older than threshold."""
        output_path = tmp_path / "inactive.json"
        cache_path = tmp_path / "fresh_cache.json"

        async def mock_iter_dialogs():
            for dialog in mock_dialogs:
                yield dialog

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await collect_inactive_chats(output_path, months=6, fresh_cache_path=cache_path, deleted_chats_path=tmp_path / "deleted.json")

        result = json.loads(output_path.read_text())
        assert len(result) == 2
        ids = [item["id"] for item in result]
        assert 123 in ids  # old user
        assert 789 in ids  # old channel
        assert 456 not in ids  # active user

    @pytest.mark.asyncio
    async def test_stores_all_required_fields(self, mock_dialogs, tmp_path):
        """Should store all required fields for each chat."""
        output_path = tmp_path / "inactive.json"
        cache_path = tmp_path / "fresh_cache.json"

        async def mock_iter_dialogs():
            for dialog in mock_dialogs:
                yield dialog

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await collect_inactive_chats(output_path, months=6, fresh_cache_path=cache_path, deleted_chats_path=tmp_path / "deleted.json")

        result = json.loads(output_path.read_text())
        user_entry = next(item for item in result if item["id"] == 123)

        assert "id" in user_entry
        assert "name" in user_entry
        assert "type" in user_entry
        assert "last_message_date" in user_entry
        assert "username" in user_entry

    @pytest.mark.asyncio
    async def test_respects_months_parameter(self, mock_dialogs, tmp_path):
        """Should use the months parameter for filtering."""
        output_path = tmp_path / "inactive.json"
        cache_path = tmp_path / "fresh_cache.json"

        async def mock_iter_dialogs():
            for dialog in mock_dialogs:
                yield dialog

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            # With 12 months threshold, none should be inactive
            await collect_inactive_chats(output_path, months=12, fresh_cache_path=cache_path, deleted_chats_path=tmp_path / "deleted.json")

        result = json.loads(output_path.read_text())
        # 200 days is less than 12 months, so both "old" items should now be active
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self, mock_dialogs, tmp_path):
        """Should limit the number of collected chats."""
        output_path = tmp_path / "inactive.json"
        cache_path = tmp_path / "fresh_cache.json"

        async def mock_iter_dialogs():
            for dialog in mock_dialogs:
                yield dialog

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            # There are 2 inactive chats, but limit to 1
            await collect_inactive_chats(output_path, months=6, limit=1, fresh_cache_path=cache_path, deleted_chats_path=tmp_path / "deleted.json")

        result = json.loads(output_path.read_text())
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_appends_to_existing_json(self, tmp_path: Path) -> None:
        """Should append new chats to existing JSON instead of overwriting."""
        output_path = tmp_path / "inactive.json"
        cache_path = tmp_path / "fresh_cache.json"

        # Pre-existing chat in JSON
        existing_data = [{"id": 999, "name": "Existing Chat", "type": "user"}]
        output_path.write_text(json.dumps(existing_data))

        now = datetime.now(UTC)
        old_date = now - timedelta(days=200)

        # New inactive user
        new_user = create_mock_user(
            user_id=123,
            first_name="New",
            last_name="User",
            username="newuser",
            phone=None,
        )
        new_dialog = MagicMock()
        new_dialog.id = 123
        new_dialog.entity = new_user
        new_dialog.date = old_date
        new_dialog.unread_count = 0

        async def mock_iter_dialogs():
            yield new_dialog

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await collect_inactive_chats(output_path, months=6, fresh_cache_path=cache_path, deleted_chats_path=tmp_path / "deleted.json")

        result = json.loads(output_path.read_text())
        assert len(result) == 2
        ids = [item["id"] for item in result]
        assert 999 in ids  # existing
        assert 123 in ids  # new

    @pytest.mark.asyncio
    async def test_does_not_add_duplicate_ids(self, tmp_path: Path) -> None:
        """Should not add chats that already exist in JSON (by ID)."""
        output_path = tmp_path / "inactive.json"
        cache_path = tmp_path / "fresh_cache.json"

        # Pre-existing chat in JSON
        existing_data = [{"id": 123, "name": "Already There", "type": "user"}]
        output_path.write_text(json.dumps(existing_data))

        now = datetime.now(UTC)
        old_date = now - timedelta(days=200)

        # Same ID as existing
        same_user = create_mock_user(
            user_id=123,
            first_name="Same",
            last_name="User",
            username="sameuser",
            phone=None,
        )
        same_dialog = MagicMock()
        same_dialog.id = 123
        same_dialog.entity = same_user
        same_dialog.date = old_date
        same_dialog.unread_count = 0

        async def mock_iter_dialogs():
            yield same_dialog

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await collect_inactive_chats(output_path, months=6, fresh_cache_path=cache_path, deleted_chats_path=tmp_path / "deleted.json")

        result = json.loads(output_path.read_text())
        assert len(result) == 1
        # Should keep the original entry, not update it
        assert result[0]["name"] == "Already There"

    @pytest.mark.asyncio
    async def test_removes_kept_chats_from_existing(self, tmp_path: Path) -> None:
        """Should remove chats from existing JSON if they are now in keep list."""
        output_path = tmp_path / "inactive.json"
        cache_path = tmp_path / "fresh_cache.json"
        keep_path = tmp_path / "keep.json"

        # Chat 123 is in inactive list
        existing_data = [
            {"id": 123, "name": "Now Kept", "type": "user"},
            {"id": 456, "name": "Still Inactive", "type": "user"},
        ]
        output_path.write_text(json.dumps(existing_data))

        # But chat 123 was later added to keep list
        keep_data = [{"id": 123, "name": "Now Kept"}]
        keep_path.write_text(json.dumps(keep_data))

        async def mock_iter_dialogs():
            if False:
                yield  # Make it an async generator that yields nothing

        with (
            patch("telegram_cleaner.get_client") as mock_get_client,
            patch("telegram_cleaner.load_keep_list", return_value={123}),
        ):
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await collect_inactive_chats(output_path, months=6, fresh_cache_path=cache_path, deleted_chats_path=tmp_path / "deleted.json")

        # Chat 123 should be removed from inactive list
        result = json.loads(output_path.read_text())
        assert len(result) == 1
        assert result[0]["id"] == 456

    @pytest.mark.asyncio
    async def test_saves_fresh_chats_to_cache(self, tmp_path: Path) -> None:
        """Should save active (fresh) chats to cache with last message date."""
        output_path = tmp_path / "inactive.json"
        cache_path = tmp_path / "fresh_cache.json"

        now = datetime.now(UTC)
        recent_date = now - timedelta(days=30)

        # Active user (should be cached)
        active_user = create_mock_user(
            user_id=456,
            first_name="Active",
            last_name="User",
            username="activeuser",
            phone=None,
        )
        active_dialog = MagicMock()
        active_dialog.id = 456
        active_dialog.entity = active_user
        active_dialog.date = recent_date
        active_dialog.unread_count = 5

        async def mock_iter_dialogs():
            yield active_dialog

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await collect_inactive_chats(output_path, months=6, fresh_cache_path=cache_path, deleted_chats_path=tmp_path / "deleted.json")

        # Fresh cache should have the active chat with last_message_date
        cache = load_fresh_chats_cache(cache_path)
        assert 456 in cache
        assert "last_message_date" in cache[456]

    @pytest.mark.asyncio
    async def test_skips_fresh_chats_based_on_last_message(self, tmp_path: Path) -> None:
        """Should skip chats where cached last_message_date is within threshold."""
        output_path = tmp_path / "inactive.json"
        cache_path = tmp_path / "fresh_cache.json"

        now = datetime.now(UTC)
        old_date = now - timedelta(days=200)
        recent_date = now - timedelta(days=30)  # Within 6 months

        # Pre-populate cache with a chat that has recent last_message_date
        cache_data = {
            "789": {"last_message_date": recent_date.isoformat(), "name": "Cached Fresh Chat"},
        }
        cache_path.write_text(json.dumps(cache_data))

        # Old inactive user
        old_user = create_mock_user(
            user_id=123,
            first_name="Old",
            last_name="User",
            username="olduser",
            phone=None,
        )
        old_dialog = MagicMock()
        old_dialog.id = 123
        old_dialog.entity = old_user
        old_dialog.date = old_date
        old_dialog.unread_count = 0

        # Chat 789 from cache - should be skipped because cached last_message is recent
        cached_user = create_mock_user(
            user_id=789,
            first_name="Cached",
            last_name="User",
            username="cacheduser",
            phone=None,
        )
        cached_dialog = MagicMock()
        cached_dialog.id = 789
        cached_dialog.entity = cached_user
        cached_dialog.date = old_date  # API says old, but cache says recent - trust cache
        cached_dialog.unread_count = 0

        async def mock_iter_dialogs():
            yield old_dialog
            yield cached_dialog

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await collect_inactive_chats(output_path, months=6, fresh_cache_path=cache_path, deleted_chats_path=tmp_path / "deleted.json")

        # Only the old user should be in inactive list, not the cached one
        result = json.loads(output_path.read_text())
        assert len(result) == 1
        assert result[0]["id"] == 123


class TestFreshChatsCache:
    """Tests for the fresh chats cache functions."""

    def test_load_returns_empty_dict_for_missing_file(self, tmp_path: Path) -> None:
        """Should return empty dict if cache file doesn't exist."""
        cache_path = tmp_path / "nonexistent.json"
        result = load_fresh_chats_cache(cache_path)
        assert result == {}

    def test_load_returns_empty_dict_for_invalid_json(self, tmp_path: Path) -> None:
        """Should return empty dict for invalid JSON."""
        cache_path = tmp_path / "invalid.json"
        cache_path.write_text("invalid json {")
        result = load_fresh_chats_cache(cache_path)
        assert result == {}

    def test_save_and_load_cache(self, tmp_path: Path) -> None:
        """Should save and load cache correctly."""
        cache_path = tmp_path / "cache.json"
        now = datetime.now(UTC)
        cache = {
            123: {"next_check": now.isoformat(), "name": "Test Chat"},
        }

        save_fresh_chats_cache(cache_path, cache)
        loaded = load_fresh_chats_cache(cache_path)

        assert 123 in loaded
        assert loaded[123]["name"] == "Test Chat"
