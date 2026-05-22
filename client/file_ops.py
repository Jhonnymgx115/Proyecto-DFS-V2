"""Cliente DFS: orquesta NameNode (metadatos) y DataNodes (bloques)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from client.config import CONFIRM_POLL_SECONDS, CONFIRM_TIMEOUT_SECONDS, NAMENODE_URL, SESSION_FILE

logger = logging.getLogger("client.file_ops")


class DfsError(Exception):
    """Error de operación contra el DFS."""


class DfsAuthError(DfsError):
    """Falta autenticación o credenciales inválidas."""


class DfsClient:
    def __init__(self, namenode_url: str | None = None, token: str | None = None) -> None:
        self.namenode_url = (namenode_url or NAMENODE_URL).rstrip("/")
        self.token = token
        self._http = httpx.Client(timeout=120.0)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> DfsClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @property
    def auth_headers(self) -> dict[str, str]:
        if not self.token:
            raise DfsAuthError("Not authenticated. Run login first.")
        return {"Authorization": f"Bearer {self.token}"}

    def _namenode_request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        url = f"{self.namenode_url}{path}"
        headers = kwargs.pop("headers", {})
        if auth:
            headers.update(self.auth_headers)
        try:
            response = self._http.request(method, url, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise DfsError(f"NameNode unreachable ({url}): {exc}") from exc
        return response

    def _datanode_request(self, method: str, base_url: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{base_url.rstrip('/')}{path}"
        try:
            return self._http.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise DfsError(f"DataNode unreachable ({url}): {exc}") from exc

    def register(self, username: str, password: str) -> dict[str, str]:
        response = self._namenode_request(
            "POST",
            "/auth/register",
            auth=False,
            json={"username": username, "password": password},
        )
        if response.status_code not in (200, 201):
            raise DfsError(self._error_detail(response))
        return response.json()

    def login(self, username: str, password: str) -> str:
        response = self._namenode_request(
            "POST",
            "/auth/login",
            auth=False,
            json={"username": username, "password": password},
        )
        if response.status_code != 200:
            raise DfsAuthError(self._error_detail(response))
        self.token = response.json()["access_token"]
        return self.token

    def save_session(self, username: str) -> None:
        if not self.token:
            raise DfsAuthError("No token to save")
        SESSION_FILE.write_text(
            json.dumps({"username": username, "token": self.token, "namenode_url": self.namenode_url}),
            encoding="utf-8",
        )

    @classmethod
    def load_session(cls) -> DfsClient | None:
        if not SESSION_FILE.exists():
            return None
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        client = cls(namenode_url=data.get("namenode_url"), token=data.get("token"))
        me = client._namenode_request("GET", "/auth/me")
        if me.status_code != 200:
            SESSION_FILE.unlink(missing_ok=True)
            return None
        return client

    def put_file(self, local_path: str | Path, remote_name: str | None = None) -> dict[str, Any]:
        path = Path(local_path)
        if not path.is_file():
            raise DfsError(f"Local file not found: {path}")
        filename = remote_name or path.name
        file_size = path.stat().st_size

        plan_resp = self._namenode_request(
            "POST",
            "/files/put",
            json={"filename": filename, "file_size": file_size},
        )
        if plan_resp.status_code != 200:
            raise DfsError(self._error_detail(plan_resp))

        plan = plan_resp.json()
        assignments = sorted(plan["block_plan"], key=lambda b: b["block_index"])
        datanode_urls: set[str] = set()

        with path.open("rb") as fh:
            offset = 0
            for assignment in assignments:
                size = assignment["size_bytes"]
                chunk = fh.read(size) if size > 0 else b""
                offset += len(chunk)
                block_id = assignment["block_id"]
                primary = assignment["primary_url"]
                secondary = assignment["secondary_url"]
                datanode_urls.add(primary)
                datanode_urls.add(secondary)

                put_resp = self._datanode_request(
                    "PUT",
                    primary,
                    f"/blocks/{block_id}",
                    content=chunk,
                    headers={"Content-Type": "application/octet-stream"},
                )
                if put_resp.status_code not in (200, 201):
                    raise DfsError(
                        f"Failed to upload block {block_id} to {primary}: {self._error_detail(put_resp)}"
                    )

                rep_resp = self._datanode_request(
                    "POST",
                    primary,
                    f"/blocks/{block_id}/replicate",
                    params={"target_url": secondary},
                )
                if rep_resp.status_code not in (200, 201):
                    raise DfsError(
                        f"Replication failed for {block_id} -> {secondary}: {self._error_detail(rep_resp)}"
                    )
                logger.info("Block %s uploaded and replicated (%d bytes)", block_id, len(chunk))

        self._refresh_datanode_reports(datanode_urls)
        self._wait_for_confirm(filename)

        return {
            "filename": filename,
            "size": file_size,
            "blocks": len(assignments),
            "status": "ready",
        }

    def get_file(self, remote_name: str, local_path: str | Path) -> Path:
        meta_resp = self._namenode_request("GET", f"/files/get/{remote_name}")
        if meta_resp.status_code != 200:
            raise DfsError(self._error_detail(meta_resp))

        meta = meta_resp.json()
        blocks = sorted(meta["blocks"], key=lambda b: b["block_index"])
        out = Path(local_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        with out.open("wb") as fh:
            for block in blocks:
                data = self._download_block(block)
                fh.write(data)

        return out

    def list_files(self) -> list[dict[str, Any]]:
        response = self._namenode_request("GET", "/files/ls")
        if response.status_code != 200:
            raise DfsError(self._error_detail(response))
        return response.json()

    def remove_file(self, filename: str) -> dict[str, str]:
        response = self._namenode_request("DELETE", f"/files/rm/{filename}")
        if response.status_code != 200:
            raise DfsError(self._error_detail(response))
        return response.json()

    def mkdir(self, dirname: str) -> dict[str, str]:
        response = self._namenode_request("POST", "/files/mkdir", json={"dirname": dirname})
        if response.status_code not in (200, 201):
            raise DfsError(self._error_detail(response))
        return response.json()

    def rmdir(self, dirname: str) -> dict[str, str]:
        response = self._namenode_request("DELETE", f"/files/rmdir/{dirname}")
        if response.status_code != 200:
            raise DfsError(self._error_detail(response))
        return response.json()

    def health(self) -> dict[str, Any]:
        response = self._namenode_request("GET", "/health", auth=False)
        if response.status_code != 200:
            raise DfsError(self._error_detail(response))
        return response.json()

    def _download_block(self, block: dict[str, Any]) -> bytes:
        replicas = block.get("replicas") or []
        block_id = block["block_id"]
        last_error = "no replicas"
        for replica_url in replicas:
            resp = self._datanode_request("GET", replica_url, f"/blocks/{block_id}")
            if resp.status_code == 200:
                return resp.content
            last_error = self._error_detail(resp)
        raise DfsError(f"Could not download block {block_id}: {last_error}")

    def _refresh_datanode_reports(self, datanode_urls: set[str]) -> None:
        for url in datanode_urls:
            try:
                self._datanode_request("POST", url, "/report")
            except DfsError as exc:
                logger.warning("Report to %s failed: %s", url, exc)

    def _wait_for_confirm(self, filename: str) -> None:
        deadline = time.time() + CONFIRM_TIMEOUT_SECONDS
        while time.time() < deadline:
            resp = self._namenode_request("POST", f"/files/confirm/{filename}")
            if resp.status_code == 200:
                return
            detail = self._error_detail(resp)
            if resp.status_code not in (400, 503):
                raise DfsError(detail)
            logger.debug("Confirm pending for %s: %s", filename, detail)
            time.sleep(CONFIRM_POLL_SECONDS)
        raise DfsError(f"Timeout waiting for file '{filename}' to become ready")

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
            return str(body.get("detail") or body.get("error") or body)
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:200]}"
