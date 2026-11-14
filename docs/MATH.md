# Math and parameters

All prices are **paise/kWh** (100 paise = ₹1). Energy in the engine is **kWh**; on-chain quantities are **Wh**.

Source of truth for defaults: `backend/app/core/params.py` and `backend/app/reputation/params.py`.

## Tariffs and interval

| Symbol | Default | Meaning |
|--------|---------|---------|
| \(p_{\mathrm{fit}}\) | 300 | Feed-in tariff (price floor) |
| \(p_{\mathrm{ret}}\) | 800 | Retail tariff (price ceiling) |
| \(\Delta t\) | 900 s (demo 30–60 s) | Market interval |

## SDR pricing

Supply/demand ratio and raw price (Phase 1):

\[
\mathrm{SDR} = \frac{S}{D}, \quad
p_{\mathrm{raw}} = p_{\mathrm{fit}} + (p_{\mathrm{ret}} - p_{\mathrm{fit}}) \cdot \frac{1}{1 + \mathrm{SDR}^{k}}
\]

with \(k = 2\). Smoothed reference:

\[
p_{\mathrm{ref}} = \alpha\, p_{\mathrm{raw}} + (1-\alpha)\, p_{\mathrm{ref}}^{\mathrm{prev}}, \quad \alpha = 0.7
\]

(first interval uses \(p_{\mathrm{raw}}\)).

Side totals \(S,D\) use reputation weights \(w(R) = \min(1, R / R_{\mathrm{ref}})\) with \(R_{\mathrm{ref}} = 0.8\), and an optional **median quantity cap**: for each side, median over positions with \(R \ge \rho_{\min}\), then \(\mathrm{cap} = c \cdot \mathrm{median}\) (\(c = 3\)).

## Matching

Grid-aware bipartite matching on the 13-node radial feeder with line capacities. Fairness term \(\beta \le 5\%\) of \((p_{\mathrm{ret}}-p_{\mathrm{fit}})\) (default 25 paise) adjusts match priority; ablating fairness sets \(\beta = 0\).

Payment (on-chain, floor division):

\[
\mathrm{payment} = \left\lfloor \frac{q_{\mathrm{Wh}} \cdot p_{\mathrm{paise}}}{1000} \right\rfloor
\]

## Reputation (Beta + LCB)

Per-interval evidence score:

\[
s_t = w_{\mathrm{del}} r_{\mathrm{del}} + w_{\mathrm{rev}} r_{\mathrm{rev}} + w_{\mathrm{hon}}(1-a_i) + w_{\mathrm{col}}(1-c_i)
\]

Weights default \((0.45, 0.15, 0.20, 0.20)\). Evidence weight \(n_t = \min(1, v_t / v_{\mathrm{ref}})\).

Update with forgetting \(\phi = 0.5^{1/H}\), \(H = 672\):

\[
\alpha \leftarrow \phi\alpha + n_t s_t, \quad
\beta \leftarrow \phi\beta + \kappa n_t (1-s_t), \quad \kappa = 3
\]

\[
\mu = \frac{\alpha}{\alpha+\beta}, \quad
\sigma = \sqrt{\frac{\alpha\beta}{(\alpha+\beta)^2(\alpha+\beta+1)}}, \quad
R = \max(0, \mu - z\sigma)
\]

Default prior \((\alpha_0,\beta_0)=(1,2)\), \(z=1\). Ablations: \(z=0\) (no LCB), \(H\to\infty\) (no forgetting).

### Tiers

| Tier | Rule (simplified) |
|------|-------------------|
| Suspended | \(R < 0.15\) |
| Probation / newcomer | \(R < \rho_{\min}=0.30\) or low evidence |
| Trusted | \(R \ge 0.80\) and enough evidence |
| Volume cap | \(Q_{\max} = Q_{\mathrm{base}}(0.2 + 0.8 R)\) |

Participation gate: \(R \ge \rho_{\min}\) when defenses are on.

## Shortfall

Penalty fraction \(f = 0.1\) of undelivered energy valued at \(p_{\mathrm{ret}}\).

## Fairness metrics (reporting)

Jain index, Gini of gains, HHI, welfare efficiency vs grid-only baseline — computed in `app.reputation.fairness` and written by the simulator / fairness API.

## Grid model

DC-style radial feeder (13 nodes). Line loading from cleared trades; P2P curtailment when capacities bind. No reactive power, voltage bands, or losses (see RESULTS limitations).
