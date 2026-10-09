import { RequestContext, RequestMetrics } from '../config/models';
import { ModelManager } from '../models/ModelManager';
import { PhiloRouter } from '../router/PhiloRouter';
import { 
  OrchestrationError, 
  RoutingError,
  InferenceError 
} from '../orchestrator/OrchestrationError';

export class RequestQueue {
  private queue: Array<{
    request: RequestContext;
    resolve: (value: string) => void;
    reject: (reason?: any) => void;
    startTime: number;
  }> = [];

  constructor(
    private modelManager: ModelManager,
    private router: PhiloRouter
  ) {}

  async enqueue(request: RequestContext): Promise<string> {
    return new Promise((resolve, reject) => {
      this.queue.push({
        request,
        resolve,
        reject,
        startTime: Date.now()
      });
      this.processQueue();
    });
  }

  private async processQueue(): Promise<void> {
    if (this.queue.length === 0) return;

    const item = this.queue.shift()!;

    try {
      await this.processRequest(item.request, item.resolve, item.reject);
    } catch (error) {
      item.reject(error);
    }

    // Continue processing
    if (this.queue.length > 0) {
      setTimeout(() => this.processQueue(), 10);
    }
  }

  private async processRequest(
    request: RequestContext,
    resolve: (value: string) => void,
    reject: (reason?: any) => void
  ): Promise<void> {
    const startTime = Date.now();
    let activeModel = this.modelManager.getActiveModel();
    let previousModel: string | null = null;
    let routingResult = null;
    let fallback = false;

    try {
      // Step 1: Load Clef for classification
      await this.modelManager.loadModel('clef');
      const vramBefore = await this.modelManager.getVRAMUsage();

      // Step 2: Classify with Clef
      const routingTimeStart = Date.now();
      routingResult = await this.router.classify(request.userMessage);
      const routingTimeMs = Date.now() - routingTimeStart;

      // Step 3: Validate routing result
      this.router.validateResult(routingResult);

      // Step 4: Unload Clef
      await this.modelManager.unloadModel('clef');

      // Step 5: Determine target model
      const targetModel = this.determineTargetModel(routingResult);
      previousModel = activeModel;

      // Step 6: Load target model if needed
      if (activeModel !== targetModel) {
        await this.modelManager.loadModel(targetModel);
      }

      // Step 7: Generate response
      const inferenceTimeStart = Date.now();
      const response = await this.generateResponse(request, routingResult);
      const inferenceTimeMs = Date.now() - inferenceTimeStart;

      const totalTimeMs = Date.now() - startTime;
      const vramAfter = await this.modelManager.getVRAMUsage();

      // Log metrics (in production, send to monitoring)
      const metrics: RequestMetrics = {
        requestId: request.requestId,
        activeModel: this.modelManager.getActiveModel(),
        previousModel,
        requestedModel: targetModel,
        loadTimeMs: 0, // Would track actual load time
        unloadTimeMs: 0, // Would track actual unload time
        inferenceTimeMs,
        routingTimeMs,
        totalTimeMs,
        vramBefore: vramBefore.free,
        vramAfter: vramAfter.free,
        route: routingResult.route,
        confidence: routingResult.confidence,
        cacheHit: activeModel === targetModel,
        fallback,
        error: null
      };

      console.log('[Metrics]', JSON.stringify(metrics));

      resolve(response);

    } catch (error) {
      const totalTimeMs = Date.now() - startTime;
      
      // Fallback handling
      if (error instanceof RoutingError && !fallback) {
        fallback = true;
        try {
          // Retry with general model
          await this.modelManager.loadModel('model-a-27b');
          const response = await this.generateFallbackResponse(request);
          resolve(response);
          return;
        } catch (fallbackError) {
          reject(new OrchestrationError(
            'All fallback attempts failed',
            'FALLBACK_FAILED',
            { originalError: error, fallbackError }
          ));
          return;
        }
      }

      reject(error);
    }
  }

  private determineTargetModel(routingResult: any): string {
    // In production, use routing result to determine model
    // For now, default to model-a-27b
    if (routingResult?.route && ['model-a-27b', 'model-b-27b'].includes(routingResult.route)) {
      return routingResult.route;
    }
    return 'model-a-27b';
  }

  private async generateResponse(request: RequestContext, routingResult: any): Promise<string> {
    // In production, this would call the loaded model with the original message + context
    const context = JSON.stringify({
      user_message: request.userMessage,
      routing: {
        school: routingResult.school?.primary,
        thinker: routingResult.thinker?.primary,
        confidence: routingResult.confidence
      }
    });

    // Simulate response generation
    return `Response based on ${routingResult.school?.primary} perspective: ${request.userMessage}`;
  }

  private async generateFallbackResponse(request: RequestContext): Promise<string> {
    return `Generic response to: ${request.userMessage}`;
  }

  getQueueLength(): number {
    return this.queue.length;
  }
}
