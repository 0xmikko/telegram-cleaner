"""Tests for the legacy-chats command."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telethon.tl.types import User

from telegram_cleaner import collect_legacy_chats


def create_mock_user(user_id: int, first_name: str, last_name: str | None = None, username: str | None = None) -> MagicMock:
    """Create a mock User that passes isinstance checks."""
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = first_name
    user.last_name = last_name
    user.username = username
    user.phone = None
    user.bot = False
    return user


class TestCollectLegacyChats:
    """Tests for the collect_legacy_chats function."""

    @pytest.mark.asyncio
    async def test_finds_chats_not_in_dialogs(self, tmp_path: Path) -> None:
        """Should find chats from search that are not in dialogs."""
        output_path = tmp_path / "legacy.json"

        # Dialog user (already visible)
        dialog_user = create_mock_user(user_id=123, first_name="Dialog", last_name="User")
        dialog = MagicMock()
        dialog.id = 123
        dialog.entity = dialog_user
        dialog.date = datetime.now(UTC)

        # Search result user (legacy, not in dialogs)
        legacy_user = create_mock_user(user_id=456, first_name="Legacy", last_name="User")

        async def mock_iter_dialogs():
            yield dialog

        # Mock search result
        search_result = MagicMock()
        search_result.users = [legacy_user]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = search_result
            mock_get_client.return_value = mock_client

            await collect_legacy_chats(output_path, search_letters="a")

        result = json.loads(output_path.read_text())
        assert len(result) == 1
        assert result[0]["id"] == 456
        assert result[0]["name"] == "Legacy User"

    @pytest.mark.asyncio
    async def test_skips_chats_already_in_dialogs(self, tmp_path: Path) -> None:
        """Should not add chats that are already in dialogs."""
        output_path = tmp_path / "legacy.json"

        # User in both dialogs and search
        user = create_mock_user(user_id=123, first_name="Common", last_name="User")
        dialog = MagicMock()
        dialog.id = 123
        dialog.entity = user
        dialog.date = datetime.now(UTC)

        async def mock_iter_dialogs():
            yield dialog

        search_result = MagicMock()
        search_result.users = [user]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = search_result
            mock_get_client.return_value = mock_client

            await collect_legacy_chats(output_path, search_letters="a")

        result = json.loads(output_path.read_text())
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_searches_all_letters_and_numbers(self, tmp_path: Path) -> None:
        """Should search with all specified letters."""
        output_path = tmp_path / "legacy.json"

        async def mock_iter_dialogs():
            if False:
                yield

        search_result = MagicMock()
        search_result.users = []

        search_calls: list[str] = []

        async def mock_call(request: MagicMock) -> MagicMock:
            search_calls.append(request.q)
            return search_result

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.side_effect = mock_call
            mock_get_client.return_value = mock_client

            await collect_legacy_chats(output_path, search_letters="abc")

        assert "a" in search_calls
        assert "b" in search_calls
        assert "c" in search_calls

    @pytest.mark.asyncio
    async def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        """Should append to existing file, not overwrite."""
        output_path = tmp_path / "legacy.json"
        existing_data = [{"id": 999, "name": "Existing", "type": "user"}]
        output_path.write_text(json.dumps(existing_data))

        legacy_user = create_mock_user(user_id=456, first_name="New", last_name="Legacy")

        async def mock_iter_dialogs():
            if False:
                yield

        search_result = MagicMock()
        search_result.users = [legacy_user]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = search_result
            mock_get_client.return_value = mock_client

            await collect_legacy_chats(output_path, search_letters="a")

        result = json.loads(output_path.read_text())
        assert len(result) == 2
        ids = [r["id"] for r in result]
        assert 999 in ids
        assert 456 in ids

    @pytest.mark.asyncio
    async def test_does_not_add_duplicates(self, tmp_path: Path) -> None:
        """Should not add duplicate chats from multiple searches."""
        output_path = tmp_path / "legacy.json"

        # Same user found in multiple searches
        user = create_mock_user(user_id=123, first_name="Alice", last_name="Smith")

        async def mock_iter_dialogs():
            if False:
                yield

        search_result = MagicMock()
        search_result.users = [user]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = search_result
            mock_get_client.return_value = mock_client

            # Search with multiple letters that might find the same user
            await collect_legacy_chats(output_path, search_letters="as")

        result = json.loads(output_path.read_text())
        # Should only have one entry even if found by both 'a' and 's'
        assert len(result) == 1
        assert result[0]["id"] == 123

    @pytest.mark.asyncio
    async def test_skips_keep_list_chats(self, tmp_path: Path) -> None:
        """Should skip chats that are in the keep list."""
        output_path = tmp_path / "legacy.json"

        legacy_user = create_mock_user(user_id=456, first_name="Kept", last_name="User")

        async def mock_iter_dialogs():
            if False:
                yield

        search_result = MagicMock()
        search_result.users = [legacy_user]

        with (
            patch("telegram_cleaner.get_client") as mock_get_client,
            patch("telegram_cleaner.load_keep_list", return_value={456}),
        ):
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = search_result
            mock_get_client.return_value = mock_client

            await collect_legacy_chats(output_path, search_letters="a")

        result = json.loads(output_path.read_text())
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_stores_required_fields(self, tmp_path: Path) -> None:
        """Should store all required fields for each legacy chat."""
        output_path = tmp_path / "legacy.json"

        legacy_user = create_mock_user(
            user_id=456,
            first_name="Legacy",
            last_name="User",
            username="legacyuser",
        )

        async def mock_iter_dialogs():
            if False:
                yield

        search_result = MagicMock()
        search_result.users = [legacy_user]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.iter_dialogs = mock_iter_dialogs
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = search_result
            mock_get_client.return_value = mock_client

            await collect_legacy_chats(output_path, search_letters="a")

        result = json.loads(output_path.read_text())
        assert len(result) == 1
        chat = result[0]
        assert "id" in chat
        assert "name" in chat
        assert "type" in chat
        assert "username" in chat
        assert "source" in chat
        assert chat["source"] == "search"
