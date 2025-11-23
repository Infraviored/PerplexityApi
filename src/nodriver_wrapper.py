"""
Nodriver wrapper for synchronous Selenium-like API compatibility
Uses nodriver's own event loop (uc.loop().run_until_complete())
"""
import asyncio
import logging
from typing import Optional, List, Tuple
import time
import nodriver as uc


class NodriverElement:
    """Wrapper for nodriver element with Selenium-like API"""
    
    def __init__(self, element, loop):
        self._element = element
        self._loop = loop
    
    def click(self):
        """Click the element"""
        async def _click():
            await self._element.click()
        return self._loop.run_until_complete(_click())
    
    def send_keys(self, text: str):
        """Send keys to element"""
        async def _send_keys():
            await self._element.send_keys(text)
        return self._loop.run_until_complete(_send_keys())
    
    def clear(self):
        """Clear element text"""
        async def _clear():
            await self._element.clear()
        return self._loop.run_until_complete(_clear())
    
    @property
    def text(self) -> str:
        """Get element text"""
        async def _get_text():
            return await self._element.text()
        return self._loop.run_until_complete(_get_text())
    
    @property
    def is_displayed(self) -> bool:
        """Check if element is displayed"""
        async def _is_displayed():
            try:
                return await self._element.is_displayed()
            except:
                return False
        return self._loop.run_until_complete(_is_displayed())
    
    def get_attribute(self, name: str) -> Optional[str]:
        """Get element attribute"""
        async def _get_attr():
            try:
                return await self._element.get_attribute(name)
            except:
                return None
        return self._loop.run_until_complete(_get_attr())
    
    def find_element(self, by_or_selector, selector=None):
        """Find child element"""
        async def _find():
            if selector is not None:
                actual_selector = selector
            else:
                actual_selector = by_or_selector
            
            try:
                elem = await asyncio.wait_for(
                    self._element.select(actual_selector, timeout=5),
                    timeout=10
                )
                return NodriverElement(elem, self._loop) if elem else None
            except:
                return None
        return self._loop.run_until_complete(_find())
    
    def find_elements(self, by_or_selector, selector=None) -> List['NodriverElement']:
        """Find child elements"""
        async def _find_all():
            if selector is not None:
                actual_selector = selector
            else:
                actual_selector = by_or_selector
            
            try:
                elems = await asyncio.wait_for(
                    self._element.select_all(actual_selector, timeout=5),
                    timeout=10
                )
                return [NodriverElement(e, self._loop) for e in elems] if elems else []
            except:
                return []
        return self._loop.run_until_complete(_find_all())


class NodriverBrowser:
    """Wrapper for nodriver browser with Selenium-like API"""
    
    def __init__(self, browser, page, loop):
        self._browser = browser
        self._page = page
        self._loop = loop
        self._current_url = ""
    
    @property
    def page(self):
        """Get underlying nodriver page"""
        return self._page
    
    @property
    def current_url(self) -> str:
        """Get current URL"""
        try:
            self._current_url = self._page.url if hasattr(self._page, 'url') else self._current_url
            return self._current_url
        except:
            return self._current_url
    
    @property
    def title(self) -> str:
        """Get page title"""
        try:
            return self._page.title if hasattr(self._page, 'title') else ""
        except:
            return ""
    
    @property
    def page_source(self) -> str:
        """Get page source"""
        async def _get_source():
            try:
                if hasattr(self._page, 'content'):
                    content = self._page.content
                    if callable(content):
                        return await content()
                    return content
                return await self._page.evaluate("document.documentElement.outerHTML", await_promise=False)
            except Exception as e:
                logging.debug(f"Error getting page source: {e}")
                return ""
        return self._loop.run_until_complete(_get_source())
    
    def get(self, url: str):
        """Navigate to URL"""
        async def _get():
            new_page = await asyncio.wait_for(
                self._page.get(url),
                timeout=30
            )
            self._page = new_page
            self._current_url = new_page.url if hasattr(new_page, 'url') else url
        return self._loop.run_until_complete(_get())
    
    def find_element(self, by_or_selector, selector=None):
        """Find element - supports both Selenium-style (By, selector) and direct selector"""
        async def _find():
            if selector is not None:
                # Selenium-style: find_element(By.CSS_SELECTOR, "selector")
                actual_selector = selector
            else:
                # Direct selector: find_element("selector")
                actual_selector = by_or_selector
            
            try:
                elem = await asyncio.wait_for(
                    self._page.select(actual_selector, timeout=5),
                    timeout=10
                )
                return NodriverElement(elem, self._loop) if elem else None
            except Exception as e:
                logging.debug(f"Element not found: {e}")
                return None
        return self._loop.run_until_complete(_find())
    
    def find_elements(self, by_or_selector, selector=None) -> List[NodriverElement]:
        """Find elements - supports both Selenium-style (By, selector) and direct selector"""
        async def _find_all():
            if selector is not None:
                actual_selector = selector
            else:
                actual_selector = by_or_selector
            
            try:
                elems = await asyncio.wait_for(
                    self._page.select_all(actual_selector, timeout=5),
                    timeout=10
                )
                return [NodriverElement(e, self._loop) for e in elems] if elems else []
            except Exception as e:
                logging.debug(f"Elements not found: {e}")
                return []
        return self._loop.run_until_complete(_find_all())
    
    def execute_script(self, script: str, *args):
        """Execute JavaScript"""
        async def _execute():
            if args:
                result = await asyncio.wait_for(
                    self._page.evaluate(expression=script, await_promise=True, *args),
                    timeout=30
                )
            else:
                result = await asyncio.wait_for(
                    self._page.evaluate(expression=script, await_promise=True),
                    timeout=30
                )
            return result
        return self._loop.run_until_complete(_execute())
    
    def execute_async_script(self, script: str, *args):
        """Execute async JavaScript"""
        async def _execute():
            result = await asyncio.wait_for(
                self._page.evaluate(expression=script, await_promise=True, *args),
                timeout=30
            )
            return result
        return self._loop.run_until_complete(_execute())
    
    def wait_for(self, selector: str, timeout: int = 10):
        """Wait for element to appear"""
        async def _wait():
            try:
                await asyncio.wait_for(
                    self._page.wait_for(selector, timeout=timeout),
                    timeout=timeout + 5
                )
                return True
            except:
                return False
        return self._loop.run_until_complete(_wait())
    
    def refresh(self):
        """Refresh page"""
        async def _refresh():
            await asyncio.wait_for(
                self._page.reload(),
                timeout=30
            )
        return self._loop.run_until_complete(_refresh())
    
    def save_screenshot(self, path: str):
        """Save screenshot"""
        async def _screenshot():
            await asyncio.wait_for(
                self._page.save_screenshot(path),
                timeout=30
            )
        return self._loop.run_until_complete(_screenshot())
    
    def quit(self):
        """Close browser"""
        async def _quit():
            try:
                stop_result = self._browser.stop()
                if stop_result and asyncio.iscoroutine(stop_result):
                    await stop_result
            except Exception as e:
                logging.debug(f"Error stopping browser: {e}")
        try:
            self._loop.run_until_complete(_quit())
        except Exception as e:
            logging.debug(f"Error in quit: {e}")
    
    def close(self):
        """Alias for quit"""
        self.quit()


def get_browser(headless: bool = True, user_data_dir: Optional[str] = None):
    """Get nodriver browser instance using nodriver's own event loop"""
    import shutil
    import os
    
    # Reduce nodriver's verbose debug logging (but keep some for debugging)
    logging.getLogger('nodriver').setLevel(logging.INFO)
    logging.getLogger('websockets').setLevel(logging.WARNING)
    
    # Get nodriver's event loop
    loop = uc.loop()
    
    async def _start():
        # Find Chrome binary
        chrome_binary = None
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "google-chrome",
            "chromium",
            "chromium-browser",
        ]
        chrome_binary = next((p for p in candidates if shutil.which(p)), None)
        
        # Start browser with timeout and no_sandbox=True (critical!)
        start_kwargs = {
            'headless': headless,
            'no_sandbox': True,  # Prevents hangs and connection failures
        }
        
        if chrome_binary:
            start_kwargs['browser_executable_path'] = chrome_binary
        
        browser = await asyncio.wait_for(
            uc.start(**start_kwargs),
            timeout=30
        )
        
        # Wait a bit for browser to fully initialize
        await asyncio.sleep(1)
        
        # Get main tab - try different methods
        try:
            if hasattr(browser, 'main_tab') and browser.main_tab:
                page = browser.main_tab
            elif hasattr(browser, 'tabs') and browser.tabs:
                # Get first page tab
                page = next((t for t in browser.tabs if t.type == 'page'), None)
                if not page:
                    page = browser.tabs[0] if browser.tabs else None
            else:
                # Fallback: navigate to about:blank to get a page
                page = await asyncio.wait_for(
                    browser.get('about:blank'),
                    timeout=10
                )
        except Exception as e:
            logging.debug(f"Error getting main tab: {e}, trying fallback")
            # Fallback: navigate to about:blank
            page = await asyncio.wait_for(
                browser.get('about:blank'),
                timeout=10
            )
        
        return browser, page
    
    browser, page = loop.run_until_complete(_start())
    return NodriverBrowser(browser, page, loop)


def close_browser(browser: NodriverBrowser):
    """Close browser"""
    if browser:
        browser.quit()


# WebDriverWait compatibility
class WebDriverWait:
    """Selenium WebDriverWait compatibility wrapper"""
    
    def __init__(self, driver: NodriverBrowser, timeout: int):
        self.driver = driver
        self.timeout = timeout
    
    def until(self, method, message=""):
        """Wait until condition is met"""
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                result = method(self.driver)
                if result:
                    return result
            except Exception:
                pass
            time.sleep(0.5)
        raise TimeoutError(f"Timeout waiting for condition: {message}")


# ExpectedConditions compatibility
class expected_conditions:
    """Selenium expected_conditions compatibility"""
    
    @staticmethod
    def presence_of_element_located(locator: Tuple):
        """Wait for element to be present"""
        def _predicate(driver: NodriverBrowser):
            by, selector = locator
            return driver.find_element(by, selector)
        return _predicate
    
    @staticmethod
    def element_to_be_clickable(locator: Tuple):
        """Wait for element to be clickable"""
        def _predicate(driver: NodriverBrowser):
            by, selector = locator
            elem = driver.find_element(by, selector)
            if elem and elem.is_displayed:
                return elem
            return None
        return _predicate


# By enum compatibility
class By:
    """Selenium By enum compatibility"""
    CSS_SELECTOR = "css selector"
    XPATH = "xpath"
    ID = "id"
    NAME = "name"
    TAG_NAME = "tag name"
    CLASS_NAME = "class name"
    LINK_TEXT = "link text"
    PARTIAL_LINK_TEXT = "partial link text"
