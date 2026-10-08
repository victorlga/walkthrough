export const RATE = 2;

export function discount(amount: number): number {
  return Math.floor(amount / 10);
}

export function basePrice(amount: number): number {
  const localTotal = amount * RATE;
  return localTotal - discount(amount);
}

export function describe(amount: number): string {
  return JSON.stringify({ price: basePrice(amount) });
}
