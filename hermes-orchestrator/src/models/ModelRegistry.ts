import { ModelDefinition, ModelState, ModelStatus } from '../config/models';

export class ModelRegistry {
  private models: Map<string, ModelDefinition> = new Map();
  private states: Map<string, ModelStatus> = new Map();

  constructor() {
    this.initializeDefaultModels();
  }

  private initializeDefaultModels(): void {
    const defaultModels: ModelDefinition[] = [
      {
        id: 'clef',
        path: process.env.CLEF_MODEL_PATH || '/models/clef',
        type: 'router',
        estimatedVRAM: 4000, // ~4GB for a smaller router model
        backend: 'default'
      },
      {
        id: 'model-a-27b',
        path: process.env.MODEL_A_PATH || '/models/model-a-27b',
        type: 'specialist',
        estimatedVRAM: 54000, // ~54GB for 27B model
        backend: 'default'
      },
      {
        id: 'model-b-27b',
        path: process.env.MODEL_B_PATH || '/models/model-b-27b',
        type: 'specialist',
        estimatedVRAM: 54000, // ~54GB for 27B model
        backend: 'default'
      }
    ];

    for (const model of defaultModels) {
      this.register(model);
    }
  }

  register(model: ModelDefinition): void {
    this.models.set(model.id, model);
    this.states.set(model.id, {
      id: model.id,
      state: 'UNLOADED' as ModelState
    });
  }

  get(id: string): ModelDefinition | undefined {
    return this.models.get(id);
  }

  getAll(): ModelDefinition[] {
    return Array.from(this.models.values());
  }

  getState(id: string): ModelStatus | undefined {
    return this.states.get(id);
  }

  setState(id: string, state: ModelState): void {
    const currentState = this.states.get(id);
    if (currentState) {
      this.states.set(id, { ...currentState, state });
    }
  }

  isLoaded(id: string): boolean {
    const state = this.states.get(id);
    return state?.state === 'READY' || state?.state === 'RUNNING';
  }

  isActive(): string | null {
    for (const [id, state] of this.states.entries()) {
      if (state.state === 'READY' || state.state === 'RUNNING') {
        return id;
      }
    }
    return null;
  }

  getActiveState(): ModelStatus | null {
    const activeId = this.isActive();
    return activeId ? this.states.get(activeId) || null : null;
  }
}
