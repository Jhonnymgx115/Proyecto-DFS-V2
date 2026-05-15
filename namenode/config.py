import os

from dotenv import load_dotenv

load_dotenv()

NAMENODE_HOST: str = os.getenv("NAMENODE_HOST", "0.0.0.0")
NAMENODE_PORT: int = int(os.getenv("NAMENODE_PORT", "8000"))
JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
BLOCK_SIZE_MB: int = int(os.getenv("BLOCK_SIZE_MB", "64"))
REPLICATION_FACTOR: int = int(os.getenv("REPLICATION_FACTOR", "2"))
METADATA_FILE: str = os.getenv("METADATA_FILE", "namenode_metadata.json")

BLOCK_SIZE_BYTES: int = BLOCK_SIZE_MB * 1024 * 1024
