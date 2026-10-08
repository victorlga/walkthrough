import { describe } from "./pricing";

export function handler(event: { amount: number }): string {
  return describe(event.amount);
}
