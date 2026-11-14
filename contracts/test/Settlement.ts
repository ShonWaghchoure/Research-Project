import { expect } from "chai";
import { ethers } from "hardhat";
import type { HardhatEthersSigner } from "@nomicfoundation/hardhat-ethers/signers";
import {
  MIN_STAKE,
  P_RET,
  commitHash,
  deploySystem,
  fundAndApprove,
  openInterval,
  registerParticipant,
  time,
} from "./helpers/fixtures";
import { buildMerkleTree, getProof, shortfallLeaf } from "./helpers/merkle";

describe("Settlement", function () {
  async function activate(sys: Awaited<ReturnType<typeof deploySystem>>, u: HardhatEthersSigner, stake = MIN_STAKE) {
    await registerParticipant(sys.token, sys.registry, sys.settlement, u, ethers.id(`meter:${u.address}`), stake);
  }

  async function setupBuyerSeller() {
    const sys = await deploySystem();
    const { token, registry, settlement, users } = sys;
    const buyer = users[0];
    const seller = users[1];
    await registerParticipant(token, registry, settlement, buyer, ethers.id("buyer"));
    await registerParticipant(token, registry, settlement, seller, ethers.id("seller"), MIN_STAKE + 50_000n);
    await fundAndApprove(token, registry, settlement, buyer, 200_000n);
    await settlement.connect(buyer).deposit(100_000n);
    return { ...sys, buyer, seller };
  }

  /** Open interval 1, have buyer and seller commit, close reveal, post clearing at pRef. */
  async function clearedInterval(pRef = 500) {
    const sys = await setupBuyerSeller();
    const { settlement, operator, buyer, seller } = sys;
    const { revealDeadline } = await openInterval(settlement, operator, 1, 50, 50);
    await settlement.connect(buyer).commitPosition(1, ethers.id("buyer-c"));
    await settlement.connect(seller).commitPosition(1, ethers.id("seller-c"));
    await time.increaseTo(revealDeadline);
    await settlement.connect(operator).postClearing(1, ethers.id("in"), ethers.id("out"), pRef);
    return { ...sys, revealDeadline };
  }

  it("openInterval access and deadline checks", async function () {
    const { settlement, operator, users } = await deploySystem();
    const now = await time.latest();
    await expect(
      settlement.connect(users[0]).openInterval(1, now + 100, now + 200)
    ).to.be.revertedWithCustomError(settlement, "AccessControlUnauthorizedAccount");

    await expect(settlement.connect(operator).openInterval(1, now - 1, now + 100)).to.be.revertedWith(
      "Settlement: commit deadline"
    );
    await expect(settlement.connect(operator).openInterval(1, now + 200, now + 100)).to.be.revertedWith(
      "Settlement: reveal deadline"
    );

    await expect(settlement.connect(operator).openInterval(1, now + 100, now + 200))
      .to.emit(settlement, "IntervalOpened");
    await expect(settlement.connect(operator).openInterval(1, now + 100, now + 200)).to.be.revertedWith(
      "Settlement: already open"
    );
  });

  it("commitPosition: one per participant, before deadline only", async function () {
    const sys = await deploySystem();
    const { settlement, operator, users } = sys;
    const [u] = users;
    await activate(sys, u);
    const { commitDeadline } = await openInterval(settlement, operator, 1, 100, 100);
    const hash = await commitHash(settlement, 1, u.address, 0, 1000, 800, Number(commitDeadline), ethers.id("s1"));

    await expect(settlement.connect(u).commitPosition(1, hash))
      .to.emit(settlement, "PositionCommitted")
      .withArgs(1, u.address, hash);
    await expect(settlement.connect(u).commitPosition(1, hash)).to.be.revertedWith(
      "Settlement: already committed"
    );
    await expect(settlement.connect(u).commitPosition(1, ethers.ZeroHash)).to.be.revertedWith(
      "Settlement: empty commit"
    );

    await time.increaseTo(commitDeadline);
    await expect(settlement.connect(users[1]).commitPosition(1, ethers.id("late"))).to.be.revertedWith(
      "Settlement: commit closed"
    );
  });

  it("only registered, unsuspended, sufficiently staked accounts can commit", async function () {
    const sys = await deploySystem();
    const { settlement, registry, operator, users } = sys;
    await openInterval(settlement, operator, 1, 1000, 1000);
    // Never registered
    await expect(settlement.connect(users[0]).commitPosition(1, ethers.id("x"))).to.be.revertedWith(
      "Settlement: not active"
    );
    // Suspended
    await activate(sys, users[1]);
    await registry.connect(operator).suspend(users[1].address);
    await expect(settlement.connect(users[1]).commitPosition(1, ethers.id("y"))).to.be.revertedWith(
      "Settlement: not active"
    );
    expect(await registry.isActive(users[1].address)).to.equal(false);
  });

  it("replayed commit hash allowed in a new interval (fresh slot)", async function () {
    const sys = await deploySystem();
    const { settlement, operator, users } = sys;
    const [u] = users;
    await activate(sys, u);
    await openInterval(settlement, operator, 1, 1000, 1000);
    const h = ethers.id("same-bytes");
    await settlement.connect(u).commitPosition(1, h);

    // Same hash in another interval is a new interval slot (intervalId is in off-chain preimage).
    await openInterval(settlement, operator, 2, 1000, 1000);
    await expect(settlement.connect(u).commitPosition(2, h))
      .to.emit(settlement, "PositionCommitted")
      .withArgs(2, u.address, h);

    // But double-commit in same interval still blocked.
    await expect(settlement.connect(u).commitPosition(2, ethers.id("other"))).to.be.revertedWith(
      "Settlement: already committed"
    );
  });

  it("deposit and withdrawEscrow", async function () {
    const { token, registry, settlement, users } = await deploySystem();
    const [u] = users;
    await fundAndApprove(token, registry, settlement, u, 50_000n);
    await settlement.connect(u).deposit(10_000n);
    expect(await settlement.escrow(u.address)).to.equal(10_000n);
    await settlement.connect(u).withdrawEscrow(4_000n);
    expect(await settlement.escrow(u.address)).to.equal(6_000n);
    await expect(settlement.connect(u).withdrawEscrow(99_000n)).to.be.revertedWith(
      "Settlement: insufficient escrow"
    );
  });

  it("postClearing only after reveal closes; settleBatch moves escrow at pRef", async function () {
    const { settlement, operator, buyer, seller } = await setupBuyerSeller();
    const { revealDeadline } = await openInterval(settlement, operator, 1, 50, 50);
    await settlement.connect(buyer).commitPosition(1, ethers.id("buyer-c"));
    await settlement.connect(seller).commitPosition(1, ethers.id("seller-c"));

    await expect(
      settlement.connect(operator).postClearing(1, ethers.id("in"), ethers.id("out"), 500)
    ).to.be.revertedWith("Settlement: reveal open");

    await time.increaseTo(revealDeadline);
    await expect(
      settlement.connect(buyer).postClearing(1, ethers.id("in"), ethers.id("out"), 500)
    ).to.be.revertedWithCustomError(settlement, "AccessControlUnauthorizedAccount");

    await expect(settlement.connect(operator).postClearing(1, ethers.id("in"), ethers.id("out"), 500))
      .to.emit(settlement, "ClearingPosted")
      .withArgs(1, ethers.id("in"), ethers.id("out"), 500);

    const trade = {
      buyer: buyer.address,
      seller: seller.address,
      qtyWh: 2000n,
      pricePaise: 500,
    };
    const payment = (2000n * 500n) / 1000n;
    const buyerBefore = await settlement.escrow(buyer.address);
    const sellerBefore = await settlement.escrow(seller.address);

    await expect(settlement.connect(operator).settleBatch(1, [trade]))
      .to.emit(settlement, "TradeSettled")
      .withArgs(1, buyer.address, seller.address, 2000n, 500, payment);

    expect(await settlement.escrow(buyer.address)).to.equal(buyerBefore - payment);
    expect(await settlement.escrow(seller.address)).to.equal(sellerBefore + payment);

    // wrong price
    await expect(
      settlement.connect(operator).settleBatch(1, [{ ...trade, qtyWh: 1n, pricePaise: 501 }])
    ).to.be.revertedWith("Settlement: price != pRef");

    // double settlement
    await expect(settlement.connect(operator).settleBatch(1, [trade])).to.be.revertedWith(
      "Settlement: already settled"
    );
  });

  it("the same match cannot be settled again with a different quantity", async function () {
    const { settlement, operator, buyer, seller } = await clearedInterval();
    await settlement
      .connect(operator)
      .settleBatch(1, [{ buyer: buyer.address, seller: seller.address, qtyWh: 1n, pricePaise: 500 }]);
    for (const qty of [2n, 3n, 90_000n]) {
      await expect(
        settlement.connect(operator).settleBatch(1, [{ buyer: buyer.address, seller: seller.address, qtyWh: qty, pricePaise: 500 }])
      ).to.be.revertedWith("Settlement: already settled");
    }
  });

  it("cannot settle a trade for an account that did not commit in the interval", async function () {
    const sys = await clearedInterval();
    const { settlement, operator, token, registry, buyer, seller, users } = sys;
    // A depositor who never committed: an operator key must not be able to drain them.
    const bystander = users[3];
    await fundAndApprove(token, registry, settlement, bystander, 50_000n);
    await settlement.connect(bystander).deposit(50_000n);
    await expect(
      settlement.connect(operator).settleBatch(1, [{ buyer: bystander.address, seller: seller.address, qtyWh: 1000n, pricePaise: 500 }])
    ).to.be.revertedWith("Settlement: party not committed");
    await expect(
      settlement.connect(operator).settleBatch(1, [{ buyer: buyer.address, seller: bystander.address, qtyWh: 1000n, pricePaise: 500 }])
    ).to.be.revertedWith("Settlement: party not committed");
    expect(await settlement.escrow(bystander.address)).to.equal(50_000n);
  });

  it("buyer escrow is locked between commit and delivery, unlocked after delivery or timeout", async function () {
    const { settlement, operator, buyer, revealDeadline } = await clearedInterval(800);
    expect(await settlement.escrowUnlocked(buyer.address)).to.equal(false);
    await expect(settlement.connect(buyer).withdrawEscrow(1n)).to.be.revertedWith("Settlement: escrow locked");

    await settlement.connect(operator).postDelivery(1, ethers.id("delivery"));
    expect(await settlement.escrowUnlocked(buyer.address)).to.equal(true);
    await settlement.connect(buyer).withdrawEscrow(1n);

    // Timeout escape hatch when delivery is never posted.
    const sys2 = await clearedInterval(800);
    await time.increaseTo(BigInt(sys2.revealDeadline) + 24n * 3600n + 1n);
    await sys2.settlement.connect(sys2.buyer).withdrawEscrow(1n);
    expect(revealDeadline).to.be.greaterThan(0n);
  });

  it("buyer with too little escrow cannot settle", async function () {
    const sys = await clearedInterval(800);
    const { settlement, operator, seller, users } = sys;
    const poorBuyer = users[2];
    // Registered and committed, but never deposited.
    await activate(sys, poorBuyer);
    // poorBuyer cannot commit into interval 1 (commit closed), so use interval 2.
    const { revealDeadline } = await openInterval(settlement, operator, 2, 50, 50);
    await settlement.connect(poorBuyer).commitPosition(2, ethers.id("poor"));
    await settlement.connect(seller).commitPosition(2, ethers.id("seller-2"));
    await time.increaseTo(revealDeadline);
    await settlement.connect(operator).postClearing(2, ethers.id("in2"), ethers.id("out2"), 800);
    await expect(
      settlement.connect(operator).settleBatch(2, [
        { buyer: poorBuyer.address, seller: seller.address, qtyWh: 1000n, pricePaise: 800 },
      ])
    ).to.be.revertedWith("Settlement: buyer escrow");
  });

  it("participant who never reveals: commit exists, no trade settled for them", async function () {
    const sys = await setupBuyerSeller();
    const { settlement, operator, buyer, seller, users } = sys;
    const ghost = users[2];
    await activate(sys, ghost);
    const { commitDeadline, revealDeadline } = await openInterval(settlement, operator, 1, 100, 100);
    const ghostHash = await commitHash(
      settlement,
      1,
      ghost.address,
      0,
      5000,
      P_RET,
      Number(commitDeadline),
      ethers.id("ghost")
    );
    await settlement.connect(ghost).commitPosition(1, ghostHash);
    await settlement.connect(buyer).commitPosition(1, ethers.id("buyer-c"));
    await settlement.connect(seller).commitPosition(1, ethers.id("seller-c"));

    await time.increaseTo(revealDeadline);
    await settlement.connect(operator).postClearing(1, ethers.id("in"), ethers.id("out"), 500);
    await settlement.connect(operator).settleBatch(1, [
      { buyer: buyer.address, seller: seller.address, qtyWh: 1000n, pricePaise: 500 },
    ]);

    expect(await settlement.commits(1, ghost.address)).to.equal(ghostHash);
    // ghost never appears in trades — escrow unchanged if they deposited nothing
    expect(await settlement.escrow(ghost.address)).to.equal(0n);
  });

  it("under-delivery: buyer gets refund + compensation from seller stake, penalty to treasury", async function () {
    const { token, registry, settlement, operator, buyer, seller } = await clearedInterval(500);
    const pRef = 500;

    const shortfallWh = 2000n;
    const leaf = shortfallLeaf(1, seller.address, buyer.address, shortfallWh);
    const { root } = buildMerkleTree([leaf]);
    await settlement.connect(operator).postDelivery(1, root);

    const refund = (shortfallWh * BigInt(pRef)) / 1000n;
    const compensation = (shortfallWh * BigInt(P_RET - pRef)) / 1000n;
    const penalty = (shortfallWh * BigInt(pRef) * 1n) / (1000n * 10n);
    const stakeBefore = (await registry.getParticipant(seller.address)).stake;
    const buyerTokenBefore = await token.balanceOf(buyer.address);

    await expect(
      settlement.connect(operator).settleShortfall(1, seller.address, shortfallWh, [], buyer.address)
    )
      .to.emit(settlement, "ShortfallSettled")
      .withArgs(1, seller.address, buyer.address, shortfallWh, refund, compensation, penalty);

    expect((await registry.getParticipant(seller.address)).stake).to.equal(stakeBefore - refund - compensation - penalty);
    // Buyer ends up whole: refund of what it paid for undelivered energy + grid premium.
    expect(await token.balanceOf(buyer.address)).to.equal(buyerTokenBefore + refund + compensation);
    expect(await settlement.treasury()).to.equal(penalty);

    await expect(
      settlement.connect(operator).settleShortfall(1, seller.address, shortfallWh, [], buyer.address)
    ).to.be.revertedWith("Settlement: shortfall done");
  });

  it("each short-changed buyer of the same seller is compensated (leaf names the buyer)", async function () {
    const sys = await clearedInterval(500);
    const { settlement, operator, token, seller, buyer, users } = sys;
    const buyer2 = users[4];
    const leafA = shortfallLeaf(1, seller.address, buyer.address, 300n);
    const leafB = shortfallLeaf(1, seller.address, buyer2.address, 200n);
    const leaves = [leafA, leafB];
    const { root } = buildMerkleTree(leaves);
    await settlement.connect(operator).postDelivery(1, root);

    const before2 = await token.balanceOf(buyer2.address);
    await settlement.connect(operator).settleShortfall(1, seller.address, 300n, getProof(leaves, 0), buyer.address);
    await settlement.connect(operator).settleShortfall(1, seller.address, 200n, getProof(leaves, 1), buyer2.address);
    expect(await token.balanceOf(buyer2.address)).to.equal(before2 + (200n * BigInt(P_RET)) / 1000n);

    // A proof for one buyer cannot be redirected to another address.
    await expect(
      settlement.connect(operator).settleShortfall(1, seller.address, 300n, getProof(leaves, 0), users[5].address)
    ).to.be.revertedWith("Settlement: bad proof");
  });

  it("a seller cannot escape a shortfall by requesting withdrawal first", async function () {
    const { registry, settlement, operator, buyer, seller } = await clearedInterval(500);
    // Seller staked MIN_STAKE + 50_000; queue everything above the minimum for withdrawal.
    await registry.connect(seller).requestWithdraw();
    expect((await registry.getParticipant(seller.address)).stake).to.equal(MIN_STAKE);

    const shortfallWh = 30_000n; // total slash 30_000*800/1000 + 1_500 = 25_500 > MIN_STAKE
    const leaf = shortfallLeaf(1, seller.address, buyer.address, shortfallWh);
    await settlement.connect(operator).postDelivery(1, buildMerkleTree([leaf]).root);
    await settlement.connect(operator).settleShortfall(1, seller.address, shortfallWh, [], buyer.address);

    const p = await registry.getParticipant(seller.address);
    expect(p.stake).to.equal(0n);
    expect(p.pendingWithdraw).to.equal(MIN_STAKE + 50_000n - 25_500n);
  });

  it("an uncovered shortfall slashes what exists, pays the buyer first, and does not revert", async function () {
    const sys = await clearedInterval(500);
    const { registry, settlement, operator, token, buyer, users } = sys;
    // A seller with only the minimum stake.
    const thin = users[6];
    await activate(sys, thin);
    const { revealDeadline } = await openInterval(settlement, operator, 2, 50, 50);
    await settlement.connect(thin).commitPosition(2, ethers.id("thin"));
    await settlement.connect(buyer).commitPosition(2, ethers.id("b2"));
    await time.increaseTo(revealDeadline);
    await settlement.connect(operator).postClearing(2, ethers.id("i"), ethers.id("o"), 500);
    const shortfallWh = 50_000n; // owes 40_000 to the buyer, stake is 10_000
    const leaf = shortfallLeaf(2, thin.address, buyer.address, shortfallWh);
    await settlement.connect(operator).postDelivery(2, buildMerkleTree([leaf]).root);

    const before = await token.balanceOf(buyer.address);
    await settlement.connect(operator).settleShortfall(2, thin.address, shortfallWh, [], buyer.address);
    expect(await token.balanceOf(buyer.address)).to.equal(before + MIN_STAKE);
    expect((await registry.getParticipant(thin.address)).stake).to.equal(0n);
    expect(await registry.isActive(thin.address)).to.equal(false);
  });

  it("a shortfall worth less than one paisa is recorded without reverting", async function () {
    const { settlement, operator, buyer, seller } = await clearedInterval(800);
    const leaf = shortfallLeaf(1, seller.address, buyer.address, 1n);
    await settlement.connect(operator).postDelivery(1, buildMerkleTree([leaf]).root);
    await expect(settlement.connect(operator).settleShortfall(1, seller.address, 1n, [], buyer.address)).to.emit(
      settlement,
      "ShortfallSettled"
    );
  });

  it("admin can sweep only the treasury, not user escrow", async function () {
    const { settlement, operator, admin, buyer, seller, users } = await clearedInterval(500);
    const leaf = shortfallLeaf(1, seller.address, buyer.address, 2000n);
    await settlement.connect(operator).postDelivery(1, buildMerkleTree([leaf]).root);
    await settlement.connect(operator).settleShortfall(1, seller.address, 2000n, [], buyer.address);
    const t = await settlement.treasury();
    await expect(settlement.connect(admin).sweepTreasury(users[7].address, t + 1n)).to.be.revertedWith(
      "Settlement: amount"
    );
    await expect(settlement.connect(admin).sweepTreasury(users[7].address, t))
      .to.emit(settlement, "TreasurySwept")
      .withArgs(users[7].address, t);
    await expect(
      settlement.connect(operator).sweepTreasury(users[7].address, 1n)
    ).to.be.revertedWithCustomError(settlement, "AccessControlUnauthorizedAccount");
  });

  it("pause blocks commits but not escrow withdrawal", async function () {
    const sys = await deploySystem();
    const { settlement, admin, operator, users, token, registry } = sys;
    await activate(sys, users[0]);
    await openInterval(settlement, operator, 1, 1000, 1000);
    await settlement.connect(admin).pause();
    await expect(settlement.connect(users[0]).commitPosition(1, ethers.id("x"))).to.be.revertedWithCustomError(
      settlement,
      "EnforcedPause"
    );
    // A pause must not freeze user funds.
    await fundAndApprove(token, registry, settlement, users[1], 10_000n);
    await settlement.connect(admin).unpause();
    await settlement.connect(users[1]).deposit(5_000n);
    await settlement.connect(admin).pause();
    await settlement.connect(users[1]).withdrawEscrow(5_000n);
    await settlement.connect(admin).unpause();
    await settlement.connect(users[0]).commitPosition(1, ethers.id("x"));
  });

  it("paymentOf floors qtyWh * price / 1000", async function () {
    const { settlement } = await deploySystem();
    expect(await settlement.paymentOf(999, 800)).to.equal(799n); // 799200/1000
  });
});
