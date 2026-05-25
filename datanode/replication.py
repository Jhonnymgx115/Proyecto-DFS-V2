import logging

import httpx

from datanode.config import REPLICATION_TIMEOUT_SECONDS
from datanode.storage import block_exists, read_block

logger = logging.getLogger("datanode.replication")


def replicate_block(block_id: str, target_url: str) -> bool:
    if not block_exists(block_id):
        logger.error("Replication failed: block not found locally: %s", block_id)
        return False

    data = read_block(block_id)
    url = f"{target_url.rstrip('/')}/blocks/{block_id}"

    try:
        response = httpx.put(
            url,
            content=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=REPLICATION_TIMEOUT_SECONDS,
        )
        if response.status_code in (200, 201, 409):
            logger.info("Replicated block %s -> %s (status=%d)", block_id, target_url, response.status_code)
            return True
        logger.warning("Replication unexpected status %d for block %s -> %s", response.status_code, block_id, target_url)
        return False
    except httpx.RequestError as exc:
        logger.error("Replication request error block %s -> %s: %s", block_id, target_url, exc)
        return False


def replicate_blocks(block_ids: list[str], target_url: str) -> dict[str, bool]:
    return {bid: replicate_block(bid, target_url) for bid in block_ids}
