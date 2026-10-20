/**
 * codelab_adapter.ts — Secure Routeur pour les tâches Code Lab / Pi
 * 
 * Déélègue les tâches de programmation à Pi via le bridge Python.
 * Toutes les routes sont protégées par authentification et validation stricte.
 */

import { Router, Request, Response } from 'express';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { v4 as uuidv4 } from 'uuid';
import { validateTaskRequest, isValidTaskId, sanitizeWorkspacePath, ValidatedTask } from './middleware/validation';
import { AuthRequest } from './middleware/auth';
import { securityGate } from './security_gate/adapter';
import { Audit } from './security_gate/audit';

// ── Types ────────────────────────────────────────────────────────────────────

type TaskMode = 'AUDIT' | 'DEV' | 'APPROVAL';

interface TaskPermission {
  task_id: string;
  origin: string;
  request_id: string;
  mode: TaskMode;
  workspace_id: string;
  allowed_paths: string[];
  allowed_commands: string[];
  max_duration_seconds: number;
  can_commit: boolean;
  deadline?: string;
}

interface CodeLabTask {
  task_id: string;
  origin: string;
  request_id: string;
  mode: TaskMode;
  workspace_id: string;
  permissions: TaskPermission;
  description: string;
  deadline?: string;
  authenticatedBy?: string; // From auth middleware
}

interface TaskResult {
  task_id: string;
  status: 'pending' | 'pending_approval' | 'running' | 'completed' | 'failed' | 'approved' | 'rejected' | 'expired' | 'blocked_isolation_required';
  files_modified: string[];
  diff: string;
  tests_passed: boolean;
  commands_executed: string[];
  errors: string[];
  duration_seconds: number;
  audit_trail: Record<string, unknown>[];
}

// ── Isolation entitlement ────────────────────────────────────────────────────
//
// SÉCURITÉ (Phase 0.5) : on DISTINGUE clairement
//   1. L'AUTORISATION MÉTIER  -> securityGate.checkSecurity() (permission/approbation).
//   2. L'ISOLATION EFFECTIVE  -> securityGate.isolatedExecution().
// Exécuter du code arbitraire (le bridge Python) est une opération SENSIBLE qui
// REQUIERT une isolation effective. Ce Security Gate n'en fournit AUCUNE.
//
// Comportement par défaut : REFUS (fail-closed). Le seul contournement est un
// opt-in EXPLICITE et documenté via la variable d'environnement
// `ALLOW_UNSANDBOXED_EXECUTION=1`, qui reconnaît l'absence d'isolation au lieu
// de la feindre. Un sous-processus lancé dans ce cas est NOTÉ "unsandboxed".
//
// RISQUE RÉSIDUEL (finalement non isolé) : si ALLOW_UNSANDBOXED_EXECUTION=1,
// le bridge Python s'exécute DANS LE MÊME hôte, sans sandbox. Ce n'est PAS un
// environnement sûr : c'est un contournement assumé, visible dans l'audit.

type ExecutionEntitlement =
  | { allowed: true; isolated: true; reason: string }
  | { allowed: true; isolated: false; reason: string }
  | { allowed: false; isolated: false; reason: string };

const ALLOW_UNSANDBOXED_EXECUTION = 'ALLOW_UNSANDBOXED_EXECUTION';

export function resolveExecutionEntitlement(): ExecutionEntitlement {
  if (securityGate.isolatedExecution()) {
    return { allowed: true, isolated: true, reason: 'effective isolation' };
  }
  if (process.env[ALLOW_UNSANDBOXED_EXECUTION] === '1') {
    return {
      allowed: true,
      isolated: false,
      reason: 'explicit unsandboxed opt-in (ALLOW_UNSANDBOXED_EXECUTION=1) — NO OS isolation; do not treat as safe',
    };
  }
  return {
    allowed: false,
    isolated: false,
    reason: 'ISOLATION_REQUIRED: security gate provides no effective isolation; refusing to execute arbitrary code. Set ALLOW_UNSANDBOXED_EXECUTION=1 ONLY to run with NO isolation (explicit, documented risk).',
  };
}

// ── State ────────────────────────────────────────────────────────────────────

const tasks = new Map<string, CodeLabTask>();
const results = new Map<string, TaskResult>();
const approvals = new Map<string, boolean>();

// Chemin vers le bridge Python (sécurisé)
const BRIDGE_DIR = process.env.BRIDGE_DIR || join(__dirname, '..', '..', 'HOME-EXT', 'bridge');
const RUNS_DIR = process.env.CODE_LAB_RUNS_DIR || join(__dirname, '..', '..', '..', 'code_lab_runs', 'pi_runs');

// ── Helpers ──────────────────────────────────────────────────────────────────

function ensureRunsDir(): void {
  if (!existsSync(RUNS_DIR)) {
    mkdirSync(RUNS_DIR, { recursive: true });
  }
}

function startPiTask(task: CodeLabTask): { ok: boolean; isolated: boolean; reason: string } {
  // GARDE D'ISOLATION : on ne lance JAMAIS le bridge Python (code arbitraire)
  // tant qu'aucune isolation effective n'est fournie (ou un opt-in explicite).
  const entitlement = resolveExecutionEntitlement();
  if (!entitlement.allowed) {
    results.set(task.task_id, {
      task_id: task.task_id,
      status: 'blocked_isolation_required',
      files_modified: [],
      diff: '',
      tests_passed: false,
      commands_executed: [],
      errors: [entitlement.reason],
      duration_seconds: 0,
      audit_trail: [{ event: 'EXECUTION_BLOCKED', isolated: false, reason: entitlement.reason }],
    });
    return { ok: false, isolated: false, reason: entitlement.reason };
  }

  ensureRunsDir();

  const runDir = join(RUNS_DIR, task.task_id);
  if (!existsSync(runDir)) {
    mkdirSync(runDir, { recursive: true });
  }

  // Écrire la tâche dans un fichier JSON pour le bridge
  const taskFile = join(runDir, 'task.json');
  writeFileSync(taskFile, JSON.stringify(task, null, 2), 'utf-8');

  // Démarrer le bridge Python en mode détaché
  const bridgeScript = join(BRIDGE_DIR, 'run_task.py');
  if (!existsSync(bridgeScript)) {
    // Fallback : exécuter directement via python -m
    const pythonCmd = `python -m bridge.run_task "${taskFile}"`;
    spawn('cmd', ['/c', pythonCmd], {
      detached: true,
      stdio: 'ignore',
      cwd: BRIDGE_DIR,
    }).unref();
  } else {
    spawn('python', [bridgeScript, taskFile], {
      detached: true,
      stdio: 'ignore',
      cwd: BRIDGE_DIR,
    }).unref();
  }

  // Marquer comme running (isolation status conservé dans l'audit_trail)
  results.set(task.task_id, {
    task_id: task.task_id,
    status: 'running',
    files_modified: [],
    diff: '',
    tests_passed: false,
    commands_executed: [],
    errors: [],
    duration_seconds: 0,
    audit_trail: [{ event: 'EXECUTION_STARTED', isolated: entitlement.isolated, mode: entitlement.isolated ? 'isolated' : 'unsandboxed' }],
  });

  return { ok: true, isolated: entitlement.isolated, reason: entitlement.reason };
}

// ── Routes ───────────────────────────────────────────────────────────────────

export const codelabRouter = Router();

/**
 * POST /codelab/task — soumettre une tâche (requires RUNNER or ADMIN)
 */
codelabRouter.post('/task', async (req: AuthRequest, res: Response) => {
  // Validate request body
  const validation = validateTaskRequest(req.body);
  
  if (validation.error) {
    return res.status(400).json({ error: validation.error });
  }

  const validatedTask = validation.task!;

  // Check task_id format
  if (!isValidTaskId(validatedTask.task_id)) {
    return res.status(400).json({ error: 'Invalid task_id format' });
  }

  // Sanitize workspace path
  const safeWorkspaceId = sanitizeWorkspacePath(validatedTask.workspace_id);

  // Create task with authenticated user info
  const task: CodeLabTask = {
    task_id: validatedTask.task_id,
    origin: validatedTask.origin,
    request_id: validatedTask.request_id,
    mode: validatedTask.mode,
    workspace_id: safeWorkspaceId,
    permissions: {
      task_id: validatedTask.task_id,
      origin: validatedTask.origin,
      request_id: validatedTask.request_id,
      mode: validatedTask.mode,
      workspace_id: safeWorkspaceId,
      allowed_paths: [], // Must be explicitly granted
      allowed_commands: ['python', 'pytest', 'python3'], // Whitelist only
      max_duration_seconds: 300,
      can_commit: false, // Never auto-commit
      deadline: validatedTask.deadline,
    },
    description: validatedTask.description,
    deadline: validatedTask.deadline,
    authenticatedBy: req.auth?.token?.sub, // Set by auth middleware
  };

  if (tasks.has(task.task_id)) {
    return res.status(409).json({ error: `Task ${task.task_id} already exists` });
  }

  tasks.set(task.task_id, task);

  // Enregistrer la permission auprès du Security Gate
  securityGate.registerPermission({
    task_id: task.task_id,
    origin: task.origin,
    request_id: task.request_id,
    mode: task.mode,
    workspace_id: task.workspace_id,
    allowed_commands: task.permissions.allowed_commands,
    max_duration_seconds: task.permissions.max_duration_seconds,
    can_commit: task.permissions.can_commit,
    deadline: task.deadline,
  });

  // Mode APPROVAL : attendre approbation du Security Gate
  if (task.mode === 'APPROVAL') {
    const gateResult = await securityGate.checkSecurity({
      task_id: task.task_id,
      origin: task.origin,
      request_id: task.request_id,
      mode: task.mode,
      workspace_id: task.workspace_id,
      authenticatedBy: req.auth?.token?.sub || 'unknown',
      operation: 'submit',
      resources: [task.workspace_id],
      parameters: { description: task.description },
    });

    if (gateResult.decision === 'DENY') {
      Audit.taskRejected(task.task_id, req.auth?.token?.sub || 'unknown', gateResult.reason || 'Security Gate denied');
      return res.status(403).json({ error: `Task rejected: ${gateResult.reason}` });
    }

    approvals.set(task.task_id, false);
    results.set(task.task_id, {
      task_id: task.task_id,
      status: 'pending_approval',
      files_modified: [],
      diff: '',
      tests_passed: false,
      commands_executed: [],
      errors: [],
      duration_seconds: 0,
      audit_trail: [],
    });
    
    Audit.taskSubmitted(task.task_id, task.workspace_id, 'APPROVAL');
    
    return res.status(202).json({
      message: 'Task registered, awaiting Security Gate approval',
      task_id: task.task_id,
      mode: 'APPROVAL',
    });
  }

  // Modes AUDIT et DEV : vérifier le Security Gate avant de lancer
  const devGateResult = await securityGate.checkSecurity({
    task_id: task.task_id,
    origin: task.origin,
    request_id: task.request_id,
    mode: task.mode,
    workspace_id: task.workspace_id,
    authenticatedBy: req.auth?.token?.sub || 'unknown',
    operation: 'submit',
    resources: [task.workspace_id],
    parameters: { description: task.description },
  });

  if (devGateResult.decision === 'DENY') {
    Audit.taskRejected(task.task_id, req.auth?.token?.sub || 'unknown', devGateResult.reason || 'Security Gate denied');
    return res.status(403).json({ error: `Task blocked by Security Gate: ${devGateResult.reason}` });
  }

  Audit.taskSubmitted(task.task_id, task.workspace_id, task.mode);
  const launch = startPiTask(task);

  if (!launch.ok) {
    Audit.taskBlocked(task.task_id, req.auth?.token?.sub || 'unknown', launch.reason);
    return res.status(403).json({
      error: `Task registered but execution blocked: ${launch.reason}`,
      code: 'ISOLATION_REQUIRED',
      task_id: task.task_id,
    });
  }

  return res.status(201).json({
    message: launch.isolated ? 'Task submitted' : 'Task submitted (UNSANDBOXED: no OS isolation — explicit override)',
    task_id: task.task_id,
    mode: task.mode,
    execution: launch.isolated ? 'isolated' : 'unsandboxed',
  });
});

/**
 * GET /codelab/status/:id — statut d'une tâche (requires auth)
 */
codelabRouter.get('/status/:id', (req: AuthRequest, res: Response) => {
  const taskId = req.params.id;
  
  // Validate task_id format
  if (!isValidTaskId(taskId)) {
    return res.status(400).json({ error: 'Invalid task_id format' });
  }

  const task = tasks.get(taskId);
  const result = results.get(taskId);

  if (!task && !result) {
    return res.status(404).json({ error: `Task ${taskId} not found` });
  }

  // Return safe fields only (no permissions details)
  return res.json({
    task: task ? {
      task_id: task.task_id,
      origin: task.origin,
      mode: task.mode,
      description: task.description,
      workspace_id: task.workspace_id,
      authenticatedBy: task.authenticatedBy,
    } : null,
    result: result || null,
  });
});

/**
 * POST /codelab/approve/:id — approuver une tâche (requires ADMIN)
 */
codelabRouter.post('/approve/:id', async (req: AuthRequest, res: Response) => {
  const taskId = req.params.id;
  
  // Validate task_id format
  if (!isValidTaskId(taskId)) {
    return res.status(400).json({ error: 'Invalid task_id format' });
  }

  const task = tasks.get(taskId);

  if (!task) {
    return res.status(404).json({ error: `Task ${taskId} not found` });
  }

  if (task.mode !== 'APPROVAL') {
    return res.status(400).json({ error: `Task ${taskId} is not in APPROVAL mode` });
  }

  // Verify requester has permission to approve this task
  if (task.authenticatedBy && req.auth?.token?.sub !== task.authenticatedBy && req.auth?.token?.role !== 'ADMIN') {
    Audit.attemptBypass(taskId, req.auth?.token?.sub || 'unknown', 'approval_injection');
    return res.status(403).json({ error: 'You do not have permission to approve this task' });
  }

  // Vérifier auprès du Security Gate
  const gateResult = await securityGate.checkSecurity({
    task_id: taskId,
    origin: task.origin,
    request_id: task.request_id,
    mode: task.mode,
    workspace_id: task.workspace_id,
    authenticatedBy: req.auth?.token?.sub || 'unknown',
    operation: 'approve',
    resources: [task.workspace_id],
    parameters: { description: task.description },
  });

  if (gateResult.decision === 'DENY') {
    Audit.taskRejected(taskId, req.auth?.token?.sub || 'unknown', gateResult.reason || 'Security Gate denied approval');
    return res.status(403).json({ error: `Approval blocked by Security Gate: ${gateResult.reason}` });
  }

  // Approuver via le Security Gate
  securityGate.approveTask(taskId, req.auth?.token?.sub || 'unknown');
  
  const existingResult = results.get(taskId);
  if (existingResult) {
    existingResult.status = 'approved';
  } else {
    results.set(taskId, {
      task_id: taskId,
      status: 'approved',
      files_modified: [],
      diff: '',
      tests_passed: false,
      commands_executed: [],
      errors: [],
      duration_seconds: 0,
      audit_trail: [],
    });
  }

  Audit.taskApproved(taskId, req.auth?.token?.sub || 'unknown');

  // Lancer la tâche maintenant qu'elle est approuvée — SAUF si aucune isolation.
  const launch = startPiTask(task);

  if (!launch.ok) {
    Audit.taskBlocked(taskId, req.auth?.token?.sub || 'unknown', launch.reason);
    return res.json({
      message: `Task ${taskId} approved but execution blocked (no effective isolation)`,
      task_id: taskId,
      approved: true,
      execution: 'blocked_isolation_required',
      reason: launch.reason,
    });
  }

  return res.json({
    message: launch.isolated
      ? `Task ${taskId} approved and started`
      : `Task ${taskId} approved and started (UNSANDBOXED: no OS isolation — explicit override)`,
    task_id: taskId,
    approved: true,
    execution: launch.isolated ? 'isolated' : 'unsandboxed',
  });
});

/**
 * POST /codelab/reject/:id — rejeter une tâche (requires ADMIN)
 */
codelabRouter.post('/reject/:id', (req: AuthRequest, res: Response) => {
  const taskId = req.params.id;
  
  // Validate task_id format
  if (!isValidTaskId(taskId)) {
    return res.status(400).json({ error: 'Invalid task_id format' });
  }

  const task = tasks.get(taskId);

  if (!task) {
    return res.status(404).json({ error: `Task ${taskId} not found` });
  }

  approvals.set(taskId, false);
  const existingResult2 = results.get(taskId);
  if (existingResult2) {
    existingResult2.status = 'rejected';
  } else {
    results.set(taskId, {
      task_id: taskId,
      status: 'rejected',
      files_modified: [],
      diff: '',
      tests_passed: false,
      commands_executed: [],
      errors: [],
      duration_seconds: 0,
      audit_trail: [],
    });
  }

  return res.json({
    message: `Task ${taskId} rejected`,
    task_id: taskId,
  });
});

/**
 * POST /codelab/abort/:id — aborter une tâche (requires ADMIN)
 */
codelabRouter.post('/abort/:id', (req: AuthRequest, res: Response) => {
  const taskId = req.params.id;
  
  // Validate task_id format
  if (!isValidTaskId(taskId)) {
    return res.status(400).json({ error: 'Invalid task_id format' });
  }

  const result = results.get(taskId);

  if (!result) {
    return res.status(404).json({ error: `Task ${taskId} not found` });
  }

  // Abort the task
  results.set(taskId, {
    ...result,
    status: 'failed',
    errors: ['Task aborted by user'],
  });

  return res.json({
    message: `Task ${taskId} aborted`,
    task_id: taskId,
  });
});

/**
 * GET /codelab/tasks — liste des tâches (requires auth)
 */
codelabRouter.get('/tasks', (req: AuthRequest, res: Response) => {
  const taskList = Array.from(tasks.values()).map((t) => ({
    task_id: t.task_id,
    origin: t.origin,
    mode: t.mode,
    description: t.description,
    status: results.get(t.task_id)?.status || 'unknown',
    authenticatedBy: t.authenticatedBy,
  }));

  return res.json({ tasks: taskList });
});
