/**
 * Hermes Orchestrator - Secure Backend
 * 
 * This module provides the HTTP API for the Life_mean system.
 * All sensitive routes are protected by authentication and authorization.
 */

import express from 'express';
import { ModelRegistry } from './models/ModelRegistry';
import { VRAMManager } from './models/VRAMManager';
import { ModelManager } from './models/ModelManager';
import { PhiloRouter } from './router/PhiloRouter';
import { RequestQueue } from './orchestrator/RequestQueue';
import { DEFAULT_CONFIG } from './config/models';
import { codelabRouter } from './codelab_adapter';
import { authenticate, authorize, UserRole } from './middleware/auth';
import { corsMiddleware } from './middleware/cors';
import { rateLimitMiddleware } from './middleware/rate-limit';

const app = express();

// ── Security Middleware ──────────────────────────────────────────────────────

// CORS with strict origin policy
app.use(corsMiddleware);

// Rate limiting to prevent abuse
app.use(rateLimitMiddleware);

// Parse JSON bodies
app.use(express.json({ limit: '1mb' }));

// ── Initialize Components ───────────────────────────────────────────────────

const registry = new ModelRegistry();
const vramManager = new VRAMManager(DEFAULT_CONFIG.vramReserveMB);
const modelManager = new ModelManager(registry, vramManager);
const router = new PhiloRouter();
const requestQueue = new RequestQueue(modelManager, router);

// ── Public Endpoints (no auth required) ─────────────────────────────────────

/**
 * Health check endpoint - public info only.
 */
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    activeModel: modelManager.getActiveModel(),
    vram: vramManager.getFreeVRAMSync(),
    queueLength: requestQueue.getQueueLength()
  });
});

// ── Protected Endpoints (authentication required) ───────────────────────────

/**
 * Main inference endpoint - requires RUNNER or ADMIN role.
 */
app.post('/inference', authenticate, authorize('RUNNER'), async (req, res) => {
  const message = req.body?.message;

  if (!message || typeof message !== 'string') {
    return res.status(400).json({ error: 'message is required and must be a string' });
  }

  try {
    const response = await requestQueue.enqueue({
      requestId: `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      userMessage: message,
      timestamp: new Date(),
    });

    res.json({ response });
  } catch (error) {
    console.error('Inference error:', error);
    res.status(500).json({
      error: 'Inference failed',
      details: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});

// ── Model Management (ADMIN only) ───────────────────────────────────────────

/**
 * Get model list - requires authentication.
 */
app.get('/models', authenticate, async (req, res) => {
  const models = registry.getAll();
  const states = await Promise.all(
    models.map(async m => ({
      ...m,
      state: await modelManager.getModelStatus(m.id)
    }))
  );
  res.json(states);
});

/**
 * Load a model - requires ADMIN role.
 */
app.post('/models/:id/load', authenticate, authorize('ADMIN'), async (req, res) => {
  try {
    await modelManager.loadModel(req.params.id);
    res.json({ success: true, activeModel: modelManager.getActiveModel() });
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

/**
 * Unload a model - requires ADMIN role.
 */
app.post('/models/:id/unload', authenticate, authorize('ADMIN'), async (req, res) => {
  try {
    await modelManager.unloadModel(req.params.id);
    res.json({ success: true, activeModel: modelManager.getActiveModel() });
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

// ── Code Lab / Pi routes (authenticated + validated) ────────────────────────

app.use('/codelab', authenticate, codelabRouter);

// ── Start Server (loopback only) ────────────────────────────────────────────

const PORT = parseInt(process.env.PORT || '3000', 10);
const HOST = process.env.HOST || '127.0.0.1'; // Localhost only by default

app.listen(PORT, HOST, () => {
  console.log(`Hermes Orchestrator running on http://${HOST}:${PORT}`);
  console.log(`Available models: ${registry.getAll().map(m => m.id).join(', ')}`);
  console.log(`Code Lab routes: POST /codelab/task, GET /codelab/status/:id, POST /codelab/approve/:id, POST /codelab/abort/:id`);
  console.log(`Security: Authentication required for all write operations`);
});

export { app };
