import { expect } from "chai";
import { ethers } from "hardhat";
import { time } from "@nomicfoundation/hardhat-network-helpers";
import { deploySystem, FAUCET } from "./helpers/fixtures";

describe("MockINR", function () {
  it("has 2 decimals and mints faucet once per day", async function () {
    const { token, users } = await deploySystem();
    const [u] = users;
    expect(await token.decimals()).to.equal(2);

    await expect(token.connect(u).faucet()).to.emit(token, "FaucetClaimed");
    expect(await token.balanceOf(u.address)).to.equal(FAUCET);
    expect(await token.hasClaimedToday(u.address)).to.equal(true);
    await expect(token.connect(u).faucet()).to.be.revertedWith("MockINR: already claimed today");

    await time.increase(86400);
    await token.connect(u).faucet();
    expect(await token.balanceOf(u.address)).to.equal(FAUCET * 2n);
  });

  it("only owner can mint", async function () {
    const { token, users } = await deploySystem();
    await expect(token.connect(users[0]).mint(users[0].address, 1n)).to.be.revertedWithCustomError(
      token,
      "OwnableUnauthorizedAccount"
    );
  });

  it("rejects zero faucet amount in constructor", async function () {
    await expect((await ethers.getContractFactory("MockINR")).deploy(0)).to.be.revertedWith("MockINR: zero faucet");
  });
});
