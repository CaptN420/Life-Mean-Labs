import { RoutingResult } from '../config/models';

export class CloudflareClefClient {
  private accountId: string;
  private authToken: string;
  private baseUrl: string;

  constructor(accountId: string, authToken: string) {
    this.accountId = accountId;
    this.authToken = authToken;
    this.baseUrl = `https://api.cloudflare.com/client/v4/accounts/${accountId}/ai/run`;
  }

  async classify(input: string): Promise<RoutingResult> {
    const response = await fetch(`${this.baseUrl}/@cf/cloudflare/clef`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.authToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'clef',
        state: input,
        questions: {
          school: {
            type: 'choice',
            instructions: 'What philosophical school does this question belong to?',
            criteria: {
              existentialism: 'Focus on individual freedom, choice, and existence',
              stoicism: 'Focus on virtue, reason, and acceptance of nature',
              nihilism: 'Focus on meaninglessness, absurdity, and rejection of values',
              spiritualism: 'Focus on metaphysics, transcendence, and spirit',
              skepticism: 'Focus on doubt, questioning, and suspension of judgment',
              pragmatism: 'Focus on practical consequences and utility'
            }
          },
          thinker: {
            type: 'choice',
            instructions: 'Which philosopher is most relevant?',
            criteria: {
              sartre: 'Existentialism - freedom and responsibility',
              camus: 'Absurdism - meaning and rebellion',
              marcus_aurelius: 'Stoicism - virtue and reason',
              nietzsche: 'Nihilism - will to power and revaluation',
             Descartes: 'Rationalism - doubt and certainty',
              hume: 'Skepticism - empiricism and doubt',
              james: 'Pragmatism - truth and utility'
            }
          },
          concepts: {
            type: 'noul',
            instructions: 'Extract key philosophical concepts from this input.'
          },
          route: {
            type: 'choice',
            instructions: 'Which model should handle this request?',
            criteria: {
              'model-a-27b': 'Specialist - deep philosophical analysis',
              'model-b-27b': 'Alternative specialist - different perspective',
              general: 'General - broad overview sufficient'
            }
          },
          needs_clarification: {
            type: 'noul',
            instructions: 'Does this question need clarification before answering?'
          }
        }
      })
    });

    if (!response.ok) {
      throw new Error(`Clef API error: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    
    // Parse Clef response into RoutingResult
    return this.parseResponse(data);
  }

  private parseResponse(data: any): RoutingResult {
    const answers = data.answers || {};
    
    // Extract school from clef response
    const schoolChoice = answers.school?.selected || 'existentialism';
    
    // Extract thinker from clef response
    const thinkerChoice = answers.thinker?.selected || 'sartre';
    
    // Extract route from clef response
    const routeChoice = answers.route?.selected || 'model-a-27b';
    
    // Check if clarification is needed
    const needsClarification = answers.needs_clarification === true;
    
    return {
      school: {
        primary: schoolChoice,
        confidence: answers.school?.probabilities?.[schoolChoice] || 0.91,
        alternatives: this.extractAlternatives(answers.school)
      },
      thinker: {
        primary: thinkerChoice,
        confidence: answers.thinker?.probabilities?.[thinkerChoice] || 0.88,
        alternatives: this.extractAlternatives(answers.thinker)
      },
      concepts: this.extractConcepts(answers.concepts),
      route: routeChoice,
      confidence: this.calculateConfidence(answers),
      needs_clarification: needsClarification
    };
  }

  private extractAlternatives(answer: any): Array<{ label: string; confidence: number }> {
    if (!answer?.probabilities) return [];
    
    return Object.entries(answer.probabilities)
      .filter(([key]) => key !== answer.selected)
      .map(([label, confidence]) => ({
        label,
        confidence: confidence as number
      }))
      .slice(0, 2);
  }

  private extractConcepts(answer: any): string[] {
    if (!answer?.text) return ['freedom', 'existence', 'meaning'];

    // Extract key terms from the response text
    const words = answer.text.toLowerCase()
      .split(/\s+/)
      .filter((w: string) => w.length > 4 && !['about', 'this', 'that', 'with', 'from', 'have', 'what', 'when', 'where', 'which', 'while', 'whose', 'would'].includes(w));

    return [...new Set(words)].slice(0, 5) as string[];
  }

  private calculateConfidence(answers: any): number {
    const schoolConf = answers.school?.probabilities?.[answers.school?.selected] || 0.9;
    const thinkerConf = answers.thinker?.probabilities?.[answers.thinker?.selected] || 0.85;
    const routeConf = answers.route?.probabilities?.[answers.route?.selected] || 0.9;
    
    return (schoolConf * 0.4 + thinkerConf * 0.3 + routeConf * 0.3);
  }
}
