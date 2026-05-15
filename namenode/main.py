import logging
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from namenode import auth, block_manager
from namenode.config import REPLICATION_FACTOR
from namenode.metadata import MetadataStore
from namenode.schemas import (
    BlockPlan,
    DataNodeReport,
    DirectoryRequest,
    FileInfo,
    FilePutRequest,
    Token,
    UserCreate,
    UserLogin,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("namenode.main")

app = FastAPI(title="MiniHDFS NameNode")
store = MetadataStore()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "detail": str(exc.detail)},
        )
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": str(exc)},
    )


def _count_alive_datanodes() -> int:
    now = time.time()
    return sum(
        1
        for info in store.datanodes.values()
        if now - info.get("last_seen", 0) < 60
    )


@app.get("/health")
def health() -> dict[str, Any]:
    alive = _count_alive_datanodes()
    logger.info("Health check: datanodes_alive=%d", alive)
    return {"status": "ok", "datanodes_alive": alive}


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(user: UserCreate) -> dict[str, str]:
    if store.get_user(user.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    store.add_user(user.username, auth.hash_password(user.password))
    logger.info("User registered: %s", user.username)
    return {"username": user.username, "message": "User registered successfully"}


@app.post("/auth/login", response_model=Token)
def login(credentials: UserLogin) -> Token:
    hashed = store.get_user(credentials.username)
    if hashed is None or not auth.verify_password(credentials.password, hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = auth.create_token(credentials.username)
    logger.info("User logged in: %s", credentials.username)
    return Token(access_token=token)


@app.get("/auth/me")
def me(current_user: str = Depends(auth.get_current_user)) -> dict[str, str]:
    return {"username": current_user}


@app.post("/files/put", response_model=BlockPlan)
def put_file(
    body: FilePutRequest,
    current_user: str = Depends(auth.get_current_user),
) -> BlockPlan:
    existing = store.get_file(current_user, body.filename)
    if existing is not None and existing.get("status") != "deleted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="File already exists",
        )

    plan = block_manager.compute_block_plan(
        current_user,
        body.filename,
        body.file_size,
        store.datanodes,
        REPLICATION_FACTOR,
    )

    block_ids = [assignment.block_id for assignment in plan]
    for assignment in plan:
        store.register_block(
            assignment.block_id,
            [assignment.primary_url, assignment.secondary_url],
        )
        logger.info(
            "Block assigned: block_id=%s primary=%s secondary=%s size=%d",
            assignment.block_id,
            assignment.primary_url,
            assignment.secondary_url,
            assignment.size_bytes,
        )

    record = {
        "size": body.file_size,
        "blocks": block_ids,
        "block_count": len(block_ids),
        "status": "uploading",
        "is_directory": False,
    }
    store.add_file(current_user, body.filename, record)
    logger.info(
        "File put planned: user=%s filename=%s size=%d blocks=%d",
        current_user,
        body.filename,
        body.file_size,
        len(plan),
    )

    return BlockPlan(
        filename=body.filename,
        total_blocks=len(plan),
        block_plan=plan,
    )


@app.get("/files/get/{filename}")
def get_file(
    filename: str,
    current_user: str = Depends(auth.get_current_user),
) -> dict:
    record = store.get_file(current_user, filename)
    if record is None or record.get("status") == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if record.get("is_directory"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path is a directory")

    blocks_response = []
    for block_index, block_id in enumerate(record.get("blocks", [])):
        urls = block_manager.resolve_block_locations(block_id, store)
        blocks_response.append(
            {"block_id": block_id, "replicas": urls, "block_index": block_index}
        )

    logger.info("File get: user=%s filename=%s blocks=%d", current_user, filename, len(blocks_response))
    return {
        "filename": filename,
        "size": record.get("size", 0),
        "blocks": blocks_response,
    }


@app.get("/files/ls", response_model=list[FileInfo])
def list_files(current_user: str = Depends(auth.get_current_user)) -> list[FileInfo]:
    entries = store.list_files(current_user)
    logger.info("File list: user=%s count=%d", current_user, len(entries))
    return [
        FileInfo(
            filename=entry["filename"],
            size=entry.get("size", 0),
            block_count=entry.get("block_count", 0),
            status=entry.get("status", "unknown"),
            is_directory=entry.get("is_directory", False),
        )
        for entry in entries
    ]


@app.delete("/files/rm/{filename}")
def remove_file(
    filename: str,
    current_user: str = Depends(auth.get_current_user),
) -> dict[str, str]:
    record = store.get_file(current_user, filename)
    if record is None or record.get("status") == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if record.get("is_directory"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove directory with rm; use rmdir",
        )
    if not store.delete_file(current_user, filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    logger.info("File removed: user=%s filename=%s", current_user, filename)
    return {"message": f"File '{filename}' removed"}


@app.post("/files/mkdir", status_code=status.HTTP_201_CREATED)
def mkdir(
    body: DirectoryRequest,
    current_user: str = Depends(auth.get_current_user),
) -> dict[str, str]:
    existing = store.get_file(current_user, body.dirname)
    if existing is not None and existing.get("status") != "deleted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Path already exists")
    store.add_file(
        current_user,
        body.dirname,
        {
            "size": 0,
            "blocks": [],
            "block_count": 0,
            "status": "ready",
            "is_directory": True,
        },
    )
    logger.info("Directory created: user=%s dirname=%s", current_user, body.dirname)
    return {"message": f"Directory '{body.dirname}' created"}


@app.delete("/files/rmdir/{dirname}")
def rmdir(
    dirname: str,
    current_user: str = Depends(auth.get_current_user),
) -> dict[str, str]:
    record = store.get_file(current_user, dirname)
    if record is None or record.get("status") == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Directory not found")
    if not record.get("is_directory"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path is not a directory")
    store.delete_file(current_user, dirname)
    logger.info("Directory removed: user=%s dirname=%s", current_user, dirname)
    return {"message": f"Directory '{dirname}' removed"}


@app.post("/blocks/report")
def report_blocks(body: DataNodeReport) -> dict[str, str | int]:
    now = time.time()
    store.register_datanode(body.datanode_url)
    store.update_datanode_blocks(body.datanode_url, body.block_ids, now)
    logger.info(
        "DataNode registered/reported: url=%s blocks=%d",
        body.datanode_url,
        len(body.block_ids),
    )

    known_blocks = set(store.blocks.keys())
    for block_id in body.block_ids:
        if block_id not in known_blocks:
            logger.warning(
                "Orphan block reported by %s: %s",
                body.datanode_url,
                block_id,
            )

    return {
        "message": "Block report received",
        "blocks_reported": len(body.block_ids),
    }


@app.get("/datanodes/status")
def datanodes_status() -> dict[str, list[dict]]:
    now = time.time()
    nodes = []
    for url, info in store.datanodes.items():
        last_seen = info.get("last_seen", 0)
        alive = now - last_seen < 60
        nodes.append(
            {
                "url": url,
                "alive": alive,
                "last_seen": last_seen,
                "block_count": len(info.get("blocks", [])),
            }
        )
    return {"datanodes": nodes}


@app.post("/files/confirm/{filename}")
def confirm_upload(
    filename: str,
    current_user: str = Depends(auth.get_current_user),
) -> dict[str, str]:
    record = store.get_file(current_user, filename)
    if record is None or record.get("status") == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if record.get("status") != "uploading":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File is not uploading (status={record.get('status')})",
        )

    block_ids = record.get("blocks", [])
    for block_id in block_ids:
        replica_count = 0
        for _url, info in store.datanodes.items():
            if block_id in info.get("blocks", []):
                replica_count += 1
        if replica_count < REPLICATION_FACTOR:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incomplete replication for block {block_id}: {replica_count}/{REPLICATION_FACTOR}",
            )

    record["status"] = "ready"
    store.add_file(current_user, filename, record)
    logger.info("File confirmed ready: user=%s filename=%s", current_user, filename)
    return {"message": f"File '{filename}' is ready", "status": "ready"}
