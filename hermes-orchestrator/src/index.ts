import express from 'express';
import { ModelRegistry } from './models/ModelRegistry';
import { VRAMManager } from './models/VRAMManager';
import { ModelManager } from './models/ModelManager';
import { PhiloRouter } from './router/PhiloRouter';
import { RequestQueue } from './orchestrator/RequestQueue';
import { DEFAULT_CONFIG } from './config/models';

const app = express();
app.use(express.json());

// Initialize components
const registry = new ModelRegistry();
const vramManager = new VRAMManager(DEFAULT_CONFIG.vramReserveMB);
const modelManager = new ModelManager(registry, vramManager);
const router = new PhiloRouter();
const requestQueue = new RequestQueue(modelManager, router);

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    activeModel: modelManager.getActiveModel(),
    vram: vramManager.getFreeVRAMSync(),
    queueLength: requestQueue.getQueueLength()
  });
});

// Main inference endpoint
app.post('/inference', async (req, res) => {
  const { message } = req.body;
  
  if (!message) {
    return res.status(400).json({ error: 'Message is required' });
  }

  try {
    const response = await requestQueue.enqueue({
      requestId: `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      userMessage: message,
      timestamp: new Date()
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

// Model management endpoints
app.get('/models', async (req, res) => {
  const models = registry.getAll();
  const states = await Promise.all(
    models.map(async m => ({
      ...m,
      state: await modelManager.getModelStatus(m.id)
    }))
  );
  res.json(states);
});

app.post('/models/:id/load', async (req, res) => {
  try {
    await modelManager.loadModel(req.params.id);
    res.json({ success: true, activeModel: modelManager.getActiveModel() });
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

app.post('/models/:id/unload', async (req, res) => {
  try {
    await modelManager.unloadModel(req.params.id);
    res.json({ success: true, activeModel: modelManager.getActiveModel() });
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Hermes Orchestrator running on port ${PORT}`);
  console.log(`Available models: ${registry.getAll().map(m => m.id).join(', ')}`);
});

export { app };
