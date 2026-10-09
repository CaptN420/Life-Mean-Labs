import { VRAMInfo } from '../config/models';

export class VRAMManager {
  private totalVRAM: number = 80000; // 80GB simulated
  private usedVRAM: number = 0;
  private reserveMB: number = 1024;

  constructor(reserveMB: number = 1024) {
    this.reserveMB = reserveMB;
  }

  async updateVRAM(): Promise<VRAMInfo> {
    // In production, this would query the actual GPU via CUDA/MPS/etc.
    // For now, we simulate based on model states
    const simulatedTotal = 80000; // 80GB hypothetical GPU
    const simulatedUsed = this.usedVRAM;
    
    this.totalVRAM = simulatedTotal;
    return {
      total: this.totalVRAM,
      used: simulatedUsed,
      free: this.totalVRAM - simulatedUsed
    };
  }

  async getFreeVRAM(): Promise<number> {
    const info = await this.updateVRAM();
    return info.free;
  }

  hasEnoughVRAM(estimatedVRAM: number): boolean {
    return (this.totalVRAM - this.usedVRAM - this.reserveMB) >= estimatedVRAM;
  }

  async checkAndReserve(estimatedVRAM: number): Promise<boolean> {
    const info = await this.updateVRAM();
    const available = info.free - this.reserveMB;
    
    if (available >= estimatedVRAM) {
      this.usedVRAM += estimatedVRAM;
      return true;
    }
    return false;
  }

  releaseVRAM(estimatedVRAM: number): void {
    this.usedVRAM = Math.max(0, this.usedVRAM - estimatedVRAM);
  }

  getTotalVRAM(): number {
    return this.totalVRAM;
  }

  getUsedVRAM(): number {
    return this.usedVRAM;
  }

  getFreeVRAMSync(): number {
    return this.totalVRAM - this.usedVRAM;
  }

  getReserveMB(): number {
    return this.reserveMB;
  }
}
