import logging
from pathlib import Path

from datanode.config import STORAGE_DIR

logger = logging.getLogger("datanode.storage")
_storage_path = Path(STORAGE_DIR)


def _ensure_dir() -> None:
    _storage_path.mkdir(parents=True, exist_ok=True)


def _block_path(block_id: str) -> Path:
    return _storage_path / block_id


def init_storage() -> None:
    _ensure_dir()
    logger.info("Storage ready: %s", _storage_path.resolve())


def write_block(block_id: str, data: bytes) -> int:
    _ensure_dir()
    _block_path(block_id).write_bytes(data)
    logger.info("Block written: %s (%d bytes)", block_id, len(data))
    return len(data)


def read_block(block_id: str) -> bytes:
    path = _block_path(block_id)
    if not path.exists():
        raise FileNotFoundError(f"Block not found: {block_id}")
    return path.read_bytes()


def delete_block(block_id: str) -> bool:
    path = _block_path(block_id)
    if not path.exists():
        return False
    path.unlink()
    logger.info("Block deleted: %s", block_id)
    return True


def block_exists(block_id: str) -> bool:
    return _block_path(block_id).exists()


def list_blocks() -> list[str]:
    _ensure_dir()
    return [p.name for p in _storage_path.iterdir() if p.is_file()]


def storage_stats() -> dict[str, int]:
    _ensure_dir()
    blocks = list_blocks()
    total_bytes = sum(_block_path(b).stat().st_size for b in blocks)
    return {"block_count": len(blocks), "total_bytes": total_bytes}
