import time

from selenium.common.exceptions import SessionNotCreatedException

from src.browser import BrowserManager
from src.config import Config


def main():
    print("[MANUAL LOGIN] Starting Chromium/Chrome in visible mode for manual login...")

    config = Config()
    browser_manager = BrowserManager(config)
    perplexity_url = config.get('browser', 'perplexity_url') or "https://www.perplexity.ai/?login-source=signupButton&login-new=false"
    driver = None

    try:
        driver = browser_manager.start_visible_browser(use_ephemeral=False)
        driver.get(perplexity_url)
        print("[MANUAL LOGIN] Please log in to Perplexity.ai in the opened Chromium/Chrome window.")
        print("[MANUAL LOGIN] This window will auto-close once login is detected.")

        timeout_seconds = 600
        poll_interval = 2
        deadline = time.time() + timeout_seconds
        success = False
        check_count = 0
        
        while time.time() < deadline:
            check_count += 1
            elapsed = time.time() - (deadline - timeout_seconds)
            
            if check_count % 5 == 0:  # Log every 5 checks (every 10 seconds)
                print(f"[MANUAL LOGIN] Still checking... ({int(elapsed)}s elapsed, {int(deadline - time.time())}s remaining)")
            
            # Use the browser manager's check_login method
            if browser_manager.check_login():
                success = True
                print(f"[MANUAL LOGIN] Login detected after {int(elapsed)}s!")
                
                # Send one prompt to store the login cookie
                print("[MANUAL LOGIN] Sending first prompt to store login cookie...")
                print("[MANUAL LOGIN] This is the first prompt to store the login cookie. Just say 'nice to meet you'")
                try:
                    # Set global browser references so ask_plexi uses the existing browser
                    import src.perplexity as perplexity_module
                    perplexity_module._browser_driver = driver
                    perplexity_module._browser_manager = browser_manager
                    
                    from src.perplexity import ask_plexi
                    # Send the prompt using the current browser instance
                    response, session_id, final_url = ask_plexi(
                        "Demo request for cookie storage. Just say 'nice to meet you' - don't Lookup anything.",
                        config=config,
                        debug=False,
                        headless=False  # Keep visible since we're in manual login
                    )
                    print("[MANUAL LOGIN] First prompt sent successfully. Login cookie stored.")
                except Exception as e:
                    print(f"[MANUAL LOGIN] Warning: Error sending first prompt: {e}")
                    # Continue anyway - the login was detected
                
                print("[MANUAL LOGIN] Session saved. Closing browser...")
                break
            
            time.sleep(poll_interval)
    except SessionNotCreatedException as exc:
        raise SystemExit(
            f"[MANUAL LOGIN] Failed to launch Chromium via Selenium: {exc}. "
            "This usually means another Chromium window is already using "
            "the shared profile. Close other Chromium windows and retry."
        ) from exc
    finally:
        try:
            browser_manager.close()
        except Exception:
            pass

    if success:
        print("[MANUAL LOGIN] Login session saved. You can now use ask_plexi() in headless mode.")
    else:
        raise SystemExit("[MANUAL LOGIN] Timed out waiting for login. Please rerun and log in.")


if __name__ == "__main__":
    main()
