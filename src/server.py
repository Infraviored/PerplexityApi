"""
Lightweight HTTP server for Perplexity.ai API
Handles single endpoint: POST /ask
"""
import json
import logging
import re
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Optional

from .perplexity import ask_plexi, ask_in_session, close_browser
from .perplexity import _ensure_browser_started, _ensure_logged_in
from .session_manager import SessionManager
from .config import load_config


logger = logging.getLogger(__name__)

# Global request lock for handling one request at a time
_request_lock = threading.Lock()

# Global session manager
_session_manager: Optional[SessionManager] = None

# Global config
_config = None


def clean_response_text(text, include_sources=True):
    """
    Clean response text by removing citations and URLs unless include_sources is True
    
    Args:
        text: The response text to clean
        include_sources: If True, keep citations and URLs. If False, remove them.
    
    Returns:
        Cleaned text
    """
    if include_sources:
        return text
    
    # Remove citation markers like [1], [2], etc. from the text
    text = re.sub(r'\[\d+\]', '', text)
    
    # Remove URL sections at the bottom
    # Look for patterns like:
    # [1](https://...)
    # (https://...)
    # or just URLs
    lines = text.split('\n')
    cleaned_lines = []
    in_url_section = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Check if this line is a URL/citation reference
        # Patterns:
        # - [1](https://...)
        # - (https://...)
        # - https://...
        is_url_line = (
            re.match(r'^\[\d+\]\(https?://', stripped) or
            re.match(r'^\(https?://', stripped) or
            re.match(r'^https?://', stripped) or
            (stripped.startswith('[') and '](http' in stripped) or
            (stripped.startswith('(') and 'http' in stripped and stripped.endswith(')'))
        )
        
        if is_url_line:
            in_url_section = True
            continue
        
        # If we're in URL section and hit a blank line, skip it
        if in_url_section and stripped == '':
            continue
        
        # If we're in URL section and hit content that's not a URL, exit URL section
        if in_url_section and not is_url_line:
            # Check if previous lines were URLs - if so, we've exited the URL section
            in_url_section = False
            cleaned_lines.append(line)
            continue
        
        if not in_url_section:
            cleaned_lines.append(line)
    
    result = '\n'.join(cleaned_lines).strip()
    
    # Clean up any remaining citation markers that might have been missed
    result = re.sub(r'\s+\[\d+\]', '', result)
    result = re.sub(r'\[\d+\]\s+', '', result)
    
    # Remove URLs in parentheses that might be inline: (https://...)
    result = re.sub(r'\(https?://[^\)]+\)', '', result)
    
    # Remove multiple consecutive blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result.strip()


class PerplexityAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Perplexity API"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_OPTIONS(self):
        """Handle CORS preflight and health checks"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests for health checks"""
        if self.path == '/health' or self.path == '/':
            self._send_json_response(200, {'status': 'ok', 'service': 'perplexity-api'})
        else:
            self._send_error_response(404, "Not Found", "Only /ask, /health endpoints are supported")
    
    def do_POST(self):
        """Handle POST requests"""
        global _request_lock, _session_manager, _config
        
        # Only handle /ask endpoint
        if self.path != '/ask':
            self._send_error_response(404, "Not Found", "Only /ask endpoint is supported")
            return
        
        # Handle one request at a time
        if not _request_lock.acquire(blocking=False):
            self._send_error_response(503, "Service Unavailable", "Server is busy processing another request")
            return
        
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_error_response(400, "Bad Request", "Request body is required")
                return
            
            body = self.rfile.read(content_length)
            try:
                request_data = json.loads(body.decode('utf-8'))
            except json.JSONDecodeError:
                self._send_error_response(400, "Bad Request", "Invalid JSON in request body")
                return
            
            question = request_data.get('question')
            if not question:
                self._send_error_response(400, "Bad Request", "Missing 'question' field")
                return
            
            new_session = request_data.get('new_session', False)
            return_sources = request_data.get('return_sources', False)
            
            # Initialize session manager if needed
            if _session_manager is None:
                _session_manager = SessionManager()
            
            # Initialize config if needed
            if _config is None:
                _config = load_config()
            
            # Process request
            if new_session:
                # Create new session
                logger.info(f"Creating new session for question: {question[:50]}...")
                response_text, session_id, final_url = ask_plexi(
                    question,
                    config=_config,
                    debug=False,
                    headless=True
                )
                
                if session_id and final_url:
                    _session_manager.create_session(session_id, final_url)
            else:
                # Continue in existing session
                current_session_id = _session_manager.get_current_session()
                
                if current_session_id:
                    session_url = _session_manager.get_session_url(current_session_id)
                    if session_url:
                        logger.info(f"Continuing in session {current_session_id} for question: {question[:50]}...")
                        response_text, session_id, final_url = ask_in_session(
                            question,
                            session_url,
                            config=_config,
                            debug=False
                        )
                        _session_manager.update_session_usage(current_session_id)
                    else:
                        # Session URL not found, create new session
                        logger.info(f"Session URL not found, creating new session for question: {question[:50]}...")
                        response_text, session_id, final_url = ask_plexi(
                            question,
                            config=_config,
                            debug=False,
                            headless=True
                        )
                        if session_id and final_url:
                            _session_manager.create_session(session_id, final_url)
                else:
                    # No current session, create new one
                    logger.info(f"No current session, creating new session for question: {question[:50]}...")
                    response_text, session_id, final_url = ask_plexi(
                        question,
                        config=_config,
                        debug=False,
                        headless=True
                    )
                    if session_id and final_url:
                        _session_manager.create_session(session_id, final_url)
            
            # Clean response text (remove citations and URLs unless return_sources is True)
            cleaned_response = clean_response_text(response_text, include_sources=return_sources)
            
            # Send success response
            response_data = {
                'response': cleaned_response,
                'session_id': session_id
            }
            self._send_json_response(200, response_data)
            
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            self._send_error_response(500, "Internal Server Error", str(e))
        finally:
            _request_lock.release()
    
    def _send_json_response(self, status_code: int, data: dict):
        """Send JSON response"""
        response_json = json.dumps(data).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(response_json)))
        self.end_headers()
        self.wfile.write(response_json)
    
    def _send_error_response(self, status_code: int, error: str, message: str):
        """Send error response"""
        response_data = {
            'error': error,
            'message': message
        }
        self._send_json_response(status_code, response_data)


def start_server(host: str = 'localhost', port: int = 8000):
    """
    Start the Perplexity API server
    
    Args:
        host: Host to bind to (default: localhost)
        port: Port to listen on (default: 8000)
    """
    global _config, _session_manager
    
    # Initialize config and session manager
    _config = load_config()
    _session_manager = SessionManager()
    
    # Initialize browser at startup - navigate to main page
    logger.info("Initializing browser...")
    try:
        driver = _ensure_browser_started(_config)
        logger.info("Browser started")
        
        _ensure_logged_in(_config)
        logger.info("Login verified")
        
        # Navigate to main Perplexity page and wait for input to be ready
        perplexity_url = _config.get('browser', 'perplexity_url')
        base_url = perplexity_url.split('?')[0]  # Remove query params
        if driver.current_url != base_url and not base_url in driver.current_url:
            logger.info(f"Navigating to main page: {base_url}")
            driver.get(base_url)
        
        # Wait for input field to be ready (this is the slow part, do it at startup)
        logger.info("Waiting for input field to be ready...")
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import time
        
        wait = WebDriverWait(driver, 30)
        try:
            question_input = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "p[dir='auto']"))
            )
            wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "p[dir='auto']")))
            logger.info("✓ Browser initialized and ready - input field available")
        except Exception as e:
            logger.warning(f"Input field not ready yet: {e}")
            logger.info("Browser initialized (input will be ready on first request)")
    except Exception as e:
        logger.error(f"Failed to initialize browser: {e}", exc_info=True)
        raise
    
    # Start HTTP server
    server_address = (host, port)
    httpd = HTTPServer(server_address, PerplexityAPIHandler)
    
    logger.info(f"Perplexity API server starting on http://{host}:{port}")
    logger.info("Press Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        httpd.shutdown()
        close_browser()
        logger.info("Server stopped")


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    start_server()

