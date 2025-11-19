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
    
    # Wait for page to load
    time.sleep(config.get('browser', 'browser_load_wait_seconds') or 5)
    
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
    logging.info("Starting browser...")
    driver = _ensure_browser_started(config)
    logging.info("✓ Browser started")
    
    # Ensure logged in
    logging.info("Checking login status...")
    _ensure_logged_in(config)
    logging.info("✓ Logged in")
    
    # Navigate to Perplexity.ai if not already there
    perplexity_url = config.get('browser', 'perplexity_url')
    if driver.current_url != perplexity_url and not perplexity_url.split('?')[0] in driver.current_url:
        logging.info("Navigating to Perplexity.ai...")
        driver.get(perplexity_url)
        logging.info("✓ Page loaded")
    
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
            logging.error(f"Failed to find question input within {input_timeout} seconds")
            _dump_html("input_not_found")
            raise Exception("Question input element not found - HTML dumped for inspection")
        
        logging.info("✓ Page ready, question input found")
        
        # Click, focus, and enter text
        logging.info("Pasting question...")
        
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
            logging.error(f"Failed to enter text after all methods. Expected: '{question}', Got: '{current_text}'")
            _dump_html("text_input_failed")
            raise Exception("Failed to enter question text - HTML dumped for inspection")
        
        logging.info(f"✓ Question pasted: '{current_text[:50]}...'")
        
        # Step 2: Skip model selection for now (as requested)
        logging.debug("Skipping model selection (disabled for testing)")
        
        # Step 3: Toggle reasoning if needed (optional - may not always be available)
        if reasoning:
            try:
                logging.info("Enabling reasoning mode...")
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
                        logging.info("Reasoning mode enabled")
                else:
                    logging.debug("Reasoning toggle not found, skipping")
            except Exception as e:
                logging.debug(f"Could not toggle reasoning (optional): {e}")
        
        # Step 4: Submit the question (click GO button)
        logging.info("Looking for submit/GO button...")
        
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
            logging.error(f"Failed to find submit button within {submit_timeout} seconds")
            _dump_html("submit_button_not_found")
            raise Exception("Submit button not found - HTML dumped for inspection")
        
        logging.info("✓ Submit button found, hitting send button...")
        
        # Click immediately
        driver.execute_script("arguments[0].click();", submit_button)
        logging.info("✓ Question submitted")
        
        # Step 5: Wait for response to complete
        logging.info("Waiting for result...")
        response_wait_timeout = config.get('perplexity', 'response_wait_timeout') or 300
        
        # Wait for stop button to disappear (indicates generation started)
        try:
            stop_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "button[data-testid='stop-generating-response-button']"
                ))
            )
            logging.info("Response generation started...")
        except TimeoutException:
            logging.warning("Stop button not found, assuming response is generating...")
        
        # Wait for stop button to disappear and "Ask a follow-up" to appear
        start_time = time.time()
        while time.time() - start_time < response_wait_timeout:
            try:
                # Check if stop button is gone
                stop_button = driver.find_element(
                    By.CSS_SELECTOR,
                    "button[data-testid='stop-generating-response-button']"
                )
                if not stop_button.is_displayed():
                    # Check for "Ask a follow-up" div
                    follow_up = driver.find_element(
                        By.XPATH,
                        "//div[contains(text(), 'Ask a follow-up')]"
                    )
                    if follow_up.is_displayed():
                        logging.info("Response generation complete!")
                        break
            except (NoSuchElementException, Exception):
                # Stop button not found - check for follow-up
                try:
                    follow_up = driver.find_element(
                        By.XPATH,
                        "//div[contains(text(), 'Ask a follow-up')]"
                    )
                    if follow_up.is_displayed():
                        logging.info("Response generation complete!")
                        break
                except Exception:
                    pass
            
            time.sleep(2)
        else:
            raise TimeoutException("Timeout waiting for response to complete")
        
        # Step 6: Extract response text from page (more reliable than clipboard in headless)
        logging.info("Response complete! Extracting response text...")
        
        response_text = None
        
        # Method 1: Try to find and click copy button, then get from clipboard
        try:
            copy_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "button[aria-label='Copy']"
                ))
            )
            copy_button.click()
            time.sleep(0.5)
            response_text = pyperclip.paste()
            if response_text and len(response_text.strip()) >= 10:
                logging.info("✓ Response retrieved from clipboard")
        except Exception as e:
            if debug:
                logging.debug(f"Copy button method failed: {e}")
        
        # Method 2: Extract directly from page using JavaScript (most reliable)
        if not response_text or len(response_text.strip()) < 10:
            logging.info("Extracting response from page...")
            try:
                # Use JavaScript to find the answer text more precisely
                response_text = driver.execute_script("""
                    // Find all text nodes and elements
                    function findAnswerText(question) {
                        // Find "Ask a follow-up" element first
                        const followUp = Array.from(document.querySelectorAll('*')).find(el => 
                            el.textContent && el.textContent.includes('Ask a follow-up')
                        );
                        
                        if (!followUp) return null;
                        
                        // Walk backwards from "Ask a follow-up" to find the answer
                        let current = followUp;
                        let answerParts = [];
                        const visited = new Set();
                        
                        // Look for the answer container - it should be before "Ask a follow-up"
                        for (let i = 0; i < 10; i++) {
                            current = current.previousElementSibling || current.parentElement;
                            if (!current || visited.has(current)) break;
                            visited.add(current);
                            
                            const text = current.textContent || '';
                            // Skip if it contains navigation or question
                            if (text.includes('Home') || text.includes('Discover') || 
                                text.includes('Account') || text.includes('Upgrade') ||
                                question.toLowerCase().includes(text.toLowerCase().substring(0, 20))) {
                                continue;
                            }
                            
                            // If this looks like answer content
                            if (text.length > 50 && !text.includes('Ask a follow-up') && 
                                !text.includes('Working…') && !text.includes('Answer')) {
                                answerParts.unshift(text.trim());
                            }
                        }
                        
                        // Also try finding by looking for the largest text block
                        if (answerParts.length === 0) {
                            const allDivs = Array.from(document.querySelectorAll('div, p, article'));
                            const candidates = [];
                            
                            for (const div of allDivs) {
                                const text = (div.textContent || '').trim();
                                if (text.length > 50 && text.length < 10000) {
                                    // Check if it's likely the answer
                                    if (!text.includes('Home') && !text.includes('Discover') &&
                                        !text.includes('Account') && !text.includes('Upgrade') &&
                                        !question.toLowerCase().includes(text.toLowerCase().substring(0, 30)) &&
                                        !text.includes('Ask a follow-up') && !text.includes('Working…')) {
                                        candidates.push({length: text.length, text: text});
                                    }
                                }
                            }
                            
                            if (candidates.length > 0) {
                                candidates.sort((a, b) => b.length - a.length);
                                return candidates[0].text;
                            }
                        }
                        
                        return answerParts.join('\\n').trim() || null;
                    }
                    
                    return findAnswerText(arguments[0]);
                """, question)
                
                if response_text and len(response_text.strip()) >= 10:
                    logging.info(f"✓ Response extracted via JavaScript (length: {len(response_text)})")
                else:
                    response_text = None
                    
            except Exception as e:
                if debug:
                    logging.debug(f"JavaScript extraction failed: {e}")
                response_text = None
            
            # Fallback: Simple text extraction from body
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
                        response_text = '\n'.join(answer_lines).strip()
                        if len(response_text) > 20:
                            logging.info(f"✓ Response extracted from body text (length: {len(response_text)})")
                except Exception as e:
                    if debug:
                        logging.debug(f"Body text extraction failed: {e}")
        
        if not response_text or len(response_text.strip()) < 10:
            logging.error("Failed to retrieve response text")
            _dump_html("response_extraction_failed")
            raise Exception("Could not retrieve response text - HTML dumped for inspection")
        
        logging.info(f"✓ Response retrieved ({len(response_text)} characters)")
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

