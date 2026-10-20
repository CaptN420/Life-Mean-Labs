/**
 * AuditLogger — Journal d'audit des décisions de sécurité
 * 
 * Enregistre les événements de sécurité dans un fichier JSONL.
 * Ne journalise JAMAIS les tokens, clés API ou secrets.
 */

import { existsSync, mkdirSync, writeFileSync, appendFileSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import * as crypto from 'crypto';

// ── Types ────────────────────────────────────────────────────────────────────

export type AuditEventType =
  | 'AUTH_REQUIRED'
  | 'AUTH_SUCCESS'
  | 'AUTH_FAILED'
  | 'AUTHZ_REQUIRED'
  | 'AUTHZ_GRANTED'
  | 'AUTHZ_DENIED'
  | 'SECURITY_GATE_CHECK'
  | 'SECURITY_GATE_ALLOW'
  | 'SECURITY_GATE_DENY'
  | 'SECURITY_GATE_ERROR'
  | 'TASK_SUBMITTED'
  | 'TASK_APPROVED'
  | 'TASK_REJECTED'
  | 'TASK_ABORTED'
  | 'TASK_BLOCKED'
  | 'TASK_EXPIRED'
  | 'ATTEMPT_BYPASS'
  | 'ERROR';

export interface AuditEvent {
  event_id: string;
  timestamp: string;
  correlation_id?: string;
  event_type: AuditEventType;
  task_id?: string;
  workspace_id?: string;
  operation?: string;
  decision?: 'ALLOW' | 'DENY' | 'PENDING_APPROVAL';
  reason?: string;
  component: string;
  details?: Record<string, unknown>;
}

// ── Configuration ────────────────────────────────────────────────────────────

const AUDIT_LOG_PATH = process.env.AUDIT_LOG_PATH || join(__dirname, '..', '..', 'audit_log.jsonl');
const RETENTION_DAYS = parseInt(process.env.AUDIT_RETENTION_DAYS || '90', 10);

// ── Helpers ──────────────────────────────────────────────────────────────────

function generateEventId(): string {
  return `evt_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
}

function generateCorrelationId(): string {
  return `corr_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
}

// ── Core Functions ───────────────────────────────────────────────────────────

/**
 * Enregistre un événement d'audit.
 * Ne journalise PAS les tokens, clés API ou secrets.
 */
export function logEvent(event: Omit<AuditEvent, 'event_id' | 'timestamp' | 'correlation_id'> & { correlation_id?: string }): AuditEvent {
  const sanitizedEvent = sanitizeEvent(event);
  const fullEvent: AuditEvent = {
    ...sanitizedEvent,
    event_id: generateEventId(),
    timestamp: new Date().toISOString(),
  };

  try {
    writeAuditLog(fullEvent);
  } catch (error) {
    console.error('[AuditLogger] Failed to write audit log:', error);
  }

  return fullEvent;
}

/**
 * Sanitise l'événement pour supprimer les secrets.
 */
function sanitizeEvent(event: Omit<AuditEvent, 'event_id' | 'timestamp'> & { correlation_id?: string }): Omit<AuditEvent, 'event_id' | 'timestamp'> & { correlation_id?: string } {
  const sanitized = { ...event, correlation_id: event.correlation_id || generateCorrelationId() };
  
  // Supprimer les champs sensibles des détails
  if (sanitized.details) {
    const sensitiveKeys = ['token', 'api_key', 'secret', 'password', 'authorization'];
    for (const key of sensitiveKeys) {
      delete sanitized.details[key];
    }
  }

  return sanitized;
}

/**
 * Écrit l'événement dans le fichier JSONL.
 */
function writeAuditLog(event: AuditEvent): void {
  try {
    const dir = join(AUDIT_LOG_PATH, '..');
    if (!existsSync(dir)) {
      mkdirSync(dir, { recursive: true });
    }
    appendFileSync(AUDIT_LOG_PATH, JSON.stringify(event) + '\n', 'utf-8');
  } catch (error) {
    console.error('[AuditLogger] Failed to write audit log:', error);
  }
}

/**
 * Nettoie les anciens événements d'audit.
 */
export function rotateAuditLog(maxAgeDays: number = RETENTION_DAYS): void {
  try {
    if (!existsSync(AUDIT_LOG_PATH)) {
      return;
    }

    const content = readFileSync(AUDIT_LOG_PATH, 'utf-8');
    const lines = content.split('\n').filter(line => line.trim());
    
    const cutoff = Date.now() - maxAgeDays * 24 * 60 * 60 * 1000;
    const validLines = lines.filter(line => {
      try {
        const event = JSON.parse(line) as AuditEvent;
        return new Date(event.timestamp).getTime() > cutoff;
      } catch {
        return false;
      }
    });

    writeFileSync(AUDIT_LOG_PATH, validLines.join('\n') + '\n', 'utf-8');
  } catch (error) {
    console.error('[AuditLogger] Failed to rotate audit log:', error);
  }
}

// ── Convenience Functions ────────────────────────────────────────────────────

export const Audit = {
  /**
   * Authentification requise.
   */
  authRequired(taskId: string, operation: string): AuditEvent {
    return logEvent({
      event_type: 'AUTH_REQUIRED',
      task_id: taskId,
      operation,
      component: 'AuditLogger',
      reason: 'Authentication required',
    });
  },

  /**
   * Authentification réussie.
   */
  authSuccess(taskId: string, clientId: string, role: string): AuditEvent {
    return logEvent({
      event_type: 'AUTH_SUCCESS',
      task_id: taskId,
      operation: 'AUTH',
      component: 'AuditLogger',
      reason: `Authenticated as ${clientId} with role ${role}`,
      details: { client_id: clientId, role },
    });
  },

  /**
   * Échec d'authentification.
   */
  authFailed(taskId: string, reason: string): AuditEvent {
    return logEvent({
      event_type: 'AUTH_FAILED',
      task_id: taskId,
      operation: 'AUTH',
      decision: 'DENY',
      component: 'AuditLogger',
      reason,
    });
  },

  /**
   * Autorisation requise.
   */
  authzRequired(taskId: string, operation: string, requiredRole: string): AuditEvent {
    return logEvent({
      event_type: 'AUTHZ_REQUIRED',
      task_id: taskId,
      operation,
      component: 'AuditLogger',
      reason: `Authorization required: ${requiredRole}`,
      details: { required_role: requiredRole },
    });
  },

  /**
   * Autorisation accordée.
   */
  authzGranted(taskId: string, clientId: string, role: string): AuditEvent {
    return logEvent({
      event_type: 'AUTHZ_GRANTED',
      task_id: taskId,
      operation: 'AUTHZ',
      decision: 'ALLOW',
      component: 'AuditLogger',
      reason: `Authorization granted for ${clientId} with role ${role}`,
      details: { client_id: clientId, role },
    });
  },

  /**
   * Autorisation refusée.
   */
  authzDenied(taskId: string, clientId: string, requiredRole: string): AuditEvent {
    return logEvent({
      event_type: 'AUTHZ_DENIED',
      task_id: taskId,
      operation: 'AUTHZ',
      decision: 'DENY',
      component: 'AuditLogger',
      reason: `Insufficient permissions: requires ${requiredRole}`,
      details: { client_id: clientId },
    });
  },

  /**
   * Vérification Security Gate.
   */
  gateCheck(taskId: string, operation: string, decision: 'ALLOW' | 'DENY', reason: string): AuditEvent {
    return logEvent({
      event_type: decision === 'ALLOW' ? 'SECURITY_GATE_ALLOW' : 'SECURITY_GATE_DENY',
      task_id: taskId,
      operation,
      decision,
      component: 'AuditLogger',
      reason,
    });
  },

  /**
   * Erreur Security Gate.
   */
  gateError(taskId: string, error: string): AuditEvent {
    return logEvent({
      event_type: 'SECURITY_GATE_ERROR',
      task_id: taskId,
      operation: 'SECURITY_GATE',
      decision: 'DENY',
      component: 'AuditLogger',
      reason: `Security Gate error: ${error}`,
      details: { error },
    });
  },

  /**
   * Tâche soumise.
   */
  taskSubmitted(taskId: string, workspaceId: string, mode: string): AuditEvent {
    return logEvent({
      event_type: 'TASK_SUBMITTED',
      task_id: taskId,
      workspace_id: workspaceId,
      operation: 'SUBMIT',
      decision: 'ALLOW',
      component: 'AuditLogger',
      reason: `Task submitted in ${mode} mode`,
      details: { mode },
    });
  },

  /**
   * Tâche approuvée.
   */
  taskApproved(taskId: string, approvedBy: string): AuditEvent {
    return logEvent({
      event_type: 'TASK_APPROVED',
      task_id: taskId,
      operation: 'APPROVE',
      decision: 'ALLOW',
      component: 'AuditLogger',
      reason: `Task approved by ${approvedBy}`,
      details: { approved_by: approvedBy },
    });
  },

  /**
   * Tâche rejetée.
   */
  taskRejected(taskId: string, rejectedBy: string, reason: string): AuditEvent {
    return logEvent({
      event_type: 'TASK_REJECTED',
      task_id: taskId,
      operation: 'REJECT',
      decision: 'DENY',
      component: 'AuditLogger',
      reason: `Task rejected by ${rejectedBy}: ${reason}`,
      details: { rejected_by: rejectedBy, reason },
    });
  },

  /**
   * Tâche abortée.
   */
  taskAborted(taskId: string, abortedBy: string): AuditEvent {
    return logEvent({
      event_type: 'TASK_ABORTED',
      task_id: taskId,
      operation: 'ABORT',
      decision: 'DENY',
      component: 'AuditLogger',
      reason: `Task aborted by ${abortedBy}`,
      details: { aborted_by: abortedBy },
    });
  },

  /**
   * Tâche expirée.
   */
  taskExpired(taskId: string): AuditEvent {
    return logEvent({
      event_type: 'TASK_EXPIRED',
      task_id: taskId,
      operation: 'EXPIRE',
      decision: 'DENY',
      component: 'AuditLogger',
      reason: 'Task approval expired',
    });
  },

  /**
   * Exécution bloquée par absence d'isolation effective.
   * DISTINCT de taskRejected : l'opération est métier-autorisée mais ne sera
   * PAS lancée car aucune isolation effective n'est fournie (ou pas de
   * contournement explicite). Jamais présenté comme une exécution sûre.
   */
  taskBlocked(taskId: string, blockedBy: string, reason: string): AuditEvent {
    return logEvent({
      event_type: 'TASK_BLOCKED',
      task_id: taskId,
      operation: 'EXECUTE',
      decision: 'DENY',
      component: 'AuditLogger',
      reason,
      details: { blocked_by: blockedBy },
    });
  },

  /**
   * Tentative de contournement.
   */
  attemptBypass(taskId: string, attemptedBy: string, method: string): AuditEvent {
    return logEvent({
      event_type: 'ATTEMPT_BYPASS',
      task_id: taskId,
      operation: 'BYPASS',
      decision: 'DENY',
      component: 'AuditLogger',
      reason: `Attempted bypass via ${method} by ${attemptedBy}`,
      details: { attempted_by: attemptedBy, method },
    });
  },

  /**
   * Erreur système.
   */
  error(taskId: string, component: string, error: string): AuditEvent {
    return logEvent({
      event_type: 'ERROR',
      task_id: taskId,
      operation: 'ERROR',
      decision: 'DENY',
      component,
      reason: error,
      details: { error },
    });
  },
};

// ── Export singleton ─────────────────────────────────────────────────────────

export const auditLogger = {
  log: logEvent,
  rotate: rotateAuditLog,
  events: Audit,
};
