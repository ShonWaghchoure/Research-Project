import { expect } from "chai";
import { ethers } from "hardhat";
import { Ping } from "../typechain-types";

describe("Ping Contract", function () {
  let ping: Ping;
  let owner: any;
  let user: any;

  beforeEach(async function () {
    [owner, user] = await ethers.getSigners();
    const PingFactory = await ethers.getContractFactory("Ping");
    ping = (await PingFactory.deploy()) as unknown as Ping;
    await ping.waitForDeployment();
  });

  it("should deploy with the correct owner", async function () {
    expect(await ping.owner()).to.equal(owner.address);
  });

  it("should return pong and emit Pong event on ping()", async function () {
    await expect(ping.connect(user).ping())
      .to.emit(ping, "Pong")
      .withArgs(user.address, (timestamp: any) => typeof timestamp === "bigint" || typeof timestamp === "number");
  });

  it("should return ping on pong() view call", async function () {
    expect(await ping.pong()).to.equal("ping");
  });
});
