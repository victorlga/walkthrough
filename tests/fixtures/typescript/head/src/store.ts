export interface PriceStore {
  save(price: number): void;
  label?: string;
}

export class MemoryStore implements PriceStore {
  saved: number[] = [];

  save(price: number): void {
    this.saved.push(price);
  }
}
