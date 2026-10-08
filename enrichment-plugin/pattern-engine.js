/**
 * pattern-engine.js — Email pattern prediction + MX/SMTP verification helper.
 *
 * This module is intentionally data-pure and provider-agnostic. It generates
 * *candidate* email addresses from a person's name + company domain using common
 * B2B patterns, then (optionally) verifies reachability.
 *
 * Compliance guardrails:
 *   - Only uses PUBLIC identity data (name, company, domain) the customer already
 *     has or that is publicly visible.
 *   - SMTP verification checks ONE candidate address at a time via a single
 *     RCPT-TO probe. It performs NO CAPTCHA bypass, NO hidden-field scraping,
 *     and NO bulk/automated enumeration of a domain's mailbox space.
 *
 * Dependencies: Node built-ins only (dns, net). No external packages required.
 */
'use strict';

const dns = require('dns').promises;
const net = require('net');

// Common corporate email patterns, ordered by observed frequency.
const DEFAULT_PATTERNS = [
  { key: 'first.last', build: (f, l) => `${f}.${l}` },
  { key: 'firstlast', build: (f, l) => `${f}${l}` },
  { key: 'first', build: (f, l) => `${f}` },
  { key: 'flast', build: (f, l) => `${f[0]}${l}` },
  { key: 'first_l', build: (f, l) => `${f}_${l[0]}` },
  { key: 'f.last', build: (f, l) => `${f[0]}.${l}` },
  { key: 'last', build: (f, l) => `${l}` },
  { key: 'last.first', build: (f, l) => `${l}.${f}` },
];

function normalizeNamePart(value) {
  if (!value || typeof value !== 'string') return '';
  return value
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // strip accents/diacritics
    .replace(/[^a-z0-9]/g, '');       // drop spaces/hyphens/apostrophes
}

function normalizeDomain(value) {
  if (!value || typeof value !== 'string') return '';
  return value.toLowerCase().trim().replace(/^https?:\/\//, '').replace(/\/.*$/, '');
}

// ---------------------------------------------------------------------------
// SMTP mailbox validation (a single, authorized RCPT-TO probe per address).
//
// Connects to the recipient domain's MX on port 25 and walks the SMTP dialog
// up to `RCPT TO`. A 250/251/252 means the mailbox likely exists; a 550/551/
// 552/553/554 means it is rejected. Soft-fail codes (450/451/452 = greylisting)
// and connection problems return `verified: null` so the caller can try the
// next MX host or report the address as unverifiable. No message is ever sent:
// the socket is closed immediately after RCPT TO / QUIT.
// ---------------------------------------------------------------------------
function probeMailbox(host, senderDomain, recipient, timeoutMs) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port: 25 });
    let buffer = '';
    let step = 0; // 0 = greeting, 1 = EHLO, 2 = MAIL FROM, 3 = RCPT TO
    let settled = false;

    function finish(result) {
      if (settled) return;
      settled = true;
      try { socket.write('QUIT\r\n'); } catch (e) { /* ignore */ }
      try { socket.end(); } catch (e) { /* ignore */ }
      const timer = setTimeout(() => {
        try { socket.destroy(); } catch (e) { /* ignore */ }
      }, 300);
      if (timer.unref) timer.unref();
      resolve(result);
    }

    function send(line) {
      try {
        socket.write(`${line}\r\n`);
      } catch (e) {
        finish({ verified: null, reason: 'write_error', code: null });
      }
    }

    function handleLine(line) {
      const codeStr = line.slice(0, 3);
      const sep = line[3];
      if (!/^\d{3}$/.test(codeStr)) return; // ignore non-reply noise
      if (sep === '-') return;               // multiline continuation -> wait for terminator
      const code = parseInt(codeStr, 10);

      if (step === 0) {
        if (code === 220) { step = 1; send(`EHLO ${senderDomain}`); }
        else finish({ verified: null, reason: 'greeting_rejected', code });
      } else if (step === 1) {
        if (code === 250) { step = 2; send(`MAIL FROM:<verify@${senderDomain}>`); }
        else if (code >= 500) finish({ verified: null, reason: 'ehlo_rejected', code });
        else finish({ verified: null, reason: 'ehlo_rejected', code });
      } else if (step === 2) {
        if (code === 250) { step = 3; send(`RCPT TO:<${recipient}>`); }
        else if (code >= 500) finish({ verified: null, reason: 'mail_from_rejected', code });
        else finish({ verified: null, reason: 'mail_from_rejected', code });
      } else if (step === 3) {
        if (code === 250 || code === 251 || code === 252) {
          finish({ verified: true, reason: 'mailbox_accepted', code });
        } else if (code === 450 || code === 451 || code === 452) {
          finish({ verified: null, reason: 'greylisted', code });
        } else if (code === 550 || code === 551 || code === 552 || code === 553 || code === 554) {
          finish({ verified: false, reason: 'mailbox_rejected', code });
        } else if (code >= 500) {
          finish({ verified: false, reason: 'rcpt_rejected', code });
        } else {
          finish({ verified: null, reason: 'rcpt_inconclusive', code });
        }
      }
    }

    socket.setEncoding('utf8');
    socket.setTimeout(timeoutMs);
    socket.on('data', (chunk) => {
      buffer += chunk;
      let idx;
      while (!settled && (idx = buffer.indexOf('\r\n')) !== -1) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        handleLine(line);
      }
    });
    socket.on('timeout', () => finish({ verified: null, reason: 'timeout', code: null }));
    socket.on('error', () => finish({ verified: null, reason: 'smtp_unreachable', code: null }));
    socket.on('close', () => finish({ verified: null, reason: 'connection_closed', code: null }));
  });
}

function mailboxConfidence(best, hasMx) {
  if (best && best.smtp_verified) return 0.95;
  if (hasMx) return 0.6;
  return 0.3;
}

class EmailPatternEngine {
  constructor({ patterns = DEFAULT_PATTERNS } = {}) {
    this.patterns = patterns;
  }

  /**
   * Generate candidate emails for {firstName, lastName, domain}.
   * Returns an array of { email, pattern } — never mutated, never persisted here.
   */
  generateCandidates({ firstName, lastName, domain }) {
    const f = normalizeNamePart(firstName);
    const l = normalizeNamePart(lastName);
    const d = normalizeDomain(domain);

    if (!f || !l || !d) return [];

    const seen = new Set();
    const candidates = [];

    for (const pattern of this.patterns) {
      try {
        const local = pattern.build(f, l);
        if (!local) continue;
        const email = `${local}@${d}`;
        if (seen.has(email)) continue;
        seen.add(email);
        candidates.push({ email, pattern: pattern.key });
      } catch (err) {
        // A single broken pattern must never abort the whole generation.
        continue;
      }
    }

    return candidates;
  }

  /**
   * Resolve MX hosts for a domain (real DNS lookup; harmless).
   * Returns { domain, hasMx, mxHosts }.
   */
  async lookupMx(domain) {
    const d = normalizeDomain(domain);
    if (!d) return { domain: d, hasMx: false, mxHosts: [] };
    try {
      const records = await dns.resolveMx(d);
      const mxHosts = records
        .sort((a, b) => a.priority - b.priority)
        .map((r) => r.exchange);
      return { domain: d, hasMx: mxHosts.length > 0, mxHosts };
    } catch (err) {
      return { domain: d, hasMx: false, mxHosts: [] };
    }
  }

  /**
   * Verify a single candidate email against the domain's mail server.
   *
   * Performs a real MX lookup followed by an SMTP RCPT-TO probe. Returns
   *   { verified: boolean, reason: string, code: number|null }.
   *
   * Defaults to `enableSmtp: true`; pass `enableSmtp: false` to short-circuit
   * and skip any network probe (e.g. in restricted environments).
   */
  async smtpVerify(email, { enableSmtp = true, timeoutMs = 8000, senderDomain = null, maxMxAttempts = 3 } = {}) {
    if (!enableSmtp) {
      return { verified: false, reason: 'smtp_verification_disabled', code: null };
    }
    const at = (email || '').lastIndexOf('@');
    if (at <= 0) return { verified: false, reason: 'invalid_email', code: null };
    const domain = normalizeDomain(email.slice(at + 1));
    if (!domain) return { verified: false, reason: 'invalid_email', code: null };

    const { hasMx, mxHosts } = await this.lookupMx(domain);
    if (!hasMx) return { verified: false, reason: 'no_mx', code: null };

    const sender = normalizeDomain(senderDomain || domain);
    for (const host of mxHosts.slice(0, maxMxAttempts)) {
      const result = await probeMailbox(host, sender, email, timeoutMs);
      if (result && result.verified !== null) return result;
    }
    return { verified: false, reason: 'smtp_unreachable', code: null };
  }

  /**
   * Generate candidate emails and verify each against the domain's MX/SMTP.
   * Returns the best-guess (verified) email, a confidence score, and the full
   * candidate list enriched with { mx, smtp_verified, smtp_reason, smtp_code }.
   */
  async generateAndVerify(profile, { enableSmtp = true, timeoutMs = 8000, concurrency = 3, maxCandidates = 8 } = {}) {
    const candidates = this.generateCandidates(profile);
    if (!candidates.length) {
      return { email: null, confidence: 0, candidates: [], verified: false, source: 'pattern' };
    }

    const domain = normalizeDomain(profile.domain);
    const { hasMx, mxHosts } = await this.lookupMx(domain);
    const target = candidates.slice(0, maxCandidates);

    // Verify candidates in a small worker pool so a single MX isn't hammered.
    const seen = new Map();
    let next = 0;
    const workers = Array.from({ length: Math.max(1, Math.min(concurrency, target.length)) }, async () => {
      while (next < target.length) {
        const candidate = target[next++];
        const smtp = await this.smtpVerify(candidate.email, { enableSmtp, timeoutMs });
        seen.set(candidate.email, {
          ...candidate,
          mx: hasMx,
          mx_hosts: mxHosts,
          smtp_verified: smtp.verified,
          smtp_reason: smtp.reason,
          smtp_code: smtp.code,
        });
      }
    });
    await Promise.all(workers);

    const ordered = target.map((c) => seen.get(c.email)).filter(Boolean);
    const verified = ordered.find((r) => r.smtp_verified);
    const best = verified || ordered[0] || null;

    return {
      email: best ? best.email : null,
      confidence: mailboxConfidence(best, hasMx),
      candidates: ordered,
      verified: !!verified,
      source: 'pattern',
    };
  }
}

module.exports = { EmailPatternEngine, DEFAULT_PATTERNS, probeMailbox, mailboxConfidence };
