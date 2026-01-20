#!/usr/bin/env python3
"""Telegram Cleaner - A script for managing Telegram DMs, chats, and admin operations."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import click
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import (
    Channel,
    Chat,
    Dialog,
    User,
)
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header

if TYPE_CHECKING:
    from textual.binding import BindingType

from datetime import UTC, datetime, timedelta

load_dotenv()

API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")
SESSION_NAME = os.getenv("TG_SESSION_NAME", "telegram_cleaner")

DEFAULT_MESSAGE_LIMIT = 100
RATE_LIMIT_DELAY = 0.5  # seconds between API calls
KEEP_FILE = Path("keep.json")  # Chats to skip during collect


class FloodWaitStop(Exception):
    """Raised when a FloodWaitError is encountered to trigger emergency stop."""

    def __init__(self, wait_seconds: int) -> None:
        self.wait_seconds = wait_seconds
        super().__init__(f"Telegram rate limit hit. Required wait: {wait_seconds} seconds")


def get_client() -> TelegramClient:
    """Create and return a Telegram client."""
    if not API_ID or not API_HASH:
        click.echo("Error: TG_API_ID and TG_API_HASH must be set in .env file")
        sys.exit(1)
    return TelegramClient(SESSION_NAME, int(API_ID), API_HASH)


def format_date(date: datetime | None) -> str:
    """Format a datetime object to ISO format string."""
    if date is None:
        return ""
    return date.isoformat()


def get_entity_name(entity: User | Chat | Channel) -> str:
    """Extract the display name from a Telegram entity."""
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name or entity.username or str(entity.id)
    # entity is Chat or Channel
    return entity.title or str(entity.id)


def get_entity_type(entity: User | Chat | Channel) -> str:
    """Determine the type of Telegram entity."""
    if isinstance(entity, User):
        return "user" if not entity.bot else "bot"
    if isinstance(entity, Chat):
        return "group"
    # entity is Channel
    return "channel" if entity.broadcast else "supergroup"


def is_inactive(last_message_date: datetime | None, months: int) -> bool:
    """Check if a chat is inactive based on last message date.

    Args:
        last_message_date: The date of the last message, or None if no messages.
        months: Number of months to consider as inactive threshold.

    Returns:
        True if the chat is inactive (last message older than threshold or no messages).
    """
    if last_message_date is None:
        return True
    threshold = datetime.now(UTC) - timedelta(days=months * 30)
    # Ensure last_message_date is timezone-aware
    if last_message_date.tzinfo is None:
        last_message_date = last_message_date.replace(tzinfo=UTC)
    return last_message_date < threshold


def load_chats_from_json(file_path: Path) -> list[dict[str, Any]]:
    """Load chats from a JSON file.

    Args:
        file_path: Path to the JSON file.

    Returns:
        List of chat dictionaries.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    with file_path.open() as f:
        return json.load(f)  # type: ignore[no-any-return]


def save_chats_to_json(file_path: Path, chats: list[dict[str, Any]]) -> None:
    """Save chats to a JSON file.

    Args:
        file_path: Path to the JSON file.
        chats: List of chat dictionaries to save.
    """
    file_path.write_text(json.dumps(chats, indent=2, ensure_ascii=False))


def load_keep_list(keep_file: Path = KEEP_FILE) -> set[int]:
    """Load the set of chat IDs to keep (skip during collect).

    Args:
        keep_file: Path to the keep list JSON file.

    Returns:
        Set of chat IDs that should be skipped.
    """
    if not keep_file.exists():
        return set()
    try:
        with keep_file.open() as f:
            chats = json.load(f)
            return {chat.get("id") for chat in chats if chat.get("id") is not None}
    except (json.JSONDecodeError, OSError):
        return set()


def add_to_keep_list(chat: dict[str, Any], keep_file: Path = KEEP_FILE) -> None:
    """Add a chat to the keep list.

    Args:
        chat: Chat dictionary to add to the keep list.
        keep_file: Path to the keep list JSON file.
    """
    # Load existing keep list
    existing: list[dict[str, Any]] = []
    if keep_file.exists():
        try:
            with keep_file.open() as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = []

    # Check if already in list
    existing_ids = {c.get("id") for c in existing}
    if chat.get("id") not in existing_ids:
        existing.append(chat)
        keep_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


class ChatsViewerApp(App[None]):
    """TUI app to view and navigate chats."""

    TITLE = "Telegram Cleaner"

    BINDINGS: ClassVar[list[BindingType]] = [
        ("q", "quit", "Quit"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("d", "remove_chat", "Delete"),
        ("s", "keep_chat", "Keep"),
    ]

    def __init__(self, chats: list[dict[str, Any]], file_path: Path) -> None:
        super().__init__()
        self.chats = chats
        self.file_path = file_path
        self.row_keys: list[Any] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True

        table.add_columns("Name", "Type", "Last Message")
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Refresh the table with current chats data."""
        table = self.query_one(DataTable)
        table.clear()
        self.row_keys = []

        for chat in self.chats:
            name = chat.get("name", "Unknown")
            chat_type = chat.get("type", "unknown")
            last_date = chat.get("last_message_date", "")
            if last_date:
                last_date = last_date[:10]  # Just the date part
            row_key = table.add_row(name, chat_type, last_date)
            self.row_keys.append(row_key)

    def action_cursor_down(self) -> None:
        table = self.query_one(DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self.query_one(DataTable)
        table.action_cursor_up()

    def action_remove_chat(self) -> None:
        """Remove the currently selected chat from the list and save."""
        table = self.query_one(DataTable)
        if table.row_count == 0:
            self.notify("No chats to remove", severity="warning")
            return

        # Get current cursor row index
        row_index = table.cursor_row
        if row_index is None or row_index < 0 or row_index >= len(self.chats):
            self.notify("No chat selected", severity="warning")
            return

        # Get chat name for notification
        chat_name = self.chats[row_index].get("name", "Unknown")

        # Remove from our data
        del self.chats[row_index]

        # Save to file
        save_chats_to_json(self.file_path, self.chats)

        # Refresh the table
        self._refresh_table()

        # Notify user
        self.notify(f"Removed: {chat_name}")

    def action_keep_chat(self) -> None:
        """Mark the selected chat to keep (skip in future collects) and remove from list."""
        table = self.query_one(DataTable)
        if table.row_count == 0:
            self.notify("No chats to keep", severity="warning")
            return

        # Get current cursor row index
        row_index = table.cursor_row
        if row_index is None or row_index < 0 or row_index >= len(self.chats):
            self.notify("No chat selected", severity="warning")
            return

        # Get the chat data
        chat = self.chats[row_index]
        chat_name = chat.get("name", "Unknown")

        # Add to keep list
        add_to_keep_list(chat)

        # Remove from our data
        del self.chats[row_index]

        # Save to file
        save_chats_to_json(self.file_path, self.chats)

        # Refresh the table
        self._refresh_table()

        # Notify user
        self.notify(f"Keeping: {chat_name}")


async def collect_inactive_chats(
    output_path: Path,
    months: int,
    limit: int | None = None,
) -> None:
    """Collect chats where last activity was older than specified months.

    Args:
        output_path: Path to write the JSON output.
        months: Number of months of inactivity threshold.
        limit: Maximum number of inactive chats to collect (None for unlimited).
    """
    # Load keep list to skip
    keep_ids = load_keep_list()
    if keep_ids:
        click.echo(f"Skipping {len(keep_ids)} chats from keep list")

    client = get_client()
    async with client:
        click.echo(f"Fetching dialogs (looking for chats inactive for {months}+ months)...")
        dialogs: list[Dialog] = await client.get_dialogs()  # type: ignore[assignment]

        result: list[dict[str, Any]] = []
        skipped_count = 0
        for dialog in dialogs:
            # Skip chats in keep list
            if dialog.id in keep_ids:
                skipped_count += 1
                continue

            if not is_inactive(dialog.date, months):
                continue

            entity = dialog.entity
            dialog_info: dict[str, Any] = {
                "id": dialog.id,
                "name": get_entity_name(entity),
                "type": get_entity_type(entity),
                "last_message_date": format_date(dialog.date),
                "unread_count": dialog.unread_count,
            }

            if isinstance(entity, User):
                dialog_info["username"] = entity.username
                dialog_info["phone"] = entity.phone
            elif isinstance(entity, (Chat, Channel)):
                dialog_info["username"] = getattr(entity, "username", None)
                dialog_info["participants_count"] = getattr(entity, "participants_count", None)

            result.append(dialog_info)

            if limit is not None and len(result) >= limit:
                break

        output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        click.echo(f"Found {len(result)} inactive chats (out of {len(dialogs)} total)")
        if skipped_count > 0:
            click.echo(f"Skipped {skipped_count} chats from keep list")
        click.echo(f"Saved to {output_path}")


async def clear_messages(
    chat_identifier: str,
    limit: int,
    dry_run: bool,
) -> None:
    """Clear user's own messages from a chat."""
    client = get_client()
    async with client:
        me = await client.get_me()
        if me is None:
            click.echo("Error: Could not get current user")
            return

        click.echo(f"Resolving chat: {chat_identifier}")
        try:
            entity = await client.get_entity(chat_identifier)
        except ValueError:
            try:
                entity = await client.get_entity(int(chat_identifier))
            except (ValueError, TypeError):
                click.echo(f"Error: Could not find chat '{chat_identifier}'")
                return

        if not isinstance(entity, (User, Chat, Channel)):
            click.echo(f"Error: Unexpected entity type for '{chat_identifier}'")
            return

        click.echo(f"Chat: {get_entity_name(entity)} ({get_entity_type(entity)})")
        click.echo(f"Limit: {limit} messages")
        if dry_run:
            click.echo("DRY RUN - No messages will be deleted")

        deleted_count = 0
        messages_to_delete: list[int] = []

        click.echo("Scanning messages...")
        async for message in client.iter_messages(entity, from_user=me, limit=limit):  # type: ignore[arg-type]
            messages_to_delete.append(message.id)
            text_preview = (message.text or "[media]")[:50]
            date_str = format_date(message.date)
            click.echo(f"  [{date_str}] ID:{message.id} - {text_preview}")

        if not messages_to_delete:
            click.echo("No messages found to delete")
            return

        click.echo(f"\nFound {len(messages_to_delete)} messages")

        if dry_run:
            click.echo("Dry run complete. Use without --dry-run to delete.")
            return

        click.echo("Deleting messages...")
        try:
            for msg_id in messages_to_delete:
                try:
                    await client.delete_messages(entity, msg_id)  # type: ignore[arg-type]
                    deleted_count += 1
                    click.echo(f"  Deleted message ID: {msg_id}")
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                except FloodWaitError as e:
                    click.echo(f"\n  EMERGENCY STOP: Rate limit hit!")
                    click.echo(f"  Telegram requires waiting {e.seconds} seconds")
                    click.echo(f"  Deleted {deleted_count}/{len(messages_to_delete)} before stop")
                    raise FloodWaitStop(e.seconds) from e
                except Exception as e:
                    click.echo(f"  Failed to delete message {msg_id}: {e}")
        except FloodWaitStop:
            click.echo("\nOperation stopped due to rate limiting.")
            click.echo("Please wait and try again later.")
            return

        click.echo(f"\nDeleted {deleted_count}/{len(messages_to_delete)} messages")


async def clean_chats_messages(
    chats: list[dict[str, Any]],
    dry_run: bool,
    file_path: Path | None = None,
) -> dict[str, int]:
    """Delete user's messages from multiple chats.

    Args:
        chats: List of chat dictionaries (with 'id' and 'name' keys).
        dry_run: If True, only show what would be deleted without deleting.
        file_path: Optional path to JSON file. If provided, removes cleaned chats from file.

    Returns:
        Dictionary with stats: total_deleted, total_found, chats_processed, errors.
    """
    result = {
        "total_deleted": 0,
        "total_found": 0,
        "chats_processed": 0,
        "errors": 0,
    }

    if not chats:
        return result

    # Track remaining chats (ones that failed or weren't processed)
    remaining_chats = list(chats)
    total_chats = len(chats)

    client = get_client()
    async with client:
        me = await client.get_me()
        if me is None:
            click.echo("Error: Could not get current user")
            return result

        for chat_info in chats:
            chat_id = chat_info.get("id")
            chat_name = chat_info.get("name", str(chat_id))

            progress = result["chats_processed"] + result["errors"] + 1
            click.echo(f"\n[{progress}/{total_chats}] {chat_name}")

            # Resolve the chat entity
            try:
                entity = await client.get_entity(chat_id)
            except (ValueError, TypeError):
                click.echo("  Error: Could not find chat")
                result["errors"] += 1
                continue

            # Find messages to delete
            messages_to_delete: list[int] = []
            async for message in client.iter_messages(entity, from_user=me):  # type: ignore[arg-type]
                messages_to_delete.append(message.id)

            result["total_found"] += len(messages_to_delete)

            if not messages_to_delete:
                click.echo("  No messages found")
                result["chats_processed"] += 1
                # Remove from remaining list and save
                if not dry_run and file_path:
                    remaining_chats = [c for c in remaining_chats if c.get("id") != chat_id]
                    save_chats_to_json(file_path, remaining_chats)
                continue

            click.echo(f"  Found {len(messages_to_delete)} messages")

            if dry_run:
                click.echo(f"  [DRY RUN] Would delete {len(messages_to_delete)} messages")
                result["chats_processed"] += 1
                continue

            # Delete messages
            deleted_count = 0
            flood_stopped = False
            for msg_id in messages_to_delete:
                try:
                    await client.delete_messages(entity, msg_id)  # type: ignore[arg-type]
                    deleted_count += 1
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                except FloodWaitError as e:
                    click.echo(f"\n  EMERGENCY STOP: Rate limit hit!")
                    click.echo(f"  Telegram requires waiting {e.seconds} seconds")
                    click.echo(f"  Deleted {deleted_count}/{len(messages_to_delete)} in this chat")
                    result["total_deleted"] += deleted_count
                    # Save remaining chats before stopping
                    if file_path:
                        save_chats_to_json(file_path, remaining_chats)
                    result["flood_wait_seconds"] = e.seconds  # type: ignore[typeddict-unknown-key]
                    flood_stopped = True
                    break
                except Exception as e:
                    click.echo(f"  Failed to delete message {msg_id}: {e}")

            if flood_stopped:
                click.echo("\nOperation stopped due to rate limiting.")
                click.echo("Progress has been saved. Run again later to continue.")
                return result

            result["total_deleted"] += deleted_count
            result["chats_processed"] += 1
            click.echo(f"  Deleted {deleted_count}/{len(messages_to_delete)} messages")

            # Remove from remaining list and save after successful clean
            if file_path:
                remaining_chats = [c for c in remaining_chats if c.get("id") != chat_id]
                save_chats_to_json(file_path, remaining_chats)

    return result


@click.group()
def cli() -> None:
    """Telegram Cleaner - Manage your Telegram DMs and chats."""


@cli.command()
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=Path("inactive_chats.json"),
    help="Output JSON file path",
)
@click.option(
    "-m",
    "--months",
    type=int,
    default=6,
    help="Number of months of inactivity (default: 6)",
)
@click.option(
    "-l",
    "--limit",
    type=int,
    default=None,
    help="Maximum number of chats to collect (for testing)",
)
def collect(output: Path, months: int, limit: int | None) -> None:
    """Collect inactive chats where last message was older than specified months.

    Stores the list of inactive chats to a JSON file for review before cleanup.
    """
    asyncio.run(collect_inactive_chats(output, months, limit))


@cli.command()
@click.argument(
    "file",
    type=click.Path(exists=True, path_type=Path),
    default=Path("inactive_chats.json"),
)
def view(file: Path) -> None:
    """View collected chats in an interactive TUI.

    FILE is the path to a JSON file created by the collect command.
    Use arrow keys or j/k to navigate, d to remove selected chat, q to quit.
    """
    chats = load_chats_from_json(file)
    if not chats:
        click.echo("No chats found in the file.")
        return
    app = ChatsViewerApp(chats, file)
    app.run()


@cli.command()
@click.argument(
    "file",
    type=click.Path(exists=True, path_type=Path),
    default=Path("inactive_chats.json"),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deleted without actually deleting",
)
def clean(file: Path, dry_run: bool) -> None:
    """Delete your messages from all chats in the JSON file.

    FILE is the path to a JSON file created by the collect command.
    This will iterate through each chat and delete only YOUR messages,
    leaving the chat and other participants' messages untouched.

    Use --dry-run first to see what would be deleted.
    """
    chats = load_chats_from_json(file)
    if not chats:
        click.echo("No chats found in the file.")
        return

    click.echo(f"Processing {len(chats)} chats...")
    if dry_run:
        click.echo("DRY RUN - No messages will be deleted\n")

    result = asyncio.run(clean_chats_messages(chats, dry_run, file_path=file))

    click.echo("\n" + "=" * 40)
    click.echo("Summary:")
    click.echo(f"  Chats processed: {result['chats_processed']}/{len(chats)}")
    click.echo(f"  Messages found: {result['total_found']}")
    if dry_run:
        click.echo(f"  Messages to delete: {result['total_found']}")
    else:
        click.echo(f"  Messages deleted: {result['total_deleted']}")
    if result["errors"] > 0:
        click.echo(f"  Errors: {result['errors']}")


@cli.command()
@click.argument("chat")
@click.option(
    "-l",
    "--limit",
    type=int,
    default=DEFAULT_MESSAGE_LIMIT,
    help=f"Maximum number of messages to delete (default: {DEFAULT_MESSAGE_LIMIT})",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be deleted without actually deleting",
)
def clear(chat: str, limit: int, dry_run: bool) -> None:
    """Clear your own messages from a chat.

    CHAT can be a username, phone number, or chat ID.
    """
    asyncio.run(clear_messages(chat, limit, dry_run))


if __name__ == "__main__":
    cli()
