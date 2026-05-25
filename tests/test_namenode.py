import os
import time

import pytest
from fastapi.testclient import TestClient

os.environ["JWT_SECRET"] = "test-secret-key"
os.environ["METADATA_FILE"] = "test_namenode_metadata.json"
os.environ["REPLICATION_FACTOR"] = "2"
os.environ["BLOCK_SIZE_MB"] = "64"

from namenode.main import app, store  # noqa: E402

DN1 = "http://datanode1:5001"
DN2 = "http://datanode2:5002"


@pytest.fixture(autouse=True)
def clean_metadata(tmp_path, monkeypatch):
    metadata_file = tmp_path / "metadata.json"
    monkeypatch.setenv("METADATA_FILE", str(metadata_file))
    store.users.clear()
    store.files.clear()
    store.blocks.clear()
    store.datanodes.clear()
    store._path = metadata_file
    yield
    if metadata_file.exists():
        metadata_file.unlink()


@pytest.fixture
def client():
    return TestClient(app)


def _register_datanodes(client: TestClient) -> None:
    now = time.time()
    for url in (DN1, DN2):
        store.register_datanode(url)
        store.update_datanode_blocks(url, [], now)
    client.post("/blocks/report", json={"datanode_url": DN1, "block_ids": []})
    client.post("/blocks/report", json={"datanode_url": DN2, "block_ids": []})


def test_register_login_and_token_validation(client: TestClient):
    response = client.post(
        "/auth/register",
        json={"username": "alice", "password": "secret123"},
    )
    assert response.status_code == 201

    login = client.post(
        "/auth/login",
        json={"username": "alice", "password": "secret123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    invalid = client.get("/auth/me", headers={"Authorization": "Bearer invalid"})
    assert invalid.status_code == 401


def test_put_plan_with_mock_datanodes(client: TestClient):
    client.post("/auth/register", json={"username": "bob", "password": "pass"})
    login = client.post("/auth/login", json={"username": "bob", "password": "pass"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    _register_datanodes(client)

    put = client.post(
        "/files/put",
        json={"filename": "data.bin", "file_size": 1024},
        headers=headers,
    )
    assert put.status_code == 200
    body = put.json()
    assert body["filename"] == "data.bin"
    assert body["total_blocks"] >= 1
    assert len(body["block_plan"]) == body["total_blocks"]
    assert body["block_plan"][0]["primary_url"] in (DN1, DN2)


def test_ls_returns_file_list(client: TestClient):
    client.post("/auth/register", json={"username": "carol", "password": "pass"})
    login = client.post("/auth/login", json={"username": "carol", "password": "pass"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    _register_datanodes(client)
    client.post("/files/put", json={"filename": "doc.txt", "file_size": 512}, headers=headers)

    ls = client.get("/files/ls", headers=headers)
    assert ls.status_code == 200
    files = ls.json()
    assert len(files) == 1
    assert files[0]["filename"] == "doc.txt"
    assert files[0]["status"] == "uploading"


def test_rm_removes_file(client: TestClient):
    client.post("/auth/register", json={"username": "dave", "password": "pass"})
    login = client.post("/auth/login", json={"username": "dave", "password": "pass"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    _register_datanodes(client)
    client.post("/files/put", json={"filename": "temp.dat", "file_size": 256}, headers=headers)

    rm = client.delete("/files/rm/temp.dat", headers=headers)
    assert rm.status_code == 200

    ls = client.get("/files/ls", headers=headers)
    assert ls.json() == []


def test_heartbeat_updates_datanode_status(client: TestClient):
    report = client.post(
        "/blocks/report",
        json={"datanode_url": DN1, "block_ids": ["orphan-block"]},
    )
    assert report.status_code == 200

    status_resp = client.get("/datanodes/status")
    assert status_resp.status_code == 200
    nodes = status_resp.json()["datanodes"]
    assert len(nodes) == 1
    assert nodes[0]["url"] == DN1
    assert nodes[0]["alive"] is True
