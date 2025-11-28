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
import signal
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
        self.vdisplay = None
        
    def start_headless_browser(self, use_ephemeral: bool = False):
        """
        Start a headless Chromium/Chrome browser and navigate to Perplexity.ai
        
        Returns:
            webdriver: Undetected Chrome WebDriver instance
        """
        # Check if Xvfb is enabled
        use_xvfb = self.config.get('browser', 'use_xvfb') or False
        if use_xvfb:
            return self._start_browser_with_xvfb(use_ephemeral=use_ephemeral)
        return self._start_browser(headless=True, use_ephemeral=use_ephemeral)
    
    def start_visible_browser(self, use_ephemeral: bool = False):
        """
        Start a visible Chromium/Chrome browser (non-headless) and navigate to Perplexity.ai.

        Primarily used for manual login flows so the user can complete authentication.
        """
        return self._start_browser(headless=False, use_ephemeral=use_ephemeral)
    
    def _start_browser_with_xvfb(self, use_ephemeral: bool = False):
        """Start browser in headed mode using Xvfb virtual display"""
        try:
            from xvfbwrapper import Xvfb
        except ImportError:
            logging.error("xvfbwrapper not installed. Install with: pip install xvfbwrapper")
            logging.warning("Falling back to regular headless mode")
            return self._start_browser(headless=True, use_ephemeral=use_ephemeral)
        
        # Start virtual display
        try:
            self.vdisplay = Xvfb(width=1920, height=1080)
            self.vdisplay.start()
            logging.info("Started Xvfb virtual display")
        except Exception as e:
            logging.error(f"Failed to start Xvfb: {e}")
            logging.warning("Falling back to regular headless mode")
            return self._start_browser(headless=True, use_ephemeral=use_ephemeral)
        
        try:
            # Use headed mode (headless=False) but it runs on virtual display
            driver = self._start_browser(headless=False, use_ephemeral=use_ephemeral)
            return driver
        except Exception as e:
            # Clean up virtual display on error
            if self.vdisplay is not None:
                try:
                    self.vdisplay.stop()
                    self.vdisplay = None
                except Exception:
                    pass
            raise e
    
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
        
        # Use --headless=new instead of headless parameter for better stealth
        # This makes headless Chrome work exactly like regular Chrome with same backend code
        if headless:
            options.add_argument("--headless=new")
            # Set realistic window size
            options.add_argument("--window-size=1920,1080")
        
        # Disable password manager and save password prompts
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
        }
        options.add_experimental_option("prefs", prefs)
        
        # Build driver kwargs
        # Note: We use --headless=new flag in options for better stealth
        # The headless parameter still needs to be set correctly for undetected-chromedriver
        uc_kwargs = {
            "use_subprocess": False,
            "headless": headless,  # This is still needed for undetected-chromedriver
            "options": options,    # --headless=new flag in options makes it more realistic
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
                
                # DON'T use CDP in headless mode - it's detectable
                # Only use CDP in visible mode (restore original behavior that worked)
                if not headless:
                    try:
                        # Comprehensive anti-detection script injection via CDP (visible mode only)
                        # Original approach: inject after navigation (this worked before)
                        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                            'source': '''
                                // Override navigator.webdriver (critical for detection)
                                Object.defineProperty(navigator, 'webdriver', {
                                    get: () => undefined
                                });
                                
                                // Override chrome runtime (make it look like real Chrome)
                                if (!window.chrome) {
                                    window.chrome = {};
                                }
                                if (!window.chrome.runtime) {
                                    window.chrome.runtime = {};
                                }
                                
                                // WebGL fingerprinting fix - make it look like real hardware
                                const getParameter = WebGLRenderingContext.prototype.getParameter;
                                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                                    if (parameter === 37445) return 'Intel Inc.';  // UNMASKED_VENDOR_WEBGL
                                    if (parameter === 37446) return 'Intel Iris OpenGL Engine';  // UNMASKED_RENDERER_WEBGL
                                    return getParameter.call(this, parameter);
                                };
                                
                                // Also fix WebGL2
                                if (typeof WebGL2RenderingContext !== 'undefined') {
                                    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
                                    WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                                        if (parameter === 37445) return 'Intel Inc.';
                                        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                                        return getParameter2.call(this, parameter);
                                    };
                                }
                                
                                // Fix plugins array
                                Object.defineProperty(navigator, 'plugins', {
                                    get: () => [1, 2, 3, 4, 5]
                                });
                                
                                // Fix languages
                                Object.defineProperty(navigator, 'languages', {
                                    get: () => ['en-US', 'en']
                                });
                                
                                // Override permissions API
                                const originalQuery = window.navigator.permissions.query;
                                window.navigator.permissions.query = (parameters) => (
                                    parameters.name === 'notifications' ?
                                        Promise.resolve({ state: Notification.permission }) :
                                        originalQuery(parameters)
                                );
                                
                                // Remove automation indicators
                                delete navigator.__proto__.webdriver;
                            '''
                        })
                        logging.debug("Anti-detection scripts injected via CDP (visible mode)")
                    except Exception as e:
                        logging.debug(f"Could not inject anti-detection scripts via CDP: {e}")
                
                # Grant clipboard permissions
                if not headless:
                    # Use CDP in visible mode (preferred)
                    try:
                        self.driver.execute_cdp_cmd('Browser.grantPermissions', {
                            'origin': perplexity_url.split('?')[0],
                            'permissions': ['clipboardReadWrite', 'clipboardSanitizedWrite']
                        })
                    except Exception:
                        try:
                            self.driver.set_permissions("clipboard-read", "granted")
                            self.driver.set_permissions("clipboard-write", "granted")
                        except Exception as e:
                            logging.debug(f"Could not set clipboard permissions: {e}")
                else:
                    # In headless mode, use execute_script instead of CDP
                    try:
                        self.driver.execute_script("""
                            navigator.permissions.query = (parameters) => {
                                if (parameters.name === 'clipboard-read' || parameters.name === 'clipboard-write') {
                                    return Promise.resolve({ state: 'granted' });
                                }
                                return Promise.resolve({ state: 'prompt' });
                            };
                        """)
                    except Exception as e:
                        logging.debug(f"Permission override failed in headless: {e}")
                
                # Inject stealth scripts AFTER page load in headless mode only (no CDP)
                # Visible mode uses CDP above (original working approach)
                if headless:
                    self._inject_stealth_scripts_post_load()
                    self._add_realistic_navigator_properties()
                    # Skip human behavior on initial load - it can interfere
                
                # Wait a bit and check for Cloudflare (reduced from 3 to 1 second for faster startup)
                time.sleep(1)
                if self._check_cloudflare_challenge():
                    logging.info("Cloudflare challenge detected, attempting bypass...")
                    self._bypass_cloudflare()
                
                return self.driver
            except Exception as e:
                message = str(e).lower()
                lock_related_error = "user data directory is already in use" in message
                chrome_unreachable_error = "cannot connect to chrome" in message or "chrome not reachable" in message
                if (lock_related_error or chrome_unreachable_error) and not use_ephemeral:
                    logging.warning("Chrome launch failed (%s). Forcing profile cleanup and retrying...", message.splitlines()[0])
                    self._kill_profile_chrome_processes(user_data_dir)
                    self._clear_profile_singleton_locks(user_data_dir)
                    time.sleep(1)
                    return _launch()
                raise

        return _launch()
    
    def _inject_stealth_scripts_post_load(self):
        """Inject anti-detection scripts AFTER page load without CDP (for headless mode)"""
        if self.driver is None:
            return
        
        try:
            self.driver.execute_script("""
                // Override navigator.webdriver (critical for detection)
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Override chrome runtime (make it look like real Chrome)
                if (!window.chrome) {
                    window.chrome = {};
                }
                if (!window.chrome.runtime) {
                    window.chrome.runtime = {};
                }
                
                // WebGL fingerprinting fix - make it look like real hardware
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';  // UNMASKED_VENDOR_WEBGL
                    if (parameter === 37446) return 'Intel Iris OpenGL Engine';  // UNMASKED_RENDERER_WEBGL
                    return getParameter.call(this, parameter);
                };
                
                // Also fix WebGL2
                if (typeof WebGL2RenderingContext !== 'undefined') {
                    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
                    WebGL2RenderingContext.prototype.getParameter = function(parameter) {
                        if (parameter === 37445) return 'Intel Inc.';
                        if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                        return getParameter2.call(this, parameter);
                    };
                }
                
                // Fix plugins array
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Fix languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                // Override permissions API
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Remove automation indicators
                delete navigator.__proto__.webdriver;
            """)
            logging.debug("Anti-detection scripts injected via execute_script (headless mode)")
        except Exception as e:
            logging.debug(f"Script injection failed in headless mode: {e}")
    
    def _add_realistic_navigator_properties(self):
        """Add realistic navigator and screen properties for headless mode"""
        if self.driver is None:
            return
        
        try:
            self.driver.execute_script("""
                // Set realistic navigator properties
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Linux x86_64'
                });
                
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8
                });
                
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8
                });
                
                Object.defineProperty(navigator, 'maxTouchPoints', {
                    get: () => 0
                });
                
                // Add realistic screen properties
                Object.defineProperty(screen, 'width', {
                    get: () => 1920
                });
                
                Object.defineProperty(screen, 'height', {
                    get: () => 1080
                });
                
                Object.defineProperty(screen, 'availWidth', {
                    get: () => 1920
                });
                
                Object.defineProperty(screen, 'availHeight', {
                    get: () => 1080
                });
                
                // Override notification permission
                Object.defineProperty(Notification, 'permission', {
                    get: () => 'default'
                });
            """)
            logging.debug("Realistic navigator properties added")
        except Exception as e:
            logging.debug(f"Failed to add realistic navigator properties: {e}")
    
    def _add_human_behavior(self):
        """Add random delays and mouse movements to appear more human"""
        if self.driver is None:
            return
        
        try:
            import random
            from selenium.webdriver.common.action_chains import ActionChains
            
            # Random mouse movement
            actions = ActionChains(self.driver)
            for _ in range(random.randint(2, 5)):
                x = random.randint(100, 800)
                y = random.randint(100, 600)
                actions.move_by_offset(x, y)
            actions.perform()
            
            # Random delay
            time.sleep(random.uniform(0.5, 2.0))
            logging.debug("Human behavior simulation added")
        except Exception as e:
            logging.debug(f"Human behavior simulation failed: {e}")
    
    def _debug_navigator_properties(self):
        """Debug: Print all navigator properties for comparison between modes"""
        if self.driver is None:
            return
        
        try:
            props = self.driver.execute_script("""
                return {
                    webdriver: navigator.webdriver,
                    platform: navigator.platform,
                    userAgent: navigator.userAgent,
                    hardwareConcurrency: navigator.hardwareConcurrency,
                    deviceMemory: navigator.deviceMemory,
                    languages: navigator.languages,
                    plugins: navigator.plugins.length,
                    maxTouchPoints: navigator.maxTouchPoints,
                    vendor: navigator.vendor,
                    vendorSub: navigator.vendorSub,
                    productSub: navigator.productSub,
                    screenWidth: screen.width,
                    screenHeight: screen.height,
                    availWidth: screen.availWidth,
                    availHeight: screen.availHeight,
                    colorDepth: screen.colorDepth,
                    pixelDepth: screen.pixelDepth,
                    hasChrome: typeof window.chrome !== 'undefined',
                    permissions: typeof navigator.permissions !== 'undefined'
                };
            """)
            
            logging.info("Navigator properties:")
            for key, value in props.items():
                logging.info(f"  {key}: {value}")
        except Exception as e:
            logging.debug(f"Failed to debug navigator properties: {e}")
    
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
        Bypass Cloudflare Turnstile challenge.
        Uses CDP clicks in visible mode (where it works), ActionChains as fallback.
        In visible mode, records manual click coordinates for future use.
        
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
        
        headless = self.config.get('browser', 'headless') or False
        
        # Try ActionChains first (works in both modes, more realistic)
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            
            # Wait for iframe
            iframe = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='challenges.cloudflare.com']"))
            )
            
            # Switch to iframe
            self.driver.switch_to.frame(iframe)
            
            # Find and click the checkbox
            checkbox = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='checkbox']"))
            )
            
            # Use ActionChains for more realistic clicking
            actions = ActionChains(self.driver)
            actions.move_to_element(checkbox).pause(0.5).click().perform()
            
            # Switch back
            self.driver.switch_to.default_content()
            
            time.sleep(3)
            if success_check():
                logging.info("✓ Turnstile bypassed with ActionChains!")
                return True
        except Exception as e:
            logging.debug(f"ActionChains click failed: {e}")
            # Make sure we're back to default content
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass
        
        # Fallback: Use CDP clicks (only in visible mode where it works)
        if not headless:
            # Check if we have saved click coordinates
            saved_coords = self._load_saved_click_coords()
            if saved_coords:
                logging.info(f"Using saved click coordinates: ({saved_coords['x']}, {saved_coords['y']})")
                try:
                    self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                        "type": "mouseMoved",
                        "x": float(saved_coords['x']),
                        "y": float(saved_coords['y'])
                    })
                    self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                        "type": "mousePressed",
                        "x": float(saved_coords['x']),
                        "y": float(saved_coords['y']),
                        "button": "left",
                        "buttons": 1,
                        "clickCount": 1
                    })
                    self.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                        "type": "mouseReleased",
                        "x": float(saved_coords['x']),
                        "y": float(saved_coords['y']),
                        "button": "left",
                        "buttons": 1,
                        "clickCount": 1
                    })
                    time.sleep(2)
                    if success_check():
                        logging.info("✓ Turnstile bypassed using saved coordinates!")
                        return True
                except Exception as e:
                    logging.debug(f"Saved coordinates failed: {e}")
            
            # Try clicks at multiple vertical offsets from center (original approach)
            offsets_percent = [0.02, 0.04, 0.06, 0.08, 0.10]
            
            for offset_pct in offsets_percent:
                if success_check():
                    logging.info("✓ Turnstile bypassed!")
                    return True
                
                click_y = cy + (viewport_height * offset_pct)
                logging.info(f"🖱️  Clicking at offset {offset_pct*100:.0f}%: ({cx:.0f}, {click_y:.0f})")
                
                # CDP click (only in visible mode)
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
        
        # If automated click fails, check if we're in visible mode for manual intervention
        headless = self.config.get('browser', 'headless') or False
        if not headless:
            logging.info("⚠️ Auto-clicks didn't work - please click Turnstile manually...")
            logging.info("📝 Recording your click coordinates for future headless use...")
            
            # Inject comprehensive JavaScript to record clicks (including iframe clicks)
            self.driver.execute_script("""
                // Initialize click tracking
                window._lastClickX = null;
                window._lastClickY = null;
                window._clickRecorded = false;
                
                // Record click function
                window._recordClick = function(x, y) {
                    window._lastClickX = x;
                    window._lastClickY = y;
                    window._clickRecorded = true;
                    console.log('Click recorded at:', x, y);
                };
                
                // Capture clicks on document (including iframes)
                function captureClick(e) {
                    // Get page coordinates (not just viewport)
                    var x = e.pageX || (e.clientX + window.scrollX);
                    var y = e.pageY || (e.clientY + window.scrollY);
                    window._recordClick(x, y);
                }
                
                // Add listeners to document and all iframes
                document.addEventListener('click', captureClick, true);
                document.addEventListener('mousedown', captureClick, true);
                
                // Also try to capture clicks in iframes
                var iframes = document.querySelectorAll('iframe');
                iframes.forEach(function(iframe) {
                    try {
                        iframe.contentWindow.addEventListener('click', function(e) {
                            var rect = iframe.getBoundingClientRect();
                            var x = rect.left + e.clientX + window.scrollX;
                            var y = rect.top + e.clientY + window.scrollY;
                            window._recordClick(x, y);
                        }, true);
                    } catch(e) {
                        // Cross-origin iframe, can't access
                    }
                });
                
                // Monitor for new iframes
                var observer = new MutationObserver(function(mutations) {
                    var iframes = document.querySelectorAll('iframe');
                    iframes.forEach(function(iframe) {
                        try {
                            iframe.contentWindow.addEventListener('click', function(e) {
                                var rect = iframe.getBoundingClientRect();
                                var x = rect.left + e.clientX + window.scrollX;
                                var y = rect.top + e.clientY + window.scrollY;
                                window._recordClick(x, y);
                            }, true);
                        } catch(e) {
                            // Cross-origin iframe, can't access
                        }
                    });
                });
                observer.observe(document.body, { childList: true, subtree: true });
            """)
            
            timeout_manual = time.time() + timeout
            last_click_check = time.time()
            while time.time() < timeout_manual:
                # Check for recorded clicks periodically (not just after success)
                if time.time() - last_click_check > 0.5:
                    try:
                        click_x = self.driver.execute_script("return window._lastClickX;")
                        click_y = self.driver.execute_script("return window._lastClickY;")
                        click_recorded = self.driver.execute_script("return window._clickRecorded;")
                        
                        if click_recorded and click_x is not None and click_y is not None:
                            logging.info(f"📝 Recorded manual click at: ({click_x}, {click_y})")
                            self._save_click_coords(click_x, click_y)
                            # Reset to avoid logging multiple times
                            self.driver.execute_script("window._clickRecorded = false;")
                    except Exception as e:
                        logging.debug(f"Error checking click coordinates: {e}")
                    last_click_check = time.time()
                
                if success_check():
                    # Final check for click coordinates before returning
                    try:
                        click_x = self.driver.execute_script("return window._lastClickX;")
                        click_y = self.driver.execute_script("return window._lastClickY;")
                        if click_x is not None and click_y is not None:
                            logging.info(f"📝 Final recorded click at: ({click_x}, {click_y})")
                            self._save_click_coords(click_x, click_y)
                    except Exception:
                        pass
                    logging.info("✓ Turnstile bypassed (manual click)!")
                    return True
                time.sleep(0.2)  # Check more frequently
        else:
            # Headless mode - just wait a bit more
            logging.info("⚠️ Auto-clicks didn't work in headless mode")
            time.sleep(5)
            if success_check():
                return True
        
        return False
    
    def _save_click_coords(self, x, y):
        """Save click coordinates to config file"""
        try:
            import json
            coords_file = os.path.expanduser("~/.perplexity-click-coords.json")
            with open(coords_file, 'w') as f:
                json.dump({'x': float(x), 'y': float(y)}, f)
            logging.info(f"💾 Saved click coordinates to {coords_file}")
        except Exception as e:
            logging.debug(f"Failed to save coordinates: {e}")
    
    def _load_saved_click_coords(self):
        """Load saved click coordinates"""
        try:
            import json
            coords_file = os.path.expanduser("~/.perplexity-click-coords.json")
            if os.path.exists(coords_file):
                with open(coords_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return None
        
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
        """Close the browser and virtual display"""
        if self.driver is not None:
            try:
                self.driver.quit()
                self.driver = None
                logging.info("Browser closed")
            except Exception as e:
                logging.error(f"Failed to close browser: {e}")
        
        # Stop virtual display
        if self.vdisplay is not None:
            try:
                self.vdisplay.stop()
                self.vdisplay = None
                logging.info("Stopped Xvfb virtual display")
            except Exception as e:
                logging.debug(f"Failed to stop Xvfb: {e}")
        
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

    def _kill_profile_chrome_processes(self, user_data_dir):
        """Terminate lingering Chrome processes that are still using the profile dir."""
        if not user_data_dir:
            return
        proc_dir = "/proc"
        if not os.path.isdir(proc_dir):
            return
        killed = 0
        for entry in os.listdir(proc_dir):
            if not entry.isdigit():
                continue
            pid = int(entry)
            cmdline_path = os.path.join(proc_dir, entry, "cmdline")
            try:
                with open(cmdline_path, "rb") as fh:
                    cmdline = fh.read().decode(errors="ignore")
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
            if not cmdline:
                continue
            lc_cmd = cmdline.lower()
            if "chrome" not in lc_cmd:
                continue
            if user_data_dir not in cmdline:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                killed += 1
            except ProcessLookupError:
                continue
            except PermissionError:
                logging.debug(f"No permission to terminate Chrome PID {pid}")
        if killed:
            logging.info(f"Terminated {killed} stale Chrome process(es) using profile {user_data_dir}")
