import { ethers } from "hardhat";
import { time } from "@nomicfoundation/hardhat-network-helpers";
import type { MockINR, Registry, ReputationAnchor, Settlement } from "../../typechain-types";
import type { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";

export const FAUCET = 100_000n;
export const MIN_STAKE = 10_000n;
export const COOLDOWN = 24n * 60n * 60n;
export const P_RET = 800;
export const P_FIT = 300;

export type Deployed = {
  token: MockINR;
  registry: Registry;
  reputation: ReputationAnchor;
  settlement: Settlement;
  admin: HardhatEthersSigner;
  operator: HardhatEthersSigner;
  users: HardhatEthersSigner[];
};

export async function deploySystem(): Promise<Deployed> {
  const signers = await ethers.getSigners();
  const [admin, operator, ...rest] = signers;

  const token = (await (await ethers.getContractFactory("MockINR")).deploy(FAUCET)) as unknown as MockINR;
  await token.waitForDeployment();

  const registry = (await (
    await ethers.getContractFactory("Registry")
  ).deploy(await token.getAddress(), MIN_STAKE, COOLDOWN, admin.address, operator.address)) as unknown as Registry;
  await registry.waitForDeployment();

  const reputation = (await (
    await ethers.getContractFactory("ReputationAnchor")
  ).deploy(admin.address, operator.address)) as unknown as ReputationAnchor;
  await reputation.waitForDeployment();

  const settlement = (await (
    await ethers.getContractFactory("Settlement")
  ).deploy(
    await token.getAddress(),
    await registry.getAddress(),
    P_RET,
    admin.address,
    operator.address
  )) as unknown as Settlement;
  await settlement.waitForDeployment();

  await registry.connect(admin).grantRole(await registry.SETTLEMENT_ROLE(), await settlement.getAddress());

  return { token, registry, reputation, settlement, admin, operator, users: rest };
}

export async function fundAndApprove(
  token: MockINR,
  registry: Registry,
  settlement: Settlement,
  user: HardhatEthersSigner,
  amount: bigint
) {
  if (!(await token.hasClaimedToday(user.address))) {
    await token.connect(user).faucet();
  }
  const bal = await token.balanceOf(user.address);
  if (bal < amount) {
    const [admin] = await ethers.getSigners();
    await token.connect(admin).mint(user.address, amount - bal);
  }
  await token.connect(user).approve(await registry.getAddress(), ethers.MaxUint256);
  await token.connect(user).approve(await settlement.getAddress(), ethers.MaxUint256);
}

export async function registerParticipant(
  token: MockINR,
  registry: Registry,
  settlement: Settlement,
  user: HardhatEthersSigner,
  meterKey: string,
  stakeAmount: bigint = MIN_STAKE
) {
  await fundAndApprove(token, registry, settlement, user, stakeAmount + 50_000n);
  await registry.connect(user).stake(stakeAmount);
  await registry.connect(user).register(meterKey);
}

export async function openInterval(
  settlement: Settlement,
  operator: HardhatEthersSigner,
  id: number,
  commitSecs = 3600,
  revealExtra = 3600
) {
  const now = await time.latest();
  const commitDeadline = BigInt(now + commitSecs);
  const revealDeadline = commitDeadline + BigInt(revealExtra);
  await settlement.connect(operator).openInterval(id, commitDeadline, revealDeadline);
  return { commitDeadline, revealDeadline };
}

export function commitHash(
  settlement: Settlement,
  intervalId: number,
  participant: string,
  side: number,
  qtyWh: number,
  limitPricePaise: number,
  deadline: number,
  salt: string
) {
  return settlement.computeCommitHash(intervalId, participant, side, qtyWh, limitPricePaise, deadline, salt);
}

export { time };
