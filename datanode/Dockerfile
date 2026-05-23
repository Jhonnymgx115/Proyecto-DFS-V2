FROM python:3.11-slim

WORKDIR /app

COPY requirements-datanode.txt .
RUN pip install --no-cache-dir -r requirements-datanode.txt

COPY datanode/ ./datanode/

ENV DATANODE_HOST=0.0.0.0
ENV DATANODE_PORT=8001
ENV STORAGE_DIR=/data/blocks

EXPOSE 8001

CMD ["sh", "-c", "uvicorn datanode.main:app --host $DATANODE_HOST --port $DATANODE_PORT"]
