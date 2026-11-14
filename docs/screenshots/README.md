# Screenshots

Capture after `make demo` (browser at http://localhost:3000):

| File | Page |
|------|------|
| `landing.png` | `/` |
| `dashboard.png` | `/dashboard` |
| `trade.png` | `/trade` |
| `market.png` | `/market` |
| `grid.png` | `/grid` |
| `reputation.png` | `/reputation` |
| `fairness.png` | `/fairness` |
| `attack.png` | `/attack` |
| `audit.png` | `/audit` |
| `admin.png` | `/admin` |
| `status.png` | `/status` |

Optional helper (Playwright installed in frontend):

```bash
cd frontend && npx playwright screenshot http://localhost:3000/market ../docs/screenshots/market.png
```

The architecture diagram is textual in [`ARCHITECTURE.md`](../ARCHITECTURE.md).
