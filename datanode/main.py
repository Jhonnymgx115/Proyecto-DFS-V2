import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response

from datanode import storage
from datanode.config import DATANODE_URL, NAMENODE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("datanode.main")

app = FastAPI(title="MiniHDFS DataNode")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if hasattr(exc, "status_code"):
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": str(exc)},
    )


@app.on_event("startup")
async def startup() -> None:
    storage.init_storage()
    logger.info("DataNode started: url=%s namenode=%s", DATANODE_URL, NAMENODE_URL)


@app.get("/health")
def health() -> dict:
    stats = storage.storage_stats()
    return {"status": "ok", "datanode_url": DATANODE_URL, **stats}


@app.put("/blocks/{block_id}", status_code=status.HTTP_201_CREATED)
async def put_block(block_id: str, request: Request) -> dict:
    data = await request.body()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty block data")
    if storage.block_exists(block_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Block already exists")
    size = storage.write_block(block_id, data)
    logger.info("PUT block: block_id=%s size=%d", block_id, size)
    return {"block_id": block_id, "size": size}


@app.get("/blocks/{block_id}")
def get_block(block_id: str) -> Response:
    try:
        data = storage.read_block(block_id)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    logger.info("GET block: block_id=%s size=%d", block_id, len(data))
    return Response(content=data, media_type="application/octet-stream")
