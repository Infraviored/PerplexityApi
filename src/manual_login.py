import os
import subprocess
import time

from selenium.common.exceptions import SessionNotCreatedException

from .browser import BrowserManager
from .config import Config

DEFAULT_SERVICE_NAME = "perplexity-api"
SERVICE_ENV_VAR = "PERPLEXITY_SERVICE_NAME"


def _run_systemctl(args, capture: bool = True) -> subprocess.CompletedProcess:
    """
    Run a systemctl --user command.

    We capture stdout/stderr for better error reporting but keep failures non-fatal.
    """
    full_cmd = ["systemctl", "--user", *args]
    kwargs: dict = {"check": False}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    try:
        return subprocess.run(full_cmd, **kwargs)
    except FileNotFoundError:
        return subprocess.CompletedProcess(full_cmd, returncode=127)


def get_service_name() -> str:
    """Resolve the systemd service name to manage during manual login."""
    return os.environ.get(SERVICE_ENV_VAR, DEFAULT_SERVICE_NAME)


def is_service_active(service_name: str) -> bool:
    """Return True if the user service is currently active."""
    result = _run_systemctl(["is-active", "--quiet", service_name], capture=False)
    return result.returncode == 0


def stop_service(service_name: str) -> bool:
    """
    Stop the service if it is running.

    Returns True if the service was active before this call (regardless of stop success).
    """
    if not is_service_active(service_name):
        print(
            f"[MANUAL LOGIN] Service '{service_name}' is not running; skipping stop step."
        )
        return False

    print(f"[MANUAL LOGIN] Detected running service '{service_name}'. Stopping to avoid profile conflicts...")
    result = _run_systemctl(["stop", service_name])
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        print(
            f"[MANUAL LOGIN] Warning: Could not stop service '{service_name}' "
            f"(exit {result.returncode}). Manual intervention may be required."
        )
        if stderr:
            print(f"[MANUAL LOGIN] systemctl output: {stderr}")
    else:
        # Wait briefly for the service to fully stop.
        for _ in range(10):
            if not is_service_active(service_name):
                break
            time.sleep(0.5)
        print(f"[MANUAL LOGIN] Service '{service_name}' stopped.")
    return True


def start_service(service_name: str) -> None:
    """Start the service and wait until systemd reports it active."""
    print(f"[MANUAL LOGIN] Restarting service '{service_name}'...")
    result = _run_systemctl(["start", service_name])
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        print(
            f"[MANUAL LOGIN] Warning: Failed to start service '{service_name}' "
            f"(exit {result.returncode}). Please start it manually."
        )
        if stderr:
            print(f"[MANUAL LOGIN] systemctl output: {stderr}")
        return

    for _ in range(20):
        if is_service_active(service_name):
            print(f"[MANUAL LOGIN] Service '{service_name}' is running again.")
            return
        time.sleep(0.5)
    print(
        f"[MANUAL LOGIN] Warning: Service '{service_name}' did not report active status. "
        "Check systemctl logs manually."
    )


def run_first_prompt(driver, browser_manager, config):
    """Send first prompt after manual login to persist cookies."""
    print("[MANUAL LOGIN] Sending first prompt to store login cookie...")
    print(
        "[MANUAL LOGIN] This is the first prompt to store the login cookie. "
        "Just say 'nice to meet you'"
    )
    try:
        # Set global browser references so ask_plexi uses the existing browser
        from . import perplexity as perplexity_module

        perplexity_module._browser_driver = driver
        perplexity_module._browser_manager = browser_manager

        from .perplexity import ask_plexi

        response, session_id, final_url = ask_plexi(
            "Just say 'nice to meet you' - don't Lookup anything.",
            config=config,
            debug=False,
            headless=False,
        )
        print("[MANUAL LOGIN] First prompt sent successfully. Login cookie stored.")
    except Exception as e:
        print(f"[MANUAL LOGIN] Warning: Error sending first prompt: {e}")


def main():
    print("[MANUAL LOGIN] Starting Chromium/Chrome in visible mode for manual login...")

    service_name = get_service_name()
    stop_service(service_name)

    config = Config()
    browser_manager = BrowserManager(config)
    perplexity_url = (
        config.get("browser", "perplexity_url")
        or "https://www.perplexity.ai/?login-source=signupButton&login-new=false"
    )
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

            if check_count % 5 == 0:
                remaining = int(max(0, deadline - time.time()))
                print(f"[MANUAL LOGIN] Still checking... ({int(elapsed)}s elapsed, {remaining}s remaining)")

            if browser_manager.check_login():
                success = True
                print(f"[MANUAL LOGIN] Login detected after {int(elapsed)}s!")
                run_first_prompt(driver, browser_manager, config)
                print("[MANUAL LOGIN] Session saved. Closing browser...")
                break

            time.sleep(poll_interval)
    except SessionNotCreatedException as exc:
        raise SystemExit(
            "[MANUAL LOGIN] Failed to launch Chromium via Selenium: "
            f"{exc}. This usually means another Chromium window is already using "
            "the shared profile. Close other Chromium windows and retry."
        ) from exc
    finally:
        try:
            browser_manager.close()
        except Exception:
            pass
        # Always attempt to restart the service to keep the API available after login.
        start_service(service_name)

    if success:
        print("[MANUAL LOGIN] Login session saved. You can now use ask_plexi() in headless mode.")
    else:
        raise SystemExit("[MANUAL LOGIN] Timed out waiting for login. Please rerun and log in.")


if __name__ == "__main__":
    main()

