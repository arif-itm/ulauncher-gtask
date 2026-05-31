# ulauncher-gtask

Ulauncher 5.15+ extension for Google Tasks. Pure Python stdlib — zero dependencies, no build, no tests, no CI.

## Architecture

- `main.py` — Ulauncher `Extension` entrypoint; `KeywordQueryEventListener` and `ItemEnterEventListener` handle all UI logic
- `gtask_client.py` — `GoogleTasksAuth` (OAuth 2.0 via local HTTP server + `urllib`) + `GoogleTasksClient` (REST to `tasks.googleapis.com` + `cache.json` disk cache)
- `manifest.json` — Extension metadata and 3 user preferences (keyword, default list, show completed)
- Cache-first reads; writes go to API then update cache

## State files (all gitignored, all in repo root)

| File | Origin | Notes |
|---|---|---|
| `credentials.json` | User-placed from Google Cloud Console | OAuth client ID/secret for a Desktop app |
| `token.json` | Auto-generated on first auth | OAuth tokens (auto-refresh via refresh_token) |
| `cache.json` | Auto-generated on first `sync_all()` | Full local copy; delete to force re-fetch |

## Commands

Dev testing (only works inside Ulauncher runtime):
```
ulauncher --no-extensions --dev -v
```

Extension keywords (default: `gt`):
- `gt` — browse lists; `gt <search>` — filter lists; click a list to see tasks
- `gt new <title>` — add task (to selected list, default list, or first list)
- `gt newlist <name>` — create new task list
- `gt del` — delete task (two-click confirm inside a list)
- `gt dellist` — delete list (two-click confirm at list level)
- `gt back` — return to list level
- Click a task to toggle complete/uncomplete (strikethrough via `\u0336`)

Views are paginated at 8 items per page (lists) and 7 items per page (tasks). `Previous page` / `Next page` appear at bottom when more items exist. New searches reset to page 0.

## Gotchas

- **No `pip install` needed**. Adding a requirements.txt or pyproject.toml is wrong unless a new dependency is added.
- **No tests, no linter, no typechecker, no CI**. Don't look for them; don't add them unless asked.
- **`main.py` cannot run standalone** (`__name__ == '__main__'` calls `GTaskExtension().run()` which requires Ulauncher's WebSocket IPC).
- **Cache never auto-re-syncs from Google**. Only writes update it. Delete `cache.json` to force a full refresh.
- **OAuth setup is manual**: requires Google Cloud Console → enable Tasks API → create Desktop app OAuth credentials → save as `credentials.json`.
