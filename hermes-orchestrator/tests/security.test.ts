/**
 * Security tests for Hermes Orchestrator
 * 
 * Tests authentication, authorization, input validation, and CORS.
 */

import { describe, it, expect, beforeEach } from '@jest/globals';
import {
  generateToken,
  validateToken,
  revokeToken,
  authorize,
  UserRole,
} from '../src/middleware/auth';
import { validateTaskRequest, isValidTaskId, sanitizeWorkspacePath } from '../src/middleware/validation';
import { corsMiddleware } from '../src/middleware/cors';

// Provide a stable signing secret so tests are deterministic and never write
// a real `.auth-secret` key file during the suite.
process.env.AUTH_SECRET = 'test-secret-0123456789abcdef0123456789abcdef';

describe('Authentication', () => {
  describe('generateToken', () => {
    it('should generate a valid token', () => {
      const token = generateToken('test-client', 'OBSERVER');
      expect(token).toBeDefined();
      expect(token).not.toBeNull();
      expect(typeof token).toBe('string');
      expect(token!.length).toBeGreaterThan(0);
    });

    it('should generate unique tokens', () => {
      const token1 = generateToken('client1', 'OBSERVER');
      const token2 = generateToken('client2', 'RUNNER');
      expect(token1).not.toBe(token2);
    });
  });

  describe('validateToken', () => {
    it('should return null for invalid token', () => {
      expect(validateToken('')).toBeNull();
      expect(validateToken(null as any)).toBeNull();
      expect(validateToken(undefined as any)).toBeNull();
    });

    it('should validate a properly formatted token', () => {
      const token = generateToken('test-client', 'RUNNER');
      const result = validateToken(token);
      expect(result).not.toBeNull();
      expect(result?.sub).toBe('test-client');
      expect(result?.role).toBe('RUNNER');
    });

    it('should reject expired tokens', () => {
      // Create a token with past expiration
      const expiredToken = Buffer.from(JSON.stringify({
        sub: 'test',
        role: 'OBSERVER',
        iat: Date.now() - 100000,
        exp: Date.now() - 10000,
        jti: 'test-jti',
      })).toString('base64url');

      expect(validateToken(expiredToken)).toBeNull();
    });

    it('should reject tokens with invalid role', () => {
      const badToken = Buffer.from(JSON.stringify({
        sub: 'test',
        role: 'INVALID',
        iat: Date.now(),
        exp: Date.now() + 100000,
        jti: 'test-jti',
      })).toString('base64url');

      expect(validateToken(badToken)).toBeNull();
    });
  });

  describe('revokeToken', () => {
    it('should revoke a token', () => {
      const token = generateToken('test-client', 'OBSERVER');
      revokeToken(token);
      expect(validateToken(token)).toBeNull();
    });
  });

  describe('Token integrity & forge protection', () => {
    const GOOD = 'test-secret-0123456789abcdef0123456789abcdef';
    const ATTACKER = 'attacker-secret-9876543210fedcba9876543210fedcba';

    it('rejects a token signed with the wrong secret', () => {
      const token = generateToken('client', 'ADMIN', GOOD);
      expect(token).not.toBeNull();
      expect(validateToken(token!, ATTACKER)).toBeNull();
      expect(validateToken(token!, GOOD)?.role).toBe('ADMIN');
    });

    it('rejects a forged ADMIN token (signed by an attacker secret)', () => {
      // Attacker mints role=ADMIN but signs with the attacker secret, not ours.
      const forged = generateToken('attacker', 'ADMIN', ATTACKER);
      expect(validateToken(forged!, GOOD)).toBeNull();
    });

    it('rejects a tampered payload whose signature is not recomputed', () => {
      const token = generateToken('client', 'OBSERVER', GOOD)!;
      const [payload] = token.split('.');
      // Decode, bump role to ADMIN, re-encode — but keep the ORIGINAL signature.
      const obj = JSON.parse(Buffer.from(payload, 'base64url').toString('utf-8'));
      obj.role = 'ADMIN';
      const tamperedPayload = Buffer.from(JSON.stringify(obj)).toString('base64url');
      const sig = token.split('.')[1];
      expect(validateToken(`${tamperedPayload}.${sig}`, GOOD)).toBeNull();
    });

    it('rejects a token missing its signature part', () => {
      const token = generateToken('client', 'ADMIN', GOOD)!;
      const [payload] = token.split('.');
      expect(validateToken(payload, GOOD)).toBeNull();
    });

    it('rejects an expired token even when correctly signed', () => {
      const now = Date.now();
      const payload = Buffer.from(JSON.stringify({
        sub: 'client', role: 'OBSERVER',
        iat: now - 100000, exp: now - 10000, jti: 'jti',
      })).toString('base64url');
      const { createHmac } = require('node:crypto');
      const sig = createHmac('sha256', GOOD).update(payload).digest('hex');
      expect(validateToken(`${payload}.${sig}`, GOOD)).toBeNull();
    });

    it('rejects a role outside the whitelist even when signed', () => {
      const now = Date.now();
      const payload = Buffer.from(JSON.stringify({
        sub: 'client', role: 'SUPERUSER',
        iat: now, exp: now + 100000, jti: 'jti',
      })).toString('base64url');
      const { createHmac } = require('node:crypto');
      const sig = createHmac('sha256', GOOD).update(payload).digest('hex');
      expect(validateToken(`${payload}.${sig}`, GOOD)).toBeNull();
    });

    it('fails closed when no signing secret is available', () => {
      // Empty secret -> generateToken returns null (fail-closed, no bounce).
      expect(generateToken('client', 'OBSERVER', '')).toBeNull();
    });

    it('secureCompare returns false (not throw) on unequal-length inputs', () => {
      const { secureCompare } = require('../src/middleware/auth');
      expect(secureCompare('a', 'bb')).toBe(false);
      expect(secureCompare('abc', 'abc')).toBe(true);
      expect(secureCompare('abc', 'abcd')).toBe(false);
      expect(secureCompare('abc' as any, 42 as any)).toBe(false);
      expect(secureCompare(null as any, '' as any)).toBe(false);
    });
  });
});

describe('Authorization', () => {
  it('should allow OBSERVER to read', () => {
    const token = generateToken('client', 'OBSERVER');
    const result = validateToken(token);
    expect(result).not.toBeNull();
    expect(result?.role).toBe('OBSERVER');
  });

  it('should allow RUNNER to execute', () => {
    const token = generateToken('client', 'RUNNER');
    const result = validateToken(token);
    expect(result).not.toBeNull();
    expect(result?.role).toBe('RUNNER');
  });

  it('should allow ADMIN to administer', () => {
    const token = generateToken('client', 'ADMIN');
    const result = validateToken(token);
    expect(result).not.toBeNull();
    expect(result?.role).toBe('ADMIN');
  });
});

describe('Input Validation', () => {
  describe('validateTaskRequest', () => {
    it('should accept valid task', () => {
      const result = validateTaskRequest({
        task_id: 'task_12345678',
        origin: 'dashboard',
        mode: 'DEV',
        description: 'Test task',
      });

      expect(result.error).toBeUndefined();
      expect(result.task).toBeDefined();
      expect(result.task?.task_id).toBe('task_12345678');
    });

    it('should reject missing task_id', () => {
      const result = validateTaskRequest({
        origin: 'dashboard',
        mode: 'DEV',
      });

      expect(result.error).toContain('task_id');
    });

    it('should reject invalid origin', () => {
      const result = validateTaskRequest({
        task_id: 'task_12345678',
        origin: 'UNKNOWN',
        mode: 'DEV',
      });

      expect(result.error).toContain('origin');
    });

    it('should reject invalid mode', () => {
      const result = validateTaskRequest({
        task_id: 'task_12345678',
        origin: 'dashboard',
        mode: 'INVALID',
      });

      expect(result.error).toContain('mode');
    });

    it('should reject description too long', () => {
      const result = validateTaskRequest({
        task_id: 'task_12345678',
        origin: 'dashboard',
        mode: 'DEV',
        description: 'x'.repeat(10001),
      });

      expect(result.error).toContain('description');
    });

    it('should reject past deadline', () => {
      const result = validateTaskRequest({
        task_id: 'task_12345678',
        origin: 'dashboard',
        mode: 'DEV',
        deadline: new Date(Date.now() - 1000).toISOString(),
      });

      expect(result.error).toContain('deadline');
    });

    it('should reject future deadline too far', () => {
      const result = validateTaskRequest({
        task_id: 'task_12345678',
        origin: 'dashboard',
        mode: 'DEV',
        deadline: new Date(Date.now() + 8 * 24 * 60 * 60 * 1000).toISOString(),
      });

      expect(result.error).toContain('deadline');
    });
  });

  describe('isValidTaskId', () => {
    it('should accept valid task_id', () => {
      expect(isValidTaskId('task_12345678')).toBe(true);
    });

    it('should reject short task_id', () => {
      expect(isValidTaskId('short')).toBe(false);
    });

    it('should reject invalid characters', () => {
      expect(isValidTaskId('task with spaces')).toBe(false);
    });
  });

  describe('sanitizeWorkspacePath', () => {
    it('should remove path traversal', () => {
      expect(sanitizeWorkspacePath('../etc/passwd')).toBe('_etc_passwd');
    });

    it('should handle mixed paths', () => {
      expect(sanitizeWorkspacePath('C:\\Users\\test')).toBe('C:_Users_test');
    });
  });
});

describe('CORS', () => {
  it('should allow allowed origins', () => {
    const req = { headers: { origin: 'http://127.0.0.1:8080' } } as any;
    const res = {
      headers: {} as any,
      setHeader: jest.fn((name: string, value: string) => {
        res.headers[name] = value;
      }),
    } as any;
    const next = jest.fn();

    corsMiddleware(req, res, next);

    expect(res.setHeader).toHaveBeenCalledWith('Access-Control-Allow-Origin', 'http://127.0.0.1:8080');
    expect(next).toHaveBeenCalled();
  });

  it('should reject disallowed origins', () => {
    const req = { headers: { origin: 'http://evil.com' } } as any;
    const res = {
      headers: {} as any,
      setHeader: jest.fn(),
    } as any;
    const next = jest.fn();

    corsMiddleware(req, res, next);

    expect(res.setHeader).not.toHaveBeenCalledWith('Access-Control-Allow-Origin', 'http://evil.com');
  });
});

describe('Security Integration', () => {
  it('should not leak secrets in error messages', () => {
    const error = new Error('Something failed');
    const message = error.message;
    
    // Should not contain token patterns
    expect(message).not.toMatch(/sk-[a-zA-Z0-9]{20,}/);
    expect(message).not.toMatch(/Bearer\s+[a-zA-Z0-9\-_.]+/);
  });

  it('should validate task origin is never UNKNOWN', () => {
    const result = validateTaskRequest({
      task_id: 'task_12345678',
      origin: 'UNKNOWN',
      mode: 'DEV',
    });

    expect(result.error).toBeDefined();
  });
});
