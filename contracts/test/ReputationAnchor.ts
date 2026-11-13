import { expect } from "chai";
import { ethers } from "hardhat";
import { deploySystem } from "./helpers/fixtures";
import { buildMerkleTree, getProof, reputationLeaf } from "./helpers/merkle";

describe("ReputationAnchor", function () {
  it("posts root once and verifies scores", async function () {
    const { reputation, operator, users } = await deploySystem();
    const [a, b] = users;
    const leaves = [
      reputationLeaf(a.address, 8000, 10),
      reputationLeaf(b.address, 5000, 5),
    ];
    const { root } = buildMerkleTree(leaves);

    await expect(reputation.connect(users[0]).postRoot(1, root)).to.be.revertedWithCustomError(
      reputation,
      "AccessControlUnauthorizedAccount"
    );

    await expect(reputation.connect(operator).postRoot(1, root)).to.emit(reputation, "RootPosted").withArgs(1, root);
    await expect(reputation.connect(operator).postRoot(1, root)).to.be.revertedWith(
      "ReputationAnchor: already posted"
    );
    await expect(reputation.connect(operator).postRoot(2, ethers.ZeroHash)).to.be.revertedWith(
      "ReputationAnchor: empty root"
    );

    const proofA = getProof(leaves, 0);
    expect(await reputation.verifyScore(1, a.address, 8000, 10, proofA)).to.equal(true);
    expect(await reputation.verifyScore(1, a.address, 8001, 10, proofA)).to.equal(false);

    await expect(reputation.verifyScore(99, a.address, 8000, 10, proofA)).to.be.revertedWith(
      "ReputationAnchor: no root"
    );
  });
});
