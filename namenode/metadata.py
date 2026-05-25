import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from namenode.config import METADATA_FILE

logger = logging.getLogger("namenode.metadata")


class MetadataStore:
  """Persistent JSON metadata with atomic writes and lazy disk flush."""

  def __init__(self, metadata_file: str | None = None) -> None:
    self._path = Path(metadata_file or METADATA_FILE)
    self._dirty = False
    self.users: dict[str, str] = {}
    self.files: dict[str, dict[str, Any]] = {}
    self.blocks: dict[str, list[str]] = {}
    self.datanodes: dict[str, dict[str, Any]] = {}
    self.load()

  # ── persistence ──────────────────────────────────────────────

  def _atomic_save(self, data: dict[str, Any]) -> None:
    tmp_path = self._path.with_suffix(".tmp")
    payload = json.dumps(data, indent=2)
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(self._path)
    self._dirty = False
    logger.debug("Metadata saved to %s", self._path)

  def save(self) -> None:
    if not self._dirty:
      return
    data = {
      "users": self.users,
      "files": self.files,
      "blocks": self.blocks,
      "datanodes": self.datanodes,
    }
    self._atomic_save(data)

  def flush(self) -> None:
    """Force write even if callers forgot to rely on auto-save."""
    self._dirty = True
    self.save()

  def _mark_dirty(self) -> None:
    self._dirty = True

  def _backup_corrupt_file(self) -> None:
    backup = self._path.with_suffix(".bak")
    shutil.copy2(self._path, backup)
    logger.warning("Corrupt metadata backed up to %s", backup)

  def load(self) -> None:
    if not self._path.exists():
      logger.info("Metadata file not found, starting empty: %s", self._path)
      return
    try:
      data = json.loads(self._path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
      self._backup_corrupt_file()
      logger.warning("Corrupt metadata, starting fresh: %s", self._path)
      return
    self.users = data.get("users", {})
    self.files = data.get("files", {})
    self.blocks = data.get("blocks", {})
    self.datanodes = data.get("datanodes", {})
    self._dirty = False

  # ── users ────────────────────────────────────────────────────

  def add_user(self, username: str, hashed_password: str) -> None:
    self.users[username] = hashed_password
    self._mark_dirty()
    self.save()

  def get_user(self, username: str) -> str | None:
    return self.users.get(username)

  def user_exists(self, username: str) -> bool:
    return username in self.users

  # ── files ────────────────────────────────────────────────────

  def _file_key(self, user: str, filename: str) -> str:
    return f"{user}/{filename}"

  def add_file(self, user: str, filename: str, record: dict[str, Any]) -> None:
    record.setdefault("created_at", time.time())
    record["updated_at"] = time.time()
    self.files[self._file_key(user, filename)] = record
    self._mark_dirty()
    self.save()

  def get_file(self, user: str, filename: str) -> dict[str, Any] | None:
    return self.files.get(self._file_key(user, filename))

  def list_files(self, user: str) -> list[dict[str, Any]]:
    prefix = f"{user}/"
    results: list[dict[str, Any]] = []
    for key, record in self.files.items():
      if key.startswith(prefix) and record.get("status") != "deleted":
        name = key[len(prefix):]
        results.append({**record, "filename": name})
    return results

  def delete_file(self, user: str, filename: str) -> bool:
    key = self._file_key(user, filename)
    record = self.files.get(key)
    if record is None:
      return False
    record["status"] = "deleted"
    record["updated_at"] = time.time()
    for block_id in record.get("blocks", []):
      self.blocks.pop(block_id, None)
    self._mark_dirty()
    self.save()
    return True

  def is_file_ready(self, user: str, filename: str) -> bool:
    record = self.get_file(user, filename)
    return record is not None and record.get("status") == "ready"

  # ── blocks / datanodes ───────────────────────────────────────

  def register_block(self, block_id: str, datanode_urls: list[str]) -> None:
    self.blocks[block_id] = list(datanode_urls)
    self._mark_dirty()
    self.save()

  def get_block_locations(self, block_id: str) -> list[str]:
    return list(self.blocks.get(block_id, []))

  def count_block_replicas(self, block_id: str) -> int:
    count = 0
    for info in self.datanodes.values():
      if block_id in info.get("blocks", []):
        count += 1
    return count

  def register_datanode(self, url: str) -> None:
    if url not in self.datanodes:
      self.datanodes[url] = {"last_seen": 0.0, "blocks": []}
      self._mark_dirty()
      self.save()

  def update_datanode_blocks(
    self, url: str, block_ids: list[str], last_seen: float
  ) -> None:
    self.datanodes[url] = {
      "last_seen": last_seen,
      "blocks": list(block_ids),
    }
    self._mark_dirty()
    self.save()

  def get_alive_datanodes(self, ttl_seconds: int = 60) -> list[str]:
    now = time.time()
    return sorted(
      url
      for url, info in self.datanodes.items()
      if now - info.get("last_seen", 0) < ttl_seconds
    )

  def get_storage_stats(self) -> dict[str, int]:
    active_files = sum(
      1 for r in self.files.values() if r.get("status") != "deleted"
    )
    return {
      "users": len(self.users),
      "files_active": active_files,
      "files_total": len(self.files),
      "blocks": len(self.blocks),
      "datanodes": len(self.datanodes),
    }
