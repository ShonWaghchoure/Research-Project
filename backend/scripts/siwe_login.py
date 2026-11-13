#!/usr/bin/env python3
"""Acceptance script: SIWE login against a running API (default http://127.0.0.1:8000).

Usage:
  python scripts/siwe_login.py [--base-url URL] [--account-index N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.hardhat_accounts import HARDHAT_ACCOUNTS  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="SIWE login smoke script")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--account-index", type=int, default=0)
    args = parser.parse_args()

    acct = HARDHAT_ACCOUNTS[args.account_index]
    with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
        nonce_resp = client.post("/auth/nonce", json={"address": acct.address})
        nonce_resp.raise_for_status()
        nonce_body = nonce_resp.json()
        message = nonce_body["message"]
        sig = Account.from_key(acct.private_key).sign_message(
            encode_defunct(text=message)
        ).signature.hex()
        if not sig.startswith("0x"):
            sig = "0x" + sig

        verify_resp = client.post(
            "/auth/verify",
            json={"address": acct.address, "message": message, "signature": sig},
        )
        verify_resp.raise_for_status()
        token_body = verify_resp.json()

        me_resp = client.get(
            "/me", headers={"Authorization": f"Bearer {token_body['access_token']}"}
        )
        me_resp.raise_for_status()

    print(
        json.dumps(
            {
                "ok": True,
                "address": token_body["address"],
                "role": token_body["role"],
                "me": me_resp.json(),
                "access_token_prefix": token_body["access_token"][:24] + "…",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
