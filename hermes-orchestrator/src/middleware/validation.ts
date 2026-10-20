/**
 * Input validation middleware for Code Lab tasks.
 */

import { Request, Response, NextFunction } from 'express';

// Allowed origins (strict whitelist)
const ALLOWED_ORIGINS = ['dashboard', 'api', 'hermes', 'rpc'] as const;
type AllowedOrigin = typeof ALLOWED_ORIGINS[number];

// Allowed modes
const ALLOWED_MODES = ['AUDIT', 'DEV', 'APPROVAL'] as const;
type AllowedMode = typeof ALLOWED_MODES[number];

// Max task description length
const MAX_DESCRIPTION_LENGTH = 10000;

// Max deadline offset (7 days)
const MAX_DEADLINE_OFFSET_MS = 7 * 24 * 60 * 60 * 1000;

export interface ValidatedTask {
  task_id: string;
  origin: AllowedOrigin;
  request_id: string;
  mode: AllowedMode;
  workspace_id: string;
  description: string;
  deadline?: string;
}

/**
 * Validate and sanitize a Code Lab task request.
 */
export function validateTaskRequest(body: unknown): { task?: ValidatedTask; error?: string } {
  if (!body || typeof body !== 'object') {
    return { error: 'Request body must be a JSON object' };
  }

  const b = body as Record<string, unknown>;

  // Validate task_id (required, min 8 chars)
  const taskId = b.task_id;
  if (!taskId || typeof taskId !== 'string' || taskId.length < 8) {
    return { error: 'task_id is required and must be at least 8 characters' };
  }

  // Validate origin (required, from whitelist)
  const origin = b.origin;
  if (!origin || !ALLOWED_ORIGINS.includes(origin as AllowedOrigin)) {
    return { error: 'origin is required and must be one of: dashboard, api, hermes, rpc' };
  }

  // Validate mode (required, from whitelist)
  const mode = b.mode;
  if (!mode || !ALLOWED_MODES.includes(mode as AllowedMode)) {
    return { error: 'mode is required and must be one of: AUDIT, DEV, APPROVAL' };
  }

  // Validate description (optional but bounded)
  const description = b.description || '';
  if (typeof description !== 'string') {
    return { error: 'description must be a string' };
  }
  if (description.length > MAX_DESCRIPTION_LENGTH) {
    return { error: `description exceeds maximum length of ${MAX_DESCRIPTION_LENGTH}` };
  }

  // Validate deadline (optional, must be future date)
  let deadline: string | undefined;
  if (b.deadline) {
    if (typeof b.deadline !== 'string') {
      return { error: 'deadline must be an ISO date string' };
    }
    const deadlineMs = new Date(b.deadline).getTime();
    const now = Date.now();
    if (deadlineMs <= now) {
      return { error: 'deadline must be in the future' };
    }
    if (deadlineMs - now > MAX_DEADLINE_OFFSET_MS) {
      return { error: 'deadline cannot be more than 7 days in the future' };
    }
    deadline = b.deadline;
  }

  // Generate workspace_id if not provided
  const workspaceId = (b.workspace_id as string) || `ws_${Date.now()}`;

  // Sanitize request_id
  const requestId = (b.request_id as string) || `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  return {
    task: {
      task_id: taskId,
      origin: origin as AllowedOrigin,
      request_id: requestId,
      mode: mode as AllowedMode,
      workspace_id: workspaceId,
      description: description.trim(),
      deadline,
    },
  };
}

/**
 * Validate task ID format (alphanumeric + hyphens).
 */
export function isValidTaskId(taskId: string): boolean {
  return /^[a-zA-Z0-9_-]{8,}$/.test(taskId);
}

/**
 * Validate workspace path (prevent directory traversal).
 */
export function sanitizeWorkspacePath(workspaceId: string): string {
  // Remove any path traversal attempts
  return workspaceId.replace(/[/\\]/g, '_').replace(/\.\./g, '');
}
