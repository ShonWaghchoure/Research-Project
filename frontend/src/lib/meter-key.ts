import { keccak256, toBytes, type Hex } from "viem";

/**
 * Meter key hash bound to the wallet in Registry.register.
 * The simulator derives a deterministic signing key per participant; the demo UI
 * mirrors that with a deterministic hash. A real deployment would hash the meter's
 * public key.
 */
export function demoMeterKeyHash(address: string): Hex {
  return keccak256(toBytes(`meter:${address.toLowerCase()}`));
}
