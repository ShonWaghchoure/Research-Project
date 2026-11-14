# Smart contracts

Generated from NatSpec / public interfaces in `contracts/contracts/`. Deploy with
`npx hardhat run scripts/deploy.ts --network localhost` (default demo) or
`npm run deploy:sepolia` when `SEPOLIA_RPC_URL` and a funded `OPERATOR_PRIVATE_KEY` are set.

Addresses and ABIs: `contracts/deployments/<network>.json` (frontend snapshot:
`frontend/src/contracts/localhost.json`).

## MockINR

- **Title:** MockINR  
- **Role:** ERC-20 test INR (paise). Daily faucet for demo wallets.  
- **Key params:** faucet amount (default 100_000 paise / day).

## Registry

- **Title:** Registry  
- **Role:** Participant registry, stake lock, roles (`OPERATOR_ROLE`, `SETTLEMENT_ROLE`).  
- **Key params:** `minStake`, withdraw cooldown (1 day).  
- **Notes:** Settlement is granted `SETTLEMENT_ROLE` at deploy so it can slash / move stake.

## Settlement

- **Title:** Settlement  
- **Notice:** Commit-reveal market escrow, clearing posting, trade settlement, and shortfall slashing.  
- **Units:** Energy Wh (`uint64`), prices paise/kWh (`uint32`).  
  Payment = `qtyWh * pricePaise / 1000` (floor).  
- **Constants:** `SIDE_BUY=0`, `SIDE_SELL=1`, shortfall penalty \(f=1/10\).  
- **Flow:** `openInterval` → `commit` / `reveal` → `postClearing` → `settleTrade` →
  `postDelivery` → `settleShortfall`.  
- **Security:** AccessControl, Pausable, ReentrancyGuard, Merkle proofs where applicable.

## ReputationAnchor

- **Title:** ReputationAnchor  
- **Role:** Publishes Merkle roots of reputation scores; `verifyScore` for client proofs.  
- **Roles:** admin + operator.

## Ping

- **Title:** Ping  
- **Role:** Phase 0 smoke contract (liveness). Kept for health / deploy compatibility.

## Networks

| Network | chainId | Deployment file | Default for demos |
|---------|---------|-----------------|-------------------|
| Hardhat / localhost | 31337 | `deployments/localhost.json` | **Yes** |
| Sepolia | 11155111 | `deployments/sepolia.json` | Optional (see DEPLOY.md) |

## Verification (Sepolia)

```bash
cd contracts
SEPOLIA_RPC_URL=... OPERATOR_PRIVATE_KEY=... npm run deploy:sepolia
# Then verify each address on Etherscan (hardhat-verify / manual).
```

Local demos never require Sepolia.
