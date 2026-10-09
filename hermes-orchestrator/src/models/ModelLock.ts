export class ModelLock {
  private locked = false;
  private waitingQueue: Array<{ resolve: (value: void) => void; reject: (reason?: any) => void }> = [];

  async acquire(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.locked) {
        this.locked = true;
        resolve();
      } else {
        this.waitingQueue.push({ resolve, reject });
      }
    });
  }

  async release(): Promise<void> {
    if (this.waitingQueue.length > 0) {
      const next = this.waitingQueue.shift()!;
      next.resolve();
    } else {
      this.locked = false;
    }
  }

  isLocked(): boolean {
    return this.locked;
  }

  getQueueLength(): number {
    return this.waitingQueue.length;
  }
}
