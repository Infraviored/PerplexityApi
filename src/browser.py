"""
Browser management for Perplexity.ai Automation
"""
import os
import time
import logging
import glob
import shutil
import tempfile
import subprocess
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import InvalidSessionIdException


def detect_chrome_binary_and_major():
    """
    Detect Chrome binary path and major version.
    
    Returns:
        Tuple of (binary_path, major_version)
    """
    candidates = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]
    binary = next((p for p in candidates if shutil.which(p)), None)
    major = None
    try:
        cmd = binary or "google-chrome"
        out = subprocess.check_output([cmd, "--version"], text=True).strip()
        for token in out.split():
            if token and token[0].isdigit():
                major = int(token.split(".")[0])
                break
    except Exception:
        pass
    return binary, major


class BrowserManager:
    """Manages browser interactions for Perplexity.ai automation"""
    
    def __init__(self, config):
        """
        Initialize the browser manager
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.driver = None
        self._ephemeral_dir = None
        
    def start_headless_browser(self, use_ephemeral: bool = False):
        """
        Start a headless Chromium/Chrome browser and navigate to Perplexity.ai
        
        Returns:
            webdriver: Undetected Chrome WebDriver instance
        """
        return self._start_browser(headless=True, use_ephemeral=use_ephemeral)
    
    def start_visible_browser(self, use_ephemeral: bool = False):
        """
        Start a visible Chromium/Chrome browser (non-headless) and navigate to Perplexity.ai.

        Primarily used for manual login flows so the user can complete authentication.
        """
        return self._start_browser(headless=False, use_ephemeral=use_ephemeral)
    
    def _start_browser(self, headless: bool = True, use_ephemeral: bool = False):
        """Shared browser launch routine using undetected_chromedriver."""
        perplexity_url = self.config.get('browser', 'perplexity_url')
        
        if use_ephemeral:
            user_data_dir = tempfile.mkdtemp(prefix="perplexity-ephemeral-")
            self._ephemeral_dir = user_data_dir
        else:
            user_data_dir = os.path.expanduser(self.config.get('browser', 'user_data_dir'))
            os.makedirs(user_data_dir, exist_ok=True)

        chrome_binary, major = detect_chrome_binary_and_major()
        
        # Configure Chrome options
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        
        # Disable password manager and save password prompts
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
        }
        options.add_experimental_option("prefs", prefs)
        
        # Build driver kwargs
        uc_kwargs = {
            "use_subprocess": False,
            "headless": headless,
            "options": options,
        }
        if major:
            uc_kwargs["version_main"] = major
        if chrome_binary:
            uc_kwargs["browser_executable_path"] = chrome_binary

        def _launch():
            try:
                self.driver = uc.Chrome(**uc_kwargs)
                self.driver.get(perplexity_url)
                mode = "Headless" if headless else "Visible"
                logging.info("%s Chromium/Chrome started and navigated to Perplexity.ai", mode)
                
                # Wait a bit and check for Cloudflare
                time.sleep(3)
                if self._check_cloudflare_challenge():
                    logging.info("Cloudflare challenge detected, attempting bypass...")
                    self._bypass_cloudflare()
                
                return self.driver
            except Exception as e:
                message = str(e).lower()
                if "user data directory is already in use" in message and not use_ephemeral:
                    logging.warning("User data dir appears locked/in use. Attempting to clear stale Chromium 'Singleton*' locks and retry...")
                    self._clear_profile_singleton_locks(user_data_dir)
                    time.sleep(1)
                    return _launch()
                raise

        return _launch()
    
    def _check_cloudflare_challenge(self) -> bool:
        """Check if Cloudflare challenge is present."""
        if self.driver is None:
            return False
        
        try:
            # Check for Cloudflare challenge indicators
            page_source = self.driver.page_source.lower()
            if "just a moment" in page_source or "cloudflare" in page_source:
                # Also check for specific Cloudflare elements
                if self.driver.find_elements(By.XPATH, "//title[contains(text(), 'Just a moment')]"):
                    return True
                if self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Before continuing, we need to be sure you are human')]"):
                    return True
        except Exception:
            pass
        
        return False
    
    def _bypass_cloudflare(self, timeout: int = 120) -> bool:
        """
        Bypass Cloudflare Turnstile challenge by trying CDP clicks at multiple viewport positions.
        
        Returns True if bypassed, False otherwise
        """
        if self.driver is None:
            return False
        
        logging.info("⏳ Attempting Cloudflare Turnstile bypass...")
        time.sleep(5)  # Wait for widget to fully load
        
        # Get viewport center
        try:
            viewport_width = self.driver.execute_script("return window.innerWidth;")
            viewport_height = self.driver.execute_script("return window.innerHeight;")
            cx = viewport_width / 2
            cy = viewport_height / 2
        except Exception:
            return False
        
        # Check if already bypassed
        def success_check():
            try:
                return not self._check_cloudflare_challenge()
            except Exception:
                return False
        
        if success_check():
            logging.info("✓ Turnstile already bypassed!")
            return True
        
        # Try clicks at multiple vertical offsets from center
        offsets_percent = [0.02, 0.04, 0.06, 0.08, 0.10]
        
        for offset_pct in offsets_percent:
            if success_check():
                logging.info("✓ Turnstile bypassed!")
                return True
            
            click_y = cy + (viewport_height * offset_pct)
            logging.info(f"🖱️  Clicking at offset {offset_pct*100:.0f}%: ({cx:.0f}, {click_y:.0f})")
            
            # CDP click
            try:
                self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                    "type": "mouseMoved",
                    "x": float(cx),
                    "y": float(click_y)
                })
                self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                    "type": "mousePressed",
                    "x": float(cx),
                    "y": float(click_y),
                    "button": "left",
                    "buttons": 1,
                    "clickCount": 1
                })
                self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                    "type": "mouseReleased",
                    "x": float(cx),
                    "y": float(click_y),
                    "button": "left",
                    "buttons": 1,
                    "clickCount": 1
                })
                logging.info("✓ Click executed")
            except Exception:
                pass
            
            # Wait and check if success
            for check in range(3):
                if success_check():
                    logging.info(f"✓ Turnstile bypassed at {offset_pct*100:.0f}% offset!")
                    return True
                time.sleep(0.5)
        
        # Auto-clicks didn't work - wait for manual intervention
        logging.info("⚠️ Auto-clicks didn't work - please click Turnstile manually...")
        
        timeout_manual = time.time() + timeout
        while time.time() < timeout_manual:
            if success_check():
                logging.info("✓ Turnstile bypassed (manual click)!")
                return True
            time.sleep(0.5)
        
        return False
        
    def check_login(self):
        """
        Check if the user is logged in to Perplexity.ai
        
        Returns:
            bool: True if logged in, False otherwise
        """
        if self.driver is None:
            logging.error("Cannot check login: Browser not started")
            return False

        logging.debug("Checking login status...")
        
        # Check for login by looking for "Account" div (indicates logged in)
        # If not logged in, there's a "Sign In" button instead
        
        # Try multiple XPath patterns for Account
        account_xpaths = [
            "//div[contains(@class, 'gap-xs') and contains(text(), 'Account')]",
            "//div[contains(text(), 'Account')]",
            "//div[@class='gap-xs group flex w-full cursor-pointer flex-col items-center']//div[contains(text(), 'Account')]",
        ]
        
        for xpath in account_xpaths:
            try:
                logging.debug(f"Trying Account XPath: {xpath}")
                account_div = WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.XPATH, xpath))
                )
                if account_div:
                    is_displayed = account_div.is_displayed()
                    text = account_div.text
                    logging.debug(f"Found Account element: displayed={is_displayed}, text='{text}'")
                    if is_displayed:
                        logging.info("User is logged in to Perplexity.ai (Account div found)")
                        return True
            except Exception as e:
                logging.debug(f"Account XPath '{xpath}' failed: {type(e).__name__}")
                continue

        # Check for "Sign In" button - this indicates NOT logged in
        sign_in_xpaths = [
            "//div[contains(text(), 'Sign In')]",
            "//button[contains(text(), 'Sign In')]",
        ]
        
        for xpath in sign_in_xpaths:
            try:
                logging.debug(f"Trying Sign In XPath: {xpath}")
                sign_in_button = self.driver.find_element(By.XPATH, xpath)
                if sign_in_button:
                    is_displayed = sign_in_button.is_displayed()
                    text = sign_in_button.text
                    logging.debug(f"Found Sign In element: displayed={is_displayed}, text='{text}'")
                    if is_displayed:
                        logging.info("User is not logged in to Perplexity.ai (Sign In button found)")
                        return False
            except Exception as e:
                logging.debug(f"Sign In XPath '{xpath}' failed: {type(e).__name__}")
                continue

        # Try to find any text containing "Account" in the page
        try:
            logging.debug("Searching page source for 'Account' text...")
            page_source = self.driver.page_source
            if "Account" in page_source:
                logging.debug("Found 'Account' in page source, but element not found via XPath")
                # Try to find all divs with Account text
                all_account_divs = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Account')]")
                logging.debug(f"Found {len(all_account_divs)} elements containing 'Account' text")
                for idx, div in enumerate(all_account_divs):
                    try:
                        logging.debug(f"  Element {idx}: tag={div.tag_name}, displayed={div.is_displayed()}, text='{div.text[:50]}'")
                        if div.is_displayed() and "Account" in div.text:
                            logging.info("User is logged in to Perplexity.ai (Account text found in visible element)")
                            return True
                    except Exception:
                        pass
        except Exception as e:
            logging.debug(f"Page source search failed: {type(e).__name__}")

        # If neither found, assume not logged in
        logging.warning("Could not determine login status, assuming not logged in")
        return False

    def refresh_page(self):
        """
        Refresh the Perplexity.ai page
        
        Returns:
            bool: True if successful, False otherwise
        """
        if self.driver is None:
            logging.error("Cannot refresh page: Browser not started")
            return False
            
        try:
            self.driver.refresh()
            time.sleep(2)  # Give page time to reload
            
            # Check for Cloudflare after refresh
            if self._check_cloudflare_challenge():
                logging.info("Cloudflare challenge detected after refresh, attempting bypass...")
                self._bypass_cloudflare()
            
            return True
        except InvalidSessionIdException:
            logging.error("Selenium session became invalid while refreshing; restarting browser...")
            self._restart_browser()
            return True
        except Exception as e:
            logging.error(f"Failed to refresh page: {e}")
            return False
            
    def close(self):
        """Close the browser"""
        if self.driver is not None:
            try:
                self.driver.quit()
                self.driver = None
                logging.info("Browser closed")
            except Exception as e:
                logging.error(f"Failed to close browser: {e}")
        # Cleanup ephemeral profile if used
        if self._ephemeral_dir:
            try:
                shutil.rmtree(self._ephemeral_dir, ignore_errors=True)
            except Exception:
                pass
            self._ephemeral_dir = None
                
    def _restart_browser(self):
        """Restart Chromium/Chrome, preserving config."""
        try:
            self.close()
        finally:
            headless = self.config.get('browser', 'headless') or False
            if headless:
                self.start_headless_browser()
            else:
                self.start_visible_browser()
            time.sleep(self.config.get('browser', 'browser_load_wait_seconds') or 5)

    def _clear_profile_singleton_locks(self, user_data_dir):
        """Remove Chromium/Edge 'Singleton*' lock files in the given profile dir.

        This mitigates cases where a previous crash left stale locks preventing new sessions.
        """
        try:
            patterns = [
                os.path.join(user_data_dir, "Singleton*"),
            ]
            removed = 0
            for pattern in patterns:
                for path in glob.glob(pattern):
                    try:
                        os.remove(path)
                        removed += 1
                    except Exception:
                        pass
            if removed:
                logging.info(f"Removed {removed} stale 'Singleton*' lock files from profile dir {user_data_dir}")
        except Exception as e:
            logging.warning(f"Failed to clear profile locks in {user_data_dir}: {e}")
