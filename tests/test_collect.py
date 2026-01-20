"""Tests for the collect command."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telethon.tl.types import Channel, User

from telegram_cleaner import collect_inactive_chats, is_inactive


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

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_dialogs = AsyncMock(return_value=mock_dialogs)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await collect_inactive_chats(output_path, months=6)

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

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_dialogs = AsyncMock(return_value=mock_dialogs)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await collect_inactive_chats(output_path, months=6)

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

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_dialogs = AsyncMock(return_value=mock_dialogs)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            # With 12 months threshold, none should be inactive
            await collect_inactive_chats(output_path, months=12)

        result = json.loads(output_path.read_text())
        # 200 days is less than 12 months, so both "old" items should now be active
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self, mock_dialogs, tmp_path):
        """Should limit the number of collected chats."""
        output_path = tmp_path / "inactive.json"

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_dialogs = AsyncMock(return_value=mock_dialogs)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            # There are 2 inactive chats, but limit to 1
            await collect_inactive_chats(output_path, months=6, limit=1)

        result = json.loads(output_path.read_text())
        assert len(result) == 1
