FROM python:3.11-slim

WORKDIR /app

COPY requirements-client.txt .
RUN pip install --no-cache-dir -r requirements-client.txt

COPY client/ ./client/

ENV NAMENODE_URL=http://namenode:8000
ENV PYTHONPATH=/app
ENV DFS_SESSION_FILE=/data/.dfs_session.json
