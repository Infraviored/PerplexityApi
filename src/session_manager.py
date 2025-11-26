"""
Session management for Perplexity.ai API server
Uses JSON file for persistent storage
"""
import json
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Union


class SessionManager:
    """Manages Perplexity.ai sessions using JSON file storage"""
    
    def __init__(self, sessions_file: Optional[str] = None):
        """
        Initialize session manager
        
        Args:
            sessions_file: Path to JSON file for session storage (default: sessions.json in project root)
        """
        if sessions_file is None:
            # Use project root (same logic as config.py)
            # First, try current working directory (for systemd services with WorkingDirectory set)
            cwd_sessions = os.path.join(os.getcwd(), "sessions.json")
            # Use cwd if it exists, or if cwd looks like project root (has config.json or pyproject.toml)
            if os.path.exists(cwd_sessions) or \
               os.path.exists(os.path.join(os.getcwd(), "config.json")) or \
               os.path.exists(os.path.join(os.getcwd(), "pyproject.toml")):
                sessions_file = cwd_sessions
            else:
                # Fall back to sessions.json relative to this file's project root
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                sessions_file = os.path.join(base_dir, "sessions.json")
        
        self.sessions_file = sessions_file
        self._data = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Load sessions from JSON file"""
        if os.path.exists(self.sessions_file):
            try:
                with open(self.sessions_file, 'r') as f:
                    data = json.load(f)
                    # Ensure structure is correct
                    if 'sessions' not in data:
                        data['sessions'] = {}
                    if 'current_session' not in data:
                        data['current_session'] = None
                    return data
            except Exception as e:
                logging.error(f"Error loading sessions file: {e}")
                return {'sessions': {}, 'current_session': None}
        return {'sessions': {}, 'current_session': None}
    
    def _save(self):
        """Save sessions to JSON file"""
        try:
            with open(self.sessions_file, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving sessions file: {e}")
    
    def get_current_session(self) -> Optional[str]:
        """Get current session ID"""
        return self._data.get('current_session')
    
    def get_session_url(self, session_id: str) -> Optional[str]:
        """Get URL for a session ID"""
        session = self._data.get('sessions', {}).get(session_id)
        if session:
            return session.get('url')
        return None
    
    def create_session(self, session_id: str, url: str):
        """
        Create or update a session
        
        Args:
            session_id: Session ID extracted from URL
            url: Full URL of the session
        """
        now = datetime.utcnow().isoformat()
        
        if session_id not in self._data['sessions']:
            # New session
            self._data['sessions'][session_id] = {
                'url': url,
                'created_at': now,
                'last_used_at': now
            }
            logging.info(f"Created new session: {session_id}")
        else:
            # Update existing session
            self._data['sessions'][session_id]['url'] = url
            self._data['sessions'][session_id]['last_used_at'] = now
            logging.info(f"Updated session: {session_id}")
        
        # Set as current session
        self._data['current_session'] = session_id
        self._save()
    
    def update_session_usage(self, session_id: str):
        """Update last_used_at timestamp for a session"""
        if session_id in self._data.get('sessions', {}):
            self._data['sessions'][session_id]['last_used_at'] = datetime.utcnow().isoformat()
            self._save()
    
    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get all sessions"""
        return self._data.get('sessions', {}).copy()
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific session"""
        return self._data.get('sessions', {}).get(session_id)

