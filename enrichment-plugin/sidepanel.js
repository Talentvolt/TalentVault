/**
 * sidepanel.js — TalentVault Contact Enrichment side panel controller.
 *
 * Responsibilities:
 *   1. Inject a content script DIRECTLY into the active tab via
 *      chrome.scripting.executeScript and scrape Name / Headline / Current Company
 *      / active LinkedIn Profile URL using robust fallback selectors (h1 for name,
 *      div.text-body-medium for headline, plus right-panel/experience fallbacks
 *      for company, and the canonical/location URL for the profile).
 *   2. Derive { firstName, lastName, domain, profile_url } and collect public
 *      emails/phones.
 *   3. Mount the EnrichmentModule widget at #enrichment-mount.
 *   4. Provide a manual "Scrape Profile" button so the user can re-scrape any time
 *      without closing the panel.
 */
(function () {
  'use strict';

  const ENRICHMENT_API_BASE = 'http://localhost:4100';
  const ENRICHMENT_ENDPOINT = '/api/v1/enrichment/lookup';

  // Robust LinkedIn selectors, ordered most-specific -> generic fallback.
  // The injected function tries EVERY selector and returns the first non-empty
  // match, so LinkedIn DOM changes never cause a throw or a blank result.
  const LINKEDIN_SELECTORS = {
    name: [
      'h1.text-heading-xlarge',
      '.pv-text-details__left-panel h1',
      '[data-anonymize="person-name"]',
      '.top-card-layout__title',
      'h1', // generic fallback
    ],
    headline: [
      '.pv-text-details__left-panel .text-body-medium',
      '.text-body-medium.break-words',
      'div.text-body-medium.break-words',
      '.text-body-medium',        // spec: headline via .text-body-medium
      'div.text-body-medium',
    ],
    company: [
      'a[data-tracking-control-name="background_details_company"]',
      'button[data-tracking-control-name="background_details_company"]',
      '[data-anonymize="company-name"]',
      'ul.pv-text-details__right-panel li button span',
      '.pv-text-details__right-panel li button span',
      'ul.pv-text-details__right-panel li',
      '.pv-text-details__right-panel div.text-body-medium',
      '#experience .experience-item__company-name',
      '#experience .pv-entity__secondary-title',
      '.pv-entity__secondary-title',
    ],
  };

  // The most recently scraped profile, exposed to the widget via getProfile().
  let currentProfile = {
    firstName: '',
    lastName: '',
    domain: '',
    company: '',
    title: '',
    profile_url: '',
    public_emails: [],
    public_phones: [],
  };

  function setField(id, value) {
    const input = document.getElementById(id);
    if (input) input.value = value || '';
  }

  function setStatus(message) {
    const el = document.getElementById('scrape-status');
    if (el) el.textContent = message || '';
  }

  function setScraping(busy) {
    const btn = document.getElementById('scrape-btn');
    if (btn) btn.disabled = busy;
    if (btn) btn.textContent = busy ? 'Scraping…' : 'Scrape Profile';
  }

  function deriveNames(fullName) {
    const parts = (fullName || '').trim().split(/\s+/).filter(Boolean);
    return {
      firstName: parts[0] || '',
      lastName: parts.slice(1).join(' ') || '',
    };
  }

  /**
   * Best-effort company -> domain guess (heuristic only).
   * Accepts a company name, an already-resolved domain, or an email.
   * In production, replace this with a company->domain resolver / CRM lookup so
   * the pattern engine receives an accurate email domain.
   */
  function deriveDomain(company) {
    if (!company) return '';
    const trimmed = String(company).trim();
    // Already a domain -> use it directly.
    if (/^[a-z0-9\-]+(\.[a-z0-9\-]+)+$/i.test(trimmed)) return trimmed.toLowerCase();
    // Email -> take the domain part.
    const at = trimmed.lastIndexOf('@');
    if (at >= 0) return trimmed.slice(at + 1).toLowerCase();
    // Otherwise slugify the company name into <slug>.com.
    const slug = trimmed
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '')
      .replace(/(pvt|ltd|private|limited|inc|llc|corp|corporation|technologies|technology|solutions)$/g, '');
    return slug ? `${slug}.com` : '';
  }

  /**
   * Fallback: parse a domain from the headline (email domain, bare domain, or
   * a trailing "at CompanyName" fragment).
   */
  function deriveDomainFromHeadline(headline) {
    if (!headline) return '';
    const text = String(headline).trim();
    const email = text.match(/[a-z0-9._%+\-]+@([a-z0-9.\-]+\.[a-z]{2,})/i);
    if (email) return email[1].toLowerCase();
    const bare = text.match(/\b([a-z0-9\-]+\.(?:com|org|net|io|co|in|ai|dev|tech|us|uk|info|biz))\b/i);
    if (bare) return bare[1].toLowerCase();
    const at = text.match(/\bat\s+([A-Za-z0-9][A-Za-z0-9&.\-\s]{0,40}?)(?=\s*(?:[|·•,]|$))/);
    if (at) return deriveDomain(at[1]);
    return '';
  }

  /**
   * Domain resolution order: company -> headline -> gmail.com (last resort).
   */
  function resolveDomain(company, headline) {
    return deriveDomain(company) || deriveDomainFromHeadline(headline) || 'gmail.com';
  }

  /**
   * Injected into the active tab. Must be self-contained (only uses its `selectors`
   * argument and the page DOM) so Chrome can serialize it correctly.
   */
  function scrapeProfileFunc(selectors) {
    const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const pick = (sels) => {
      for (const sel of sels || []) {
        try {
          const nodes = document.querySelectorAll(sel);
          for (const node of nodes) {
            const text = clean(node.innerText || node.textContent);
            if (text) return text;
          }
        } catch (e) {
          /* skip broken/unavailable selector */
        }
      }
      return '';
    };

    let name = pick(selectors.name);
    if (!name) {
      // Fallback: LinkedIn page title is usually "Name - Role | LinkedIn".
      const titleText = clean(document.title || '');
      if (titleText) name = clean(titleText.split(/[|—–-]/)[0]);
    }

    // Headline: prefer .text-body-medium (explicit spec).
    const headline = pick(selectors.headline);

    // Company: specific selectors first, then a right-panel heuristic that
    // skips location/connection entries.
    let company = pick(selectors.company);
    if (!company) {
      company = pickCompanyFromRightPanel();
    }

    const bodyText = document.body
      ? document.body.innerText || document.body.textContent || ''
      : '';

    // Active LinkedIn profile URL: prefer the canonical link, else the live
    // location. Only /in/<slug> URLs are treated as profile URLs; anything
    // else (feed, search, company pages) yields ''.
    let profileUrl = '';
    try {
      const canonical = document.querySelector('link[rel="canonical"]');
      const href = (canonical && canonical.href) || window.location.href || '';
      const match = String(href).match(/https?:\/\/[^/]+\/in\/[^/?#]+/i);
      profileUrl = match ? match[0].replace(/\/+$/, '') : String(href).split(/[?#]/)[0];
    } catch (e) {
      profileUrl = '';
    }

    return { name, headline, company, bodyText, profileUrl };

    function pickCompanyFromRightPanel() {
      try {
        const items = document.querySelectorAll('ul.pv-text-details__right-panel li');
        for (const li of items) {
          const text = clean(li.innerText || li.textContent);
          if (!text) continue;
          // Skip follower/connection counts and location-like values.
          if (/\b(followers?|connections?)\b/i.test(text)) continue;
          if (text.split(',').length >= 2) continue; // "City, State, Country"
          return text;
        }
      } catch (e) {
        /* ignore */
      }
      return '';
    }
  }

  /**
   * Run a direct content-script injection on the active tab.
   * Returns { name, headline, company, bodyText, profileUrl } or { error }.
   */
  function scrapeLinkedInProfile() {
    return new Promise((resolve) => {
      try {
        if (typeof chrome === 'undefined' || !chrome.tabs || !chrome.scripting) {
          return resolve({ error: 'chrome.scripting is not available in this context.' });
        }

        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
          const tab = tabs && tabs[0];
          if (!tab || !tab.id) {
            return resolve({ error: 'No active tab found.' });
          }

          chrome.scripting.executeScript(
            {
              target: { tabId: tab.id },
              func: scrapeProfileFunc,
              args: [LINKEDIN_SELECTORS],
            },
            (results) => {
              // Surface the real injection failure (e.g. missing host permission
              // for the current page) instead of a generic "could not scrape".
              if (chrome.runtime.lastError) {
                return resolve({ error: chrome.runtime.lastError.message });
              }
              const result = results && results[0] ? results[0].result : null;
              resolve(result || { name: '', headline: '', company: '', bodyText: '', profileUrl: '' });
            }
          );
        });
      } catch (err) {
        resolve({ error: (err && err.message) || String(err) });
      }
    });
  }

  function buildProfile(scraped) {
    if (!scraped) return currentProfile;

    const { firstName, lastName } = deriveNames(scraped.name);
    const company = (scraped.company || '').trim();
    const title = (scraped.headline || '').trim();

    // Public contacts from visible text only (never hidden/locked fields).
    const EnrichmentModule = window.EnrichmentModule;
    const extractor =
      EnrichmentModule && EnrichmentModule.extractPublicContacts
        ? EnrichmentModule.extractPublicContacts
        : () => ({ emails: [], phones: [] });
    const { emails, phones } = extractor(scraped.bodyText || '');

    return {
      firstName,
      lastName,
      domain: resolveDomain(company, title),
      company,
      headline: title,
      title,
      profile_url: (scraped.profileUrl || '').trim(),
      public_emails: emails.slice(0, 3),
      public_phones: phones.slice(0, 3),
    };
  }

  /**
   * Build the live lookup profile. Reads the (editable) Current Company/Domain
   * field at click-time so any manual edits are sent to the backend, and
   * resolves the domain with company -> headline -> gmail.com fallback.
   */
  function buildLookupProfile() {
    const companyEl = document.getElementById('cand-company');
    const headlineEl = document.getElementById('cand-headline');

    const company = companyEl ? companyEl.value.trim() : (currentProfile.company || '');
    const headline = headlineEl ? headlineEl.value.trim() : (currentProfile.headline || '');

    return {
      firstName: currentProfile.firstName,
      lastName: currentProfile.lastName,
      domain: resolveDomain(company, headline),
      company,
      headline,
      profile_url: currentProfile.profile_url,
      public_emails: currentProfile.public_emails,
      public_phones: currentProfile.public_phones,
    };
  }

  async function runScrape() {
    setScraping(true);
    setStatus('Scraping profile…');

    const scraped = await scrapeLinkedInProfile();

    if (!scraped || scraped.error) {
      const reason = scraped && scraped.error ? scraped.error : 'unknown error';
      setStatus(`Could not scrape profile: ${reason}. Open a LinkedIn profile tab and retry.`);
      setScraping(false);
      return;
    }

    if (!scraped.name && !scraped.company && !scraped.headline) {
      setStatus('No profile data found on the active tab. Make sure a LinkedIn profile is open.');
      setScraping(false);
      return;
    }

    currentProfile = buildProfile(scraped);

    setField('cand-name', scraped.name || '');
    setField('cand-headline', scraped.headline || '');
    setField('cand-company', scraped.company || '');
    setStatus('Profile ready. Click "Access Email" or "Enrich Contact".');
    setScraping(false);
  }

  async function init() {
    const EnrichmentModule = window.EnrichmentModule;
    if (!EnrichmentModule) {
      setStatus('Enrichment widget failed to load (enrichment-module.js missing).');
      return;
    }

    // Mount the widget. getProfile() reads the live (editable) company/domain
    // field at lookup time so manual edits are sent to the backend.
    const enrichment = new EnrichmentModule({
      apiBase: ENRICHMENT_API_BASE,
      endpoint: ENRICHMENT_ENDPOINT,
      mountPoint: '#enrichment-mount',
      defaultCredits: 50,
      getProfile: () => buildLookupProfile(),
    });
    enrichment.mount();

    // Manual re-scrape button (can be clicked any time without closing the panel).
    const scrapeBtn = document.getElementById('scrape-btn');
    if (scrapeBtn) scrapeBtn.addEventListener('click', runScrape);

    // Auto-scrape once on load.
    await runScrape();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
