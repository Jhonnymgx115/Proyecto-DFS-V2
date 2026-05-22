import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

NAMENODE_URL: str = os.getenv("NAMENODE_URL", "http://localhost:8000").rstrip("/")
SESSION_FILE: Path = Path(os.getenv("DFS_SESSION_FILE", ".dfs_session.json"))
CONFIRM_TIMEOUT_SECONDS: int = int(os.getenv("DFS_CONFIRM_TIMEOUT_SECONDS", "90"))
CONFIRM_POLL_SECONDS: float = float(os.getenv("DFS_CONFIRM_POLL_SECONDS", "2"))
