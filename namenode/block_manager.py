import logging
import math
import time
from uuid import uuid4

from fastapi import HTTPException, status

from namenode.config import BLOCK_SIZE_BYTES, REPLICATION_FACTOR
from namenode.schemas import BlockAssignment

logger = logging.getLogger("namenode.block_manager")

DATANODE_TTL_SECONDS = 60


def _alive_datanodes(datanodes: dict[str, dict]) -> list[str]:
    now = time.time()
    alive = [
        url
        for url, info in datanodes.items()
        if now - info.get("last_seen", 0) < DATANODE_TTL_SECONDS
    ]
    return sorted(alive)


def compute_block_plan(
    username: str,
    filename: str,
    file_size: int,
    available_datanodes: dict[str, dict],
    replication_factor: int = REPLICATION_FACTOR,
) -> list[BlockAssignment]:
    alive = _alive_datanodes(available_datanodes)
    if len(alive) < replication_factor:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Not enough alive DataNodes for replication",
        )

    num_blocks = max(1, math.ceil(file_size / BLOCK_SIZE_BYTES)) if file_size > 0 else 1
    assignments: list[BlockAssignment] = []
    node_count = len(alive)
    rr_index = 0

    for index in range(num_blocks):
        if index == num_blocks - 1 and file_size > 0:
            remainder = file_size % BLOCK_SIZE_BYTES
            size_bytes = remainder if remainder != 0 else BLOCK_SIZE_BYTES
        elif file_size == 0:
            size_bytes = 0
        else:
            size_bytes = BLOCK_SIZE_BYTES

        block_id = f"{username}_{filename}_{index}_{uuid4().hex[:8]}"
        primary_url = alive[rr_index % node_count]
        secondary_url = alive[(rr_index + 1) % node_count]
        rr_index += 1

        assignments.append(
            BlockAssignment(
                block_id=block_id,
                block_index=index,
                primary_url=primary_url,
                secondary_url=secondary_url,
                size_bytes=size_bytes,
            )
        )

    return assignments
