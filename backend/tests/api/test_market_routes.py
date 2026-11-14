from __future__ import annotations

from datetime import datetime, timedelta, timezone

from eth_account import Account
from eth_utils import to_checksum_address
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.chain.commit import compute_commit_hash
from app.db.models import (
    Delivery,
    FairnessMetric,
    Interval,
    IntervalState,
    Participant,
    ParticipantType,
    Position,
    PositionSide,
    ReputationEvent,
    ReputationScore,
    Trade,
    User,
    UserRole,
)
from tests.conftest import login


def _account(role: UserRole = UserRole.participant) -> tuple[User, str]:
    account = Account.create()
    return (
        User(
            address=to_checksum_address(account.address),
            role=role,
            nonce_used=True,
        ),
        account.key.hex(),
    )


def _seed_market(db: Session) -> tuple[Interval, Participant, Participant, Trade, str]:
    buyer_user, buyer_private_key = _account()
    seller_user, _ = _account()
    db.add_all([buyer_user, seller_user])
    db.flush()
    buyer = Participant(
        user_id=buyer_user.id,
        type=ParticipantType.consumer,
        feeder_node_id="n1",
        display_name="buyer",
    )
    seller = Participant(
        user_id=seller_user.id,
        type=ParticipantType.prosumer,
        feeder_node_id="n2",
        display_name="seller",
        pv_capacity_w=3000,
    )
    db.add_all([buyer, seller])
    db.flush()

    start = datetime.now(timezone.utc)
    interval = Interval(
        state=IntervalState.COMMIT,
        starts_at=start,
        ends_at=start + timedelta(minutes=15),
        p_ref_paise=500,
        sdr=0.75,
    )
    db.add(interval)
    db.flush()
    db.add_all(
        [
            Position(
                participant_id=buyer.id,
                interval_id=interval.id,
                side=PositionSide.buy,
                qty_wh=4000,
                limit_price_paise=700,
                revealed=True,
                commit_hash="0x" + "11" * 32,
                salt="0x" + "22" * 32,
                deadline=0,
            ),
            Position(
                participant_id=seller.id,
                interval_id=interval.id,
                side=PositionSide.sell,
                qty_wh=3000,
                limit_price_paise=350,
                revealed=True,
                commit_hash="0x" + "33" * 32,
                salt="0x" + "44" * 32,
                deadline=0,
            ),
        ]
    )
    db.flush()
    trade = Trade(
        interval_id=interval.id,
        buyer_id=buyer.id,
        seller_id=seller.id,
        qty_wh=2000,
        price_paise=500,
    )
    db.add(trade)
    db.flush()
    db.add(Delivery(interval_id=interval.id, trade_id=trade.id, delivered_wh=2000, shortfall_wh=0))
    db.add(
        FairnessMetric(
            interval_id=interval.id,
            metrics={
                "B2": {
                    "jain": 0.8,
                    "gini": 0.2,
                    "hhi": 0.5,
                    "small_actor_parity": 0.9,
                    "price_impact": 0.1,
                    "welfare_efficiency": 0.95,
                },
                "B3": {
                    "jain": 0.75,
                    "gini": 0.25,
                    "hhi": 0.55,
                    "small_actor_parity": 0.85,
                    "price_impact": 0.12,
                    "welfare_efficiency": 0.9,
                },
            },
        )
    )
    db.add(
        ReputationScore(
            participant_id=buyer.id,
            interval_id=interval.id,
            score_bp=5500,
            evidence_count=20,
            alpha=10.0,
            beta=8.0,
            tier="standard",
            leaf_hash="0x" + "55" * 32,
        )
    )
    db.add(
        ReputationEvent(
            participant_id=buyer.id,
            interval_id=interval.id,
            event_type="score_evidence",
            payload={
                "delivery": 0.9,
                "reveal": 1.0,
                "honesty": 0.8,
                "collusion_free": 0.95,
            },
        )
    )
    db.flush()
    return interval, buyer, seller, trade, buyer_private_key


def test_market_read_routes_match_frontend_contract(
    client: TestClient,
    seeded_db: Session,
) -> None:
    interval, buyer, _, trade, buyer_private_key = _seed_market(seeded_db)

    current = client.get("/intervals/current")
    assert current.status_code == 200, current.text
    interval_json = current.json()
    assert interval_json["id"] == interval.id
    assert interval_json["commit_deadline"]
    assert interval_json["reveal_deadline"]
    assert interval_json["prev_p_ref_paise"] is None
    assert interval_json["active_participants"] == 2

    history = client.get("/price-history?limit=10")
    assert history.status_code == 200, history.text
    assert len(history.json()) == 1
    assert history.json()[0]["interval_id"] == interval.id
    assert history.json()[0]["p_ref_paise"] == 500
    assert history.json()[0]["sdr"] == 0.75

    book = client.get("/orderbook")
    assert book.status_code == 200, book.text
    assert book.json()["demand_wh"] == 4000
    assert book.json()["supply_wh"] == 3000
    assert book.json()["bids"] == [{"price_paise": 700, "qty_wh": 4000}]
    assert book.json()["asks"] == [{"price_paise": 350, "qty_wh": 3000}]

    trades = client.get("/trades?limit=1")
    assert trades.status_code == 200, trades.text
    trade_json = trades.json()[0]
    assert trade_json["id"] == trade.id
    assert trade_json["buyer"] == buyer.user.address
    assert trade_json["status"] == "delivered"
    assert trade_json["side"] is None

    assert client.get("/trades?mine=true").status_code == 401
    buyer_token = login(
        client,
        seeded_db,
        buyer.user.address,
        buyer_private_key,
        UserRole.participant,
    )
    mine = client.get(
        "/trades?mine=true",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert mine.status_code == 200, mine.text
    assert mine.json()[0]["side"] == "buy"
    assert client.get(f"/trades/{trade.id}").json()["side"] is None

    rep = client.get(f"/reputation/{buyer.user.address}")
    assert rep.status_code == 200, rep.text
    assert rep.json()["score"] == 0.55
    assert rep.json()["components"] == {
        "delivery": 0.9,
        "reveal": 1.0,
        "honesty": 0.8,
        "collusion": 0.95,
    }
    assert 0 < rep.json()["volume_cap_kwh"] <= 2.0
    rep_history = client.get(f"/reputation/{buyer.user.address}/history")
    assert rep_history.status_code == 200, rep_history.text
    assert rep_history.json()["history"][0]["interval_id"] == interval.id
    assert client.get("/reputation/not-an-address").status_code == 422

    grid = client.get("/grid/status")
    assert grid.status_code == 200, grid.text
    assert len(grid.json()["nodes"]) == 13
    assert len(grid.json()["lines"]) == 12
    assert grid.json()["interval_id"] == interval.id

    fairness = client.get("/fairness/history?baseline=B3&limit=1")
    assert fairness.status_code == 200, fairness.text
    assert fairness.json()["baseline"] == "B3"
    assert fairness.json()["metrics"][0]["jain"] == 0.75
    assert client.get("/fairness/history?baseline=nope").status_code == 422


def test_position_commit_hash_and_chain_reveal_flow(
    client: TestClient,
    seeded_db: Session,
    monkeypatch,
) -> None:
    interval, _, _, _, _ = _seed_market(seeded_db)
    user, private_key = _account()
    seeded_db.add(user)
    seeded_db.flush()
    participant = Participant(
        user_id=user.id,
        type=ParticipantType.prosumer,
        feeder_node_id="n3",
        pv_capacity_w=5000,  # 5 kW x 0.25 h = 1250 Wh: enough to offer 1200 Wh (capacity cap)
    )
    seeded_db.add(participant)
    seeded_db.flush()
    token = login(client, seeded_db, user.address, private_key, UserRole.participant)
    headers = {"Authorization": f"Bearer {token}"}
    salt = "0x" + "ab" * 32
    payload = {
        "interval_id": interval.id,
        "side": "sell",
        "qty_wh": 1200,
        "limit_price_paise": 450,
        "deadline": 0,
        "salt": salt,
    }

    created = client.post("/positions", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    position = created.json()
    expected_hash = compute_commit_hash(
        interval.id,
        user.address,
        "sell",
        1200,
        450,
        0,
        salt,
    )
    assert position["commit_hash"] == expected_hash
    assert position["salt"] == salt
    assert position["id"]
    assert position["committed_tx"] is None

    class FakeChainClient:
        def is_reachable(self) -> bool:
            return True

        def on_chain_commit(self, interval_id: int, participant_address: str) -> str:
            assert interval_id == interval.id
            assert participant_address == user.address
            return expected_hash

    import app.api.positions as positions_api

    monkeypatch.setattr(positions_api, "get_chain_client", FakeChainClient)
    tx_hash = "0x" + "cd" * 32
    confirmed = client.post(
        f"/positions/{position['id']}/commit",
        headers=headers,
        json={"tx_hash": tx_hash},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["committed_tx"] == tx_hash

    interval.state = IntervalState.REVEAL
    seeded_db.flush()
    revealed = client.post(
        f"/positions/{position['id']}/reveal",
        headers=headers,
        json={"tx_hash": tx_hash},
    )
    assert revealed.status_code == 200, revealed.text
    assert revealed.json()["revealed"] is True
    assert client.post("/positions", headers=headers, json=payload).status_code == 409
