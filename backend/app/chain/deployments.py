"""Load contract addresses and ABIs from contracts/deployments/<network>.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CHAIN_ID_TO_FILE: dict[int, str] = {
    31337: "localhost.json",
    11155111: "sepolia.json",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def deployments_dir() -> Path:
    return repo_root() / "contracts" / "deployments"


@dataclass(frozen=True)
class ContractInfo:
    name: str
    address: str
    abi: list[dict[str, Any]]


@dataclass(frozen=True)
class DeploymentBundle:
    network: str
    chain_id: int
    contracts: dict[str, ContractInfo]
    params: dict[str, Any]

    def address(self, name: str) -> str:
        return self.contracts[name].address

    def abi(self, name: str) -> list[dict[str, Any]]:
        return self.contracts[name].abi


def deployment_path_for_chain(chain_id: int) -> Path:
    name = CHAIN_ID_TO_FILE.get(chain_id, "localhost.json")
    return deployments_dir() / name


def load_deployments(chain_id: int = 31337) -> DeploymentBundle:
    path = deployment_path_for_chain(chain_id)
    if not path.is_file():
        raise FileNotFoundError(f"deployment file not found: {path}")
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    contracts_raw = raw.get("contracts") or {}
    contracts: dict[str, ContractInfo] = {}
    for name, meta in contracts_raw.items():
        if not isinstance(meta, dict):
            continue
        addr = meta.get("address") or raw.get(name)
        abi = meta.get("abi") or []
        if not addr:
            continue
        contracts[name] = ContractInfo(name=name, address=str(addr), abi=list(abi))
    # Top-level address shortcuts if contracts block incomplete
    for name in ("MockINR", "Registry", "ReputationAnchor", "Settlement", "Ping"):
        if name not in contracts and isinstance(raw.get(name), str):
            contracts[name] = ContractInfo(name=name, address=str(raw[name]), abi=[])
    return DeploymentBundle(
        network=str(raw.get("network", path.stem)),
        chain_id=int(raw.get("chainId", chain_id)),
        contracts=contracts,
        params=dict(raw.get("params") or {}),
    )
