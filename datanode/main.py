import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

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
