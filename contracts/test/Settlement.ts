import { expect } from "chai";
import { ethers } from "hardhat";
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
  async function setupBuyerSeller() {
    const sys = await deploySystem();
    const { token, registry, settlement, operator, users } = sys;
    const buyer = users[0];
    const seller = users[1];
    await registerParticipant(token, registry, settlement, buyer, ethers.id("buyer"));
    await registerParticipant(token, registry, settlement, seller, ethers.id("seller"), MIN_STAKE + 50_000n);
    await fundAndApprove(token, registry, settlement, buyer, 200_000n);
    await settlement.connect(buyer).deposit(100_000n);
    return { ...sys, buyer, seller };
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
    const { settlement, operator, users } = await deploySystem();
    const [u] = users;
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

  it("replayed commit hash allowed in a new interval (fresh slot)", async function () {
    const { settlement, operator, users } = await deploySystem();
    const [u] = users;
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

  it("buyer with too little escrow cannot settle", async function () {
    const { settlement, operator, buyer, seller } = await setupBuyerSeller();
    const { revealDeadline } = await openInterval(settlement, operator, 1, 50, 50);
    await time.increaseTo(revealDeadline);
    await settlement.connect(operator).postClearing(1, ethers.id("in"), ethers.id("out"), 800);

    // drain escrow
    const bal = await settlement.escrow(buyer.address);
    await settlement.connect(buyer).withdrawEscrow(bal);

    await expect(
      settlement.connect(operator).settleBatch(1, [
        { buyer: buyer.address, seller: seller.address, qtyWh: 1000n, pricePaise: 800 },
      ])
    ).to.be.revertedWith("Settlement: buyer escrow");
  });

  it("participant who never reveals: commit exists, no trade settled for them", async function () {
    const { settlement, operator, buyer, seller, users } = await setupBuyerSeller();
    const ghost = users[2];
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

  it("under-delivery shortfall slashes seller stake to compensate buyer", async function () {
    const { token, registry, settlement, operator, buyer, seller } = await setupBuyerSeller();
    const { revealDeadline } = await openInterval(settlement, operator, 1, 50, 50);
    await time.increaseTo(revealDeadline);
    const pRef = 500;
    await settlement.connect(operator).postClearing(1, ethers.id("in"), ethers.id("out"), pRef);

    const shortfallWh = 2000n;
    const leaf = shortfallLeaf(1, seller.address, shortfallWh);
    const { root } = buildMerkleTree([leaf]);
    await settlement.connect(operator).postDelivery(1, root);

    const compensation = (shortfallWh * BigInt(P_RET - pRef)) / 1000n;
    const penalty = (shortfallWh * BigInt(pRef) * 1n) / (1000n * 10n);
    const stakeBefore = (await registry.getParticipant(seller.address)).stake;
    const buyerTokenBefore = await token.balanceOf(buyer.address);

    await expect(
      settlement.connect(operator).settleShortfall(1, seller.address, shortfallWh, [], buyer.address)
    )
      .to.emit(settlement, "ShortfallSettled")
      .withArgs(1, seller.address, shortfallWh, compensation, penalty);

    expect((await registry.getParticipant(seller.address)).stake).to.equal(stakeBefore - compensation - penalty);
    expect(await token.balanceOf(buyer.address)).to.equal(buyerTokenBefore + compensation);

    await expect(
      settlement.connect(operator).settleShortfall(1, seller.address, shortfallWh, [], buyer.address)
    ).to.be.revertedWith("Settlement: shortfall done");
  });

  it("pause blocks commits", async function () {
    const { settlement, admin, operator, users } = await deploySystem();
    await openInterval(settlement, operator, 1, 1000, 1000);
    await settlement.connect(admin).pause();
    await expect(settlement.connect(users[0]).commitPosition(1, ethers.id("x"))).to.be.revertedWithCustomError(
      settlement,
      "EnforcedPause"
    );
    await settlement.connect(admin).unpause();
    await settlement.connect(users[0]).commitPosition(1, ethers.id("x"));
  });

  it("paymentOf floors qtyWh * price / 1000", async function () {
    const { settlement } = await deploySystem();
    expect(await settlement.paymentOf(999, 800)).to.equal(799n); // 799200/1000
  });
});
