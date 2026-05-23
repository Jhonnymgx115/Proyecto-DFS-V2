import asyncio
import logging

import httpx

from datanode.config import DATANODE_URL, HEARTBEAT_INTERVAL_SECONDS, NAMENODE_URL
from datanode.storage import list_blocks

logger = logging.getLogger("datanode.heartbeat")


async def send_heartbeat() -> bool:
    payload = {
        "datanode_url": DATANODE_URL,
        "block_ids": list_blocks(),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{NAMENODE_URL}/blocks/report", json=payload)
        if response.status_code == 200:
            logger.info("Heartbeat sent: blocks=%d", len(payload["block_ids"]))
            return True
        logger.warning("Heartbeat rejected: status=%d", response.status_code)
        return False
    except httpx.RequestError as exc:
        logger.error("Heartbeat failed: %s", exc)
        return False


async def heartbeat_loop() -> None:
    logger.info("Heartbeat loop started (interval=%ds)", HEARTBEAT_INTERVAL_SECONDS)
    while True:
        await send_heartbeat()
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
