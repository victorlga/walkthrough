import { basePrice } from "../src/pricing";

declare function it(name: string, fn: () => void): void;

it("doubles", () => {
  if (basePrice(2) !== 4) throw new Error("bad");
});
