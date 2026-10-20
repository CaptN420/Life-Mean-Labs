/**
 * Rate limiting middleware to prevent abuse.
 */

import { Request, Response, NextFunction } from 'express';

interface RateLimitInfo {
  count: number;
  resetTime: number;
}

const rateLimits = new Map<string, RateLimitInfo>();
const WINDOW_MS = 60 * 1000; // 1 minute
const MAX_REQUESTS = 60; // per window

export function rateLimitMiddleware(req: Request, res: Response, next: NextFunction): void {
  const clientIp = req.ip || req.connection.remoteAddress || 'unknown';
  const now = Date.now();

  let limitInfo = rateLimits.get(clientIp);

  if (!limitInfo || now > limitInfo.resetTime) {
    limitInfo = { count: 0, resetTime: now + WINDOW_MS };
  }

  limitInfo.count++;
  rateLimits.set(clientIp, limitInfo);

  res.setHeader('X-RateLimit-Limit', MAX_REQUESTS.toString());
  res.setHeader('X-RateLimit-Remaining', Math.max(0, MAX_REQUESTS - limitInfo.count).toString());
  res.setHeader('X-RateLimit-Reset', Math.ceil(limitInfo.resetTime / 1000).toString());

  if (limitInfo.count > MAX_REQUESTS) {
    res.status(429).json({ error: 'Too many requests. Please try again later.' });
    return;
  }

  next();
}
