import dotenv from 'dotenv';
dotenv.config();

export interface ModelDefinition {
  id: string;
  path: string;
  type: 'router' | 'specialist' | 'general';
  estimatedVRAM: number; // in MB
  backend: string;
}

export interface VRAMInfo {
  total: number;
  used: number;
  free: number;
}

export type ModelState = 'UNLOADED' | 'LOADING' | 'READY' | 'RUNNING' | 'UNLOADING' | 'ERROR';

export interface ModelStatus {
  id: string;
  state: ModelState;
  loadedAt?: Date;
  error?: string;
}

export interface RoutingResult {
  school: {
    primary: string;
    confidence: number;
    alternatives?: Array<{ label: string; confidence: number }>;
  };
  thinker: {
    primary: string;
    confidence: number;
    alternatives?: Array<{ label: string; confidence: number }>;
  };
  concepts: string[];
  route: string;
  confidence: number;
  needs_clarification: boolean;
}

export interface RequestContext {
  requestId: string;
  userMessage: string;
  routing?: RoutingResult;
  timestamp: Date;
}

export interface RequestMetrics {
  requestId: string;
  activeModel: string | null;
  previousModel: string | null;
  requestedModel: string;
  loadTimeMs: number;
  unloadTimeMs: number;
  inferenceTimeMs: number;
  routingTimeMs: number;
  totalTimeMs: number;
  vramBefore: number;
  vramAfter: number;
  route: string | null;
  confidence: number | null;
  cacheHit: boolean;
  fallback: boolean;
  error: string | null;
}

export interface ModelConfig {
  clefModelPath: string;
  modelAPath: string;
  modelBPath: string;
  gpuDevice: number;
  maxActiveModels: number;
  memoryMode: 'strict' | 'cache';
  vramReserveMB: number;
  clefTimeoutMs: number;
  modelLoadTimeoutMs: number;
  inferenceTimeoutMs: number;
}

export const DEFAULT_CONFIG: ModelConfig = {
  clefModelPath: process.env.CLEF_MODEL_PATH || '/models/clef',
  modelAPath: process.env.MODEL_A_PATH || '/models/model-a-27b',
  modelBPath: process.env.MODEL_B_PATH || '/models/model-b-27b',
  gpuDevice: parseInt(process.env.GPU_DEVICE || '0'),
  maxActiveModels: parseInt(process.env.MAX_ACTIVE_MODELS || '1'),
  memoryMode: (process.env.MODEL_MEMORY_MODE as 'strict' | 'cache') || 'cache',
  vramReserveMB: parseInt(process.env.VRAM_RESERVE_MB || '1024'),
  clefTimeoutMs: parseInt(process.env.CLEF_TIMEOUT_MS || '2000'),
  modelLoadTimeoutMs: parseInt(process.env.MODEL_LOAD_TIMEOUT_MS || '120000'),
  inferenceTimeoutMs: parseInt(process.env.INFERENCE_TIMEOUT_MS || '120000'),
};
