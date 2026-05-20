import os

from dotenv import load_dotenv

load_dotenv()

# Identity
DATANODE_HOST: str = os.getenv("DATANODE_HOST", "0.0.0.0")
DATANODE_PORT: int = int(os.getenv("DATANODE_PORT", "8001"))
DATANODE_URL: str = os.getenv("DATANODE_URL", f"http://localhost:{os.getenv('DATANODE_PORT', '8001')}")

# NameNode connection
NAMENODE_URL: str = os.getenv("NAMENODE_URL", "http://localhost:8000")

# Storage
STORAGE_DIR: str = os.getenv("STORAGE_DIR", "datanode_storage")

# Heartbeat / replication
HEARTBEAT_INTERVAL_SECONDS: int = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "30"))
REPLICATION_TIMEOUT_SECONDS: int = int(os.getenv("REPLICATION_TIMEOUT_SECONDS", "10"))
