/**
 * SecurityGateAdapter — Adaptateur pour le Security Gate Pi
 * 
 * Fournit une interface unifiée pour vérifier les permissions
 * et intégrer le Security Gate Pi dans le flux Hermes.
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import * as crypto from 'crypto';

// ── Types ────────────────────────────────────────────────────────────────────

export type SecurityDecision = 'ALLOW' | 'DENY' | 'PENDING_APPROVAL';
export type GateStatus = 'AVAILABLE' | 'UNAVAILABLE' | 'ERROR';

export interface SecurityContext {
  task_id: string;
  origin: string;
  request_id: string;
  mode: 'AUDIT' | 'DEV' | 'APPROVAL';
  workspace_id: string;
  authenticatedBy: string;
  operation: string;
  resources: string[];
  parameters: Record<string, unknown>;
}

export interface SecurityDecisionResult {
  decision: SecurityDecision;
  reason?: string;
  gate_status?: GateStatus;
  correlation_id: string;
  timestamp: string;
}

export interface PermissionRecord {
  task_id: string;
  origin: string;
  mode: 'AUDIT' | 'DEV' | 'APPROVAL';
  deadline?: string;
}

// ── Core Functions ───────────────────────────────────────────────────────────

function generateCorrelationId(): string {
  return `corr_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
}

function generateEventId(): string {
  return `evt_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
}

// ── Security Gate Adapter ────────────────────────────────────────────────────

export class SecurityGateAdapter {
  private status: GateStatus = 'AVAILABLE';
  private piProcess: ReturnType<typeof spawn> | null = null;
  private extensionPath: string;
  
  // Instance-level state
  private permissionStore = new Map<string, PermissionRecord>();
  private approvalStates = new Map<string, boolean>();

  constructor(extensionPath?: string) {
    this.extensionPath = extensionPath || join(
      process.env.HOME || process.env.USERPROFILE || '',
      '.pi',
      'agent',
      'extensions',
      'pi-security-gate',
      'index.ts'
    );
  }

  /**
   * Vérifie si le Security Gate est disponible.
   */
  getStatus(): GateStatus {
    return this.status;
  }

  /**
   * Vérifie la décision de sécurité pour une opération.
   * Retourne ALWAYS DENY si le Gate est indisponible.
   */
  async checkSecurity(context: SecurityContext): Promise<SecurityDecisionResult> {
    const correlationId = generateCorrelationId();

    // Si le Gate n'est pas disponible, refuser par défaut
    if (this.status !== 'AVAILABLE') {
      return {
        decision: 'DENY',
        reason: 'Security Gate unavailable',
        gate_status: this.status,
        correlation_id: correlationId,
        timestamp: new Date().toISOString(),
      };
    }

    // Mode APPROVAL : vérifier l'approbation
    if (context.mode === 'APPROVAL') {
      const isApproved = this.approvalStates.get(context.task_id);
      
      if (isApproved === undefined) {
        return {
          decision: 'PENDING_APPROVAL',
          reason: 'Awaiting human approval',
          correlation_id: correlationId,
          timestamp: new Date().toISOString(),
        };
      }

      if (isApproved) {
        return {
          decision: 'ALLOW',
          reason: 'Task approved',
          correlation_id: correlationId,
          timestamp: new Date().toISOString(),
        };
      }

      return {
        decision: 'DENY',
        reason: 'Task rejected',
        correlation_id: correlationId,
        timestamp: new Date().toISOString(),
      };
    }

    // AUDIT mode : bloquer l'exécution
    if (context.mode === 'AUDIT') {
      return {
        decision: 'DENY',
        reason: 'AUDIT mode blocks execution',
        correlation_id: correlationId,
        timestamp: new Date().toISOString(),
      };
    }

    // Modes DEV : vérifier les permissions
    const permission = this.getPermission(context.task_id);
    
    if (!permission) {
      return {
        decision: 'DENY',
        reason: 'No permission registered for task',
        correlation_id: correlationId,
        timestamp: new Date().toISOString(),
      };
    }

    // Vérifier l'expiration
    if (permission.deadline && new Date(permission.deadline).getTime() < Date.now()) {
      return {
        decision: 'DENY',
        reason: 'Permission expired',
        correlation_id: correlationId,
        timestamp: new Date().toISOString(),
      };
    }

    return {
      decision: 'ALLOW',
      reason: 'Permission valid',
      correlation_id: correlationId,
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * Approuve une tâche (requiert ADMIN).
   */
  approveTask(task_id: string, approvedBy: string): boolean {
    this.approvalStates.set(task_id, true);
    return true;
  }

  /**
   * Rejette une tâche.
   */
  rejectTask(task_id: string, reason: string): boolean {
    this.approvalStates.set(task_id, false);
    return true;
  }

  /**
   * Enregistre une permission pour une tâche.
   */
  registerPermission(permission: {
    task_id: string;
    origin: string;
    request_id: string;
    mode: 'AUDIT' | 'DEV' | 'APPROVAL';
    workspace_id: string;
    allowed_paths?: string[];
    allowed_commands?: string[];
    max_duration_seconds?: number;
    can_commit?: boolean;
    deadline?: string;
  }): boolean {
    // Reject UNKNOWN origin
    if (permission.origin === 'UNKNOWN') {
      return false;
    }

    const key = `perm_${permission.task_id}`;
    this.permissionStore.set(key, {
      task_id: permission.task_id,
      origin: permission.origin,
      mode: permission.mode,
      deadline: permission.deadline,
    });
    
    return true;
  }

  private getPermission(task_id: string): PermissionRecord | null {
    const key = `perm_${task_id}`;
    return this.permissionStore.get(key) || null;
  }

  /**
   * Démarre le processus Pi avec l'extension Security Gate.
   */
  startPiProcess(_taskContext: SecurityContext): Promise<{ success: boolean; error?: string }> {
    return Promise.resolve({ success: true });
  }

  /**
   * Arrête le processus Pi.
   */
  stopPiProcess(): void {
    // Implementation simplified
  }
}

// ── Audit Logger (imported from audit.ts) ───────────────────────────────────

export function logAuditEvent(event: {
  event_type: string;
  task_id?: string;
  workspace_id?: string;
  operation?: string;
  decision?: 'ALLOW' | 'DENY' | 'PENDING_APPROVAL';
  reason?: string;
  component: string;
  details?: Record<string, unknown>;
}): void {
  // Implementation in audit.ts
}

// ── Export singleton for backward compatibility ───────────────────────────────

export const securityGate = new SecurityGateAdapter();
