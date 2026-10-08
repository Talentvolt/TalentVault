/**
 * server.js — Local development bootstrap for the isolated enrichment middleware.
 *
 * Run:  node server.js
 *
 * Local-dev behavior:
 *   - Auth/RBAC is BYPASSED (options.bypassAuth = true) so POST /api/v1/enrichment/lookup
 *     works without an auth token.
 *   - If DATABASE_URL is set, a Postgres cache is used; otherwise an in-memory
 *     cache is used so the server runs with zero external dependencies.
 *
 * NOTE: Do NOT use bypassAuth in production. In production mount the router with
 * your real auth middleware (which sets req.user) and omit bypassAuth.
 */
'use strict';

// Optional env loading (safe if dotenv isn't installed).
try {
  require('dotenv').config();
} catch (e) {
  /* dotenv is optional */
}

const express = require('express');
const {
  createEnrichmentRouter,
  MemoryCreditService,
} = require('./enrichment-route');

const PORT = Number(process.env.PORT || 4100);

let db = null;
if (process.env.DATABASE_URL) {
  try {
    const { Pool } = require('pg');
    db = new Pool({ connectionString: process.env.DATABASE_URL });
    // Never let a background Postgres error crash the process; the cache layer
    // already falls back to in-memory on any query failure.
    db.on('error', (err) => {
      console.warn('[enrichment] Postgres pool error (in-memory fallback):', err && err.message);
    });
  } catch (err) {
    // `pg` not installed or misconfigured -> run fully in-memory.
    console.warn('[enrichment] pg driver unavailable — running without Postgres:', err && err.message);
    db = null;
  }
}

const app = express();

// CORS: allow the Chrome extension / side panel origin to call this server.
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Api-Key');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

app.use(express.json());

app.use(
  '/api/v1/enrichment',
  createEnrichmentRouter({
    db,
    creditService: new MemoryCreditService(50),
    options: {
      bypassAuth: true,          // local-dev only — mock RBAC
      defaultCredits: 50,
    },
  })
);

app.get('/', (req, res) => res.send('TalentVault Enrichment Server is Running!'));

app.listen(PORT, () => {
  console.log(`[enrichment] Server running on http://localhost:${PORT}`);
  console.log('[enrichment] Auth bypass ENABLED (local development only).');
});
