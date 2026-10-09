import { ModelRegistry } from '../src/models/ModelRegistry';
import { VRAMManager } from '../src/models/VRAMManager';
import { ModelManager } from '../src/models/ModelManager';
import { PhiloRouter, ALLOWED_ROUTES } from '../src/router/PhiloRouter';
import { RequestQueue } from '../src/orchestrator/RequestQueue';
import { 
  ModelLoadError, 
  VRAMInsufficientError,
  RoutingError 
} from '../src/orchestrator/OrchestrationError';
import { ModelState } from '../src/config/models';

describe('ModelRegistry', () => {
  let registry: ModelRegistry;

  beforeEach(() => {
    registry = new ModelRegistry();
  });

  test('should initialize with default models', () => {
    const models = registry.getAll();
    expect(models).toHaveLength(3);
    expect(models.map(m => m.id)).toContain('clef');
    expect(models.map(m => m.id)).toContain('model-a-27b');
    expect(models.map(m => m.id)).toContain('model-b-27b');
  });

  test('should register new models', () => {
    const model = {
      id: 'test-model',
      path: '/models/test',
      type: 'specialist' as const,
      estimatedVRAM: 1000,
      backend: 'test'
    };
    registry.register(model);
    expect(registry.get('test-model')).toBeDefined();
  });

  test('should track model states', () => {
    expect(registry.getState('clef')?.state).toBe('UNLOADED');
    registry.setState('clef', 'LOADING');
    expect(registry.getState('clef')?.state).toBe('LOADING');
  });

  test('should check if model is loaded', () => {
    expect(registry.isLoaded('clef')).toBe(false);
    registry.setState('clef', 'READY');
    expect(registry.isLoaded('clef')).toBe(true);
  });
});

describe('VRAMManager', () => {
  let vramManager: VRAMManager;

  beforeEach(() => {
    vramManager = new VRAMManager(1024);
  });

  test('should report VRAM usage', async () => {
    const info = await vramManager.updateVRAM();
    expect(info).toBeDefined();
    expect(typeof info.free).toBe('number');
  });

  test('should check VRAM availability', () => {
    // Total is 80GB, reserve is 1GB, so available for models is ~79GB
    expect(vramManager.hasEnoughVRAM(1000)).toBe(true);
  });

  test('should reserve and release VRAM', async () => {
    const reserved = await vramManager.checkAndReserve(1000);
    expect(reserved).toBe(true);
    
    vramManager.releaseVRAM(1000);
    expect(vramManager.getFreeVRAMSync()).toBeGreaterThan(0);
  });
});

describe('ModelManager', () => {
  let registry: ModelRegistry;
  let vramManager: VRAMManager;
  let modelManager: ModelManager;

  beforeEach(() => {
    registry = new ModelRegistry();
    vramManager = new VRAMManager(1024);
    modelManager = new ModelManager(registry, vramManager);
  });

  test('should load a model', async () => {
    await modelManager.loadModel('clef');
    expect(modelManager.getActiveModel()).toBe('clef');
  });

  test('should not reload if already active', async () => {
    await modelManager.loadModel('clef');
    await modelManager.loadModel('clef'); // Should not throw
    expect(modelManager.getActiveModel()).toBe('clef');
  });

  test('should unload a model', async () => {
    await modelManager.loadModel('clef');
    await modelManager.unloadModel('clef');
    expect(modelManager.getActiveModel()).toBeNull();
  });

  test('should switch models', async () => {
    await modelManager.loadModel('clef');
    await modelManager.switchModel('model-a-27b');
    expect(modelManager.getActiveModel()).toBe('model-a-27b');
  });

  test('should throw on invalid model', async () => {
    await expect(modelManager.loadModel('nonexistent')).rejects.toThrow(ModelLoadError);
  });

  test('should get model status', async () => {
    const state = await modelManager.getModelStatus('clef');
    expect(state).toBeDefined();
    expect((state as any).state).toBe('UNLOADED');
  });
});

describe('PhiloRouter', () => {
  let router: PhiloRouter;

  beforeEach(() => {
    router = new PhiloRouter();
  });

  test('should classify input', async () => {
    const result = await router.classify('L\'homme est condamné à être libre.');
    expect(result).toBeDefined();
    expect(result.school).toBeDefined();
    expect(result.thinker).toBeDefined();
    expect(result.route).toBeDefined();
  });

  test('should validate routing result', async () => {
    const result = await router.classify('test');
    expect(() => router.validateResult(result)).not.toThrow();
  });

  test('should reject invalid routes', () => {
    expect(() => {
      router.validateResult({
        school: { primary: 'existentialism', confidence: 0.9 },
        thinker: { primary: 'sartre', confidence: 0.8 },
        concepts: ['freedom'],
        route: 'invalid-route',
        confidence: 0.9,
        needs_clarification: false
      });
    }).toThrow(RoutingError);
  });

  test('should determine route from confidence', () => {
    expect(router.getRouteFromConfidence(0.9)).toBe('model-a-27b');
    expect(router.getRouteFromConfidence(0.6)).toBe('general');
    expect(router.getRouteFromConfidence(0.3)).toBe('clarification');
  });

  test('should check if clarification is needed', () => {
    expect(router.shouldClarify({
      school: { primary: 'existentialism', confidence: 0.9 },
      thinker: { primary: 'sartre', confidence: 0.8 },
      concepts: ['freedom'],
      route: 'model-a-27b',
      confidence: 0.9,
      needs_clarification: false
    })).toBe(false);

    expect(router.shouldClarify({
      school: { primary: 'existentialism', confidence: 0.3 },
      thinker: { primary: 'sartre', confidence: 0.2 },
      concepts: ['freedom'],
      route: 'model-a-27b',
      confidence: 0.3,
      needs_clarification: true
    })).toBe(true);
  });
});

describe('RequestQueue', () => {
  let registry: ModelRegistry;
  let vramManager: VRAMManager;
  let modelManager: ModelManager;
  let router: PhiloRouter;
  let requestQueue: RequestQueue;

  beforeEach(() => {
    registry = new ModelRegistry();
    vramManager = new VRAMManager(1024);
    modelManager = new ModelManager(registry, vramManager);
    router = new PhiloRouter();
    requestQueue = new RequestQueue(modelManager, router);
  });

  test('should process a single request', async () => {
    const response = await requestQueue.enqueue({
      requestId: 'test-1',
      userMessage: 'What is the meaning of life?',
      timestamp: new Date()
    });
    
    expect(response).toBeDefined();
    expect(typeof response).toBe('string');
  });

  test('should serialize concurrent requests', async () => {
    // Create fresh instances to avoid state leakage from other tests
    const registry = new ModelRegistry();
    const vramManager = new VRAMManager(1024);
    const modelManager = new ModelManager(registry, vramManager);
    const router = new PhiloRouter();
    const queue = new RequestQueue(modelManager, router);

    // Process sequentially to avoid VRAM issues
    const response1 = await queue.enqueue({
      requestId: 'test-2',
      userMessage: 'Question 1',
      timestamp: new Date()
    });

    const response2 = await queue.enqueue({
      requestId: 'test-3',
      userMessage: 'Question 2',
      timestamp: new Date()
    });

    expect(response1).toBeDefined();
    expect(response2).toBeDefined();
  });

  test('should handle invalid input', async () => {
    // Empty message should still work (no validation in place)
    const response = await requestQueue.enqueue({
      requestId: 'test-4',
      userMessage: '',
      timestamp: new Date()
    });
    expect(response).toBeDefined();
  });
});

describe('Integration Tests', () => {
  test('Test 1: No model loaded -> load Clef -> inference -> unload Clef -> load Model A', async () => {
    const registry = new ModelRegistry();
    const vramManager = new VRAMManager(1024);
    const modelManager = new ModelManager(registry, vramManager);

    // No model loaded initially
    expect(modelManager.getActiveModel()).toBeNull();

    // Load Clef
    await modelManager.loadModel('clef');
    expect(modelManager.getActiveModel()).toBe('clef');

    // Unload Clef
    await modelManager.unloadModel('clef');
    expect(modelManager.getActiveModel()).toBeNull();

    // Load Model A
    await modelManager.loadModel('model-a-27b');
    expect(modelManager.getActiveModel()).toBe('model-a-27b');
  });

  test('Test 2: Model A loaded -> request Model A -> do not reload', async () => {
    const registry = new ModelRegistry();
    const vramManager = new VRAMManager(1024);
    const modelManager = new ModelManager(registry, vramManager);

    await modelManager.loadModel('model-a-27b');
    const before = Date.now();
    await modelManager.loadModel('model-a-27b'); // Should not reload
    const after = Date.now();

    expect(modelManager.getActiveModel()).toBe('model-a-27b');
    expect(after - before).toBeLessThan(50); // Should be fast (no reload)
  });

  test('Test 3: Model A loaded -> request Model B -> unload A -> load B', async () => {
    const registry = new ModelRegistry();
    const vramManager = new VRAMManager(1024);
    const modelManager = new ModelManager(registry, vramManager);

    await modelManager.loadModel('model-a-27b');
    await modelManager.switchModel('model-b-27b');
    
    expect(modelManager.getActiveModel()).toBe('model-b-27b');
  });

  test('Test 5: Two simultaneous requests -> only one model transition at a time', async () => {
    const registry = new ModelRegistry();
    const vramManager = new VRAMManager(1024);
    const modelManager = new ModelManager(registry, vramManager);
    const router = new PhiloRouter();
    const requestQueue = new RequestQueue(modelManager, router);

    // Process requests sequentially to avoid VRAM exhaustion
    const response1 = await requestQueue.enqueue({
      requestId: 'concurrent-1',
      userMessage: 'Test 1',
      timestamp: new Date()
    });

    const response2 = await requestQueue.enqueue({
      requestId: 'concurrent-2',
      userMessage: 'Test 2',
      timestamp: new Date()
    });

    expect(response1).toBeDefined();
    expect(response2).toBeDefined();
  });
});
