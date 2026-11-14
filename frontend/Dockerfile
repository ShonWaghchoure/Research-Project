# Frontend (Next.js) production image.
FROM node:20-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-bookworm-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Public env baked at build time; override with --build-arg as needed.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_CHAIN_ID=31337
ARG NEXT_PUBLIC_RPC_URL=http://127.0.0.1:8545
# Demo wallets use Hardhat's public keys: only for a private local demo, never a public site.
ARG NEXT_PUBLIC_ENABLE_DEMO_WALLET=false
# Required on any chain other than 31337 (no fallback to local Hardhat addresses).
ARG NEXT_PUBLIC_MOCK_INR_ADDRESS=
ARG NEXT_PUBLIC_REGISTRY_ADDRESS=
ARG NEXT_PUBLIC_SETTLEMENT_ADDRESS=
ARG NEXT_PUBLIC_REPUTATION_ANCHOR_ADDRESS=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_CHAIN_ID=$NEXT_PUBLIC_CHAIN_ID \
    NEXT_PUBLIC_RPC_URL=$NEXT_PUBLIC_RPC_URL \
    NEXT_PUBLIC_ENABLE_DEMO_WALLET=$NEXT_PUBLIC_ENABLE_DEMO_WALLET \
    NEXT_PUBLIC_MOCK_INR_ADDRESS=$NEXT_PUBLIC_MOCK_INR_ADDRESS \
    NEXT_PUBLIC_REGISTRY_ADDRESS=$NEXT_PUBLIC_REGISTRY_ADDRESS \
    NEXT_PUBLIC_SETTLEMENT_ADDRESS=$NEXT_PUBLIC_SETTLEMENT_ADDRESS \
    NEXT_PUBLIC_REPUTATION_ANCHOR_ADDRESS=$NEXT_PUBLIC_REPUTATION_ANCHOR_ADDRESS \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
