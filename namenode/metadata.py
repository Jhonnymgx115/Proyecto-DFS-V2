import json
import logging
from pathlib import Path
from typing import Any

from namenode.config import METADATA_FILE

logger = logging.getLogger("namenode.metadata")


class MetadataStore:
    def __init__(self, metadata_file: str | None = None) -> None:
        self._path = Path(metadata_file or METADATA_FILE)
        self.users: dict[str, str] = {}
        self.files: dict[str, dict[str, Any]] = {}
        self.blocks: dict[str, list[str]] = {}
        self.datanodes: dict[str, dict[str, Any]] = {}
        self.load()

    def save(self) -> None:
        data = {
            "users": self.users,
            "files": self.files,
            "blocks": self.blocks,
            "datanodes": self.datanodes,
        }
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self) -> None:
        if not self._path.exists():
            logger.info("Metadata file not found, starting with empty store: %s", self._path)
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Corrupt metadata file, starting fresh: %s", self._path)
            return
        self.users = data.get("users", {})
        self.files = data.get("files", {})
        self.blocks = data.get("blocks", {})
        self.datanodes = data.get("datanodes", {})

    def add_user(self, username: str, hashed_password: str) -> None:
        self.users[username] = hashed_password
        self.save()

    def get_user(self, username: str) -> str | None:
        return self.users.get(username)

    def _file_key(self, user: str, filename: str) -> str:
        return f"{user}/{filename}"

    def add_file(self, user: str, filename: str, record: dict[str, Any]) -> None:
        self.files[self._file_key(user, filename)] = record
        self.save()

    def get_file(self, user: str, filename: str) -> dict[str, Any] | None:
        return self.files.get(self._file_key(user, filename))

    def list_files(self, user: str) -> list[dict[str, Any]]:
        prefix = f"{user}/"
        results: list[dict[str, Any]] = []
        for key, record in self.files.items():
            if key.startswith(prefix) and record.get("status") != "deleted":
                name = key[len(prefix) :]
                results.append({**record, "filename": name})
        return results

    def delete_file(self, user: str, filename: str) -> bool:
        key = self._file_key(user, filename)
        record = self.files.get(key)
        if record is None:
            return False
        record["status"] = "deleted"
        for block_id in record.get("blocks", []):
            self.blocks.pop(block_id, None)
        self.save()
        return True

    def register_block(self, block_id: str, datanode_urls: list[str]) -> None:
        self.blocks[block_id] = datanode_urls
        self.save()

    def get_block_locations(self, block_id: str) -> list[str]:
        return self.blocks.get(block_id, [])

    def register_datanode(self, url: str) -> None:
        if url not in self.datanodes:
            self.datanodes[url] = {"last_seen": 0.0, "blocks": []}
        self.save()

    def update_datanode_blocks(self, url: str, block_ids: list[str], last_seen: float) -> None:
        if url not in self.datanodes:
            self.datanodes[url] = {"last_seen": last_seen, "blocks": block_ids}
        else:
            self.datanodes[url]["last_seen"] = last_seen
            self.datanodes[url]["blocks"] = block_ids
        self.save()
