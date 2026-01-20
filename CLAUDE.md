# Project Notes for Claude

You're writing code that will be used in production, and many people will depend on it. 
Any small mistake or bug could cause great losses or even nuclear war.


We use a strict TDD approach, writing tests before implementation. 
Do not add features unless the user requests them. If the user asks for Grok integration, do only that, 
not perplexity or OpenAI. If your experience suggests that adding something would be beneficial, 
ask the user first. Make flows extremely clear.



## Package Manager
This project uses **uv** as the package manager, not pip.

Install packages with:
```bash
uv add <package>
```

## Import Rules (STRICT)

**ALL imports MUST be at the top of the file. NO EXCEPTIONS.**

### Forbidden patterns:

```python
# FORBIDDEN: Imports inside functions
def my_function():
    import something  # NO!
    from module import thing  # NO!

# FORBIDDEN: Conditional imports
if condition:
    import something  # NO!

# FORBIDDEN: Try/except around imports
try:
    import optional_module  # NO!
except ImportError:
    optional_module = None  # NO!

# FORBIDDEN: Lazy imports
def get_thing():
    from module import Thing  # NO!
    return Thing()
```

### Required pattern:

```python
# All imports at the TOP of the file, ALWAYS
from __future__ import annotations

import os
import sys
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import select

from src.database import get_db
```

If a dependency is missing, the application should **fail fast** at startup, not silently degrade.

When you finish the file, check and remove unused imports.

## Environment Variables (STRICT)

**All required env vars are checked at startup. Server will NOT start if any are missing.**

### Required variables (in `.env`):
- `ANYSITE_API_KEY` - Required for Twitter import

### How it works:
1. `pydantic-settings` loads `.env` automatically via `src/config/settings.py`
2. `src/main.py` validates required vars at import time
3. Server exits with error if any required var is missing

### Adding new required env vars:
1. Add to `Settings` class in `src/config/settings.py`
2. Add to `REQUIRED_ENV_VARS` dict in `src/main.py`

### NEVER use `os.environ` or `os.getenv` directly. Always use `settings` from `src.config`.


## Clean Architecture & Testing (STRICT)

**NEVER use production database in tests. NEVER.**

### Architecture layers:
```
Route (HTTP) → Service (business logic) → Repo (data access)
```

Each layer can be replaced/mocked independently. This is the point of clean architecture.

### Testing rules:

1. **Repo layer**: Mock the database, not the real one
2. **Service layer**: Inject mock repo, test business logic
3. **Route layer**: Mock service, test HTTP handling

### FORBIDDEN in tests:

```python
# FORBIDDEN: Using real database
async with AsyncSessionLocal() as db:
    await real_repo.create(db, data)  # NO!

# FORBIDDEN: Calling real external APIs
client = AnysiteClient()
await client.get_twitter_user("handle")  # NO!
```

### Required pattern:

```python
# Mock the repo or external client
with patch.object(AnysiteClient, "get_twitter_user", return_value=mock_data):
    response = await client.post("/endpoint")

# Or use dependency injection with mock repo
class MockTwitterRepo:
    async def get_by_alias(self, alias: str):
        return mock_account
```

### Why this matters:
- Tests must be deterministic and fast
- Tests must not pollute production data
- Tests must not depend on external services being available
- Each component should be testable in isolation


## External Data Sources (STRICT)

**When fetching data from external APIs (Telegram, Google, Anysite, etc.) - STORE ALL INFORMATION POSSIBLE.**

### Why:
- API calls are expensive (rate limits, latency, costs)
- Data might become unavailable later
- We may need fields we didn't think of initially
- This is a CRM - more data = better

### Rules:

1. **Schema must include ALL fields** the API returns
2. **Store arrays as JSON** (phones_json, emails_json, etc.)
3. **Never discard data** - if API returns it, we store it
4. **Include raw_json field** for unexpected/new fields

### Example - Google People API:
```python
# WRONG - minimal schema
class GoogleContact:
    given_name: str
    family_name: str

# CORRECT - store everything
class GoogleContact:
    # Names
    given_name, family_name, display_name, middle_name, prefix, suffix

    # Contact info (JSON arrays)
    phones_json      # [{value, type, label}, ...]
    emails_json      # [{value, type, label}, ...]
    addresses_json   # [{street, city, region, country, postalCode}, ...]

    # Professional
    organizations_json  # [{name, title, department}, ...]

    # Personal
    birthdays_json   # [{date, text}, ...]
    relations_json   # [{person, type}, ...]
    events_json      # [{date, type}, ...]  (anniversaries, etc.)

    # Links
    urls_json        # [{value, type}, ...]  (websites, social)

    # Other
    biographies_json
    photos_json
    notes

    # Raw data for anything we missed
    raw_json
```

### Same applies to:
- **Telegram**: Store all user fields, chat metadata, message content
- **Twitter/Anysite**: Store all profile fields, metrics, verification info
- **Any future integration**: Always capture full API response
