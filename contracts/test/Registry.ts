import { expect } from "chai";
import { ethers } from "hardhat";
import {
  COOLDOWN,
  MIN_STAKE,
  deploySystem,
  fundAndApprove,
  registerParticipant,
  time,
} from "./helpers/fixtures";

describe("Registry", function () {
  it("stakes, registers uniquely, and emits Registered", async function () {
    const { token, registry, settlement, users } = await deploySystem();
    const [a, b] = users;
    const key = ethers.id("meter-a");

    await fundAndApprove(token, registry, settlement, a, MIN_STAKE);
    await registry.connect(a).stake(MIN_STAKE);
    await expect(registry.connect(a).register(key))
      .to.emit(registry, "Registered")
      .withArgs(a.address, key, MIN_STAKE);

    expect((await registry.getParticipant(a.address)).registered).to.equal(true);
    expect(await registry.meterKeyOwner(key)).to.equal(a.address);

    await fundAndApprove(token, registry, settlement, b, MIN_STAKE);
    await registry.connect(b).stake(MIN_STAKE);
    await expect(registry.connect(b).register(key)).to.be.revertedWith("Registry: key taken");
    await expect(registry.connect(a).register(ethers.id("other"))).to.be.revertedWith(
      "Registry: already registered"
    );
  });

  it("rejects register below min stake and empty key", async function () {
    const { token, registry, settlement, users } = await deploySystem();
    const [a] = users;
    await fundAndApprove(token, registry, settlement, a, MIN_STAKE);
    await registry.connect(a).stake(MIN_STAKE - 1n);
    await expect(registry.connect(a).register(ethers.id("m"))).to.be.revertedWith("Registry: min stake");
    await registry.connect(a).stake(1n);
    await expect(registry.connect(a).register(ethers.ZeroHash)).to.be.revertedWith("Registry: empty key");
  });

  it("withdrawal before cooldown reverts; succeeds after", async function () {
    const { token, registry, settlement, users } = await deploySystem();
    const [a] = users;
    await registerParticipant(token, registry, settlement, a, ethers.id("m1"), MIN_STAKE + 5_000n);

    await registry.connect(a).requestWithdraw();
    await expect(registry.connect(a).withdraw()).to.be.revertedWith("Registry: cooldown");

    await time.increase(Number(COOLDOWN));
    const before = await token.balanceOf(a.address);
    await expect(registry.connect(a).withdraw()).to.emit(registry, "Withdrawn").withArgs(a.address, 5_000n);
    expect(await token.balanceOf(a.address)).to.equal(before + 5_000n);
    expect((await registry.getParticipant(a.address)).stake).to.equal(MIN_STAKE);
  });

  it("cannot request withdraw with nothing above min stake", async function () {
    const { token, registry, settlement, users } = await deploySystem();
    const [a] = users;
    await registerParticipant(token, registry, settlement, a, ethers.id("m2"), MIN_STAKE);
    await expect(registry.connect(a).requestWithdraw()).to.be.revertedWith("Registry: nothing to withdraw");
  });

  it("operator can suspend; non-operator cannot", async function () {
    const { token, registry, settlement, operator, users } = await deploySystem();
    const [a] = users;
    await registerParticipant(token, registry, settlement, a, ethers.id("m3"));
    await expect(registry.connect(a).suspend(a.address)).to.be.revertedWithCustomError(
      registry,
      "AccessControlUnauthorizedAccount"
    );
    await expect(registry.connect(operator).suspend(a.address)).to.emit(registry, "Suspended").withArgs(a.address);
    await expect(registry.connect(operator).suspend(a.address)).to.be.revertedWith("Registry: already suspended");
  });

  it("slash only by settlement role", async function () {
    const { token, registry, settlement, users, operator } = await deploySystem();
    const [a, b] = users;
    await registerParticipant(token, registry, settlement, a, ethers.id("m4"), MIN_STAKE + 1_000n);

    await expect(registry.connect(operator).slash(a.address, 100n, b.address)).to.be.revertedWithCustomError(
      registry,
      "AccessControlUnauthorizedAccount"
    );

    // Settlement holds SETTLEMENT_ROLE — exercise via settleShortfall path in Settlement tests.
    // Direct role call: grant operator temporarily.
    const [admin] = await ethers.getSigners();
    await registry.connect(admin).grantRole(await registry.SETTLEMENT_ROLE(), operator.address);
    await expect(registry.connect(operator).slash(a.address, 500n, b.address))
      .to.emit(registry, "Slashed")
      .withArgs(a.address, 500n, b.address);
    expect(await token.balanceOf(b.address)).to.be.gte(500n);
  });

  it("rejects zero stake amount", async function () {
    const { registry, users } = await deploySystem();
    await expect(registry.connect(users[0]).stake(0)).to.be.revertedWith("Registry: zero amount");
  });

  it("admin can update minStake and withdrawCooldown", async function () {
    const { registry, admin, users } = await deploySystem();
    await expect(registry.connect(users[0]).setMinStake(1n)).to.be.revertedWithCustomError(
      registry,
      "AccessControlUnauthorizedAccount"
    );
    await expect(registry.connect(admin).setMinStake(12_000n))
      .to.emit(registry, "MinStakeUpdated")
      .withArgs(12_000n);
    expect(await registry.minStake()).to.equal(12_000n);

    await expect(registry.connect(admin).setWithdrawCooldown(3600))
      .to.emit(registry, "WithdrawCooldownUpdated")
      .withArgs(3600);
    expect(await registry.withdrawCooldown()).to.equal(3600);
  });
});
