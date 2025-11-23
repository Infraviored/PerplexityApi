# Installation

## Install the CLI wrapper to system path

To make `askplexi` available system-wide:

```bash
# Option 1: Create symlink (recommended)
sudo ln -s $(pwd)/askplexi /usr/local/bin/askplexi

# Option 2: Copy to /usr/local/bin
sudo cp askplexi /usr/local/bin/

# Option 3: Add to PATH in your shell config
echo 'export PATH="$PATH:/path/to/PerplexityApi"' >> ~/.bashrc
```

## Usage

```bash
# Basic usage
askplexi "What is 2+2?"

# Create new session
askplexi "What is 2+2?" --new

# Use specific session (future feature)
askplexi "What is 2+2?" --id "session-id-123"

# Read from stdin
echo "What is 2+2?" | askplexi

# Custom server URL
askplexi "What is 2+2?" --server "http://localhost:9000"

# Or set environment variable
export PERPLEXITY_API_URL="http://localhost:9000"
askplexi "What is 2+2?"
```

## Requirements

Make sure the server is running:
```bash
python3 server.py --host localhost --port 8088
```

The CLI wrapper connects to the server via HTTP.

