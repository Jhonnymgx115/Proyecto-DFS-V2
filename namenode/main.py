import logging
import time

from fastapi import Depends, FastAPI, HTTPException, status

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

logger = logging.getLogger("namenode.main")

app = FastAPI(title="MiniHDFS NameNode")
store = MetadataStore()


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(user: UserCreate) -> dict[str, str]:
    if store.get_user(user.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    store.add_user(user.username, auth.hash_password(user.password))
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

    record = {
        "size": body.file_size,
        "blocks": block_ids,
        "block_count": len(block_ids),
        "status": "uploading",
        "is_directory": False,
    }
    store.add_file(current_user, body.filename, record)

    return BlockPlan(
        filename=body.filename,
        total_blocks=len(plan),
        block_plan=plan,
    )
