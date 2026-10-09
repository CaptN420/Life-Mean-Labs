import { ModelDefinition, VRAMInfo, ModelState } from '../config/models';

export class OrchestrationError extends Error {
  constructor(
    message: string,
    public code: string,
    public details?: Record<string, any>
  ) {
    super(message);
    this.name = 'OrchestrationError';
  }
}

export class ModelLoadError extends OrchestrationError {
  constructor(modelId: string, cause?: Error) {
    super(`Failed to load model: ${modelId}`, 'MODEL_LOAD_ERROR', { modelId, cause });
    this.name = 'ModelLoadError';
  }
}

export class ModelUnloadError extends OrchestrationError {
  constructor(modelId: string, cause?: Error) {
    super(`Failed to unload model: ${modelId}`, 'MODEL_UNLOAD_ERROR', { modelId, cause });
    this.name = 'ModelUnloadError';
  }
}

export class VRAMInsufficientError extends OrchestrationError {
  constructor(available: number, required: number) {
    super(`Insufficient VRAM: ${available}MB available, ${required}MB required`, 'VRAM_INSUFFICIENT', { available, required });
    this.name = 'VRAMInsufficientError';
  }
}

export class RoutingError extends OrchestrationError {
  constructor(message: string, routingResult?: any) {
    super(message, 'ROUTING_ERROR', { routingResult });
    this.name = 'RoutingError';
  }
}

export class InferenceError extends OrchestrationError {
  constructor(modelId: string, cause?: Error) {
    super(`Inference failed on model: ${modelId}`, 'INFERENCE_ERROR', { modelId, cause });
    this.name = 'InferenceError';
  }
}
