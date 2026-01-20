# Telegram Cleaner

A CLI tool for cleaning up your Telegram message history. Features an interactive TUI for reviewing chats and bulk operations for deleting your messages from inactive conversations.

## Features

- **Collect inactive chats** - Find chats with no activity for X months
- **Interactive TUI** - Review and manage collected chats with vim-style navigation
- **Keep list** - Mark chats to skip permanently in future collects
- **Bulk message cleanup** - Delete your messages from multiple chats at once
- **Single chat cleanup** - Clear your messages from a specific chat

## Requirements

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Telegram API credentials (API ID and API Hash)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/telegram-cleaner.git
   cd telegram-cleaner
   ```

2. Install dependencies with uv:
   ```bash
   uv sync
   ```

3. Get your Telegram API credentials:
   - Go to https://my.telegram.org
   - Log in with your phone number
   - Go to "API development tools"
   - Create a new application to get your `API_ID` and `API_HASH`

4. Create your environment file:
   ```bash
   cp .env.example .env
   ```

5. Edit `.env` and add your credentials:
   ```env
   TG_API_ID=your_api_id
   TG_API_HASH=your_api_hash
   ```

6. On first run, you'll be prompted to authenticate with your phone number and verification code.

## Usage

Run commands using uv:

```bash
uv run python telegram_cleaner.py <command> [options]
```

### Commands

#### `collect` - Find inactive chats

Collect chats where the last message is older than a specified number of months:

```bash
uv run python telegram_cleaner.py collect
uv run python telegram_cleaner.py collect -m 12 -o old_chats.json
uv run python telegram_cleaner.py collect --months 3 --limit 50
```

Options:
- `-o, --output PATH` - Output file path (default: `inactive_chats.json`)
- `-m, --months INT` - Inactivity threshold in months (default: 6)
- `-l, --limit INT` - Maximum number of chats to collect (for testing)

#### `view` - Interactive TUI

Review collected chats in an interactive terminal interface:

```bash
uv run python telegram_cleaner.py view
uv run python telegram_cleaner.py view my_chats.json
```

**Keybindings:**
| Key | Action |
|-----|--------|
| `j` / `↓` | Move cursor down |
| `k` / `↑` | Move cursor up |
| `d` | Delete - remove chat from list (will be cleaned) |
| `s` | Skip - keep chat permanently (skip in future collects) |
| `q` | Quit |

- **`d` (Delete)** - Removes the chat from the current list. Use this when you want to clean messages from this chat.
- **`s` (Skip)** - Adds the chat to `keep.json` and removes from current list. These chats will be automatically skipped in future `collect` runs. Use this for chats you want to preserve.

#### `clean` - Bulk delete your messages

Delete your messages from all chats in a JSON file:

```bash
uv run python telegram_cleaner.py clean --dry-run
uv run python telegram_cleaner.py clean inactive_chats.json
uv run python telegram_cleaner.py clean my_list.json --dry-run
```

Options:
- `--dry-run` - Preview what would be deleted without making changes

**Important:** Always use `--dry-run` first to verify the operation. Successfully cleaned chats are automatically removed from the JSON file.

#### `clear` - Clear messages from a single chat

Delete your messages from a specific chat:

```bash
uv run python telegram_cleaner.py clear @username
uv run python telegram_cleaner.py clear @username --dry-run
uv run python telegram_cleaner.py clear 123456789 -l 500
```

Arguments:
- `CHAT` - Username, phone number, or chat ID

Options:
- `-l, --limit INT` - Maximum messages to delete (default: 100)
- `--dry-run` - Preview without deleting

## Typical Workflow

1. **Collect inactive chats:**
   ```bash
   uv run python telegram_cleaner.py collect -m 12
   ```

2. **Review and curate the list:**
   ```bash
   uv run python telegram_cleaner.py view inactive_chats.json
   ```
   - Press `s` to mark chats you want to **keep** (they'll be skipped in future collects)
   - Press `d` to remove chats from the list (they stay for cleaning)

3. **Preview the cleanup:**
   ```bash
   uv run python telegram_cleaner.py clean inactive_chats.json --dry-run
   ```

4. **Execute the cleanup:**
   ```bash
   uv run python telegram_cleaner.py clean inactive_chats.json
   ```

## Configuration

All configuration is done via environment variables in `.env`:

| Variable | Description | Required |
|----------|-------------|----------|
| `TG_API_ID` | Telegram API ID | Yes |
| `TG_API_HASH` | Telegram API Hash | Yes |
| `TG_SESSION_NAME` | Session file name | No (default: `telegram_cleaner`) |

## Running Tests

```bash
uv run pytest
uv run pytest -v  # verbose output
```

## License

MIT
