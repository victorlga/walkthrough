import { describe } from "./pricing";
import { PriceStore } from "./store";

export function handler(event: { amount: number }, store: PriceStore): string {
  store.save(event.amount);
  return describe(event.amount);
}
