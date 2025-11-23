# Perplexity.ai API Server

A lightweight HTTP server that provides programmatic access to Perplexity.ai through browser automation. The server maintains a persistent browser session and manages conversation sessions via URL tracking.

## Features

- **Persistent Browser Session**: Single headless browser instance that stays open
- **Session Management**: Automatic session tracking via URL extraction
- **Follow-up Questions**: Continue conversations in existing sessions
- **Fast Response Times**: Optimized for minimal delays
- **RESTful API**: Simple HTTP endpoint
- **CLI Wrapper**: Easy command-line access

## Architecture

- **Server** (`server.py`): HTTP server that manages browser and sessions
- **Session Manager** (`src/session_manager.py`): JSON-based session storage
- **Perplexity Module** (`src/perplexity.py`): Browser automation logic
- **CLI Wrapper** (`askplexi`): Command-line interface

## Quick Start

### Option 1: Systemd Service (Recommended for Production)

Install as a system service that runs automatically:

```bash
# Install dependencies
pip install -r requirements.txt

# Run manual login first (browser will open)
python3 manual_login.py

# Install as user systemd service (no sudo needed)
./install-service.sh
```

The installer will:
- Create a systemd service file
- Enable the service to start on boot
- Optionally start the service immediately

**Service Management:**
```bash
# Start/stop/restart service
systemctl --user start perplexity-api
systemctl --user stop perplexity-api
systemctl --user restart perplexity-api

# View logs
journalctl --user -u perplexity-api -f

# Check status
systemctl --user status perplexity-api
```

### Option 2: Manual Run

```bash
# Install dependencies
pip install -r requirements.txt

# Start server manually
python3 server.py --host localhost --port 8088
```

**Note**: On first run, the browser will open for manual login. After login, subsequent runs will use the saved session.

## API Usage

### Single Endpoint: `POST /ask`

**Request:**
```json
{
  "question": "What is 2+2?",
  "new_session": false
}
```

**Response:**
```json
{
  "response": "The answer is 4.",
  "session_id": "what-is-2-2-abc123"
}
```

**Parameters:**
- `question` (required): The question to ask
- `new_session` (optional, default: `false`): Create a new session instead of continuing in current one

**Examples:**

```bash
# Ask a question (continues in current session)
curl -X POST http://localhost:8088/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is 2+2?"}'

# Create new session
curl -X POST http://localhost:8088/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is 2+2?", "new_session": true}'
```

## CLI Wrapper

### Installation

```bash
# Make executable and add to PATH
sudo ln -s $(pwd)/askplexi /usr/local/bin/askplexi
```

### Usage

```bash
# Basic usage
askplexi "What is 2+2?"

# Create new session
askplexi "What is 2+2?" --new

# Custom server URL
askplexi "What is 2+2?" --server "http://localhost:9000"

# Read from stdin
echo "What is 2+2?" | askplexi
```

## Configuration

Edit `config.json` to customize:

```json
{
  "browser": {
    "perplexity_url": "https://www.perplexity.ai/",
    "user_data_dir": "~/.perplexity-browser-profile",
    "headless": true,
    "use_xvfb": true
  },
  "perplexity": {
    "default_model": "Claude Sonnet 4.5",
    "default_reasoning": true
  }
}
```

## Session Management

Sessions are automatically tracked and stored in `sessions.json`:

```json
{
  "sessions": {
    "session-id-123": {
      "url": "https://www.perplexity.ai/search/...",
      "created_at": "2024-01-01T12:00:00",
      "last_used_at": "2024-01-01T12:05:00"
    }
  },
  "current_session": "session-id-123"
}
```

## Systemd Service Details

### Installation

The `install-service.sh` script creates a systemd service that:
- Runs as the user who executed the installer (via sudo)
- Automatically restarts on failure
- Starts on system boot
- Logs to systemd journal

### Configuration

The service runs with:
- Host: `0.0.0.0` (listens on all interfaces)
- Port: `8088`
- Working directory: Project root directory

To change these settings, edit `~/.config/systemd/user/perplexity-api.service` after installation and run:
```bash
systemctl --user daemon-reload
systemctl --user restart perplexity-api
```

**Note:** The service starts automatically when you log in. To enable it to start at boot (without login), run:
```bash
loginctl enable-linger $USER
```

### Environment Variables

- `PERPLEXITY_API_URL`: Server URL (for CLI wrapper)

## Development

```bash
# Run server in debug mode
python3 server.py --host localhost --port 8088 --debug

# Test with CLI
askplexi "test question" --new

# Check server logs (if running as service)
journalctl -u perplexity-api -f
```

## Troubleshooting

### Server won't start

- Check if port 8088 is available
- Verify browser dependencies are installed
- Check logs: `journalctl --user -u perplexity-api -n 50` (service) or check terminal output (manual run)

### Login issues

- **First run**: Browser will open automatically for login on first run
- Browser profile is saved in `~/.perplexity-browser-profile/`
- Delete profile to force re-login: `rm -rf ~/.perplexity-browser-profile`
- Run `python3 manual_login.py` to re-authenticate

### Slow responses

- Server initializes browser at startup (one-time delay)
- Subsequent requests are faster
- Check network connectivity to Perplexity.ai

## License

Private project - All rights reserved

