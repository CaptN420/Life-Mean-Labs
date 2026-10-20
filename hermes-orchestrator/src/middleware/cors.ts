/**
 * CORS middleware with strict policy for local deployment.
 */

import { Request, Response, NextFunction } from 'express';

// Allowed origins - strictly local for security
const ALLOWED_ORIGINS = [
  'http://127.0.0.1:8080',
  'http://localhost:8080',
  'http://127.0.0.1:3000',
  'http://localhost:3000',
];

export function corsMiddleware(req: Request, res: Response, next: NextFunction): void {
  const origin = req.headers.origin;

  if (origin && ALLOWED_ORIGINS.includes(origin)) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type');
    res.setHeader('Access-Control-Allow-Credentials', 'true');
    res.setHeader('Access-Control-Max-Age', '86400');
  }

  // Handle preflight requests
  if (req.method === 'OPTIONS') {
    res.status(200).end();
    return;
  }

  next();
}
