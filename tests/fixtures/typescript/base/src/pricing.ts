export const RATE = 2;

export function basePrice(amount: number): number {
  return amount * RATE;
}

export function describe(amount: number): string {
  return JSON.stringify({ price: basePrice(amount) });
}
