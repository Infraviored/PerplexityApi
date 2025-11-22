"""
Perplexity.ai automation module
"""
import json
import os
import time
import logging
import pyperclip
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from .browser import BrowserManager

# Configure logging to suppress Selenium/undetected-chromedriver noise
logging.getLogger('selenium').setLevel(logging.WARNING)
logging.getLogger('undetected_chromedriver').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# Set up our logger
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)  # Default to INFO level


# Module-level browser instance for persistence
_browser_manager = None
_browser_driver = None


def _get_browser_manager(config):
    """Get or create the module-level browser manager"""
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager(config)
    return _browser_manager


def _ensure_browser_started(config):
    """Ensure browser is started and ready"""
    global _browser_driver, _browser_manager
    
    manager = _get_browser_manager(config)
    
    # Check if browser is already running and valid
    if _browser_driver is not None:
        try:
            # Try to get current URL to verify session is valid
            _browser_driver.current_url
            return _browser_driver
        except Exception:
            # Session is invalid, reset
            _browser_driver = None
            manager.driver = None
    
    # Start browser if not running
    headless = config.get('browser', 'headless') or False
    if headless:
        _browser_driver = manager.start_headless_browser()
    else:
        _browser_driver = manager.start_visible_browser()
    
    manager.driver = _browser_driver
    
    # Wait for page to load (reduced from 5 to 2 seconds for faster startup)
    time.sleep(config.get('browser', 'browser_load_wait_seconds') or 2)
    
    return _browser_driver


def _ensure_logged_in(config):
    """Ensure user is logged in, prompt for login if not"""
    global _browser_driver, _browser_manager
    
    manager = _get_browser_manager(config)
    
    if manager.check_login():
        return True
    
    # Not logged in - open visible browser for manual login
    logging.info("User not logged in. Opening visible browser for manual login...")
    
    # Close current browser if it exists
    if _browser_driver is not None:
        try:
            manager.close()
        except Exception:
            pass
        _browser_driver = None
    
    # Start visible browser for login
    manager.start_visible_browser()
    manager.driver.get(config.get('browser', 'perplexity_url'))
    
    print("[MANUAL LOGIN] Please log in to Perplexity.ai in the opened browser window.")
    print("[MANUAL LOGIN] Waiting for login to complete...")
    
    # Wait for login with timeout
    timeout_seconds = 600  # 10 minutes
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        if manager.check_login():
            print("[MANUAL LOGIN] Login successful!")
            # Update global driver reference
            _browser_driver = manager.driver
            return True
        time.sleep(2)
    
    raise Exception("Login timeout: Please log in manually and try again")


def ask_plexi(question, model=None, reasoning=None, config=None, debug=False, headless=None):
    """
    Ask a question to Perplexity.ai and return the response
    
    Args:
        question (str): The question to ask
        model (str, optional): Model to use (default: Claude Sonnet 4.5)
        reasoning (bool, optional): Enable reasoning mode (default: True)
        config: Configuration object. If None, loads from config.json
        debug (bool): Enable debug logging (default: False)
        headless (bool, optional): Override headless mode from config (default: None, uses config)
    
    Returns:
        str: The response text from Perplexity.ai
    """
    # Set logging level based on debug flag
    if debug:
        _logger.setLevel(logging.DEBUG)
        logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    else:
        _logger.setLevel(logging.INFO)
        logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    # Initialize timing tracking
    start_time = time.time()
    last_step_time = start_time
    
    def log_with_timing(message, level='info'):
        """Log message with time since last step in milliseconds"""
        nonlocal last_step_time
        current_time = time.time()
        elapsed_ms = int((current_time - last_step_time) * 1000)
        total_elapsed = int((current_time - start_time) * 1000)
        last_step_time = current_time
        
        if level == 'info':
            logging.info(f"[+{elapsed_ms}ms] {message}")
        elif level == 'debug':
            logging.debug(f"[+{elapsed_ms}ms] {message}")
        elif level == 'warning':
            logging.warning(f"[+{elapsed_ms}ms] {message}")
        elif level == 'error':
            logging.error(f"[+{elapsed_ms}ms] {message}")
    
    # Override headless mode if provided
    if headless is not None:
        if config is None:
            from .config import load_config
            config = load_config()
        config._config['browser']['headless'] = headless
    # Load config if not provided
    if config is None:
        from .config import load_config
        config = load_config()
    
    # Use defaults from config
    if model is None:
        model = config.get('perplexity', 'default_model') or "Claude Sonnet 4.5"
    if reasoning is None:
        reasoning = config.get('perplexity', 'default_reasoning')
        if reasoning is None:
            reasoning = True
    
    # Ensure browser is started
    log_with_timing("Starting browser...")
    driver = _ensure_browser_started(config)
    log_with_timing("✓ Browser started")
    
    # Ensure logged in
    log_with_timing("Checking login status...")
    _ensure_logged_in(config)
    log_with_timing("✓ Logged in")
    
    # Navigate to Perplexity.ai if not already there
    perplexity_url = config.get('browser', 'perplexity_url')
    if driver.current_url != perplexity_url and not perplexity_url.split('?')[0] in driver.current_url:
        log_with_timing("Navigating to Perplexity.ai...")
        driver.get(perplexity_url)
        log_with_timing("✓ Page loaded")
    
    element_wait_timeout = config.get('perplexity', 'element_wait_timeout') or 30
    wait = WebDriverWait(driver, element_wait_timeout)
    
    def _dump_html(label):
        """Helper to dump HTML for debugging"""
        try:
            import os
            from datetime import datetime
            debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug_dumps")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = os.path.join(debug_dir, f"{timestamp}_{label}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            logging.error(f"HTML dumped to: {html_path}")
        except Exception as e:
            logging.error(f"Failed to dump HTML: {e}")
    
    try:
        # Step 1: Wait for page to be ready and find question input
        if debug:
            logging.debug("Waiting for page to be ready...")
        
        # Wait for the input element to be present and ready (with timeout)
        input_timeout = 15  # seconds
        start_time = time.time()
        question_input = None
        
        while time.time() - start_time < input_timeout:
            try:
                question_input = driver.find_element(By.CSS_SELECTOR, "p[dir='auto']")
                if question_input and question_input.is_displayed():
                    # Wait for it to be interactable
                    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "p[dir='auto']")))
                    break
            except Exception:
                pass
            time.sleep(0.5)
        
        if not question_input:
            log_with_timing(f"Failed to find question input within {input_timeout} seconds", 'error')
            _dump_html("input_not_found")
            raise Exception("Question input element not found - HTML dumped for inspection")
        
        log_with_timing("✓ Page ready, question input found")
        
        # Click, focus, and enter text
        log_with_timing("Pasting question...")
        
        # Method 1: Direct JavaScript (works in headless)
        driver.execute_script("""
            var el = arguments[0];
            var text = arguments[1];
            el.focus();
            el.click();
            el.textContent = text;
            el.innerText = text;
            
            // Trigger all necessary events
            var events = ['input', 'change', 'keyup', 'keydown', 'keypress'];
            events.forEach(function(eventType) {
                var event = new Event(eventType, { bubbles: true, cancelable: true });
                el.dispatchEvent(event);
            });
        """, question_input, question)
        time.sleep(0.3)
        
        # Verify text was entered
        current_text = driver.execute_script("return arguments[0].textContent || arguments[0].innerText || '';", question_input)
        
        if debug:
            logging.debug(f"After JS method, text is: '{current_text}' (length: {len(current_text)})")
        
        if not current_text or len(current_text.strip()) < len(question) * 0.5:
            if debug:
                logging.debug("JS method didn't work, trying Selenium send_keys...")
            # Method 2: Selenium send_keys (works better in some cases)
            try:
                question_input.clear()
                question_input.send_keys(question)
                time.sleep(0.3)
                current_text = driver.execute_script("return arguments[0].textContent || arguments[0].innerText || '';", question_input)
                if debug:
                    logging.debug(f"After send_keys, text is: '{current_text}' (length: {len(current_text)})")
            except Exception as e:
                if debug:
                    logging.debug(f"send_keys failed: {e}")
        
        if not current_text or len(current_text.strip()) < len(question) * 0.5:
            if debug:
                logging.debug("Both methods failed, trying clipboard paste...")
            # Method 3: Clipboard paste (may not work in headless)
            try:
                pyperclip.copy(question)
                question_input.send_keys(Keys.CONTROL + "a")
                time.sleep(0.1)
                question_input.send_keys(Keys.DELETE)
                time.sleep(0.1)
                question_input.send_keys(Keys.CONTROL + "v")
                time.sleep(0.3)
                current_text = driver.execute_script("return arguments[0].textContent || arguments[0].innerText || '';", question_input)
                if debug:
                    logging.debug(f"After clipboard paste, text is: '{current_text}' (length: {len(current_text)})")
            except Exception as e:
                if debug:
                    logging.debug(f"Clipboard paste failed: {e}")
        
        # Final check
        if not current_text or len(current_text.strip()) < len(question) * 0.5:
            log_with_timing(f"Failed to enter text after all methods. Expected: '{question}', Got: '{current_text}'", 'error')
            _dump_html("text_input_failed")
            raise Exception("Failed to enter question text - HTML dumped for inspection")
        
        log_with_timing(f"✓ Question pasted: '{current_text[:50]}...'")
        
        # Step 2: Skip model selection for now (as requested)
        if debug:
            log_with_timing("Skipping model selection (disabled for testing)", 'debug')
        
        # Step 3: Toggle reasoning if needed (optional - may not always be available)
        if reasoning:
            try:
                log_with_timing("Enabling reasoning mode...")
                # Try multiple selectors for "With reasoning" toggle
                reasoning_selectors = [
                    "//div[contains(text(), 'With reasoning')]",
                    "//div[contains(., 'With reasoning')]",
                    "//button[contains(., 'With reasoning')]",
                ]
                reasoning_toggle = None
                for selector in reasoning_selectors:
                    try:
                        reasoning_toggle = driver.find_element(By.XPATH, selector)
                        if reasoning_toggle.is_displayed():
                            break
                    except Exception:
                        continue
                
                if reasoning_toggle:
                    # Check if it's already enabled
                    parent = reasoning_toggle.find_element(By.XPATH, "./..")
                    if "active" not in parent.get_attribute("class").lower() and \
                       "selected" not in parent.get_attribute("class").lower():
                        reasoning_toggle.click()
                        time.sleep(0.5)
                        log_with_timing("Reasoning mode enabled")
                else:
                    if debug:
                        log_with_timing("Reasoning toggle not found, skipping", 'debug')
            except Exception as e:
                if debug:
                    log_with_timing(f"Could not toggle reasoning (optional): {e}", 'debug')
        
        # Step 4: Submit the question (click GO button)
        log_with_timing("Looking for submit/GO button...")
        
        # Wait a moment for UI to update after text entry
        time.sleep(1)
        
        # Try multiple selectors for submit button (GO icon)
        submit_selectors = [
            "button[data-testid='submit-button']",
            "button[aria-label='Submit']",
            "button[type='submit']",
            "button svg[class*='send']",
            "button svg[class*='arrow']",
            "button:has(svg)",
        ]
        
        # Wait for submit button to be ready (should appear after text is entered)
        submit_timeout = 10
        start_time = time.time()
        submit_button = None
        
        while time.time() - start_time < submit_timeout:
            try:
                submit_button = driver.find_element(By.CSS_SELECTOR, "button[data-testid='submit-button'], button[aria-label='Submit']")
                if submit_button and submit_button.is_displayed():
                    break
            except Exception:
                pass
            time.sleep(0.3)
        
        if not submit_button:
            log_with_timing(f"Failed to find submit button within {submit_timeout} seconds", 'error')
            _dump_html("submit_button_not_found")
            raise Exception("Submit button not found - HTML dumped for inspection")
        
        log_with_timing("✓ Submit button found, hitting send button...")
        
        # Click immediately
        driver.execute_script("arguments[0].click();", submit_button)
        log_with_timing("✓ Question submitted")
        
        # Step 5: Wait for response to complete
        log_with_timing("Waiting for result...")
        # Harden timeout to 20 seconds max
        response_wait_timeout = 20
        
        # Wait for stop button to appear (indicates generation started)
        try:
            stop_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "button[data-testid='stop-generating-response-button']"
                ))
            )
            log_with_timing("Response generation started...")
        except TimeoutException:
            log_with_timing("Stop button not found, assuming response is generating...", 'warning')
            if debug:
                _dump_html("stop_button_not_found")
        
        # Wait for response to be ready - check for completion indicators
        # Completion is indicated by BOTH:
        # 1. Submit button with data-testid="submit-button" AND disabled="" attribute
        # 2. Copy button with aria-label="Copy" is available/clickable
        response_wait_start = time.time()
        last_check = response_wait_start
        last_debug_dump = response_wait_start
        response_content_found = False
        
        def _debug_element_state():
            """Collect detailed debug info about element states"""
            state = {
                'stop_button': {'found': False, 'visible': False},
                'submit_button': {'found': False, 'disabled': False, 'disabled_attr': None},
                'copy_button': {'found': False, 'visible': False},
                'current_url': driver.current_url,
                'page_title': driver.title,
            }
            
            # Check stop button
            try:
                stop_btn = driver.find_element(By.CSS_SELECTOR, "button[data-testid='stop-generating-response-button']")
                state['stop_button']['found'] = True
                state['stop_button']['visible'] = stop_btn.is_displayed()
            except NoSuchElementException:
                pass
            
            # Check submit button
            try:
                submit_btn = driver.find_element(By.CSS_SELECTOR, "button[data-testid='submit-button']")
                state['submit_button']['found'] = True
                disabled_attr = submit_btn.get_attribute("disabled")
                state['submit_button']['disabled_attr'] = disabled_attr
                state['submit_button']['disabled'] = (disabled_attr is not None and disabled_attr != "false")
                state['submit_button']['visible'] = submit_btn.is_displayed()
            except NoSuchElementException:
                pass
            
            # Check copy button
            try:
                copy_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Copy']")
                state['copy_button']['found'] = True
                state['copy_button']['visible'] = copy_btn.is_displayed()
            except NoSuchElementException:
                pass
            
            return state
        
        while time.time() - response_wait_start < response_wait_timeout:
            # Check if still generating (stop button visible)
            stop_button_visible = False
            try:
                stop_button = driver.find_element(
                    By.CSS_SELECTOR,
                    "button[data-testid='stop-generating-response-button']"
                )
                if stop_button.is_displayed():
                    stop_button_visible = True
            except NoSuchElementException:
                stop_button_visible = False
            
            # If stop button is gone, check for completion indicators
            if not stop_button_visible:
                # Check for BOTH completion indicators
                submit_button_disabled = False
                copy_button_available = False
                submit_button_found = False
                copy_button_found = False
                
                # Check 1: Submit button with disabled attribute
                try:
                    submit_button = driver.find_element(
                        By.CSS_SELECTOR,
                        "button[data-testid='submit-button']"
                    )
                    submit_button_found = True
                    disabled_attr = submit_button.get_attribute("disabled")
                    if disabled_attr is not None and disabled_attr != "false":
                        submit_button_disabled = True
                    if debug:
                        log_with_timing(f"Submit button found: disabled_attr='{disabled_attr}', is_displayed={submit_button.is_displayed()}", 'debug')
                except NoSuchElementException:
                    if debug:
                        log_with_timing("Submit button not found", 'debug')
                
                # Check 2: Copy button is available
                try:
                    copy_button = driver.find_element(
                        By.CSS_SELECTOR,
                        "button[aria-label='Copy']"
                    )
                    copy_button_found = True
                    if copy_button.is_displayed():
                        copy_button_available = True
                    if debug:
                        log_with_timing(f"Copy button found: is_displayed={copy_button.is_displayed()}", 'debug')
                except NoSuchElementException:
                    if debug:
                        log_with_timing("Copy button not found", 'debug')
                
                # Check 3: Markdown content has actual text (fallback for headless mode)
                markdown_content_available = False
                markdown_text_length = 0
                try:
                    # Try multiple selectors for markdown content
                    markdown_selectors = [
                        "div[id^='markdown-content']",
                        "div[id*='markdown-content']",
                        "div.markdown-content",
                        "[id*='markdown']"
                    ]
                    for selector in markdown_selectors:
                        try:
                            markdown_elem = driver.find_element(By.CSS_SELECTOR, selector)
                            markdown_text = markdown_elem.text.strip()
                            markdown_text_length = len(markdown_text)
                            if markdown_text_length >= 10:  # At least 10 characters
                                markdown_content_available = True
                                if debug:
                                    log_with_timing(f"Markdown content found via '{selector}': {markdown_text_length} chars", 'debug')
                                break
                        except NoSuchElementException:
                            continue
                    if not markdown_content_available and debug:
                        log_with_timing(f"Markdown content not found or empty (length: {markdown_text_length})", 'debug')
                except Exception as e:
                    if debug:
                        log_with_timing(f"Error checking markdown content: {e}", 'debug')
                
                # Completion conditions (in order of preference):
                # 1. Submit disabled + Copy button available (best indicator)
                # 2. Submit disabled + Markdown content available (fallback for headless)
                if submit_button_disabled and copy_button_available:
                    response_content_found = True
                    log_with_timing("Response generation complete! (submit disabled + copy button available)")
                    break
                elif submit_button_disabled and markdown_content_available:
                    response_content_found = True
                    log_with_timing(f"Response generation complete! (submit disabled + markdown content available, {markdown_text_length} chars)")
                    break
                elif debug:
                    log_with_timing(f"Completion check: submit_disabled={submit_button_disabled}, copy_available={copy_button_available}, markdown_available={markdown_content_available} ({markdown_text_length} chars)", 'debug')
            
            # Log detailed debug info every 5 seconds
            if time.time() - last_check > 5:
                elapsed = int(time.time() - response_wait_start)
                log_with_timing(f"Still waiting for result... ({elapsed}s elapsed)")
                
                # Collect and log detailed element state
                if debug:
                    state = _debug_element_state()
                    log_with_timing(f"Element state: stop_button={state['stop_button']}, submit_button={state['submit_button']}, copy_button={state['copy_button']}", 'debug')
                    log_with_timing(f"Page info: url={state['current_url']}, title={state['page_title']}", 'debug')
                
                last_check = time.time()
            
            # Dump HTML and screenshot every 10 seconds for debugging
            if time.time() - last_debug_dump > 10:
                elapsed = int(time.time() - response_wait_start)
                _dump_html(f"wait_loop_{elapsed}s")
                
                # Try to take screenshot (may not work in headless, but worth trying)
                try:
                    import os
                    from datetime import datetime
                    debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug_dumps")
                    os.makedirs(debug_dir, exist_ok=True)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_path = os.path.join(debug_dir, f"{timestamp}_wait_loop_{elapsed}s.png")
                    driver.save_screenshot(screenshot_path)
                    if debug:
                        log_with_timing(f"Screenshot saved to: {screenshot_path}", 'debug')
                except Exception as e:
                    if debug:
                        log_with_timing(f"Could not take screenshot: {e}", 'debug')
                
                last_debug_dump = time.time()
            
            time.sleep(0.5)  # Check every 0.5 seconds
        
        if not response_content_found:
            # Final debug dump on timeout
            log_with_timing("Timeout waiting for response completion indicators", 'error')
            final_state = _debug_element_state()
            log_with_timing(f"Final element state: {final_state}", 'error')
            _dump_html("timeout_final_state")
            
            # Try final screenshot
            try:
                import os
                from datetime import datetime
                debug_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug_dumps")
                os.makedirs(debug_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = os.path.join(debug_dir, f"{timestamp}_timeout_final.png")
                driver.save_screenshot(screenshot_path)
                log_with_timing(f"Final screenshot saved to: {screenshot_path}", 'error')
            except Exception as e:
                log_with_timing(f"Could not take final screenshot: {e}", 'error')
            
            raise TimeoutException("Timeout waiting for response completion indicators (20s max)")
        
        # Step 6: Extract response text using multiple methods
        log_with_timing("Response complete! Extracting response text...")
        
        # Store results from all methods for debugging
        extraction_results = {}
        response_text = None
        
        # Method 1: Navigator Clipboard API (new method, headless-compatible)
        try:
            copy_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "button[aria-label='Copy']"
                ))
            )
            copy_button.click()
            time.sleep(0.2)  # Brief wait for clipboard to update
            
            # Use Navigator Clipboard API
            clipboard_text = driver.execute_async_script("""
                var callback = arguments[arguments.length - 1];
                navigator.clipboard.readText().then(function(text) {
                    callback(text);
                }).catch(function(err) {
                    callback(null);
                });
            """)
            
            if clipboard_text and len(clipboard_text.strip()) >= 10:
                extraction_results['navigator_clipboard'] = {
                    'success': True,
                    'length': len(clipboard_text.strip()),
                    'preview': clipboard_text.strip()[:100]
                }
                if not response_text:
                    response_text = clipboard_text.strip()
                    log_with_timing("✓ Response retrieved via Navigator Clipboard API")
            else:
                extraction_results['navigator_clipboard'] = {
                    'success': False,
                    'error': 'Empty or invalid clipboard content'
                }
        except Exception as e:
            extraction_results['navigator_clipboard'] = {
                'success': False,
                'error': str(e)
            }
            if debug:
                log_with_timing(f"Navigator Clipboard API failed: {e}", 'debug')
        
        # Method 2: Extract directly from markdown-content element
        if not response_text or len(response_text.strip()) < 10:
            try:
                # Try to find markdown content with multiple selectors
                markdown_element = None
                selectors = [
                    "div[id^='markdown-content']",
                    "div[class*='markdown']",
                    "div[class*='prose']",
                ]
                for selector in selectors:
                    try:
                        markdown_element = driver.find_element(By.CSS_SELECTOR, selector)
                        if markdown_element:
                            break
                    except NoSuchElementException:
                        continue
                
                if markdown_element:
                    # Get text directly from markdown element
                    markdown_text = driver.execute_script(
                        "return arguments[0].textContent || arguments[0].innerText || '';",
                        markdown_element
                    )
                    
                    if markdown_text and len(markdown_text.strip()) >= 10:
                        extraction_results['markdown_content'] = {
                            'success': True,
                            'length': len(markdown_text.strip()),
                            'preview': markdown_text.strip()[:100]
                        }
                        if not response_text:
                            response_text = markdown_text.strip()
                            log_with_timing(f"✓ Response extracted from markdown-content (length: {len(markdown_text.strip())})")
                    else:
                        extraction_results['markdown_content'] = {
                            'success': False,
                            'error': 'Empty or invalid markdown content'
                        }
                else:
                    extraction_results['markdown_content'] = {
                        'success': False,
                        'error': 'Markdown element not found'
                    }
            except Exception as e:
                extraction_results['markdown_content'] = {
                    'success': False,
                    'error': str(e)
                }
                if debug:
                    log_with_timing(f"Markdown extraction failed: {e}", 'debug')
        
        # Method 3: Simple text extraction from body
        if not response_text or len(response_text.strip()) < 10:
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text
                # Split by lines and filter
                lines = body_text.split('\n')
                answer_lines = []
                skip_until_answer = True
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    # Skip navigation
                    if line in ["Home", "Discover", "Spaces", "Finance", "Account", "Upgrade", "Install"]:
                        continue
                    # Skip question
                    if question.lower() in line.lower():
                        skip_until_answer = False
                        continue
                    # Skip UI elements
                    if line in ["Answer", "Working…", "Ask a follow-up", "Copy", "Submit"]:
                        if line == "Answer":
                            skip_until_answer = False
                        continue
                    # Collect answer lines
                    if not skip_until_answer and line and len(line) > 5:
                        if "Ask a follow-up" in line:
                            break
                        answer_lines.append(line)
                
                if answer_lines:
                    body_extracted = '\n'.join(answer_lines).strip()
                    if len(body_extracted) > 20:
                        extraction_results['body_text'] = {
                            'success': True,
                            'length': len(body_extracted),
                            'preview': body_extracted[:100]
                        }
                        if not response_text:
                            response_text = body_extracted
                            log_with_timing(f"✓ Response extracted from body text (length: {len(body_extracted)})")
                    else:
                        extraction_results['body_text'] = {
                            'success': False,
                            'error': 'Extracted text too short'
                        }
                else:
                    extraction_results['body_text'] = {
                        'success': False,
                        'error': 'No answer lines found'
                    }
            except Exception as e:
                extraction_results['body_text'] = {
                    'success': False,
                    'error': str(e)
                }
                if debug:
                    log_with_timing(f"Body text extraction failed: {e}", 'debug')
        
        # Method 4: Old click-to-copy method (fallback using pyperclip)
        if not response_text or len(response_text.strip()) < 10:
            try:
                # Click copy button again (in case it wasn't clicked before)
                copy_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((
                        By.CSS_SELECTOR,
                        "button[aria-label='Copy']"
                    ))
                )
                copy_button.click()
                time.sleep(0.5)  # Wait for clipboard to update
                pyperclip_text = pyperclip.paste()
                
                if pyperclip_text and len(pyperclip_text.strip()) >= 10 and pyperclip_text.strip() != question.strip():
                    extraction_results['pyperclip'] = {
                        'success': True,
                        'length': len(pyperclip_text.strip()),
                        'preview': pyperclip_text.strip()[:100]
                    }
                    if not response_text:
                        response_text = pyperclip_text.strip()
                        log_with_timing("✓ Response retrieved via pyperclip (old method)")
                else:
                    extraction_results['pyperclip'] = {
                        'success': False,
                        'error': 'Empty, invalid, or question text in clipboard'
                    }
            except Exception as e:
                extraction_results['pyperclip'] = {
                    'success': False,
                    'error': str(e)
                }
                if debug:
                    log_with_timing(f"Pyperclip method failed: {e}", 'debug')
        
        # Log all extraction results for debugging
        if debug:
            log_with_timing("Extraction results summary:", 'debug')
            for method, result in extraction_results.items():
                if result['success']:
                    log_with_timing(f"  {method}: SUCCESS (length: {result['length']}, preview: {result['preview']}...)", 'debug')
                else:
                    log_with_timing(f"  {method}: FAILED ({result.get('error', 'unknown error')})", 'debug')
        
        if not response_text or len(response_text.strip()) < 10:
            log_with_timing("Failed to retrieve response text from any method", 'error')
            if debug:
                log_with_timing(f"All extraction results: {extraction_results}", 'debug')
            _dump_html("response_extraction_failed")
            raise Exception("Could not retrieve response text - HTML dumped for inspection")
        
        log_with_timing(f"✓ Response retrieved ({len(response_text)} characters)")
        return response_text.strip()
        
    except Exception as e:
        logging.error(f"Error in ask_plexi: {e}", exc_info=True)
        raise


def close_browser():
    """Close the browser instance"""
    global _browser_manager, _browser_driver
    if _browser_manager is not None:
        _browser_manager.close()
        _browser_manager = None
        _browser_driver = None

