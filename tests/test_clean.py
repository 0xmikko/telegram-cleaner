"""Tests for the clean (batch delete) functionality."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner
from telethon.errors import FloodWaitError
from telethon.tl.types import User

from telegram_cleaner import DELETED_CHATS_FILE, RATE_LIMIT_DELAY, clean_chats_messages, cli


def create_mock_user(user_id: int, first_name: str) -> MagicMock:
    """Create a mock User."""
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = first_name
    user.last_name = None
    user.username = None
    user.bot = False
    return user


def create_mock_message(msg_id: int, text: str) -> MagicMock:
    """Create a mock message."""
    msg = MagicMock()
    msg.id = msg_id
    msg.text = text
    msg.date = None
    return msg


class TestCleanChatsMessages:
    """Tests for the clean_chats_messages function."""

    @pytest.mark.asyncio
    async def test_deletes_messages_from_multiple_chats(self) -> None:
        """Should delete user's messages from all chats in the list."""
        chats = [
            {"id": 123, "name": "Chat 1"},
            {"id": 456, "name": "Chat 2"},
        ]

        mock_messages_chat1 = [create_mock_message(1, "msg1"), create_mock_message(2, "msg2")]
        mock_messages_chat2 = [create_mock_message(3, "msg3")]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            mock_client.get_entity = AsyncMock(side_effect=lambda x: create_mock_user(x, f"User{x}"))
            mock_client.delete_messages = AsyncMock()

            # Mock iter_messages to return different messages for different chats
            call_count = 0

            async def mock_iter_messages(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    for msg in mock_messages_chat1:
                        yield msg
                else:
                    for msg in mock_messages_chat2:
                        yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = await clean_chats_messages(chats, dry_run=False)

        assert result["total_deleted"] == 3
        assert result["chats_processed"] == 2
        assert mock_client.delete_messages.call_count == 3

    @pytest.mark.asyncio
    async def test_dry_run_does_not_delete(self) -> None:
        """Should not delete messages when dry_run is True."""
        chats = [{"id": 123, "name": "Chat 1"}]
        mock_messages = [create_mock_message(1, "msg1")]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            mock_client.get_entity = AsyncMock(return_value=create_mock_user(123, "User"))
            mock_client.delete_messages = AsyncMock()

            async def mock_iter_messages(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
                for msg in mock_messages:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = await clean_chats_messages(chats, dry_run=True)

        assert result["total_deleted"] == 0
        assert result["total_found"] == 1
        mock_client.delete_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_empty_chat_list(self) -> None:
        """Should handle empty chat list gracefully."""
        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = await clean_chats_messages([], dry_run=False)

        assert result["total_deleted"] == 0
        assert result["chats_processed"] == 0

    @pytest.mark.asyncio
    async def test_continues_on_chat_error(self) -> None:
        """Should continue processing other chats if one fails."""
        chats = [
            {"id": 123, "name": "Bad Chat"},
            {"id": 456, "name": "Good Chat"},
        ]

        mock_messages = [create_mock_message(1, "msg1")]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)

            # First chat fails, second succeeds
            mock_client.get_entity = AsyncMock(
                side_effect=[ValueError("Not found"), create_mock_user(456, "User")]
            )
            mock_client.delete_messages = AsyncMock()

            async def mock_iter_messages(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
                for msg in mock_messages:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = await clean_chats_messages(chats, dry_run=False)

        assert result["chats_processed"] == 1
        assert result["errors"] == 1
        assert result["total_deleted"] == 1

    @pytest.mark.asyncio
    async def test_removes_cleaned_chats_from_json(self, tmp_path: Path) -> None:
        """Should remove chats from JSON file after cleaning their messages."""
        chats = [
            {"id": 123, "name": "Chat 1"},
            {"id": 456, "name": "Chat 2"},
        ]
        json_path = tmp_path / "chats.json"
        json_path.write_text(json.dumps(chats))

        mock_messages = [create_mock_message(1, "msg1")]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            mock_client.get_entity = AsyncMock(side_effect=lambda x: create_mock_user(x, f"User{x}"))
            mock_client.delete_messages = AsyncMock()

            async def mock_iter_messages(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
                for msg in mock_messages:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await clean_chats_messages(chats, dry_run=False, file_path=json_path)

        # JSON should now be empty since both chats were cleaned
        remaining = json.loads(json_path.read_text())
        assert remaining == []

    @pytest.mark.asyncio
    async def test_keeps_failed_chats_in_json(self, tmp_path: Path) -> None:
        """Should keep chats in JSON if they failed to process."""
        chats = [
            {"id": 123, "name": "Bad Chat"},
            {"id": 456, "name": "Good Chat"},
        ]
        json_path = tmp_path / "chats.json"
        json_path.write_text(json.dumps(chats))

        mock_messages = [create_mock_message(1, "msg1")]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)

            # First chat fails, second succeeds
            mock_client.get_entity = AsyncMock(
                side_effect=[ValueError("Not found"), create_mock_user(456, "User")]
            )
            mock_client.delete_messages = AsyncMock()

            async def mock_iter_messages(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
                for msg in mock_messages:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await clean_chats_messages(chats, dry_run=False, file_path=json_path)

        # Only the failed chat should remain
        remaining = json.loads(json_path.read_text())
        assert len(remaining) == 1
        assert remaining[0]["id"] == 123

    @pytest.mark.asyncio
    async def test_dry_run_does_not_modify_json(self, tmp_path: Path) -> None:
        """Should not modify JSON file during dry run."""
        chats = [{"id": 123, "name": "Chat 1"}]
        json_path = tmp_path / "chats.json"
        json_path.write_text(json.dumps(chats))

        mock_messages = [create_mock_message(1, "msg1")]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            mock_client.get_entity = AsyncMock(return_value=create_mock_user(123, "User"))

            async def mock_iter_messages(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
                for msg in mock_messages:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            await clean_chats_messages(chats, dry_run=True, file_path=json_path)

        # JSON should be unchanged
        remaining = json.loads(json_path.read_text())
        assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_stops_on_flood_wait_error(self, tmp_path: Path) -> None:
        """Should stop immediately when FloodWaitError is encountered."""
        chats = [
            {"id": 123, "name": "Chat 1"},
            {"id": 456, "name": "Chat 2"},
        ]
        json_path = tmp_path / "chats.json"
        json_path.write_text(json.dumps(chats))

        mock_messages = [
            create_mock_message(1, "msg1"),
            create_mock_message(2, "msg2"),
            create_mock_message(3, "msg3"),
        ]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            mock_client.get_entity = AsyncMock(return_value=create_mock_user(123, "User"))

            # Simulate FloodWaitError on second delete (capture param becomes seconds)
            flood_error = FloodWaitError(request=None, capture=300)
            mock_client.delete_messages = AsyncMock(
                side_effect=[None, flood_error]
            )

            async def mock_iter_messages(*args, **kwargs):
                for msg in mock_messages:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            with patch("telegram_cleaner.asyncio.sleep", new_callable=AsyncMock):
                result = await clean_chats_messages(chats, dry_run=False, file_path=json_path)

        # Should have deleted 1 message before stopping
        assert result["total_deleted"] == 1
        # Should report the wait time
        assert result.get("flood_wait_seconds") == 300
        # Second chat should not be processed
        assert result["chats_processed"] == 0

        # Remaining chats should be saved
        remaining = json.loads(json_path.read_text())
        assert len(remaining) == 2

    @pytest.mark.asyncio
    async def test_rate_limiting_delay_between_deletes(self) -> None:
        """Should have delay between delete operations."""
        chats = [{"id": 123, "name": "Chat 1"}]
        mock_messages = [
            create_mock_message(1, "msg1"),
            create_mock_message(2, "msg2"),
        ]

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            mock_client.get_entity = AsyncMock(return_value=create_mock_user(123, "User"))
            mock_client.delete_messages = AsyncMock()

            async def mock_iter_messages(*args, **kwargs):
                for msg in mock_messages:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            with patch("telegram_cleaner.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await clean_chats_messages(chats, dry_run=False)

                # Should have called sleep after each delete
                assert mock_sleep.call_count == 2
                mock_sleep.assert_called_with(RATE_LIMIT_DELAY)


class TestCleanCommand:
    """Tests for the clean CLI command."""

    def test_clears_deleted_chats_json_when_all_processed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should clear deleted_chats.json when all chats are successfully processed."""
        # Change to tmp_path so file operations work there
        monkeypatch.chdir(tmp_path)

        # Create chats_to_delete.json with one chat
        chats = [{"id": 123, "name": "Chat 1"}]
        chats_file = tmp_path / "chats_to_delete.json"
        chats_file.write_text(json.dumps(chats))

        # Create deleted_chats.json with an old entry
        deleted_file = tmp_path / "deleted_chats.json"
        deleted_file.write_text(json.dumps([{"id": 999, "name": "Old Chat"}]))

        # Patch DELETED_CHATS_FILE to point to tmp_path
        monkeypatch.setattr("telegram_cleaner.DELETED_CHATS_FILE", deleted_file)

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            mock_client.get_entity = AsyncMock(return_value=create_mock_user(123, "User"))
            mock_client.delete_messages = AsyncMock()

            async def mock_iter_messages(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
                for msg in [create_mock_message(1, "msg1")]:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            with patch("telegram_cleaner.asyncio.sleep", new_callable=AsyncMock):
                runner = CliRunner()
                result = runner.invoke(cli, ["clean", str(chats_file)])

        assert result.exit_code == 0
        # chats_to_delete.json should be empty
        assert json.loads(chats_file.read_text()) == []
        # deleted_chats.json should be removed
        assert not deleted_file.exists()
        assert "Cleared deleted_chats.json" in result.output

    def test_keeps_deleted_chats_json_when_chats_remain(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should NOT clear deleted_chats.json when some chats failed to process."""
        monkeypatch.chdir(tmp_path)

        # Create chats with one that will fail
        chats = [
            {"id": 123, "name": "Bad Chat"},
            {"id": 456, "name": "Good Chat"},
        ]
        chats_file = tmp_path / "chats_to_delete.json"
        chats_file.write_text(json.dumps(chats))

        # Create deleted_chats.json
        deleted_file = tmp_path / "deleted_chats.json"
        deleted_file.write_text(json.dumps([]))

        monkeypatch.setattr("telegram_cleaner.DELETED_CHATS_FILE", deleted_file)

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            # First chat fails, second succeeds
            mock_client.get_entity = AsyncMock(
                side_effect=[ValueError("Not found"), create_mock_user(456, "User")]
            )
            mock_client.delete_messages = AsyncMock()

            async def mock_iter_messages(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
                for msg in [create_mock_message(1, "msg1")]:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            with patch("telegram_cleaner.asyncio.sleep", new_callable=AsyncMock):
                runner = CliRunner()
                result = runner.invoke(cli, ["clean", str(chats_file)])

        assert result.exit_code == 0
        # Failed chat should remain in file
        remaining = json.loads(chats_file.read_text())
        assert len(remaining) == 1
        assert remaining[0]["id"] == 123
        # deleted_chats.json should still exist (not cleared because chats remain)
        assert deleted_file.exists()
        assert "Cleared deleted_chats.json" not in result.output

    def test_dry_run_does_not_clear_deleted_chats(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should NOT clear deleted_chats.json during dry run."""
        monkeypatch.chdir(tmp_path)

        chats = [{"id": 123, "name": "Chat 1"}]
        chats_file = tmp_path / "chats_to_delete.json"
        chats_file.write_text(json.dumps(chats))

        deleted_file = tmp_path / "deleted_chats.json"
        deleted_file.write_text(json.dumps([{"id": 999, "name": "Old Chat"}]))

        monkeypatch.setattr("telegram_cleaner.DELETED_CHATS_FILE", deleted_file)

        with patch("telegram_cleaner.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_me = create_mock_user(999, "Me")
            mock_client.get_me = AsyncMock(return_value=mock_me)
            mock_client.get_entity = AsyncMock(return_value=create_mock_user(123, "User"))

            async def mock_iter_messages(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
                for msg in [create_mock_message(1, "msg1")]:
                    yield msg

            mock_client.iter_messages = mock_iter_messages
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            runner = CliRunner()
            result = runner.invoke(cli, ["clean", str(chats_file), "--dry-run"])

        assert result.exit_code == 0
        # deleted_chats.json should still exist with original content
        assert deleted_file.exists()
        deleted_content = json.loads(deleted_file.read_text())
        assert len(deleted_content) == 1
        assert deleted_content[0]["id"] == 999
