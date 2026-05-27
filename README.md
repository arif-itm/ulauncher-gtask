<div align="center">
  <img src="images/icon.svg" width="96" alt="Google Tasks logo" />
  <h1 align="center">Google Tasks</h1>
  <p align="center">
    A Ulauncher extension for managing your Google Tasks — view, add, complete, and delete tasks<br />
    with a satisfying strikethrough effect, all without leaving your keyboard.
  </p>
  <p align="center">
    <a href="#features">Features</a> •
    <a href="#demo">Demo</a> •
    <a href="#requirements">Requirements</a> •
    <a href="#installation">Installation</a> •
    <a href="#setup">Setup</a> •
    <a href="#usage">Usage</a> •
    <a href="#faq">FAQ</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/ulauncher-5.15%2B-blue?style=flat-square" alt="Ulauncher 5.15+" />
    <img src="https://img.shields.io/badge/python-3.6%2B-blue?style=flat-square" alt="Python 3.6+" />
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License" />
    <img src="https://img.shields.io/badge/dependencies-0-brightgreen?style=flat-square" alt="Zero Dependencies" />
  </p>
</div>

---

## Features

- **Browse task lists** — explore all your Google Task lists and drill into each one
- **Add tasks** — quick-add with a single command: `gt add Buy groceries`
- **Complete tasks** — click to mark done; the task animates with strikethrough text and a green checkmark
- **Delete tasks** — click a completed task to remove it permanently
- **Instant sync** — every action hits the live Google Tasks API, so changes appear on all your devices
- **Customizable** — keyword, default list, and completed-task visibility are all configurable from Ulauncher Preferences
- **Zero dependencies** — built entirely on Python's standard library. No `pip install` required.

## Demo

| Step | Screenshot |
|---|---|
| Task lists | Todo |
| Tasks in a list | Todo |
| Adding a task | Todo |
| Completing a task (strikethrough) | Todo |

## Requirements

- [Ulauncher](https://ulauncher.io) 5.15+ (Extension API v2)
- Python 3.6+
- A Google account with [Google Tasks](https://tasks.google.com) enabled

## Installation

```bash
# Clone the repository into the Ulauncher extensions directory
git clone https://github.com/arif-itm/ulauncher-gtask.git \
  ~/.local/share/ulauncher/extensions/Ulauncher-GTask
```

Then enable the extension in **Ulauncher Preferences → Extensions**.

## Setup

This extension uses the official Google Tasks API, which requires OAuth 2.0 credentials from your Google Cloud project.

### 1. Enable the Google Tasks API

1. Go to the [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select an existing one)
3. Navigate to **APIs & Services → Library**
4. Search for **Google Tasks API** and click **Enable**

### 2. Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**
2. Select **External** as the user type
3. Fill in the required fields (app name, support email, developer contact)
4. Under **Test users**, add the email address associated with your Google Tasks
5. Click **Save**

### 3. Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. Application type: **Desktop app**
4. Give it a name (e.g., "Ulauncher Google Tasks")
5. Click **Create**
6. Download the JSON file

### 4. Place the credentials file

```bash
cp ~/Downloads/client_secret_*.json \
  ~/.local/share/ulauncher/extensions/Ulauncher-GTask/credentials.json
```

## Usage

### First run

```bash
# Restart Ulauncher in dev mode (optional, for detailed logs)
ulauncher --no-extensions --dev -v
```

1. Type your keyword (default: `gt`) and press <kbd>Space</kbd>
2. Click **Sign in with Google** — your browser will open for authorization
3. Grant access, then return to Ulauncher
4. Your task lists are now visible

### Commands

| Action | Input |
|---|---|
| Browse task lists | `gt` |
| Filter task lists | `gt <list name>` |
| Open a list | Click the list name |
| Browse tasks | `gt` (after selecting a list) |
| Filter tasks | `gt <task title>` |
| Add a task | `gt add <task title>` |
| Complete a task | Click the task |
| Delete a task | Click the completed (strikethrough) task |
| Go back to lists | `gt back` |

### Key bindings

| Key | Action |
|---|---|
| <kbd>Enter</kbd> | Complete task / open list / authenticate |
| <kbd>Esc</kbd> | Close Ulauncher |

## Customization

Open **Ulauncher Preferences → Extensions → Google Tasks**:

| Preference | Description | Default |
|---|---|---|
| Keyword | Trigger word for the extension | `gt` |
| Default Task List | List used when adding tasks without selecting one first | *(first list)* |
| Show Completed Tasks | Whether completed tasks appear in lists | `Hide` |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Ulauncher (WebSocket)                    │
└─────────────────────────┬───────────────────────────────────┘
                          │ IPC
┌─────────────────────────▼───────────────────────────────────┐
│  main.py                                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Extension (event loop)                               │   │
│  │  ├─ KeywordQueryEventListener                        │   │
│  │  └─ ItemEnterEventListener                           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │ method calls
┌─────────────────────────▼───────────────────────────────────┐
│  gtask_client.py                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ GoogleTasksAuth (OAuth 2.0)                          │   │
│  │  ├─ run_local_server() → browser auth                │   │
│  │  ├─ token persistence (token.json)                   │   │
│  │  └─ auto-refresh on expiry                           │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ GoogleTasksClient (REST)                             │   │
│  │  ├─ list_tasklists()                                 │   │
│  │  ├─ list_tasks()                                     │   │
│  │  ├─ insert_task()                                    │   │
│  │  ├─ complete_task()                                  │   │
│  │  └─ delete_task()                                    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS (raw urllib)
┌─────────────────────────▼───────────────────────────────────┐
│          Google Tasks API (tasks.googleapis.com)             │
└─────────────────────────────────────────────────────────────┘
```

## Strikethrough effect

When you complete a task, the extension:

1. Calls the Google Tasks API to mark it as `completed`
2. Renders the task title with the Unicode combining long stroke overlay (`\u0336`) applied to each character — producing `c̶o̶m̶p̶l̶e̶t̶e̶d̶`
3. Swaps the icon to `images/checked.svg` (green checkmark)
4. On your next query, completed tasks are hidden (unless you toggle **Show Completed Tasks**)

The change is instantly synced to all your devices via Google.

## File structure

```
~/.local/share/ulauncher/extensions/Ulauncher-GTask/
├── images/
│   ├── icon.svg               # Google Tasks logo
│   └── checked.svg            # Green checkmark (completed state)
├── versions.json              # Extension API version mapping
├── manifest.json              # Extension metadata & user preferences
├── main.py                    # Ulauncher extension entry point
├── gtask_client.py            # OAuth 2.0 + Google Tasks REST client
├── credentials.json           # Your Google Cloud OAuth credentials (user-provided)
├── token.json                 # Auto-generated OAuth session (do not commit)
├── .gitignore
├── LICENSE
└── README.md
```

## FAQ

<details>
<summary><strong>Why does the extension need OAuth credentials?</strong></summary>
Google Tasks is a personal API that requires authentication. The extension uses OAuth 2.0 with a local server to authorize your account. Your credentials and tokens stay on your machine.
</details>

<details>
<summary><strong>Can I use this with multiple Google accounts?</strong></summary>
Currently, the extension supports one account at a time. To switch, delete <code>token.json</code> from the extension directory and re-authenticate.
</details>

<details>
<summary><strong>Are my tasks stored locally?</strong></summary>
No. The extension acts as a read/write proxy to the Google Tasks API. Tasks are fetched live every time you search, and changes are written directly to Google's servers.
</details>

<details>
<summary><strong>What happens if my token expires?</strong></summary>
The extension automatically refreshes the token using the refresh token provided by Google during initial authorization. If the refresh token also expires (e.g., account password change), you'll be prompted to re-authenticate.
</details>

## License

[MIT](LICENSE) © 2026 arif-itm
