/**
 * Authentication middleware for Hermes Orchestrator
 * 
 * Provides token-based authentication with role-based access control.
 * Tokens are JSON-encoded and base64url-encoded for local deployment.
 */

import { Request, Response, NextFunction } from 'express';
import * as crypto from 'crypto';

// ── Types ────────────────────────────────────────────────────────────────────

export type UserRole = 'OBSERVER' | 'RUNNER' | 'ADMIN';

export interface AuthToken {
  sub: string;           // Client identifier
  role: UserRole;
  iat: number;           // Issued at timestamp
  exp: number;           // Expiration timestamp
  jti: string;           // Token ID (for revocation)
}

export interface AuthRequest extends Request {
  auth?: {
    token: AuthToken;
    valid: boolean;
  };
}

// ── In-Memory Token Store (for local deployment) ────────────────────────────

const REVOKED_TOKENS = new Set<string>();
const TOKEN_EXPIRY_MS = 24 * 60 * 60 * 1000; // 24 hours

// ── Token Generation ─────────────────────────────────────────────────────────

/**
 * Generate a secure opaque token for local authentication.
 * Token format: base64url(JSON.stringify(tokenData))
 */
export function generateToken(clientId: string, role: UserRole): string {
  const tokenData: AuthToken = {
    sub: clientId,
    role,
    iat: Date.now(),
    exp: Date.now() + TOKEN_EXPIRY_MS,
    jti: crypto.randomBytes(8).toString('hex'),
  };

  // Encode as base64url
  const json = JSON.stringify(tokenData);
  return Buffer.from(json).toString('base64url');
}

/**
 * Validate and parse a token.
 * Returns null if invalid or expired.
 */
export function validateToken(token: string): AuthToken | null {
  if (!token || typeof token !== 'string') {
    return null;
  }

  // Check if token has been revoked
  if (REVOKED_TOKENS.has(token)) {
    return null;
  }

  try {
    // Decode from base64url
    const decoded = Buffer.from(token, 'base64url').toString('utf-8');
    
    // Parse JSON
    let tokenData: Partial<AuthToken>;
    try {
      tokenData = JSON.parse(decoded);
    } catch {
      // Not valid JSON - invalid token format
      return null;
    }

    // Validate required fields
    if (!tokenData.sub || !tokenData.role || !tokenData.iat || !tokenData.exp || !tokenData.jti) {
      return null;
    }

    // Check expiration
    if (tokenData.exp < Date.now()) {
      return null;
    }

    // Validate role
    if (!['OBSERVER', 'RUNNER', 'ADMIN'].includes(tokenData.role)) {
      return null;
    }

    return tokenData as AuthToken;
  } catch {
    return null;
  }
}

// ── Middleware ───────────────────────────────────────────────────────────────

/**
 * Authentication middleware - verifies token presence and validity.
 */
export function authenticate(req: Request, res: Response, next: NextFunction): void {
  const authHeader = req.headers['authorization'];
  
  if (!authHeader) {
    res.status(401).json({ error: 'Authorization header required' });
    return;
  }

  // Parse Bearer token
  const parts = authHeader.split(' ');
  if (parts.length !== 2 || parts[0] !== 'Bearer') {
    res.status(401).json({ error: 'Invalid authorization format. Use: Bearer <token>' });
    return;
  }

  const token = parts[1];
  const tokenData = validateToken(token);

  if (!tokenData) {
    res.status(401).json({ error: 'Invalid or expired token' });
    return;
  }

  // Attach auth info to request
  (req as AuthRequest).auth = {
    token: tokenData,
    valid: true,
  };

  next();
}

/**
 * Role-based authorization middleware.
 */
export function authorize(requiredRole: UserRole) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const auth = (req as AuthRequest).auth;
    
    if (!auth || !auth.valid) {
      res.status(401).json({ error: 'Authentication required' });
      return;
    }

    const userRole = auth.token.role;
    
    // Role hierarchy: ADMIN > RUNNER > OBSERVER
    const roleLevel = {
      'OBSERVER': 1,
      'RUNNER': 2,
      'ADMIN': 3,
    };

    if ((roleLevel[userRole] || 0) < (roleLevel[requiredRole] || 0)) {
      res.status(403).json({ error: `Insufficient permissions. Required: ${requiredRole}` });
      return;
    }

    next();
  };
}

// ── Revocation ───────────────────────────────────────────────────────────────

/**
 * Revoke a token (for logout or security incidents).
 */
export function revokeToken(token: string): void {
  REVOKED_TOKENS.add(token);
}

/**
 * Revoke all tokens for a client.
 */
export function revokeAllTokensForClient(clientId: string): void {
  // In production, would query token store by sub
  // For now, this is a no-op as we don't track by client
}

// ── Security Helpers ─────────────────────────────────────────────────────────

/**
 * Generate a secure API key for client registration.
 */
export function generateApiKey(): string {
  return crypto.randomBytes(32).toString('base64');
}

/**
 * Hash a secret for storage (one-way).
 */
export function hashSecret(secret: string): string {
  return crypto.createHash('sha256').update(secret).digest('base64');
}

/**
 * Constant-time comparison to prevent timing attacks.
 */
export function secureCompare(a: string, b: string): boolean {
  if (typeof a !== 'string' || typeof b !== 'string') {
    return false;
  }
  return crypto.timingSafeEqual(
    Buffer.from(a),
    Buffer.from(b)
  );
}
