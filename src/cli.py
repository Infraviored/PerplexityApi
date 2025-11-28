"""
Command-line wrapper for Perplexity.ai API server.

This provides the implementation behind the ``askplexi`` console script.
"""
import argparse
import json
import os
import sys
from typing import Tuple, Optional

import requests


def get_server_url() -> str:
    """Get server URL from environment or use default."""
    return os.environ.get("PERPLEXITY_API_URL", "http://localhost:8088")


def call_server(
    question: str,
    session_id: str | None = None,
    return_sources: bool = False,
    timeout: int = 300,
) -> Tuple[str, str | None]:
    """
    Call the Perplexity API server /ask endpoint.

    Returns (response_text, session_id).
    """
    server_url = get_server_url()

    payload: dict = {
        "question": question,
        "return_sources": return_sources,
    }

    if session_id:
        payload["session_id"] = session_id

    response = requests.post(
        f"{server_url}/ask",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("response", ""), data.get("session_id")


def run_health_check(server_url: str) -> tuple[bool, dict | None, int | None]:
    """
    Call the /health endpoint and return (ok, payload_or_none, status_code).
    """
    try:
        resp = requests.get(f"{server_url}/health", timeout=10)
        payload = None
        try:
            payload = resp.json()
        except ValueError:
            if resp.text:
                payload = {"message": resp.text.strip()}
        status_value = ""
        if isinstance(payload, dict):
            status_value = str(payload.get("status", payload.get("error", ""))).lower()
        ok = resp.status_code == 200 and status_value == "ok"
        return ok, payload, resp.status_code
    except Exception as exc:
        return False, {"error": str(exc)}, None


def maybe_run_restart() -> None:
    """
    Optionally run a restart command if PERPLEXITY_RESTART_CMD is set and
    the user confirms.
    """
    restart_cmd = os.environ.get("PERPLEXITY_RESTART_CMD")
    if not restart_cmd:
        print(
            "No PERPLEXITY_RESTART_CMD configured. "
            "Please restart the server manually.",
            file=sys.stderr,
        )
        return

    answer = input(
        f"Health check failed. Restart server with '{restart_cmd}'? [y/N]: "
    ).strip() or "n"
    if answer.lower().startswith("y"):
        os.system(restart_cmd)


def get_xdg_config_dir() -> str:
    """Get XDG config directory: ~/.config/askplexi/"""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        config_dir = os.path.join(config_home, "askplexi")
    else:
        config_dir = os.path.join(os.path.expanduser("~"), ".config", "askplexi")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def find_sessions_file() -> str:
    """Get sessions.json file path: ~/.config/askplexi/sessions.json"""
    config_dir = get_xdg_config_dir()
    return os.path.join(config_dir, "sessions.json")


def cli_state_file() -> str:
    """Return CLI state file path."""
    return os.path.join(get_xdg_config_dir(), "cli-state.json")


def load_last_session_id() -> Optional[str]:
    """Read last session id tracked by CLI."""
    state_path = cli_state_file()
    try:
        with open(state_path, "r") as f:
            data = json.load(f)
        return data.get("last_session_id")
    except FileNotFoundError:
        return None
    except Exception:
        return None


def save_last_session_id(session_id: str | None) -> None:
    """Persist last session id for CLI convenience."""
    if not session_id:
        return
    state_path = cli_state_file()
    try:
        with open(state_path, "w") as f:
            json.dump({"last_session_id": session_id}, f, indent=2)
    except Exception:
        pass


def list_sessions() -> int:
    """List all sessions from sessions.json."""
    sessions_file = find_sessions_file()
    
    if not os.path.exists(sessions_file):
        print(f"No sessions file found at {sessions_file}", file=sys.stderr)
        print("Sessions are created when you ask questions via the API.", file=sys.stderr)
        return 1
    
    try:
        with open(sessions_file, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading sessions file: {e}", file=sys.stderr)
        return 1
    
    sessions = data.get("sessions", {})
    current_session = data.get("current_session")
    
    if not sessions:
        print("No sessions found.", file=sys.stderr)
        return 0
    
    print(f"Sessions file: {sessions_file}")
    print(f"Total sessions: {len(sessions)}")
    if current_session:
        print(f"Current session: {current_session}")
    print()
    
    # Sort by last_used_at (most recent first)
    sorted_sessions = sorted(
        sessions.items(),
        key=lambda x: x[1].get("last_used_at", ""),
        reverse=True,
    )
    
    for session_id, info in sorted_sessions:
        is_current = " (current)" if session_id == current_session else ""
        print(f"Session: {session_id}{is_current}")
        if "created_at" in info:
            print(f"  Created: {info['created_at']}")
        if "last_used_at" in info:
            print(f"  Last used: {info['last_used_at']}")
        if "url" in info:
            url = info["url"]
            # Truncate long URLs
            if len(url) > 80:
                url = url[:77] + "..."
            print(f"  URL: {url}")
        print()
    
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ask Perplexity.ai a question via local API server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  askplexi "What is 2+2?"
  askplexi "What is 2+2?" --id "session-id-123"
  askplexi "What is 2+2?" --continue
  askplexi --sessions
""",
    )

    parser.add_argument(
        "question",
        nargs="?",
        help="The question to ask",
    )
    parser.add_argument(
        "--id",
        metavar="SESSION_ID",
        help="Continue using specific session ID",
    )
    parser.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="Continue in the last session returned by askplexi",
    )
    parser.add_argument(
        "--return-sources",
        action="store_true",
        help="Include citations and URLs in the response",
    )
    parser.add_argument(
        "--sessions",
        action="store_true",
        help="List all sessions from sessions.json",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Check server health status and exit",
    )
    parser.add_argument(
        "--manual-login",
        action="store_true",
        help="Open a visible browser window to re-authenticate Perplexity",
    )

    args = parser.parse_args(argv)
    
    # Handle --sessions flag (exit early)
    if args.sessions:
        return list_sessions()
    
    server_url = get_server_url()

    # Handle --health flag
    if args.health:
        ok, payload, status_code = run_health_check(server_url)
        if payload:
            print(json.dumps(payload, indent=2))
        if ok:
            print("Health: OK")
            return 0
        reason = "unknown issue"
        if isinstance(payload, dict):
            reason = payload.get("message") or payload.get("error") or str(payload)
        print(f"Health: FAIL ({reason})")
        if status_code:
            print(f"HTTP status: {status_code}")
        maybe_run_restart()
        return 1

    if args.manual_login:
        try:
            from .manual_login import main as manual_login_main
        except ImportError:
            print("Manual login module not available inside package.", file=sys.stderr)
            return 1
        try:
            manual_login_main()
            return 0
        except SystemExit as exc:
            return exc.code or 0

    if args.id and args.continue_session:
        parser.error("Cannot specify --id and --continue together.")

    # Determine session override
    # If neither --id nor --continue is specified, session_id will be None (new session)
    session_override: str | None = None
    if args.id:
        session_override = args.id
    elif args.continue_session:
        session_override = load_last_session_id()
        if not session_override:
            print(
                "No previous session id recorded. Ask a question without --continue first.",
                file=sys.stderr,
            )
            return 1

    # Get question from argument or stdin
    if args.question:
        question = args.question
    else:
        question = sys.stdin.read().strip()
        if not question:
            parser.print_help()
            return 1

    try:
        response_text, session_id = call_server(
            question,
            session_id=session_override,
            return_sources=args.return_sources,
        )
        save_last_session_id(session_id)

        # Output session information for clarity
        if session_id and session_override:
            print(f"session id: {session_id}\n")
        elif session_id:
            print(f"new session id: {session_id}\n")

        print(response_text)
        if os.environ.get("PERPLEXITY_DEBUG") and session_id:
            print(f"\n[Session ID: {session_id}]", file=sys.stderr)
        return 0
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        print(
            f"Error: Could not reach server at {server_url}",
            file=sys.stderr,
        )
        answer = input("Run server health check now? [Y/n]: ").strip() or "y"
        if not answer.lower().startswith("y"):
            return 1

        ok, payload, status_code = run_health_check(server_url)
        if payload:
            print(json.dumps(payload, indent=2))
        if ok:
            print("Health check OK, but /ask failed. Check server logs.", file=sys.stderr)
            return 1

        reason = "unknown issue"
        if isinstance(payload, dict):
            reason = payload.get("message") or payload.get("error") or str(payload)
        print(f"Health check failed or server not responding ({reason}).", file=sys.stderr)
        if status_code:
            print(f"HTTP status: {status_code}", file=sys.stderr)
        maybe_run_restart()
        return 1
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error from server: {e}", file=sys.stderr)
        if hasattr(e.response, "text"):
            print(f"Details: {e.response.text}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


