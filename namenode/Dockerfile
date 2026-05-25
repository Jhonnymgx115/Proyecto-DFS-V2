FROM python:3.11-slim

WORKDIR /app

COPY requirements-namenode.txt .
RUN pip install --no-cache-dir -r requirements-namenode.txt

COPY namenode/ ./namenode/

ENV NAMENODE_HOST=0.0.0.0
ENV NAMENODE_PORT=8000
ENV JWT_SECRET=change-me-in-production
ENV JWT_EXPIRE_HOURS=24
ENV BLOCK_SIZE_MB=64
ENV REPLICATION_FACTOR=2
ENV METADATA_FILE=/app/namenode_metadata.json

EXPOSE 8000

CMD ["uvicorn", "namenode.main:app", "--host", "0.0.0.0", "--port", "8000"]
