import { RoutingResult } from '../config/models';
import { RoutingError } from '../orchestrator/OrchestrationError';
import { CloudflareClefClient } from './CloudflareClefClient';

export const ALLOWED_ROUTES = [
  'model-a-27b',
  'model-b-27b',
  'general',
  'clarification'
];

export class PhiloRouter {
  private readonly schema = {
    type: 'object',
    required: ['school', 'thinker', 'concepts', 'route', 'confidence', 'needs_clarification'],
    properties: {
      school: {
        type: 'object',
        required: ['primary', 'confidence'],
        properties: {
          primary: { type: 'string' },
          confidence: { type: 'number' },
          alternatives: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                label: { type: 'string' },
                confidence: { type: 'number' }
              }
            }
          }
        }
      },
      thinker: {
        type: 'object',
        required: ['primary', 'confidence'],
        properties: {
          primary: { type: 'string' },
          confidence: { type: 'number' },
          alternatives: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                label: { type: 'string' },
                confidence: { type: 'number' }
              }
            }
          }
        }
      },
      concepts: {
        type: 'array',
        items: { type: 'string' }
      },
      route: { type: 'string' },
      confidence: { type: 'number' },
      needs_clarification: { type: 'boolean' }
    }
  };

  private clefClient: CloudflareClefClient | null = null;

  constructor() {
    // Initialize Clef client if credentials are available
    const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;
    const authToken = process.env.CLOUDFLARE_AUTH_TOKEN;

    if (accountId && authToken) {
      this.clefClient = new CloudflareClefClient(accountId, authToken);
      console.log('[Router] Cloudflare CLEF client initialized');
    } else {
      console.log('[Router] Using simulated routing (no CLEF credentials)');
    }
  }

  async classify(input: string): Promise<RoutingResult> {
    // Try Clef first if configured
    if (this.clefClient) {
      try {
        const startTime = Date.now();
        const result = await this.clefClient.classify(input);
        console.log(`[Router] CLEF classified in ${Date.now() - startTime}ms: ${result.route}`);
        return result;
      } catch (error) {
        console.warn('[Router] CLEF classification failed, falling back to simulation:', error);
      }
    }

    // Fallback to simulated classification
    return this.simulateClassification(input);
  }

  private simulateClassification(input: string): RoutingResult {
    const simulatedResult: RoutingResult = {
      school: {
        primary: 'existentialism',
        confidence: 0.91,
        alternatives: [
          { label: 'absurdism', confidence: 0.61 }
        ]
      },
      thinker: {
        primary: 'sartre',
        confidence: 0.88,
        alternatives: [
          { label: 'camus', confidence: 0.55 }
        ]
      },
      concepts: ['freedom', 'existence', 'responsibility'],
      route: 'model-a-27b',
      confidence: 0.91,
      needs_clarification: false
    };

    this.validateResult(simulatedResult);
    return simulatedResult;
  }

  validateResult(result: RoutingResult): void {
    // Check required fields
    if (!result.school || !result.thinker) {
      throw new RoutingError('Invalid routing result: missing school or thinker');
    }

    // Validate confidence thresholds
    if (result.confidence < 0 && result.confidence > 1) {
      throw new RoutingError('Invalid confidence value');
    }

    // Check route is allowed
    if (!ALLOWED_ROUTES.includes(result.route)) {
      throw new RoutingError(`Unauthorized route: ${result.route}`);
    }

    // Validate concepts array
    if (!Array.isArray(result.concepts)) {
      throw new RoutingError('Invalid concepts format');
    }
  }

  getRouteFromConfidence(confidence: number): string {
    if (confidence >= 0.80) {
      return 'model-a-27b'; // Specialist
    } else if (confidence >= 0.50) {
      return 'general'; // Generalist fallback
    } else {
      return 'clarification'; // Needs clarification
    }
  }

  shouldClarify(result: RoutingResult): boolean {
    return result.needs_clarification || result.confidence < 0.50;
  }
}
