"""
Lightweight HTTP server for Perplexity.ai API
Handles single endpoint: POST /ask
"""
import json
import logging
import re
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from .perplexity import ask_plexi, ask_in_session, close_browser
from .perplexity import _ensure_browser_started, _ensure_logged_in
from .session_manager import SessionManager
from .config import load_config
from .systemd_notify import SdNotifier


logger = logging.getLogger(__name__)

# Global request lock for handling one request at a time
_request_lock = threading.Lock()

# Global session manager
_session_manager: Optional[SessionManager] = None

# Global config
_config = None

# Systemd notifier
_notifier: Optional[SdNotifier] = None
def _set_status(message: str) -> None:
    """Update systemd status if sd_notify is available."""
    if _notifier and _notifier.available():
        _notifier.status(message)


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
            # Check browser state
            status = 'ok'
            message = 'Ready'
            http_status = 200
            
            try:
                from .perplexity import _browser_driver, _browser_manager, _get_browser_manager
                from .config import load_config
                
                # Check if browser is initialized
                if _browser_driver is None or _browser_manager is None:
                    status = 'not_ready'
                    message = 'Browser not yet initialized'
                    http_status = 503
                else:
                    # Check if browser session is valid
                    try:
                        _browser_driver.current_url
                    except Exception:
                        status = 'not_ready'
                        message = 'Browser session invalid'
                        http_status = 503
                    
                    # Check for Cloudflare
                    if status == 'ok':
                        try:
                            manager = _get_browser_manager(_config if _config else load_config())
                            if manager._check_cloudflare_challenge():
                                status = 'blocked'
                                message = 'Cloudflare challenge blocking access'
                                _set_status("Blocked by Cloudflare challenge – manual login required")
                                http_status = 503
                        except Exception as e:
                            logger.debug(f"Cloudflare check failed: {e}")
                    
                    # Check login status
                    if status == 'ok':
                        try:
                            manager = _get_browser_manager(_config if _config else load_config())
                            if not manager.check_login():
                                status = 'not_logged_in'
                                message = 'User not logged in'
                                http_status = 503
                        except Exception as e:
                            logger.debug(f"Login check failed: {e}")
                            status = 'not_ready'
                            message = f'Login check failed: {e}'
                            _set_status(f"Login check failed: {e}")
                            http_status = 503
                    
                    # Check if ready for questions (input field available)
                    if status == 'ok':
                        try:
                            from selenium.webdriver.common.by import By
                            question_input = _browser_driver.find_elements(By.CSS_SELECTOR, "p[dir='auto']")
                            if not question_input or not any(inp.is_displayed() for inp in question_input):
                                status = 'not_ready'
                                message = 'Input field not ready'
                                http_status = 503
                        except Exception as e:
                            logger.debug(f"Input field check failed: {e}")
                            status = 'not_ready'
                            message = f'Input field check failed: {e}'
                            _set_status("Input field not ready – waiting for Perplexity UI")
                            http_status = 503
                            
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
                status = 'error'
                message = f'Health check failed: {e}'
                _set_status(f"Health check error: {e}")
                http_status = 503
            
            data = {
                'status': status,
                'service': 'perplexity-api',
                'message': message,
            }
            
            if http_status == 200:
                self._send_json_response(200, data)
            else:
                self._send_error_response(http_status, status.replace('_', ' ').title(), message)
        else:
            self._send_error_response(
                404,
                "Not Found",
                "Only /ask and /health endpoints are supported",
            )
    
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
            _set_status("Busy – already processing another request")
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
            
            return_sources = request_data.get('return_sources', False)
            session_id_override = request_data.get('session_id')
            if session_id_override and not isinstance(session_id_override, str):
                self._send_error_response(400, "Bad Request", "'session_id' must be a string")
                return
            
            # Initialize session manager if needed
            if _session_manager is None:
                _session_manager = SessionManager()
            
            # Initialize config if needed
            if _config is None:
                _config = load_config()
            
            # Process request
            # If session_id is provided, continue in that session
            # Otherwise, create a new session
            if session_id_override:
                # Continue in specified session
                session_url = _session_manager.get_session_url(session_id_override)
                if session_url:
                    logger.info(f"Continuing in session {session_id_override} for question: {question[:50]}...")
                    _set_status(f"Processing question (session {session_id_override[:8]})")
                    response_text, session_id, final_url = ask_in_session(
                        question,
                        session_url,
                        config=_config,
                        debug=False
                    )
                    session_id = session_id or session_id_override
                    _session_manager.update_session_usage(session_id_override)
                else:
                    self._send_error_response(
                        404,
                        "Session Not Found",
                        f"Requested session '{session_id_override}' is unknown on the server",
                    )
                    return
            else:
                # Create new session (default behavior)
                logger.info(f"Creating new session for question: {question[:50]}...")
                _set_status("Processing question (new session)")
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
            _set_status("Idle – browser ready for questions")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing request: {e}", exc_info=True)
            _set_status(f"Error while processing request: {error_msg or 'see logs'}")
            
            # Check if it's a Cloudflare error - return 503 with clear message
            if "Cloudflare" in error_msg:
                self._send_error_response(
                    503, 
                    "Cloudflare Challenge", 
                    error_msg
                )
            else:
                self._send_error_response(500, "Internal Server Error", error_msg)
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
    global _notifier
    _notifier = SdNotifier()
    _set_status("Loading configuration...")

    _config = load_config()
    _session_manager = SessionManager()
    
    # Initialize browser at startup - navigate to main page (non-blocking)
    # Start HTTP server first, then initialize browser in background
    logger.info("Starting browser initialization (non-blocking)...")

    browser_ready_event = threading.Event()

    def init_browser():
        retry_delay = 15
        while True:
            try:
                _set_status("Starting headless browser session...")
                driver = _ensure_browser_started(_config)
                logger.info("Browser started")
                
                try:
                    _set_status("Verifying Perplexity login state...")
                    _ensure_logged_in(_config)
                    logger.info("Login verified")
                except Exception as e:
                    logger.warning(f"Login check failed: {e}")
                    logger.warning("Login can be completed on first request")
                
                # Navigate to main Perplexity page and wait for input to be ready
                perplexity_url = _config.get('browser', 'perplexity_url')
                base_url = perplexity_url.split('?')[0]  # Remove query params
                if driver.current_url != base_url and base_url not in driver.current_url:
                    logger.info(f"Navigating to main page: {base_url}")
                    driver.get(base_url)
                
                # Wait for input field to be ready (this is the slow part, do it at startup)
                _set_status("Waiting for Perplexity input field to become ready...")
                logger.info("Waiting for input field to be ready...")
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                wait = WebDriverWait(driver, 30)
                try:
                    wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "p[dir='auto']"))
                    )
                    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "p[dir='auto']")))
                    logger.info("✓ Browser initialized and ready - input field available")
                    _set_status("Idle – browser ready for questions")
                except Exception as e:
                    logger.warning(f"Input field not ready yet: {e}")
                    logger.info("Browser initialized (input will be ready on first request)")
                    _set_status("Browser initialized; waiting for first request to finish setup")
                
                # Once we reached this point, break out of retry loop
                browser_ready_event.set()
                break
            except Exception as e:
                logger.error(f"Failed to initialize browser: {e}", exc_info=True)
                logger.warning(f"Retrying browser initialization in {retry_delay}s...")
                _set_status(f"Browser init failed ({e}); retrying in {retry_delay}s")
                if _notifier:
                    _notifier.extend_timeout(retry_delay)
                time.sleep(retry_delay)
    
    # Start browser initialization in background thread
    browser_thread = threading.Thread(target=init_browser, daemon=True)
    browser_thread.start()
    logger.info("Browser initialization started in background")
    
    # Wait up to 30 seconds for browser to be ready (or until ready)
    logger.info("Waiting for browser to initialize (max 30s)...")
    start_wait = time.time()
    max_wait = 30
    while time.time() - start_wait < max_wait:
        try:
            from .perplexity import _browser_driver
            if _browser_driver is not None:
                try:
                    _browser_driver.current_url
                    logger.info("Browser is ready")
                    break
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(1)
    else:
        logger.warning(f"Browser not ready after {max_wait}s, continuing anyway")
    
    # Start HTTP server
    server_address = (host, port)
    httpd = HTTPServer(server_address, PerplexityAPIHandler)

    def signal_ready_when_browser_ready():
        browser_ready_event.wait()
        if _notifier:
            _notifier.ready("Idle – browser ready for questions")

    threading.Thread(target=signal_ready_when_browser_ready, daemon=True).start()
    
    _set_status("Starting HTTP server...")
    logger.info(f"Perplexity API server starting on http://{host}:{port}")
    logger.info("Press Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        httpd.shutdown()
        close_browser()
        logger.info("Server stopped")


def cli_main() -> None:
    """Console entry point for the HTTP server."""
    import argparse

    parser = argparse.ArgumentParser(description="Perplexity.ai API Server")
    parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="Host to bind to (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    start_server(host=args.host, port=args.port)


if __name__ == '__main__':
    cli_main()

