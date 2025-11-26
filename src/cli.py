"""
Command-line wrapper for Perplexity.ai API server.

This provides the implementation behind the ``askplexi`` console script.
"""
import argparse
import json
import os
import sys
from typing import Tuple

import requests


def get_server_url() -> str:
    """Get server URL from environment or use default."""
    return os.environ.get("PERPLEXITY_API_URL", "http://localhost:8088")


def call_server(
    question: str,
    new_session: bool = False,
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

    if new_session:
        payload["new_session"] = True
    elif session_id:
        # For now, we don't thread session IDs through the API; treat as new session.
        payload["new_session"] = True

    response = requests.post(
        f"{server_url}/ask",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("response", ""), data.get("session_id")


def run_health_check(server_url: str) -> tuple[bool, dict | None]:
    """
    Call the /health endpoint and return (ok, json_payload_or_none).
    """
    try:
        resp = requests.get(f"{server_url}/health", timeout=10)
        if resp.status_code != 200:
            return False, None
        payload = resp.json()
        status = str(payload.get("status", "")).lower()
        return status == "ok", payload
    except Exception:
        return False, None


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


def find_sessions_file() -> str:
    """Find sessions.json file in project root (same logic as SessionManager)."""
    # First, try current working directory
    cwd_sessions = os.path.join(os.getcwd(), "sessions.json")
    if os.path.exists(cwd_sessions):
        return cwd_sessions
    
    # Try to find project root by looking for config.json or pyproject.toml
    current = os.getcwd()
    for _ in range(5):  # Look up to 5 levels up
        sessions_path = os.path.join(current, "sessions.json")
        if os.path.exists(sessions_path):
            return sessions_path
        # Check if this looks like project root
        if os.path.exists(os.path.join(current, "config.json")) or \
           os.path.exists(os.path.join(current, "pyproject.toml")):
            return sessions_path
        parent = os.path.dirname(current)
        if parent == current:  # Reached filesystem root
            break
        current = parent
    
    # Fallback to cwd
    return cwd_sessions


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
  askplexi "What is 2+2?" --new
  askplexi "What is 2+2?" --id "session-id-123"
  askplexi --sessions
""",
    )

    parser.add_argument(
        "question",
        nargs="?",
        help="The question to ask",
    )
    parser.add_argument(
        "--new",
        action="store_true",
        help="Create a new session",
    )
    parser.add_argument(
        "--id",
        metavar="SESSION_ID",
        help="Use specific session ID (currently treated as new session)",
    )
    parser.add_argument(
        "--server",
        metavar="URL",
        default=None,
        help=(
            "Server URL "
            "(default: http://localhost:8088 or PERPLEXITY_API_URL env var)"
        ),
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

    args = parser.parse_args(argv)
    
    # Handle --sessions flag (exit early)
    if args.sessions:
        return list_sessions()

    # Override server URL if provided
    if args.server:
        os.environ["PERPLEXITY_API_URL"] = args.server

    # Get question from argument or stdin
    if args.question:
        question = args.question
    else:
        question = sys.stdin.read().strip()
        if not question:
            parser.print_help()
            return 1

    server_url = get_server_url()

    try:
        response_text, session_id = call_server(
            question,
            new_session=args.new,
            session_id=args.id,
            return_sources=args.return_sources,
        )
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

        ok, payload = run_health_check(server_url)
        if ok:
            print("Health check OK, but /ask failed. Check server logs.", file=sys.stderr)
            return 1

        print("Health check failed or server not responding.", file=sys.stderr)
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


