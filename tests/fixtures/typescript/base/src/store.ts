export interface PriceStore {
  save(price: number): void;
}

export class MemoryStore implements PriceStore {
  saved: number[] = [];

  save(price: number): void {
    this.saved.push(price);
  }
}
