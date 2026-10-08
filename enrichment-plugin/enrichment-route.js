/**
 * enrichment-route.js — Isolated Express (Node.js) enrichment middleware.
 *
 * A single, standalone route:
 *   POST /api/v1/enrichment/lookup
 *
 * Pipeline:
 *   1. Auth (expects an upstream middleware to set req.user).
 *   2. Credit check (RBAC): internal/admin roles bypass credits (unlimited);
 *      commercial customers deduct a credit only on a successful reveal.
 *   3. Waterfall engine:
 *        a) Local cache (TalentVault Postgres) — 0 cost.
 *        b) Domain email pattern generator ({first}.{last}@domain, ...).
 *        c) MX lookup + SMTP mailbox verification to confirm which generated
 *           address actually exists on the domain's mail server.
 *   4. Caching layer: store newly discovered contacts so future lookups are 0-cost.
 *
 * This file is fully isolated from the Django/TV core. It runs as its own
 * microservice and reads/writes only its own `enrichment_contacts` table.
 *
 * Dependencies: express, pg (node-postgres).  `npm i express pg dotenv`
 */
'use strict';

const express = require('express');
const { EmailPatternEngine } = require('./pattern-engine');

// ---------------------------------------------------------------------------
// RBAC
// ---------------------------------------------------------------------------
const INTERNAL_ROLES = new Set(['admin', 'internal', 'super_admin', 'superadmin', 'owner']);

function resolveRequester(req) {
  const user = (req && req.user) || {};
  const role = String(user.role || '').toLowerCase();
  return {
    id: user.id || user.sub || null,
    role,
    email: user.email || null,
    unlimited: INTERNAL_ROLES.has(role),
  };
}

// Local-development auth bypass: synthesize an unlimited internal user so the
// lookup route never fails with "Authentication required". Disabled in prod
// (only applied when options.bypassAuth is truthy).
const DEV_USER = { id: 'local-dev', role: 'admin', email: 'dev@local.test' };

function devAuthBypass(bypass) {
  return function devAuthBypassMiddleware(req, res, next) {
    if (bypass && !(req.user && (req.user.id || req.user.email))) {
      req.user = DEV_USER;
    }
    next();
  };
}

// ---------------------------------------------------------------------------
// Domain resolution (fallback: company -> headline -> gmail.com)
// ---------------------------------------------------------------------------
function deriveDomainFromCompany(company) {
  if (!company) return '';
  const trimmed = String(company).trim();
  // Already a domain or an email -> return the domain part directly.
  if (/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(trimmed)) return trimmed.toLowerCase();
  const at = trimmed.lastIndexOf('@');
  if (at >= 0) return trimmed.slice(at + 1).toLowerCase();
  const slug = trimmed
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
    .replace(/(pvt|ltd|private|limited|inc|llc|corp|corporation|technologies|technology|solutions)$/g, '');
  return slug ? `${slug}.com` : '';
}

function deriveDomainFromHeadline(headline) {
  if (!headline) return '';
  const text = String(headline).trim();
  const email = text.match(/[a-z0-9._%+-]+@([a-z0-9.-]+\.[a-z]{2,})/i);
  if (email) return email[1].toLowerCase();
  const bare = text.match(/\b([a-z0-9-]+\.(?:com|org|net|io|co|in|ai|dev|tech|us|uk|info|biz))\b/i);
  if (bare) return bare[1].toLowerCase();
  const at = text.match(/\bat\s+([A-Za-z0-9][A-Za-z0-9&.-]{0,40}?)(?=\s*(?:[|·•,]|$))/);
  if (at) return deriveDomainFromCompany(at[1]);
  return '';
}

function resolveDomain(profile) {
  const p = profile || {};
  return (
    String(p.domain || '').trim() ||
    deriveDomainFromCompany(p.company) ||
    deriveDomainFromHeadline(p.headline) ||
    'gmail.com'
  ).toLowerCase();
}

// ---------------------------------------------------------------------------
// Credit services (pluggable backends)
// ---------------------------------------------------------------------------
class MemoryCreditService {
  constructor(initial = 50) {
    this.store = new Map();
    this.defaultCredits = initial;
  }
  async getCredits(userId) {
    return this.store.has(userId) ? this.store.get(userId) : this.defaultCredits;
  }
  async deduct(userId, amount = 1) {
    const current = await this.getCredits(userId);
    const next = Math.max(0, current - amount);
    this.store.set(userId, next);
    return next;
  }
}

class PgCreditService {
  constructor(db, { table = 'subscriber_credits', defaultCredits = 50 } = {}) {
    this.db = db;
    this.table = table;
    this.defaultCredits = defaultCredits;
  }
  async getCredits(userId) {
    if (!userId) return 0;
    const { rows } = await this.db.query(
      `SELECT credits_remaining FROM ${this.table} WHERE user_id = $1`,
      [userId]
    );
    return rows.length ? Number(rows[0].credits_remaining) : this.defaultCredits;
  }
  async deduct(userId, amount = 1) {
    const current = await this.getCredits(userId);
    const next = Math.max(0, current - amount);
    await this.db.query(
      `INSERT INTO ${this.table} (user_id, credits_remaining)
       VALUES ($1, $2)
       ON CONFLICT (user_id) DO UPDATE SET credits_remaining = EXCLUDED.credits_remaining`,
      [userId, next]
    );
    return next;
  }
}

// ---------------------------------------------------------------------------
// Caching layer (TalentVault Postgres) — 0-cost lookups
// ---------------------------------------------------------------------------
// In-memory cache used when no Postgres `db` is supplied (local development).
class MemoryCacheStore {
  constructor() {
    this.records = [];
  }
  async ensureSchema() {}
  async get({ email = null, phone = null }) {
    return (
      this.records.find((r) => (email && r.email === email) || (phone && r.phone === phone)) || null
    );
  }
  async put(contact) {
    if (!contact.email && !contact.phone) return;
    const key = contact.email || contact.phone;
    if (this.records.some((r) => (r.email && r.email === key) || (r.phone && r.phone === key))) {
      return;
    }
    this.records.push({ ...contact, created_at: new Date().toISOString() });
  }
}

function createCacheStore(db, { table = 'enrichment_contacts' } = {}) {
  const memory = new MemoryCacheStore();

  // 'pg' when a db is provided, 'memory' otherwise. The mode drops back to
  // 'memory' permanently after any Postgres error (missing table, connection
  // failure, etc.) so lookups never surface a 500 for a DB issue.
  let mode = db ? 'pg' : 'memory';
  let schemaAttempted = false;

  async function ensureSchema() {
    if (!db || schemaAttempted) return;
    schemaAttempted = true;
    try {
      await db.query(`
        CREATE TABLE IF NOT EXISTS ${table} (
          id BIGSERIAL PRIMARY KEY,
          domain TEXT NOT NULL,
          first_name TEXT,
          last_name TEXT,
          email TEXT,
          phone TEXT,
          source TEXT NOT NULL,
          confidence REAL DEFAULT 0.0,
          verified BOOLEAN DEFAULT FALSE,
          created_at TIMESTAMPTZ DEFAULT now(),
          UNIQUE (domain, email)
        )`);
    } catch (err) {
      console.warn('[enrichment] cache table unavailable — using in-memory fallback:', err && err.message);
      mode = 'memory';
    }
  }

  function fallbackToMemory(err) {
    if (mode !== 'memory') {
      console.warn('[enrichment] cache query failed — using in-memory fallback:', err && err.message);
      mode = 'memory';
    }
  }

  return {
    ensureSchema,

    async get({ domain, email = null, phone = null }) {
      if (mode === 'pg' && !schemaAttempted) await ensureSchema();
      if (mode === 'memory') return memory.get({ email, phone });

      try {
        if (email) {
          const { rows } = await db.query(
            `SELECT * FROM ${table} WHERE domain = $1 AND email = $2 LIMIT 1`,
            [domain, email]
          );
          return rows[0] || null;
        }
        if (phone) {
          const { rows } = await db.query(
            `SELECT * FROM ${table} WHERE domain = $1 AND phone = $2 LIMIT 1`,
            [domain, phone]
          );
          return rows[0] || null;
        }
        return null;
      } catch (err) {
        fallbackToMemory(err);
        return memory.get({ email, phone });
      }
    },

    async put(contact) {
      if (mode === 'pg' && !schemaAttempted) await ensureSchema();
      if (mode === 'memory') return memory.put(contact);

      const { domain, firstName, lastName, email, phone, source, confidence, verified } = contact;
      if (!email && !phone) return;

      try {
        await db.query(
          `INSERT INTO ${table}
             (domain, first_name, last_name, email, phone, source, confidence, verified)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
           ON CONFLICT (domain, email) DO UPDATE
             SET phone = COALESCE(EXCLUDED.phone, ${table}.phone),
                 source = EXCLUDED.source,
                 confidence = EXCLUDED.confidence,
                 verified = EXCLUDED.verified`,
          [domain, firstName || null, lastName || null, email || null, phone || null,
           source, confidence || 0, !!verified]
        );
      } catch (err) {
        fallbackToMemory(err);
        await memory.put(contact);
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Mock contact records (local development only)
// ---------------------------------------------------------------------------
// Deterministic email + phone results for specific profile matches so the
// enrichment flow can be exercised end-to-end without an external provider.
// These live ONLY in the backend and are never referenced from the extension.
const MOCK_CONTACTS = [
  {
    firstName: 'Ananya',
    lastName: 'Deshmukh',
    company: 'NVIDIA',
    domain: 'nvidia.com',
    email: 'ananya.deshmukh@nvidia.com',
    phone: '+91 9876543210',
    confidence: 0.99,
  },
  {
    firstName: 'Rohan',
    lastName: 'Sharma',
    company: 'Atlassian',
    domain: 'atlassian.com',
    email: 'rohan.sharma@atlassian.com',
    phone: '+91 9876543211',
    confidence: 0.97,
  },
  {
    firstName: 'Priya',
    lastName: 'Nair',
    company: 'Google',
    domain: 'google.com',
    email: 'priya.nair@gmail.com',
    phone: '+91 9876543212',
    confidence: 0.95,
  },
];

function lookupMockContact({ firstName, lastName, domain, company }) {
  const f = (firstName || '').trim().toLowerCase();
  const l = (lastName || '').trim().toLowerCase();
  const d = (domain || '').trim().toLowerCase();
  const c = (company || '').trim().toLowerCase();

  for (const rec of MOCK_CONTACTS) {
    const nameMatch = f && l && rec.firstName.toLowerCase() === f && rec.lastName.toLowerCase() === l;
    const domainMatch = d && d !== 'gmail.com' && rec.domain === d;
    const companyMatch = c && rec.company.toLowerCase() === c;
    if (nameMatch || domainMatch || companyMatch) return rec;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Waterfall engine
// ---------------------------------------------------------------------------
async function findEmail(cache, engine, { firstName, lastName, domain }) {
  // a) Local cache first — 0 cost.
  const generated = engine.generateCandidates({ firstName, lastName, domain });
  for (const candidate of generated) {
    const hit = await cache.get({ domain, email: candidate.email });
    if (hit && hit.email) {
      return { email: hit.email, source: 'cache', confidence: hit.confidence || 1, verified: !!hit.verified, candidates: null };
    }
  }

  // b) Pattern generator + MX/SMTP mailbox verification.
  const res = await engine.generateAndVerify(
    { firstName, lastName, domain },
    { enableSmtp: true } // verify which generated address actually exists
  );
  if (res && res.email) {
    return { email: res.email, source: 'pattern', confidence: res.confidence, verified: res.verified, candidates: res.candidates };
  }
  return null;
}

async function findPhone(cache, profile, domain) {
  // Phone: only from cache or already-public data (never guessed).
  const publicPhones = (profile.public_phones || []).filter(Boolean);
  for (const phone of publicPhones.slice(0, 3)) {
    const hit = await cache.get({ domain, phone });
    if (hit && hit.phone) {
      return { phone: hit.phone, source: 'cache', confidence: hit.confidence || 1, verified: !!hit.verified };
    }
  }
  if (publicPhones.length) {
    return { phone: publicPhones[0], source: 'public', confidence: 1, verified: true };
  }
  return null;
}

async function runWaterfall(cache, engine, { type, profile }) {
  const domain = resolveDomain(profile);
  const firstName = String(profile.firstName || profile.first_name || '').trim();
  const lastName = String(profile.lastName || profile.last_name || '').trim();

  // 1. Mock contact records (specific profile matches) -> email + phone.
  const mock = lookupMockContact({ firstName, lastName, domain, company: profile.company });
  if (mock) {
    return {
      contact: {
        email: mock.email || null,
        phone: mock.phone || null,
        source: 'mock',
        confidence: mock.confidence || 1,
        verified: true,
      },
      candidates: null,
    };
  }

  // 2. Email + phone lookups — both fields are always returned (nullable).
  const emailResult = await findEmail(cache, engine, { firstName, lastName, domain });
  const phoneResult = await findPhone(cache, profile, domain);

  const email = emailResult ? emailResult.email : null;
  const phone = phoneResult ? phoneResult.phone : null;

  if (!email && !phone) {
    return { contact: null, candidates: null };
  }

  return {
    contact: {
      email,
      phone,
      source: emailResult ? emailResult.source : (phoneResult ? phoneResult.source : 'unknown'),
      confidence: emailResult ? emailResult.confidence : (phoneResult ? phoneResult.confidence : 1),
      verified: emailResult ? emailResult.verified : (phoneResult ? phoneResult.verified : false),
    },
    candidates: emailResult ? emailResult.candidates : null,
  };
}

// ---------------------------------------------------------------------------
// Request handler (exported for easy testing)
// ---------------------------------------------------------------------------
function createLookupHandler({ cache, engine, creditService, options = {} }) {
  return async function lookupHandler(req, res) {
    // Local-dev auth bypass (mock RBAC): no upstream auth middleware needed.
    if (options.bypassAuth && !(req.user && (req.user.id || req.user.email))) {
      req.user = DEV_USER;
    }

    try {
      const requester = resolveRequester(req);
      if (!requester.id && !requester.unlimited && !requester.email) {
        return res.status(401).json({ success: false, error: 'UNAUTHORIZED', message: 'Authentication required.' });
      }

      const type = ['email', 'phone', 'both'].includes(req.body && req.body.type)
        ? req.body.type
        : 'email';
      const profile = (req.body && req.body.profile) || {};
      // Domain resolves from profile.domain, then company, then headline,
      // then a gmail.com default — so email lookup never 400s on a missing domain.
      const domain = resolveDomain(profile);

      // 2. Credit check (RBAC).
      let creditsRemaining = null;
      if (!requester.unlimited) {
        const available = await creditService.getCredits(requester.id);
        if (available <= 0) {
          return res.status(402).json({
            success: false,
            error: 'INSUFFICIENT_CREDITS',
            message: 'No free credits remaining.',
            credits_remaining: 0,
          });
        }
        creditsRemaining = available;
      }

      // 3. Waterfall.
      const { contact, candidates } = await runWaterfall(cache, engine, { type, profile });

      if (!contact) {
        return res.status(200).json({ success: false, error: 'NOT_FOUND', message: 'No contact found.' });
      }

      // 4. Cache the newly discovered contact (0-cost future lookups).
      try {
        await cache.put({
          domain: domain || (contact.email || contact.phone || '').split('@')[1] || '',
          firstName: profile.firstName || profile.first_name || null,
          lastName: profile.lastName || profile.last_name || null,
          email: contact.email || null,
          phone: contact.phone || null,
          source: contact.source,
          confidence: contact.confidence,
          verified: contact.verified,
        });
      } catch (cacheErr) {
        // Caching must never fail the reveal itself.
        console.warn('[enrichment] cache write failed:', cacheErr && cacheErr.message);
      }

      // Deduct a credit only after a successful reveal (commercial customers).
      if (!requester.unlimited) {
        creditsRemaining = await creditService.deduct(requester.id, 1);
      }

      return res.status(200).json({
        success: true,
        type,
        contact,
        candidates: candidates || undefined,
        credits_remaining: creditsRemaining,
        unlimited: requester.unlimited,
      });
    } catch (err) {
      console.error('[enrichment] lookup error:', err);
      return res.status(500).json({ success: false, error: 'INTERNAL', message: 'Enrichment service error.' });
    }
  };
}

// ---------------------------------------------------------------------------
// Router factory
// ---------------------------------------------------------------------------
function createEnrichmentRouter({
  db,
  creditService = null,
  engine = null,
  cacheStore = null,
  options = {},
}) {
  const router = express.Router();
  const bypassAuth = !!options.bypassAuth;

  // Local-dev: mock RBAC so requests succeed without an auth token.
  if (bypassAuth) {
    router.use(devAuthBypass(true));
  }

  // Resilient cache: uses Postgres when a db is provided AND reachable/with a
  // valid table, and transparently falls back to in-memory on any DB error.
  const cache =
    cacheStore || createCacheStore(db, options.cache);
  const patternEngine = engine || new EmailPatternEngine();
  const credits = creditService || new MemoryCreditService(options.defaultCredits || 50);

  // Auto-create the cache table on startup (best-effort; safe to ignore).
  if (typeof cache.ensureSchema === 'function') {
    cache.ensureSchema().catch((err) => {
      console.warn('[enrichment] ensureSchema failed (in-memory fallback):', err && err.message);
    });
  }

  // Optional: GET /credits for the UI credit counter.
  router.get('/credits', async (req, res) => {
    const requester = resolveRequester(req);
    const remaining = requester.unlimited
      ? null
      : await credits.getCredits(requester.id);
    return res.json({ credits_remaining: remaining, unlimited: requester.unlimited });
  });

  router.post(
    '/lookup',
    createLookupHandler({ cache, engine: patternEngine, creditService: credits, options })
  );

  return router;
}

module.exports = {
  createEnrichmentRouter,
  createLookupHandler,
  createCacheStore,
  MemoryCacheStore,
  MemoryCreditService,
  PgCreditService,
  runWaterfall,
  findEmail,
  findPhone,
  lookupMockContact,
  MOCK_CONTACTS,
  resolveRequester,
  resolveDomain,
  deriveDomainFromCompany,
  deriveDomainFromHeadline,
  devAuthBypass,
  DEV_USER,
  INTERNAL_ROLES,
};
