import { ModelDefinition, ModelState, VRAMInfo, ModelStatus } from '../config/models';
import { ModelRegistry } from './ModelRegistry';
import { VRAMManager } from './VRAMManager';
import { ModelLock } from './ModelLock';
import {
  ModelLoadError,
  ModelUnloadError,
  VRAMInsufficientError,
  OrchestrationError
} from '../orchestrator/OrchestrationError';

export class ModelManager {
  private registry: ModelRegistry;
  private vramManager: VRAMManager;
  private lock: ModelLock;
  private activeModel: string | null = null;
  private modelStates: Map<string, ModelStatus> = new Map();

  constructor(registry: ModelRegistry, vramManager: VRAMManager) {
    this.registry = registry;
    this.vramManager = vramManager;
    this.lock = new ModelLock();

    // Initialize states from registry
    for (const model of registry.getAll()) {
      this.modelStates.set(model.id, { id: model.id, state: 'UNLOADED' });
    }
  }

  async loadModel(modelId: string): Promise<void> {
    const model = this.registry.get(modelId);
    if (!model) {
      throw new ModelLoadError(modelId, new Error(`Model ${modelId} not found in registry`));
    }

    // Check if already loaded
    if (this.activeModel === modelId) {
      return; // Already active, no need to reload
    }

    // Unload current model if different
    if (this.activeModel && this.activeModel !== modelId) {
      await this.unloadModel(this.activeModel);
    }

    // Check VRAM availability
    const freeVRAM = await this.vramManager.getFreeVRAM();
    if (!this.vramManager.hasEnoughVRAM(model.estimatedVRAM)) {
      throw new VRAMInsufficientError(freeVRAM, model.estimatedVRAM);
    }

    // Update state to LOADING
    this.updateState(modelId, 'LOADING');

    try {
      // Reserve VRAM
      const reserved = await this.vramManager.checkAndReserve(model.estimatedVRAM);
      if (!reserved) {
        throw new VRAMInsufficientError(freeVRAM, model.estimatedVRAM);
      }

      // Simulate model loading (in production, this would call the backend)
      await this.simulateLoad(model);

      // Update state to READY
      this.updateState(modelId, 'READY');
      this.activeModel = modelId;
      
    } catch (error) {
      this.updateState(modelId, 'ERROR');
      if (error instanceof OrchestrationError) {
        throw error;
      }
      throw new ModelLoadError(modelId, error as Error);
    }
  }

  async unloadModel(modelId: string): Promise<void> {
    const model = this.registry.get(modelId);
    if (!model) {
      throw new ModelUnloadError(modelId, new Error(`Model ${modelId} not found in registry`));
    }

    // Check if model is running
    const state = this.modelStates.get(modelId);
    if (state?.state === 'RUNNING') {
      throw new ModelUnloadError(modelId, new Error('Cannot unload running model'));
    }

    // Update state to UNLOADING
    this.updateState(modelId, 'UNLOADING');

    try {
      // Simulate unloading (in production, this would call the backend)
      await this.simulateUnload(model);

      // Release VRAM
      this.vramManager.releaseVRAM(model.estimatedVRAM);

      // Update state to UNLOADED
      this.updateState(modelId, 'UNLOADED');

      if (this.activeModel === modelId) {
        this.activeModel = null;
      }
      
    } catch (error) {
      this.updateState(modelId, 'ERROR');
      if (error instanceof OrchestrationError) {
        throw error;
      }
      throw new ModelUnloadError(modelId, error as Error);
    }
  }

  async switchModel(targetModelId: string): Promise<void> {
    await this.lock.acquire();
    try {
      await this.unloadModel(this.activeModel || '');
      await this.loadModel(targetModelId);
    } finally {
      await this.lock.release();
    }
  }

  async getModelStatus(modelId: string): Promise<ModelStatus> {
    return this.modelStates.get(modelId) || { id: modelId, state: 'UNLOADED' };
  }

  getActiveModel(): string | null {
    return this.activeModel;
  }

  isLoaded(modelId: string): boolean {
    return this.activeModel === modelId;
  }

  async getVRAMUsage(): Promise<VRAMInfo> {
    return this.vramManager.updateVRAM();
  }

  private updateState(modelId: string, state: ModelState): void {
    const current = this.modelStates.get(modelId) || { id: modelId, state: 'UNLOADED' };
    this.modelStates.set(modelId, { ...current, state });
    this.registry.setState(modelId, state);
  }

  // Simulated methods for testing - in production these would call the actual backend
  private async simulateLoad(model: ModelDefinition): Promise<void> {
    // Simulate async loading delay
    await new Promise(resolve => setTimeout(resolve, 100));
  }

  private async simulateUnload(model: ModelDefinition): Promise<void> {
    // Simulate async unloading delay
    await new Promise(resolve => setTimeout(resolve, 50));
  }
}
