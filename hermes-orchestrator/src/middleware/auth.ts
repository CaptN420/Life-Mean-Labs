/**
 * Authentication middleware for Hermes Orchestrator
 * 
 * Provides token-based authentication with role-based access control.
 *
 * Tokens are HMAC-SHA256 signed (built-in primitive) with a server-side secret
 * that is NEVER embedded in the token and NEVER committed. The secret comes
 * from the AUTH_SECRET env var, or a git-ignored key file generated on first
 * run (`./.auth-secret`). Without a usable secret, issuance/validation fail
 * closed.
 *
 * Token format: `<base64url(payload JSON)>.<hex(hmac_sha256(secret, payload))>`
 */

import { Request, Response, NextFunction } from 'express';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';

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
// Allow a little clock skew on the "issued at" check.
const MAX_IAT_SKEW_MS = 5 * 60 * 1000;

// ── Secret Management (protected, git-ignored) ───────────────────────────────

const AUTH_SECRET_ENV = 'AUTH_SECRET';
const AUTH_SECRET_FILE_ENV = 'AUTH_SECRET_FILE';

function defaultSecretPath(): string {
  return path.join(process.cwd(), '.auth-secret');
}

let _cachedSecret: string | null = null;

/**
 * Resolve the signing secret. Priority:
 *   1. AUTH_SECRET env var (explicit, most controlled).
 *   2. AUTH_SECRET_FILE env var, or the default `./.auth-secret` git-ignored
 *      file — generated with 32 random bytes if absent (best-effort locked).
 * Returns null (fail-closed) if neither is available in a readable form.
 */
export function getAuthSecret(): string | null {
  if (_cachedSecret) return _cachedSecret;
  const fromEnv = process.env[AUTH_SECRET_ENV];
  if (fromEnv && fromEnv.length >= 32) {
    _cachedSecret = fromEnv;
    return _cachedSecret;
  }
  const filePath = process.env[AUTH_SECRET_FILE_ENV] || defaultSecretPath();
  try {
    if (fs.existsSync(filePath)) {
      const existing = fs.readFileSync(filePath, 'utf-8').trim();
      if (existing.length >= 32) {
        _cachedSecret = existing;
        return _cachedSecret;
      }
    }
    const generated = crypto.randomBytes(32).toString('hex');
    fs.writeFileSync(filePath, generated + '\n', { encoding: 'utf-8', mode: 0o600 });
    _cachedSecret = generated;
    return _cachedSecret;
  } catch {
    // Can't read a persisted secret and no env secret: fail closed.
    _cachedSecret = null;
    return null;
  }
}

// ── HMAC signing / verification (proven primitive) ───────────────────────────

function sign(payload: string, secret: string): string {
  return crypto.createHmac('sha256', secret).update(payload).digest('hex');
}

/**
 * Constant-time comparison that returns false (never throws) when the inputs
 * have different lengths. Node's timingSafeEqual throws on unequal-length
 * buffers, so lengths are checked before comparing.
 */
export function secureCompare(a: string, b: string): boolean {
  if (typeof a !== 'string' || typeof b !== 'string') {
    return false;
  }
  if (a.length !== b.length) {
    return false;
  }
  try {
    return crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));
  } catch {
    return false;
  }
}

function decodePayload(payload: string): AuthToken | null {
  try {
    const decoded = Buffer.from(payload, 'base64url').toString('utf-8');
    const tokenData = JSON.parse(decoded) as Partial<AuthToken>;
    if (
      !tokenData.sub || typeof tokenData.sub !== 'string' ||
      !tokenData.role ||
      typeof tokenData.iat !== 'number' ||
      typeof tokenData.exp !== 'number' ||
      !tokenData.jti || typeof tokenData.jti !== 'string'
    ) {
      return null;
    }
    return tokenData as AuthToken;
  } catch {
    return null;
  }
}

// ── Token Generation ─────────────────────────────────────────────────────────

/**
 * Generate a signed, opaque token. `secret` is optional and defaults to the
 * managed secret (tests pass a KNOWN secret to prove that a DIFFERENT secret
 * cannot validate the token).
 */
export function generateToken(clientId: string, role: UserRole, secret?: string): string | null {
  const secretKey = secret !== undefined ? secret : getAuthSecret();
  if (!secretKey) {
    // Fail closed: no signing secret -> no token.
    return null;
  }
  const tokenData: AuthToken = {
    sub: clientId,
    role,
    iat: Date.now(),
    exp: Date.now() + TOKEN_EXPIRY_MS,
    jti: crypto.randomBytes(8).toString('hex'),
  };
  const payload = Buffer.from(JSON.stringify(tokenData)).toString('base64url');
  const sig = sign(payload, secretKey);
  return `${payload}.${sig}`;
}

/**
 * Validate and parse a token. Returns null if malformed, unsigned, tampered,
 * missing a part, expired, revoked, signed with the wrong secret, or carrying
 * an unauthorized role. Fail-closed: a missing secret rejects everything.
 */
export function validateToken(token: string | null | undefined, secret?: string): AuthToken | null {
  if (!token || typeof token !== 'string') {
    return null;
  }
  if (REVOKED_TOKENS.has(token)) {
    return null;
  }
  const secretKey = secret !== undefined ? secret : getAuthSecret();
  if (!secretKey) {
    return null;
  }
  const parts = token.split('.');
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    return null;
  }
  const expected = sign(parts[0], secretKey);
  if (!secureCompare(parts[1], expected)) {
    // Wrong secret OR tampered payload — indistinguishable by design.
    return null;
  }
  const tokenData = decodePayload(parts[0]);
  if (!tokenData) {
    return null;
  }
  const now = Date.now();
  if (tokenData.exp < now) {
    return null;
  }
  // Reject tokens whose issue time is suspiciously in the future (re-dating).
  if (tokenData.iat > now + MAX_IAT_SKEW_MS) {
    return null;
  }
  if (!['OBSERVER', 'RUNNER', 'ADMIN'].includes(tokenData.role)) {
    return null;
  }
  return tokenData;
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
export function revokeToken(token: string | null): void {
  if (token) {
    REVOKED_TOKENS.add(token);
  }
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
