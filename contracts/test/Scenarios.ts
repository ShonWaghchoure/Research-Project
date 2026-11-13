import { expect } from "chai";
import { ethers } from "hardhat";
import {
  MIN_STAKE,
  commitHash,
  deploySystem,
  fundAndApprove,
  openInterval,
  registerParticipant,
  time,
} from "./helpers/fixtures";
import { buildMerkleTree, getProof, reputationLeaf } from "./helpers/merkle";

describe("Scenarios", function () {
  it("full 10-participant interval: commit, clear, settle", async function () {
    const { token, registry, settlement, reputation, operator, users } = await deploySystem();
    const participants = users.slice(0, 10);
    expect(participants.length).to.equal(10);

    for (let i = 0; i < 10; i++) {
      await registerParticipant(
        token,
        registry,
        settlement,
        participants[i],
        ethers.id(`meter-${i}`),
        MIN_STAKE + 20_000n
      );
      await fundAndApprove(token, registry, settlement, participants[i], 100_000n);
      if (i < 5) {
        // buyers need escrow
        await settlement.connect(participants[i]).deposit(50_000n);
      }
    }

    const intervalId = 42;
    const { commitDeadline, revealDeadline } = await openInterval(settlement, operator, intervalId, 200, 200);

    for (let i = 0; i < 10; i++) {
      const side = i < 5 ? 0 : 1;
      const h = await commitHash(
        settlement,
        intervalId,
        participants[i].address,
        side,
        1000 + i * 100,
        i < 5 ? 800 : 300,
        Number(commitDeadline),
        ethers.id(`salt-${i}`)
      );
      await settlement.connect(participants[i]).commitPosition(intervalId, h);
    }

    // Advance past reveal without on-chain reveal (off-chain process).
    await time.increaseTo(revealDeadline);
    const pRef = 500;
    await settlement
      .connect(operator)
      .postClearing(intervalId, ethers.id("input-root-10"), ethers.id("result-hash-10"), pRef);

    const trades = [];
    for (let i = 0; i < 5; i++) {
      trades.push({
        buyer: participants[i].address,
        seller: participants[i + 5].address,
        qtyWh: 1000n,
        pricePaise: pRef,
      });
    }
    await settlement.connect(operator).settleBatch(intervalId, trades);

    for (let i = 0; i < 5; i++) {
      const payment = (1000n * BigInt(pRef)) / 1000n;
      expect(await settlement.escrow(participants[i].address)).to.equal(50_000n - payment);
      expect(await settlement.escrow(participants[i + 5].address)).to.equal(payment);
    }

    // Reputation root for all 10
    const leaves = participants.map((p, i) => reputationLeaf(p.address, 7000 + i, 20 + i));
    const { root } = buildMerkleTree(leaves);
    await reputation.connect(operator).postRoot(intervalId, root);
    const proof0 = getProof(leaves, 0);
    expect(await reputation.verifyScore(intervalId, participants[0].address, 7000, 20, proof0)).to.equal(
      true
    );
  });
});
