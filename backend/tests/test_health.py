from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_keys_present():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "postgres" in data
    assert "redis" in data
    assert "chain_rpc" in data
    assert "block_number" in data
    assert "chain_id" in data


def test_health_mocked_success():
    with (
        patch("app.main.engine.connect") as mock_connect,
        patch("app.main.redis.Redis.from_url") as mock_redis_cls,
        patch("app.main.Web3") as mock_web3_cls,
    ):
        # Mock Postgres
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock Redis
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis_cls.return_value = mock_redis

        # Mock Web3
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.block_number = 42
        mock_web3_cls.return_value = mock_w3

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["postgres"] == "ok"
        assert data["redis"] == "ok"
        assert data["chain_rpc"] == "ok"
        assert data["block_number"] == 42
        assert data["chain_id"] == 31337
