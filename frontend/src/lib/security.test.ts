import { describe, expect, it } from "vitest";
import { safeHttpsUrl } from "@/components/audit/explorer-links";
import { readableTxError } from "./tx";

describe("safeHttpsUrl (audit explorer link)", () => {
  it("allows https only", () => {
    expect(safeHttpsUrl("https://sepolia.etherscan.io/address/0x1")).toBe("https://sepolia.etherscan.io/address/0x1");
    expect(safeHttpsUrl("javascript:alert(document.cookie)")).toBeNull();
    expect(safeHttpsUrl("http://example.com")).toBeNull();
    expect(safeHttpsUrl("data:text/html,<script>1</script>")).toBeNull();
    expect(safeHttpsUrl("not a url")).toBeNull();
    expect(safeHttpsUrl(null)).toBeNull();
  });
});

describe("readableTxError for the hardened contracts", () => {
  it("explains escrow locks and inactive accounts", () => {
    expect(readableTxError(new Error("execution reverted: Settlement: escrow locked"))).toMatch(/locked until/i);
    expect(readableTxError(new Error("Settlement: not active"))).toMatch(/not active/i);
  });
});
