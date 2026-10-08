/**
 * EnrichmentModule — TalentVault Chrome Extension (Manifest V3) side-panel plugin.
 *
 * A lightweight, dependency-free UI + scraper module that plugs into the existing
 * TalentVault side panel. It is intentionally isolated from TV core code:
 *   - It only reads PUBLIC, visible text from the active tab (never hidden/locked
 *     LinkedIn contact fields, never bypasses CAPTCHA/access controls).
 *   - It renders a non-intrusive "Access Email / Phone" card with a credit counter.
 *   - It talks to the isolated middleware route POST /api/v1/enrichment/lookup.
 *
 * ---------------------------------------------------------------------------
 * Integration hooks (easy to plug in without breaking existing features)
 * ---------------------------------------------------------------------------
 *   import EnrichmentModule from './enrichment-module.js';   // or use window.EnrichmentModule
 *
 *   const enrichment = new EnrichmentModule({
 *     apiBase: 'http://localhost:4100',               // your isolated middleware origin
 *     getAuthHeaders: () => ({ Authorization: `Bearer ${talentVaultToken}` }),
 *     mountPoint: '#enrichment-mount',                // CSS selector for the card container
 *     defaultCredits: 50,
 *   });
 *   enrichment.mount();
 *
 * Manifest V3: add the middleware origin to host_permissions and run this file
 * from the side panel (sidepanel.html) via a <script> tag.
 */
(function (global, factory) {
  const moduleExports = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = moduleExports;
  } else {
    global.EnrichmentModule = moduleExports;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // --- Public, visible-text extraction (safe; never touches hidden DOM) ----
  const PUBLIC_EMAIL_RE = /[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}/gi;
  const PUBLIC_PHONE_RE =
    /(?:\+?\d{1,3}[\s.\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3,4}[\s.\-]?\d{3,4}[\s.\-]?\d{3,4}/g;

  function dedupe(list) {
    return Array.from(new Set((list || []).map((s) => String(s).trim()).filter(Boolean)));
  }

  /**
   * Extract candidate emails/phones from arbitrary PUBLIC text.
   * Pure + side-effect free, so it can be reused and unit-tested.
   */
  function extractPublicContacts(text) {
    if (!text || typeof text !== 'string') return { emails: [], phones: [] };
    const emails = dedupe(text.match(PUBLIC_EMAIL_RE) || []);
    // Drop obvious image/asset extensions falsely matched as emails.
    const cleanEmails = emails.filter(
      (e) => !/\.(png|jpg|jpeg|gif|webp|svg)$/i.test(e)
    );
    const phones = dedupe(text.match(PUBLIC_PHONE_RE) || []);
    return { emails: cleanEmails, phones };
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach((k) => {
        const value = attrs[k];
        if (k === 'class') node.className = value;
        else if (k === 'text') node.textContent = value;
        else if (k === 'style') node.style.cssText = value || '';
        // Event handlers: either { on: { click: fn } } or { onclick: fn }.
        else if (k === 'on' && value && typeof value === 'object') {
          Object.keys(value).forEach((evt) => {
            if (typeof value[evt] === 'function') node.addEventListener(evt, value[evt]);
          });
        } else if (k.slice(0, 2) === 'on' && typeof value === 'function') {
          node.addEventListener(k.slice(2).toLowerCase(), value);
        } else if (value !== undefined && value !== null) {
          node.setAttribute(k, value);
        }
      });
    }
    (children || []).forEach((c) => {
      if (c === null || c === undefined) return;
      node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return node;
  }

  function escapeHtml(value) {
    return String(value === undefined || value === null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  class EnrichmentModule {
    constructor(config = {}) {
      this.config = Object.assign(
        {
          apiBase: 'http://localhost:4100',
          endpoint: '/api/v1/enrichment/lookup',
          mountPoint: null,            // CSS selector or HTMLElement
          defaultCredits: 50,
          getAuthHeaders: null,        // () => ({ Authorization: 'Bearer ...' })
          getProfile: null,            // () => ({ firstName, lastName, domain, company, title, public_emails, public_phones })
          onRevealed: null,            // (contact, meta) => {}
          onError: null,               // (error) => {}
        },
        config
      );

      this.credits = Number.isFinite(config.defaultCredits)
        ? config.defaultCredits
        : this.config.defaultCredits;

      this.root = null;
      this.revealedContact = null;     // last successful reveal result
    }

    // --- Mounting ----------------------------------------------------------
    mount(mountPoint) {
      const target = mountPoint || this.config.mountPoint;
      const container =
        typeof target === 'string' ? document.querySelector(target) : target;
      if (!container) {
        // Never throw: the side panel may simply not have the mount point yet.
        console.warn('[EnrichmentModule] Mount point not found:', target);
        return this;
      }
      this.root = container;
      this._render();
      this._refreshCredits();          // optionally sync from the backend
      return this;
    }

    // --- Rendering (non-intrusive card + credit counter) -------------------
    _render() {
      if (!this.root) return;
      this.root.innerHTML = '';

      this.card = el('div', { class: 'enrichment-card' });
      this.card.style.cssText =
        'background:#fff;border:1px solid #e2e8f0;border-radius:8px;' +
        'padding:12px;margin-top:12px;font-family:inherit;';

      this.creditBadge = el('span', {
        class: 'enrichment-credits',
        text: this._creditLabel(),
      });
      this.creditBadge.style.cssText =
        'display:inline-block;font-size:11px;font-weight:600;color:#2563eb;' +
        'background:#eff6ff;padding:2px 8px;border-radius:999px;';

      this.statusEl = el('div', { class: 'enrichment-status', text: '' });
      this.statusEl.style.cssText =
        'font-size:11px;color:#64748b;margin-top:8px;min-height:14px;';

      // Dedicated "enriched output" box shown under the buttons.
      this.outputEl = el('div', { class: 'enrichment-output' });
      this.outputEl.style.cssText =
        'display:none;margin-top:8px;padding:8px;border:1px solid #e2e8f0;' +
        'border-radius:6px;background:#f8fafc;font-size:12px;line-height:1.6;';

      this.emailBtn = this._actionButton('Access Email', () => this.reveal('email'));
      this.enrichBtn = this._actionButton('Enrich Contact', () => this.reveal('both'));

      this.card.appendChild(
        el('div', { class: 'enrichment-header' }, [
          el('strong', { text: 'Contact Enrichment' }),
          this.creditBadge,
        ])
      );
      this.card.appendChild(
        el('div', { class: 'enrichment-actions', style: 'display:flex;gap:8px;margin-top:10px;' }, [
          this.emailBtn,
          this.enrichBtn,
        ])
      );
      this.card.appendChild(this.outputEl);
      this.card.appendChild(this.statusEl);

      this.root.appendChild(this.card);
    }

    _actionButton(label, onClick) {
      const btn = el('button', { type: 'button', text: label, on: { click: onClick } });
      btn.style.cssText =
        'flex:1;padding:8px 10px;border:1px solid #2563eb;color:#2563eb;' +
        'background:transparent;border-radius:6px;cursor:pointer;font-size:12px;font-weight:600;';
      return btn;
    }

    _creditLabel() {
      return `${this.credits} Free Credits Remaining`;
    }

    _setCredits(n) {
      this.credits = Math.max(0, Number.isFinite(n) ? n : 0);
      if (this.creditBadge) this.creditBadge.textContent = this._creditLabel();
    }

    _setStatus(message, kind) {
      if (!this.statusEl) return;
      this.statusEl.textContent = message || '';
      const colors = {
        info: '#64748b',
        loading: '#2563eb',
        success: '#15803d',
        warn: '#a16207',
        error: '#b91c1c',
      };
      this.statusEl.style.color = colors[kind || 'info'] || colors.info;
    }

    // --- Enriched output box ----------------------------------------------
    _showOutput(contact, credits, candidates) {
      if (!this.outputEl) return;

      // Always render Email, then Phone directly beneath it, then confidence
      // + verification status, then the candidate list, then credits.
      const email = contact && contact.email ? escapeHtml(contact.email) : 'Not found';
      const phone = contact && contact.phone ? escapeHtml(contact.phone) : 'Not found';
      const confidence = contact && Number.isFinite(contact.confidence)
        ? `${Math.round(contact.confidence * 100)}%`
        : '—';
      const verified = contact && contact.verified ? 'Verified' : 'Not verified';

      const rows = [
        `<div class="enr-row"><strong>Email:</strong> ${email}</div>`,
        `<div class="enr-row"><strong>Phone:</strong> ${phone}</div>`,
        `<div class="enr-row"><strong>Confidence:</strong> ${confidence}</div>`,
        `<div class="enr-row"><strong>Verification:</strong> ${verified}</div>`,
      ];

      if (Array.isArray(candidates) && candidates.length) {
        rows.push('<div class="enr-row"><strong>Candidate patterns:</strong></div>');
        candidates.slice(0, 8).forEach((c) => {
          const status = c.smtp_verified
            ? '<span class="enr-status-ok">verified</span>'
            : `<span class="enr-status-bad">${escapeHtml(c.smtp_reason || 'unverified')}</span>`;
          rows.push(
            `<div class="enr-cand">${escapeHtml(c.email)} <span class="enr-pat">(${escapeHtml(c.pattern)})</span> ${status}</div>`
          );
        });
      }

      if (Number.isFinite(credits)) {
        rows.push(`<div class="enr-row"><strong>Credits remaining:</strong> ${escapeHtml(credits)}</div>`);
      }

      this.outputEl.innerHTML = rows.join('');
      this.outputEl.style.display = 'block';
      this.outputEl.style.color = '#15803d';
    }

    _showNotFound(detail) {
      if (!this.outputEl) return;
      this.outputEl.textContent = 'Email/Phone Not Found';
      this.outputEl.style.display = 'block';
      this.outputEl.style.color = '#a16207';
      this._setStatus(detail || 'Email/Phone Not Found', 'warn');
    }

    _hideOutput() {
      if (!this.outputEl) return;
      this.outputEl.innerHTML = '';
      this.outputEl.style.display = 'none';
    }

    _setBusy(busy) {
      [this.emailBtn, this.enrichBtn].forEach((b) => {
        if (b) b.disabled = busy;
      });
    }

    // --- Credit sync (optional) -------------------------------------------
    async _refreshCredits() {
      try {
        const resp = await this._request('GET', '/api/v1/enrichment/credits');
        if (resp && Number.isFinite(resp.credits_remaining)) {
          this._setCredits(resp.credits_remaining);
        }
      } catch (e) {
        /* best-effort: keep the locally seeded counter */
      }
    }

    // --- Safe public-DOM scrape of the ACTIVE tab --------------------------
    /**
     * Reads only the active tab's PUBLIC inner text and returns any emails/phones.
     * Wrapped so DOM selector changes or permission failures never throw.
     */
    async scrapeActiveTab() {
      try {
        if (typeof chrome === 'undefined' || !chrome.tabs || !chrome.scripting) {
          return { emails: [], phones: [] };
        }
        const [tab] = await new Promise((resolve) =>
          chrome.tabs.query({ active: true, currentWindow: true }, resolve)
        );
        if (!tab || !tab.id) return { emails: [], phones: [] };

        const injected = await new Promise((resolve) => {
          chrome.scripting.executeScript(
            {
              target: { tabId: tab.id },
              func: () => (document.body ? document.body.innerText : ''),
            },
            (results) => resolve(results && results[0] ? results[0].result : '')
          );
        });

        return extractPublicContacts(injected || '');
      } catch (err) {
        console.warn('[EnrichmentModule] Public scrape skipped:', err && err.message);
        return { emails: [], phones: [] };
      }
    }

    // --- Lookup ------------------------------------------------------------
    async reveal(type) {
      this._setBusy(true);
      this._hideOutput();
      this._setStatus('Enriched lookup in progress...', 'loading');

      try {
        // 1. Identity + public identifiers. Prefer the host page's injected
        //    profile (via getProfile); fall back to a safe active-tab scrape.
        let profile = {};
        if (typeof this.config.getProfile === 'function') {
          try {
            profile = this.config.getProfile() || {};
          } catch (e) {
            profile = {};
          }
        }

        let publicEmails = (profile.public_emails || []).slice(0, 3);
        let publicPhones = (profile.public_phones || []).slice(0, 3);

        if (!publicEmails.length && !publicPhones.length) {
          const found = await this.scrapeActiveTab();
          publicEmails = found.emails.slice(0, 3);
          publicPhones = found.phones.slice(0, 3);
        }

        const payload = {
          type, // 'email' | 'both'
          profile: {
            firstName: profile.firstName || profile.first_name || '',
            lastName: profile.lastName || profile.last_name || '',
            domain: profile.domain || '',
            headline: profile.headline || profile.title || '',
            profile_url: profile.profile_url || profile.profileUrl || '',
            public_emails: publicEmails,
            public_phones: publicPhones,
          },
        };

        const resp = await this._request('POST', this.config.endpoint, payload);

        if (resp && resp.success && resp.contact) {
          this.revealedContact = resp.contact;
          const credits = resp.credits_remaining;
          this._setCredits(credits);
          this._showOutput(resp.contact, credits, resp.candidates);
          this._setStatus('Contact found.', 'success');
          if (typeof this.config.onRevealed === 'function') {
            this.config.onRevealed(resp.contact, resp);
          }
        } else if (resp && resp.error === 'INSUFFICIENT_CREDITS') {
          this._setStatus('No free credits remaining.', 'warn');
          this._showNotFound('No free credits remaining.');
        } else if (resp && resp.error === 'NOT_FOUND') {
          this._showNotFound('No contact found for this profile.');
        } else {
          // Any other backend error or empty result.
          this._showNotFound(resp && resp.message ? resp.message : 'Lookup failed.');
        }
      } catch (err) {
        this._showNotFound('Could not reach enrichment service.');
        if (typeof this.config.onError === 'function') this.config.onError(err);
      } finally {
        this._setBusy(false);
      }
    }

    // --- HTTP helper -------------------------------------------------------
    async _request(method, path, body) {
      const headers = Object.assign(
        { 'Content-Type': 'application/json', Accept: 'application/json' },
        typeof this.config.getAuthHeaders === 'function'
          ? this.config.getAuthHeaders()
          : {}
      );

      const options = { method, headers };
      if (body) options.body = JSON.stringify(body);

      const resp = await fetch(`${this.config.apiBase}${path}`, options);
      let data = {};
      try {
        data = await resp.json();
      } catch (e) {
        data = {};
      }
      return data;
    }
  }

  EnrichmentModule.extractPublicContacts = extractPublicContacts;

  return EnrichmentModule;
});
