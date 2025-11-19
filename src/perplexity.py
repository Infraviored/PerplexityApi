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


def ask_plexi(question, model=None, reasoning=None, config=None, debug=False):
    """
    Ask a question to Perplexity.ai and return the response
    
    Args:
        question (str): The question to ask
        model (str, optional): Model to use (default: Claude Sonnet 4.5)
        reasoning (bool, optional): Enable reasoning mode (default: True)
        config: Configuration object. If None, loads from config.json
        debug (bool): Enable debug logging (default: False)
    
    Returns:
        str: The response text from Perplexity.ai
    """
    # Set logging level based on debug flag
    logger = logging.getLogger(__name__)
    if debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
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
    driver = _ensure_browser_started(config)
    
    # Ensure logged in
    _ensure_logged_in(config)
    
    # Navigate to Perplexity.ai if not already there
    perplexity_url = config.get('browser', 'perplexity_url')
    if driver.current_url != perplexity_url and not perplexity_url.split('?')[0] in driver.current_url:
        driver.get(perplexity_url)
    
    element_wait_timeout = config.get('perplexity', 'element_wait_timeout') or 30
    wait = WebDriverWait(driver, element_wait_timeout)
    
    try:
        # Step 1: Wait for page to be ready and find question input
        if debug:
            logging.debug("Waiting for page to be ready...")
        # Wait for the input element to be present and ready
        question_input = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "p[dir='auto']"
            ))
        )
        # Wait for it to be visible and interactable
        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "p[dir='auto']")))
        
        if debug:
            logging.debug("✓ Page ready, question input found")
        
        # Click, focus, and paste immediately
        if debug:
            logging.debug("Clicking and focusing input...")
        driver.execute_script("arguments[0].click(); arguments[0].focus();", question_input)
        
        # Clear and paste using clipboard (fastest method)
        pyperclip.copy(question)
        question_input.send_keys(Keys.CONTROL + "a" + Keys.DELETE)
        question_input.send_keys(Keys.CONTROL + "v")
        
        if debug:
            # Verify text was entered
            current_text = driver.execute_script("return arguments[0].textContent || arguments[0].innerText;", question_input)
            logging.debug(f"Text entered: '{current_text[:50]}...' (length: {len(current_text)})")
        
        logging.info(f"Question entered: {question[:50]}...")
        
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
        submit_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-testid='submit-button'], button[aria-label='Submit']"))
        )
        
        if debug:
            logging.debug("✓ Submit button found, clicking...")
        
        # Click immediately
        driver.execute_script("arguments[0].click();", submit_button)
        logging.info("Question submitted")
        
        # Step 5: Wait for response to complete
        logging.info("Waiting for response...")
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
        
        # Step 6: Find and click copy button
        logging.info("Copying response to clipboard...")
        # Find copy button in the response area
        copy_button = wait.until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "button[aria-label='Copy']"
            ))
        )
        copy_button.click()
        time.sleep(1)
        
        # Step 7: Get response from clipboard
        response_text = pyperclip.paste()
        
        # Also try to extract from page if clipboard is empty
        if not response_text or len(response_text.strip()) < 10:
            logging.warning("Clipboard appears empty, trying to extract from page...")
            # Try to find the response text in the page
            try:
                # Look for the main response content
                response_elements = driver.find_elements(
                    By.CSS_SELECTOR,
                    "div[class*='prose'], div[class*='markdown'], article"
                )
                if response_elements:
                    response_text = response_elements[-1].text
            except Exception as e:
                logging.warning(f"Could not extract response from page: {e}")
        
        if not response_text or len(response_text.strip()) < 10:
            raise Exception("Could not retrieve response text")
        
        logging.info(f"Response retrieved ({len(response_text)} characters)")
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

