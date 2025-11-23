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

### Option 1: Docker

**Important**: First-time setup requires manual login. Choose one of these methods:

#### Method A: X11 Forwarding (Recommended for Docker)

Run the container with X11 forwarding to see the browser and log in:

```bash
# Build the image
docker compose build

# Run with X11 forwarding (allows you to see browser for login)
xhost +local:docker  # Allow Docker to access X11
docker run -it --rm \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -p 8088:8088 \
  -v $(pwd)/browser-profile:/root/.perplexity-browser-profile \
  -v $(pwd)/data:/app/data \
  perplexityapi-perplexity-api \
  python3 server.py --host 0.0.0.0 --port 8088

# After logging in, stop and run normally with docker compose
docker compose up -d
```

#### Method B: Pre-authenticated Profile

Run locally first, then copy the profile:

```bash
# Step 1: Run locally once to create browser profile with login
python3 server.py --host localhost --port 8088
# Log in when browser opens, then stop the server

# Step 2: Copy browser profile to Docker volume location
mkdir -p browser-profile
cp -r ~/.perplexity-browser-profile/* browser-profile/ 2>/dev/null || true

# Step 3: Build and run with Docker Compose
docker compose up -d
```

#### Method C: Docker Compose (After Initial Login)

Once you have a browser profile (from Method A or B), use docker-compose:

```bash
docker compose up -d
```

### Option 2: Local Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Start server
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

## Docker Details

### Initial Login Setup

**The Challenge**: Perplexity.ai requires manual browser login, which is difficult in a headless Docker container.

**Solutions**:

1. **X11 Forwarding** (Best for Docker): Run container with X11 access to see browser
2. **Pre-authenticated Profile**: Run locally first, copy profile to Docker
3. **VNC** (Advanced): Use VNC server in container (not included, but possible)

### Building

```bash
docker compose build
# or
docker build -t perplexity-api .
```

### Running After Login

Once you have a browser profile with login:

```bash
# With docker-compose (recommended)
docker compose up -d

# Manual run
docker run -d \
  --name perplexity-api \
  -p 8088:8088 \
  -v $(pwd)/browser-profile:/root/.perplexity-browser-profile \
  -v $(pwd)/data:/app/data \
  perplexity-api
```

### Volumes

- `browser-profile/`: Browser user data (login session persists here)
- `data/`: Application data (sessions.json stored here)

### Environment Variables

- `PERPLEXITY_API_URL`: Server URL (for CLI wrapper)
- `DISPLAY`: X display (set automatically in Docker)

## Development

```bash
# Run server in debug mode
python3 server.py --host localhost --port 8088 --debug

# Test with CLI
askplexi "test question" --new

# Check server logs
docker-compose logs -f perplexity-api
```

## Troubleshooting

### Server won't start

- Check if port 8088 is available
- Verify browser dependencies are installed
- Check logs: `docker-compose logs perplexity-api`

### Login issues

- **Docker**: First run requires manual login. Use X11 forwarding or pre-authenticated profile (see Docker section)
- **Local**: Browser will open automatically for login on first run
- Browser profile is saved in `browser-profile/` (Docker) or `~/.perplexity-browser-profile/` (local)
- Delete profile to force re-login
- **Docker X11**: Make sure `xhost +local:docker` is run before starting container with X11

### Slow responses

- Server initializes browser at startup (one-time delay)
- Subsequent requests are faster
- Check network connectivity to Perplexity.ai

## License

Private project - All rights reserved

