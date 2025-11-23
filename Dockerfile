FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    xvfb \
    chromium \
    chromium-driver \
    dbus-x11 \
    && rm -rf /var/lib/apt/lists/*

# Set Chrome/Chromium to use no-sandbox (required for Docker)
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMIUM_FLAGS="--no-sandbox --disable-dev-shm-usage --disable-gpu"

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config.json .
COPY server.py .

# Create directory for browser profile
RUN mkdir -p /root/.perplexity-browser-profile

# Create directory for sessions
RUN mkdir -p /app/data

# Expose server port
EXPOSE 8088

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

# Run the server
CMD ["python3", "server.py", "--host", "0.0.0.0", "--port", "8088"]

