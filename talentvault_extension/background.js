// Background service worker for Talent Vault Extension
const TV_BUILD = "tv-1.0.6-20261021";
try {
  console.log(`[Talent Vault Debug] background service worker loaded | build=${TV_BUILD} | extId=${typeof chrome !== "undefined" && chrome.runtime ? chrome.runtime.id : "unknown"}`);
} catch (e) {}

if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onInstalled) {
  chrome.runtime.onInstalled.addListener(() => {
    console.log('Talent Vault extension installed.');
  });
}

// When the extension action icon is clicked in the toolbar, toggle the floating widget
if (typeof chrome !== "undefined" && chrome.action && chrome.action.onClicked) {
  chrome.action.onClicked.addListener(async (tab) => {
    if (tab && tab.id) {
      try {
        await chrome.tabs.sendMessage(tab.id, { action: "tv_toggle_widget" });
      } catch (e) {}
    }
  });
}

// ---------------------------------------------------------------------------
// Chrome Downloads API (Manifest V3).
//
// NOTE: MV3 does NOT provide an API to read the bytes of a completed download
// back into the extension (fetch on file:// is blocked, and chrome.downloads
// only exposes id/filename/url/state). We therefore use it ONLY to:
//   1. trigger a real, browser-native download (which carries the recruiter's
//      cookies and looks like a normal human download), and
//   2. track/log download lifecycle for diagnostics.
// The actual base64 attachment comes from the page-context blob: capture in
// content.js, or from the recruiter's manual upload.
// ---------------------------------------------------------------------------
if (typeof chrome !== "undefined" && chrome.downloads) {
  chrome.downloads.onCreated.addListener((item) => {
    console.log("[Talent Vault Debug] download created:", JSON.stringify(item));
  });
  chrome.downloads.onChanged.addListener((delta) => {
    if (delta && delta.state) {
      console.log(`[Talent Vault Debug] download ${delta.id} -> ${delta.state.current}`);
    }
  });
}

async function triggerResumeDownload(url) {
  if (!url || !/^https?:/i.test(url)) return { ok: false, error: "No valid resume URL." };
  if (typeof chrome === "undefined" || !chrome.downloads) {
    return { ok: false, error: "chrome.downloads unavailable." };
  }
  try {
    const id = await chrome.downloads.download({ url, saveAs: false, conflictAction: "uniquify" });
    return { ok: true, downloadId: id };
  } catch (e) {
    return { ok: false, error: (e && e.message) || "Download trigger failed." };
  }
}

// ---------------------------------------------------------------------------
// Authenticated API proxy.
//
// The in-page floating widget runs inside a content script, which is subject to
// the host page's CORS rules. All Talent Vault API calls are therefore proxied
// through this service worker (which has host permissions) so the recruiter's
// session cookies and CSRF token are sent correctly and never exposed to the page.
// ---------------------------------------------------------------------------
const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const API_BASE_STORAGE_KEY = "apiBaseUrl";
const IMPORT_PATH = "/api/v1/candidates/import/";

if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
  chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
    if (request && request.action === "tv_api_request") {
      handleApiRequest(request)
        .then(sendResponse)
        .catch((err) => sendResponse({ ok: false, error: err.message || "Request failed" }));
      return true; // async response
    }
    if (request && request.action === "tv_trigger_download") {
      triggerResumeDownload(request.url)
        .then(sendResponse)
        .catch((err) => sendResponse({ ok: false, error: err.message || "Request failed" }));
      return true;
    }
    return undefined;
  });
}

async function getApiBaseUrl() {
  return new Promise((resolve) => {
    try {
      if (chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(API_BASE_STORAGE_KEY, (stored) => {
          const override = stored && stored[API_BASE_STORAGE_KEY];
          if (override && typeof override === "string" && override.trim()) {
            resolve(override.trim().replace(/\/+$/, ""));
            return;
          }
          resolve(DEFAULT_API_BASE_URL);
        });
        return;
      }
    } catch (e) {}
    resolve(DEFAULT_API_BASE_URL);
  });
}

async function fetchCsrfToken(baseUrl) {
  try {
    const res = await fetch(`${baseUrl}${IMPORT_PATH}`, { method: "GET", credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      return data && data.csrfToken ? data.csrfToken : null;
    }
  } catch (e) {}
  return null;
}

async function handleApiRequest(request) {
  const baseUrl = (await getApiBaseUrl()).replace(/\/+$/, "");
  const method = (request.method || "GET").toUpperCase();
  const path = request.path || IMPORT_PATH;
  const url = `${baseUrl}${path}`;

  if (method === "GET") {
    const res = await fetch(url, { method: "GET", credentials: "include" });
    return { ok: res.ok, status: res.status, data: await res.json().catch(() => null) };
  }

  const doPost = async () => {
    const token = await fetchCsrfToken(baseUrl);
    const headers = { "Content-Type": "application/json", "Accept": "application/json" };
    if (token) headers["X-CSRFToken"] = token;
    return fetch(url, {
      method: "POST",
      headers: headers,
      credentials: "include",
      body: JSON.stringify(request.body || {}),
    });
  };

  let res = await doPost();
  if (res.status === 403) {
    res = await doPost(); // refresh a stale/rotated CSRF token once and retry
  }
  return { ok: res.ok, status: res.status, data: await res.json().catch(() => null) };
}
