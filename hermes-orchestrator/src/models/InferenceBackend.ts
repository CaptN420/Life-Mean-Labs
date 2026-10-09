import { ModelDefinition, ModelState, VRAMInfo } from '../config/models';

export abstract class InferenceBackend {
  abstract load(model: ModelDefinition): Promise<void>;
  abstract unload(model: ModelDefinition): Promise<void>;
  abstract generate(model: ModelDefinition, input: string, timeoutMs?: number): Promise<string>;
  abstract getVRAMUsage(): Promise<VRAMInfo>;
  abstract isModelReady(modelId: string): Promise<boolean>;
}
