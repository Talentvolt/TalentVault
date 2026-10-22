// Enhanced Content Script for Talent Vault Extension
const TV_BUILD = "tv-1.0.6-20261021";

(function logContentScriptLoaded() {
  try {
    const extId = (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id) || "unknown";
    const url = (typeof location !== "undefined" && location.href) || "";
    console.log(`[Talent Vault Debug] content.js loaded | build=${TV_BUILD} | extId=${extId} | profile=${url}`);
    console.log(`[Talent Vault Debug] chrome.runtime present=${!!(typeof chrome !== "undefined" && chrome.runtime)} | extractPageData defined=${typeof extractPageData === "function"}`);
  } catch (e) {
    console.log("[Talent Vault Debug] content.js loaded (no chrome runtime)", e);
  }
})();

if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "extract_candidate_data") {
      console.log("[Talent Vault Debug] received extract_candidate_data request");
      // The parser is ONLY invoked here, i.e. on an explicit user action (the
      // TV icon or the Parse button). It never auto-runs via observers/timers.
      (async () => {
        try {
          await preparePage();
          await humanDelay(200, 500);
          const data = extractPageData();
          console.log(`[Talent Vault Extraction Log] Candidate Name: "${data.name}", Headline: "${data.headline}", Current Company: "${data.current_company}", Location: "${data.location}"`);
          console.log(`[Talent Vault Extraction Log] Found ${data.experience.length} Experience entries, ${data.education.length} Education entries, ${data.skills.length} Skills.`);
          console.log("FINAL_EXTRACTED_PAYLOAD:", JSON.stringify(data, null, 2));
          sendResponse({
            status: "success",
            data: data,
            logs: {
              experienceCount: data.experience.length,
              educationCount: data.education.length,
              projectsCount: data.projects.length,
              certificationsCount: data.certifications.length,
              skillsCount: data.skills.length
            }
          });
        } catch (err) {
          console.error("Talent Vault extraction error:", err);
          sendResponse({ status: "error", error: err.message });
        }
      })();
      return true;
    }

    if (request.action === "tv_fetch_resume") {
      fetchResumeAsBase64(request.url)
        .then((res) => sendResponse({ ok: true, ...res }))
        .catch((err) => sendResponse({ ok: false, error: err && err.message ? err.message : "Resume download failed" }));
      return true;
    }

    if (request.action === "tv_download_resume") {
      // Human-like click the Naukri CV/download control, then read the blob:
      // resume from the page context (blob: URLs are origin-scoped and cannot be
      // fetched from the content script's isolated world).
      (async () => {
        try {
          const res = await captureNaukriResumeViaClick();
          sendResponse(res);
        } catch (err) {
          sendResponse({ ok: false, error: err && err.message ? err.message : "Resume capture failed" });
        }
      })();
      return true;
    }

    return true;
  });
}

// Randomized human-like delay. Never use a fixed/predictable timer so the
// portals cannot fingerprint us by timing alone.
function humanDelay(minMs, maxMs) {
  const min = typeof minMs === "number" ? minMs : 300;
  const max = typeof maxMs === "number" ? maxMs : 800;
  const ms = Math.floor(Math.random() * (max - min + 1)) + min;
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Simulate a real human pointer interaction (hover -> press -> release -> click)
// instead of a bare .click(), so the portal's event listeners fire naturally.
async function simulateHumanClick(el) {
  if (!el || typeof document === "undefined") return;
  const opts = { bubbles: true, cancelable: true, view: window };
  const fire = (type, ctor) => {
    try {
      let evt;
      if (typeof ctor === "function") {
        evt = new ctor(type, Object.assign({}, opts, { clientX: 10, clientY: 10 }));
      } else {
        evt = new Event(type, opts);
      }
      el.dispatchEvent(evt);
    } catch (e) {}
  };
  fire("pointerover", window.PointerEvent);
  fire("mouseover", window.MouseEvent);
  fire("pointermove", window.PointerEvent);
  fire("mousemove", window.MouseEvent);
  await humanDelay(40, 140);
  fire("pointerdown", window.PointerEvent);
  fire("mousedown", window.MouseEvent);
  await humanDelay(60, 160);
  fire("pointerup", window.PointerEvent);
  fire("mouseup", window.MouseEvent);
  fire("click", window.MouseEvent);
  // Fallback if the synthetic click didn't register (some controls only listen
  // for the native .click()).
  try { el.click(); } catch (e) {}
}

// Expand inline "...see more" sections before parsing so truncated details are
// readable. This ONLY runs on a manual trigger (TV icon / Parse button). It
// never scrolls and never polls the page in the background. Any simulated click
// uses a randomized human-like delay.
async function preparePage() {
  try {
    const seeMoreBtns = document.querySelectorAll(
      '.inline-show-more-text__button, .pv-about-section__see-more, .lt-line-clamp__more, button.pv-profile-section__see-more-inline, [data-view-name*="inline-show-more-button"]'
    );
    for (const btn of seeMoreBtns) {
      try {
        if (btn.offsetParent === null) continue; // only click visible controls
        btn.click();
        await humanDelay(80, 220);
      } catch (e) {}
    }
  } catch (e) {}

  // Naukri Resdex lazy-renders the "Work Experience" / "Education" sections and
  // shows the candidate CV behind an "Attached CV" / "Resume" tab. On a manual
  // parse we scroll to trigger the lazy render, wait for the section headers to
  // appear, and then reveal the resume tab. None of this runs in the background.
  try {
    const host = (typeof window !== "undefined" && window.location && window.location.hostname) ? window.location.hostname.toLowerCase() : "";
    if (host.includes("naukri.com")) {
      await prepareNaukriProfileDetailTab();
      await prepareNaukriSections();
      // Capture the resume URL by temporarily switching to the resume tab, then
      // restoring "Profile detail". Contact is revealed LAST so the phone number
      // (revealed by "View phone number") is not reset by a later tab switch.
      await captureNaukriResumeUrl();
      await prepareNaukriContact();
    }
  } catch (e) {}
}

// The resume URL captured from the "Attached CV" / resume iframe tab. Stored at
// module scope so detectResume() can return it even after we switch back to the
// "Profile detail" tab for extraction.
let naukriResumeUrl = "";

// Naukri renders the candidate in two mutually-exclusive tabs: "Profile detail"
// (name/contact + Work Experience + Education) and "Attached CV" (the resume).
// The Experience/Education DOM is NOT present until "Profile detail" is active,
// so we activate it first and wait for the sections to render.
async function prepareNaukriProfileDetailTab() {
  try {
    const nodes = document.querySelectorAll('[role="tab"], button, a, li, [role="button"]');
    for (const el of nodes) {
      try {
        if (el.offsetParent === null && el.getClientRects && el.getClientRects().length === 0) continue;
      } catch (e) {}
      const txt = getCleanText(el).toLowerCase().trim();
      if (!txt || txt.length > 60) continue;
      if (!/profile\s*detail/i.test(txt)) continue;
      try { el.click(); } catch (e) {}
      // Wait ~1 second for Naukri to render the profile sections after the tab
      // switch before any extraction reads them.
      await humanDelay(900, 1200);
      return;
    }
  } catch (e) {}
}

// Trigger Naukri's lazy rendering by scrolling down incrementally and then
// waiting (bounded) until the "Work Experience" / "Education" section headers
// exist in the DOM.
async function prepareNaukriSections() {
  try {
    const canScroll = typeof window !== "undefined" && typeof window.scrollBy === "function" && document.body;
    const deadline = Date.now() + 5000;

    // Scroll down in small steps so lazy sections render.
    for (let i = 0; canScroll && i < 8; i++) {
      try { window.scrollBy(0, 500); } catch (e) {}
      await humanDelay(150, 300);
    }

    while (Date.now() < deadline) {
      const hasExp = !!findNaukriSectionTitle(NAUKRI_SECTION_KEYWORDS.experience, document);
      const hasEdu = !!findNaukriSectionTitle(NAUKRI_SECTION_KEYWORDS.education, document);
      if (hasExp || hasEdu) break;
      if (canScroll) { try { window.scrollBy(0, 500); } catch (e) {} }
      await humanDelay(400, 600);
    }

    // Scroll back to the top so the header is visible again for parsing.
    if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
      try { window.scrollTo(0, 0); } catch (e) {}
    }
    await humanDelay(200, 400);
  } catch (e) {}
}

// Reveal hidden contact info: Naukri shows a "View phone number" / "View email"
// button that must be clicked before the actual mailto:/tel: value appears. The
// phone number only renders after its exact "View phone number" control is
// clicked and the reveal settles (~800ms), so we click each control and wait.
async function prepareNaukriContact() {
  try {
    const nodes = document.querySelectorAll('button, a, span, div, [role="button"], [role="link"]');
    let clickedPhone = false;
    let clickedEmail = false;
    for (const el of nodes) {
      try {
        if (el.offsetParent === null && el.getClientRects && el.getClientRects().length === 0) continue;
      } catch (e) {}
      const txt = getCleanText(el).toLowerCase().trim();
      if (!txt || txt.length > 40) continue;
      const isPhone = /view\s*(phone|phone\s*number|mobile|mobile\s*number|number)|show\s*(phone|number)/i.test(txt);
      const isEmail = /view\s*(email|email\s*id)|show\s*email/i.test(txt);
      if (!isPhone && !isEmail) continue;
      if (isPhone && clickedPhone) continue;
      if (isEmail && clickedEmail) continue;
      try { el.click(); } catch (e) {}
      if (isPhone) {
        clickedPhone = true;
        await humanDelay(800, 900);
      } else {
        clickedEmail = true;
        await humanDelay(500, 700);
      }
    }
  } catch (e) {}
}

// Resolve a possibly-relative URL to an absolute http(s) URL, else "".
function absHttpUrl(raw) {
  if (!raw) return "";
  try {
    const u = new URL(raw, window.location.href);
    if (/^https?:/i.test(u.protocol)) return u.href;
  } catch (e) {}
  return "";
}

// A resume URL is only usable if it is an absolute http(s) URL. blob:/data: URLs
// are browser-local and must never be sent to the backend.
function normalizeResumeUrl(raw) {
  if (!raw) return "";
  if (/^(blob:|data:|javascript:)/i.test(String(raw))) return "";
  return absHttpUrl(raw);
}

// Find the resume document URL from a Naukri <iframe>/<embed>/<object>/<a>.
// Naukri either points the iframe at a direct .pdf/resume endpoint or at a
// blob: viewer (in which case the real download URL lives on a Download
// button/link, a data-* attribute, or a hidden <a> tag).
function findNaukriResumeUrl() {
  if (typeof document === "undefined") return "";
  const currentUrl = (() => {
    try { return (window.location.href || "").split("?")[0].split("#")[0]; } catch (e) { return ""; }
  })();

  // 1. Direct resume/.pdf URLs on iframe/embed/object/a (absolute or relative).
  const directNodes = document.querySelectorAll('iframe, embed, object, a');
  for (const el of directNodes) {
    const raw = (el.getAttribute && (el.getAttribute("src") || el.getAttribute("href") || "")) || "";
    if (!raw) continue;
    if (/^blob:/i.test(raw)) continue; // handled in step 2
    if (!/\.pdf|resume/i.test(raw)) continue;
    const url = absHttpUrl(raw);
    if (!url) continue;
    if (url.split("?")[0].split("#")[0] === currentUrl) continue;
    console.log("RAW_RESUME_URL_FOUND:", url);
    return url;
  }

  // 2. blob: viewer iframe/embed -> resolve the real download URL. A blob: URL
  // cannot be sent to the backend, so we look for the underlying endpoint.
  const viewerNodes = document.querySelectorAll('iframe, embed, object');
  for (const el of viewerNodes) {
    const raw = (el.getAttribute && (el.getAttribute("src") || "")) || "";
    if (!/^blob:/i.test(raw)) continue;
    console.log("RAW_RESUME_URL_FOUND: (blob: viewer detected, resolving download URL)");
    const near = el.parentElement ? findNaukriDownloadUrl(el.parentElement) : "";
    const resolved = near || findNaukriDownloadUrl(document);
    if (resolved) {
      console.log("RAW_RESUME_URL_FOUND:", resolved);
      return resolved;
    }
  }

  return "";
}

// Find a real http(s) resume/download URL near a blob: viewer: check data-*
// attributes, Download buttons/links, and hidden anchors.
function findNaukriDownloadUrl(scope) {
  if (!scope || typeof scope.querySelectorAll !== "function") return "";

  // A) data-* attributes that carry a resume/download/file URL.
  const dataSel = '[data-url], [data-href], [data-download-url], [data-file-url], [data-resume-url], [data-src], [data-link], [data-download]';
  for (const el of scope.querySelectorAll(dataSel)) {
    const val = (el.getAttribute("data-url") || el.getAttribute("data-href") || el.getAttribute("data-download-url") ||
      el.getAttribute("data-file-url") || el.getAttribute("data-resume-url") || el.getAttribute("data-src") ||
      el.getAttribute("data-link") || el.getAttribute("data-download") || "").trim();
    if (/(resume|\.pdf|download|file)/i.test(val)) {
      const u = absHttpUrl(val);
      if (u) return u;
    }
  }

  // B) Download controls (text/aria-label "download") with a real href or data-* URL.
  for (const el of scope.querySelectorAll('a, button, [role="button"], [role="link"]')) {
    const text = getCleanText(el).toLowerCase();
    const label = ((el.getAttribute && el.getAttribute("aria-label")) || "").toLowerCase();
    if (!/download|save/i.test(text + " " + label)) continue;
    const href = (el.getAttribute && el.getAttribute("href")) || "";
    if (/(resume|\.pdf|download|file)/i.test(href)) {
      const u = absHttpUrl(href);
      if (u) return u;
    }
    const d = (el.getAttribute && (el.getAttribute("data-url") || el.getAttribute("data-href") || el.getAttribute("data-download-url") ||
      el.getAttribute("data-file-url") || el.getAttribute("data-resume-url") || el.getAttribute("data-src") || el.getAttribute("data-link"))) || "";
    if (d) {
      const u = absHttpUrl(d);
      if (u) return u;
    }
  }

  // C) Hidden anchor with a resume/.pdf href.
  for (const el of scope.querySelectorAll('a[href]')) {
    const href = el.getAttribute("href") || "";
    if (/(resume|\.pdf|download|file)/i.test(href)) {
      const u = absHttpUrl(href);
      if (u) return u;
    }
  }

  return "";
}

// Capture the resume URL from the "Attached CV" / "Resume" tab, then restore the
// "Profile detail" tab so Experience/Education remain visible for extraction.
async function captureNaukriResumeUrl() {
  try {
    // The resume iframe is sometimes already in the DOM even on "Profile detail".
    naukriResumeUrl = findNaukriResumeUrl();
    if (naukriResumeUrl) {
      console.log(`[Talent Vault Debug] Naukri resume URL captured: ${naukriResumeUrl}`);
      return;
    }

    const nodes = document.querySelectorAll('[role="tab"], button, a, li, [role="button"]');
    for (const el of nodes) {
      try {
        if (el.offsetParent === null && el.getClientRects && el.getClientRects().length === 0) continue;
      } catch (e) {}
      const txt = getCleanText(el).toLowerCase().trim();
      if (!txt || txt.length > 40) continue;
      if (!/(attached cv|attached resume|view cv|view resume|download cv|download resume|cv|resume)/i.test(txt)) continue;
      await simulateHumanClick(el);
      // Give Naukri ~1 second to render the CV viewer / iframe after the tab is
      // activated before we attempt to read the resume URL.
      await humanDelay(900, 1200);
      naukriResumeUrl = findNaukriResumeUrl();
      break;
    }

    console.log(`[Talent Vault Debug] Naukri resume URL after tab switch: ${naukriResumeUrl || "(none — no http(s) download URL found)"}`);

    // Switch back to "Profile detail" so the Experience/Education sections are
    // present when extractPageData() runs.
    await prepareNaukriProfileDetailTab();
  } catch (e) {}
}

// Find the exact "Download CV" / "Download Resume" control in the viewer.
function findNaukriDownloadButton() {
  if (typeof document === "undefined") return null;
  const nodes = document.querySelectorAll('a, button, [role="button"], [role="link"]');
  for (const el of nodes) {
    try {
      if (el.offsetParent === null && el.getClientRects && el.getClientRects().length === 0) continue;
    } catch (e) {}
    const txt = getCleanText(el).toLowerCase().trim();
    const label = ((el.getAttribute && el.getAttribute("aria-label")) || "").toLowerCase();
    if (/download\s*(cv|resume)/i.test(txt + " " + label)) return el;
  }
  return null;
}

// Find a blob: resume URL from the currently-rendered viewer iframe/embed.
function findBlobResumeUrl() {
  if (typeof document === "undefined") return "";
  const nodes = document.querySelectorAll('iframe, embed, object');
  for (const el of nodes) {
    const src = (el.getAttribute && el.getAttribute("src")) || "";
    if (/^blob:/i.test(src)) return src;
  }
  return "";
}

// Convert a blob: URL to base64 by running a small script in the PAGE's main
// world (blob: URLs are origin-scoped; the content script's isolated world
// cannot fetch them). Uses window.postMessage to return the result.
function captureBlobAsBase64(blobUrl) {
  return new Promise((resolve, reject) => {
    const id = "tv_blob_" + Date.now() + "_" + Math.floor(Math.random() * 1e6);
    const onMsg = (event) => {
      if (event.source !== window || !event.data || event.data.__tvBlobId !== id) return;
      window.removeEventListener("message", onMsg);
      clearTimeout(timer);
      if (event.data.error) reject(new Error(event.data.error));
      else resolve(event.data.base64 || "");
    };
    const timer = setTimeout(() => {
      window.removeEventListener("message", onMsg);
      reject(new Error("Blob capture timed out."));
    }, 15000);
    window.addEventListener("message", onMsg);

    const script = document.createElement("script");
    script.textContent =
      "(function(){try{var id=" + JSON.stringify(id) + ";var u=" + JSON.stringify(blobUrl) + ";" +
      "fetch(u).then(function(r){return r.blob();}).then(function(b){" +
      "var fr=new FileReader();fr.onloadend=function(){try{var s=fr.result||'';var i=s.indexOf(',');window.postMessage({__tvBlobId:id,base64:i>=0?s.slice(i+1):s},'*');}catch(e){window.postMessage({__tvBlobId:id,error:String(e)},'*');}};fr.readAsDataURL(b);" +
      "}).catch(function(e){window.postMessage({__tvBlobId:id,error:String(e)},'*');});}catch(e){window.postMessage({__tvBlobId:id,error:String(e)},'*');}})();";
    (document.head || document.documentElement).appendChild(script);
    script.remove();
  });
}

// Human-like "Download Resume": click the CV tab + Download button, then read the
// blob: resume as base64. Falls back to a plain http(s) resume URL otherwise.
async function captureNaukriResumeViaClick() {
  if (typeof document === "undefined") {
    return { ok: false, error: "No document available." };
  }

  // 1. Ensure the CV/resume tab is open.
  const nodes = document.querySelectorAll('[role="tab"], button, a, li, [role="button"]');
  for (const el of nodes) {
    try {
      if (el.offsetParent === null && el.getClientRects && el.getClientRects().length === 0) continue;
    } catch (e) {}
    const txt = getCleanText(el).toLowerCase().trim();
    if (!txt || txt.length > 40) continue;
    if (!/(attached cv|attached resume|view cv|view resume|cv|resume)/i.test(txt)) continue;
    await simulateHumanClick(el);
    break;
  }
  await humanDelay(900, 1200);

  // 2. If a blob: viewer is present, read its bytes directly.
  const blobUrl = findBlobResumeUrl();
  if (blobUrl) {
    try {
      const base64 = await captureBlobAsBase64(blobUrl);
      if (base64) {
        return {
          ok: true,
          data_base64: base64,
          mime_type: "application/pdf",
          filename: "Candidate_Resume.pdf",
        };
      }
    } catch (e) {
      console.warn("[Talent Vault] blob: capture failed:", e && e.message);
    }
  }

  // 3. Otherwise, human-like click the Download control so the browser downloads
  //    the file (recruiter can then attach it via Manual Upload).
  const dlBtn = findNaukriDownloadButton();
  if (dlBtn) {
    await simulateHumanClick(dlBtn);
    await humanDelay(400, 800);
  }

  const httpUrl = findNaukriResumeUrl();
  // 4. If there's a real http(s) resume URL, trigger a browser-native download
  //    via the Downloads API (carries the recruiter's cookies, looks human). MV3
  //    cannot read those bytes back, so this is a best-effort fallback.
  if (httpUrl && typeof chrome !== "undefined" && chrome.runtime) {
    try {
      chrome.runtime.sendMessage({ action: "tv_trigger_download", url: httpUrl }, () => {});
    } catch (e) {}
  }

  return {
    ok: false,
    resume_url: httpUrl || "",
    error: "No base64 could be captured; use the manual upload or the source link.",
  };
}

// ---------------------------------------------------------------------------
// Core Extraction Coordinator
// ---------------------------------------------------------------------------
function extractPageData() {
  const hostname = (typeof window !== "undefined" && window.location && window.location.hostname) ? window.location.hostname.toLowerCase() : "";
  let source = "web_import";
  if (hostname.includes("linkedin.com")) {
    source = "linkedin";
  } else if (hostname.includes("naukri.com")) {
    source = "naukri";
  } else if (hostname.includes("apna.") || hostname.includes("apna.com") || hostname.includes("apna.co")) {
    source = "apna";
  }

  let base = {
    name: "",
    email: "",
    phone: "",
    headline: "",
    current_company: "",
    current_designation: "",
    location: "",
    summary: "",
    total_experience: null,
    current_salary: null,
    expected_salary: null,
    notice_period: null,
    experience: [],
    education: [],
    projects: [],
    certifications: [],
    skills: [],
    resume_available: false,
    resume_url: "",
    resume_filename: "",
    profile_url: (typeof window !== "undefined" && window.location && window.location.href)
      ? window.location.href.split("?")[0].split("#")[0]
      : "",
    source: source,
  };

  if (source === "linkedin") {
    base = LinkedInAdapter.extract(base);
  } else if (source === "naukri") {
    base = NaukriAdapter.extract(base);
  } else if (source === "apna") {
    base = ApnaAdapter.extract(base);
  } else {
    base = GenericAdapter.extract(base);
  }

  // Detect an authorized, recruiter-visible resume document (optional attach).
  const resume = detectResume();
  if (resume && resume.resume_available) {
    base.resume_available = true;
    base.resume_url = resume.resume_url;
    base.resume_filename = resume.resume_filename;
  }

  // Extract CTC, notice period, email & phone ONLY from the main profile text
  // (or an open contact modal) — never from sidebars, "similar profiles",
  // recommendations, or navigation bars.
  const scopedText = scopedProfileText(source);
  const fullText = (base.summary + " " + base.headline + " " + scopedText).substring(0, 8000);

  // Extract email & phone number when present in the main profile / open modal.
  extractContactInfo(base, source);

  if (base.notice_period === null) {
    const npMatch = fullText.match(/(?:notice\s*period|np|joining\s*time)[:\s]*(\d+)\s*(days?|months?)/i);
    const immMatch = fullText.match(/(immediate\s*joiner|open\s*to\s*join\s*immediately)/i);
    if (immMatch) {
      base.notice_period = 0;
    } else if (npMatch) {
      let days = parseInt(npMatch[1], 10);
      if (npMatch[2].toLowerCase().startsWith("month")) {
        days = days * 30;
      }
      base.notice_period = days;
    }
  }

  if (base.current_salary === null) {
    const ctcMatch = fullText.match(/(?:current\s*ctc|current\s*salary)[:\s]*([\d\.]+)\s*(lpa|lakhs?|lac)/i);
    if (ctcMatch) {
      base.current_salary = parseFloat(ctcMatch[1]);
    }
  }

  if (base.expected_salary === null) {
    const expCtcMatch = fullText.match(/(?:expected\s*ctc|expected\s*salary)[:\s]*([\d\.]+)\s*(lpa|lakhs?|lac)/i);
    if (expCtcMatch) {
      base.expected_salary = parseFloat(expCtcMatch[1]);
    }
  }

  // Calculate total experience if not explicitly found
  if (!base.total_experience && base.experience.length > 0) {
    const calculatedExp = calculateTotalExperienceYears(base.experience);
    if (calculatedExp > 0) {
      base.total_experience = calculatedExp;
    }
  }

  // Fallback cleanup if name missing
  if (!base.name && typeof document !== "undefined") {
    const pageTitle = document.title || "";
    if (pageTitle.includes("|")) {
      base.name = pageTitle.split("|")[0].trim();
    } else if (pageTitle.includes("-")) {
      base.name = pageTitle.split("-")[0].trim();
    } else {
      base.name = pageTitle.trim();
    }
    if (base.name.toLowerCase().includes("linkedin") || base.name.toLowerCase().includes("naukri") || base.name.toLowerCase().includes("apna")) {
      base.name = "";
    }
  }

  if (!base.current_designation && base.headline) {
    base.current_designation = base.headline;
  }

  console.log(`[Talent Vault Debug] Current profile URL: "${base.profile_url}" | candidate name: "${base.name}"`);
  console.log(`[Talent Vault Debug] Number of entries extracted and passed to the widget: experience=${base.experience.length}, education=${base.education.length}, skills=${base.skills.length}`);
  console.log(
    `[Talent Vault] extractPageData -> name="${base.name}" source="${base.source}" ` +
    `experience=${base.experience.length} education=${base.education.length} skills=${base.skills.length}`
  );
  console.log("EXTRACTED_NAME:", JSON.stringify(base.name));
  console.log("EXTRACTED_EXPERIENCE:", JSON.stringify(base.experience, null, 2));
  console.log("EXTRACTED_EDUCATION:", JSON.stringify(base.education, null, 2));

  return base;
}

// ---------------------------------------------------------------------------
// Text & Duration Normalization Helpers
// ---------------------------------------------------------------------------
function calculateTotalExperienceYears(experiences) {
  let totalMonths = 0;
  const yearRegex = /\b(19\d\d|20\d\d)\b/g;

  experiences.forEach((exp) => {
    const durStr = exp.duration || exp.dates || "";
    if (!durStr) return;

    // e.g. "4 yrs 10 mos" or "Jan 2018 - Dec 2022"
    const yrMatch = durStr.match(/(\d+)\s*yrs?/i);
    const moMatch = durStr.match(/(\d+)\s*mos?/i);
    if (yrMatch || moMatch) {
      const yrs = yrMatch ? parseInt(yrMatch[1], 10) : 0;
      const mos = moMatch ? parseInt(moMatch[1], 10) : 0;
      totalMonths += (yrs * 12 + mos);
      return;
    }

    const years = durStr.match(yearRegex);
    if (years && years.length >= 1) {
      const startYr = parseInt(years[0], 10);
      let endYr = new Date().getFullYear();
      if (years.length >= 2 && !durStr.toLowerCase().includes("present")) {
        endYr = parseInt(years[1], 10);
      }
      const diff = (endYr - startYr) * 12;
      if (diff > 0) totalMonths += diff;
    }
  });

  return totalMonths > 0 ? parseFloat((totalMonths / 12.0).toFixed(1)) : null;
}

// Helper to extract clean visible text without duplicated accessibility fragments
function getCleanText(node) {
  if (!node) return "";
  const clone = node.cloneNode(true);

  const noiseEls = clone.querySelectorAll('script, style, .visually-hidden:not(:only-child), .sr-only, .inline-show-more-text__button');
  noiseEls.forEach((el) => el.remove());

  const ariaSpans = clone.querySelectorAll('span[aria-hidden="true"]');
  if (ariaSpans.length > 0) {
    const textArr = Array.from(ariaSpans)
      .filter((s) => !s.querySelector('span[aria-hidden="true"]'))
      .map((s) => (s.innerText || s.textContent || "").trim())
      .filter((t) => t.length > 0);
    if (textArr.length > 0) {
      return sanitizeString(textArr.join(" "));
    }
  }

  const rawText = clone.innerText || clone.textContent || "";
  return sanitizeString(rawText);
}

function sanitizeString(str) {
  if (!str) return "";
  let clean = String(str).replace(/[\r\n\t]+/g, " ").replace(/\s+/g, " ").trim();
  const parts = clean.split(" • ");
  if (parts.length === 2 && parts[0] === parts[1]) {
    clean = parts[0];
  }
  return clean;
}

const EMPLOYMENT_TYPE_WORDS = /(full[-\s]?time|part[-\s]?time|contract|freelance|self[-\s]?employed|internship|temporary|permanent|volunteer)/i;
const NOISE_WORDS = /^(more|see\s*more|show\s*more|show\s*all|less|show\s*less|\.\.\.|…|·|•|\||-)$/i;
const FORBIDDEN_WORDS = /^(present|current|full[-\s]?time|part[-\s]?time|contract|internship|freelance|more|see\s*more|not\s*specified|not\s*disclosed)$/i;

function cleanCompanyName(companyStr) {
  if (!companyStr) return "";
  let cleaned = String(companyStr)
    .split(/[·•|]/)[0]
    .replace(EMPLOYMENT_TYPE_WORDS, "")
    .replace(/\b(see\s*more|show\s*more|show\s*all|less|present|current|more)\b/gi, "")
    .replace(/[·•|]/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  if (FORBIDDEN_WORDS.test(cleaned)) return "";
  return cleaned;
}

function normalizeEmploymentType(raw) {
  if (!raw) return "";
  const r = String(raw).toLowerCase().replace(/[-\s]+/g, " ");
  if (r.includes("part")) return "Part-time";
  if (r.includes("contract")) return "Contract";
  if (r.includes("freelance") || r.includes("self employed")) return "Freelance";
  if (r.includes("intern")) return "Internship";
  if (r.includes("temporary")) return "Temporary";
  if (r.includes("volunteer")) return "Volunteer";
  if (r.includes("full") || r.includes("permanent")) return "Full-time";
  return "";
}

function employmentTypeOf(str) {
  const m = String(str || "").match(EMPLOYMENT_TYPE_WORDS);
  return m ? normalizeEmploymentType(m[1]) : "";
}

function normalizePhoneNumber(str) {
  if (!str) return "";
  let clean = String(str).replace(/[\s\-().]/g, "");
  clean = clean.replace(/[^\d+]/g, "");
  return clean;
}

function extractEmailFromText(text) {
  if (!text) return "";
  const match = text.match(/[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/);
  return match ? match[0] : "";
}

function extractPhoneFromText(text) {
  if (!text) return "";
  const labelMatch = text.match(/(?:phone|mobile|contact|tel|call|whatsapp)[\s:.#]*([+\d][\d\s\-().]{6,20}\d)/i);
  if (labelMatch) {
    return normalizePhoneNumber(labelMatch[1]);
  }
  const fallback = text.match(/(?:\+?\d{1,3}[\s\-]?)?(?:\(\d{2,4}\)[\s\-]?)?\d{3,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}/);
  if (fallback) {
    return normalizePhoneNumber(fallback[0]);
  }
  return "";
}

// ---------------------------------------------------------------------------
// Scoped profile extraction helpers (stealth + accuracy).
//
// Every selector here is restricted to the MAIN profile container (or an open
// contact dialog) so that sidebars, "similar profiles", recommendations and
// navigation bars can never contaminate a candidate's data.
// ---------------------------------------------------------------------------
function mainContainer() {
  if (typeof document === "undefined") return null;
  return (
    document.querySelector('main') ||
    document.querySelector('[role="main"]') ||
    document.querySelector('#main') ||
    document.querySelector('.scaffold-layout__main') ||
    document.body
  );
}

function isElementVisible(el) {
  if (!el) return false;
  try {
    if (el.offsetParent === null && el.getClientRects && el.getClientRects().length === 0) return false;
  } catch (e) {}
  return true;
}

function scopedRoot(source) {
  if (typeof document === "undefined") return null;
  if (source === "naukri" || source === "apna") return document.body;
  return mainContainer();
}

function visibleTextExcludingZones(root) {
  if (!root) return "";
  if (typeof document === "undefined") return root.innerText || root.textContent || "";
  try {
    const clone = root.cloneNode(true);
    const excluded = (typeof NAUKRI_EXCLUDED_ZONE === "string")
      ? NAUKRI_EXCLUDED_ZONE
      : 'aside, [class*="sidebar" i], [class*="similar" i], [class*="recommend" i], [class*="right-panel" i], [class*="related" i], [class*="suggestion" i], [class*="people-also" i], [class*="other-candidates" i]';
    clone.querySelectorAll(excluded).forEach((el) => el.remove());
    clone.querySelectorAll('script, style, noscript').forEach((el) => el.remove());
    return (clone.innerText || clone.textContent || "");
  } catch (e) {
    return root.innerText || root.textContent || "";
  }
}

function scopedProfileText(source) {
  const parts = [];

  // Text from any visible modal/dialog (e.g., LinkedIn "Contact info" overlay).
  if (typeof document !== "undefined") {
    document.querySelectorAll('[role="dialog"], .artdeco-modal').forEach((d) => {
      if (isElementVisible(d)) parts.push((d.innerText || d.textContent || ""));
    });
  }

  const root = scopedRoot(source);
  if (root) {
    if (source === "naukri" || source === "apna") {
      parts.push(visibleTextExcludingZones(root));
    } else {
      parts.push(root.innerText || root.textContent || "");
    }
  }
  return parts.join(" ");
}

function extractContactInfo(base, source) {
  if (typeof document === "undefined") return;

  // 1. Visible contact modal (LinkedIn "Contact info" overlay). Scoped strictly
  // to the open dialog, which is the only place LinkedIn exposes raw email/phone.
  document.querySelectorAll('[role="dialog"], .artdeco-modal').forEach((d) => {
    if (!isElementVisible(d)) return;
    if (!base.email) {
      const a = d.querySelector('a[href^="mailto:"]');
      if (a) base.email = (a.getAttribute("href") || "").replace(/^mailto:/i, "").split("?")[0].trim();
    }
    if (!base.phone) {
      const tel = d.querySelector('a[href^="tel:"]');
      if (tel) base.phone = normalizePhoneNumber(tel.getAttribute("href") || "");
    }
    const dText = (d.innerText || d.textContent || "");
    if (!base.email) base.email = extractEmailFromText(dText);
    if (!base.phone) base.phone = extractPhoneFromText(dText);
  });

  // 2. Naukri: the email sits on the profile header and the phone is only
  // rendered after "View phone number" is clicked (handled in prepareNaukriContact).
  // Read both from the header block so sidebars / "similar profiles" can never
  // contaminate the candidate's contact details.
  if (source === "naukri") {
    const headerEl = naukriHeaderElement();
    const headerText = naukriHeaderText();

    if (headerEl) {
      if (!base.email) {
        const mailto = headerEl.querySelector('a[href^="mailto:"]');
        if (mailto) base.email = (mailto.getAttribute("href") || "").replace(/^mailto:/i, "").split("?")[0].trim();
      }
      if (!base.phone) {
        const tel = headerEl.querySelector('a[href^="tel:"]');
        if (tel) base.phone = normalizePhoneNumber(tel.getAttribute("href") || "");
      }
    }
    if (!base.email && headerText) base.email = extractEmailFromText(headerText);
    if (!base.phone && headerText) base.phone = extractPhoneFromText(headerText);

    // Fallback: the revealed value may live in the main candidate container.
    const scope = (typeof naukriMainContainer === "function") ? naukriMainContainer() : null;
    if (scope && scope !== document.body && scope !== document.documentElement) {
      const scopedText = (scope.innerText || scope.textContent || "");
      if (!base.email) base.email = extractEmailFromText(scopedText);
      if (!base.phone) {
        const labeledPhone = scopedText.match(/(?:phone|mobile|contact|tel|call|whatsapp)[\s:.#]*([+\d][\d\s\-().]{6,20}\d)/i);
        if (labeledPhone) base.phone = normalizePhoneNumber(labeledPhone[1]);
      }
    }
    return;
  }

  // 3. mailto/tel links + labeled phone/email text strictly inside the MAIN
  // profile container. We NEVER scan the whole page for email/phone — that is
  // exactly what leaks another candidate's contact details (e.g. a previously
  // viewed profile still present in the DOM, or a "similar profiles" card).
  const scope = scopedRoot(source);
  // Never fall back to document.body: searching the whole page reintroduces
  // cross-candidate contact contamination.
  if (scope && scope !== document.body && scope !== document.documentElement) {
    if (!base.email) {
      const mailto = scope.querySelector('a[href^="mailto:"]');
      if (mailto) base.email = (mailto.getAttribute("href") || "").replace(/^mailto:/i, "").split("?")[0].trim();
    }
    if (!base.phone) {
      const tel = scope.querySelector('a[href^="tel:"]');
      if (tel) base.phone = normalizePhoneNumber(tel.getAttribute("href") || "");
    }

    // After clicking "View phone number"/"View email", LinkedIn reveals the value
    // as plain text (often without a mailto:/tel: link). Read it from labeled
    // text inside the main container only. We use the LABELED phone regex
    // (phone/mobile/contact/tel) so unrelated numbers (years, CTC) never match.
    const scopedText = (scope.innerText || scope.textContent || "");
    if (!base.email) base.email = extractEmailFromText(scopedText);
    if (!base.phone) {
      const labeledPhone = scopedText.match(/(?:phone|mobile|contact|tel|call|whatsapp)[\s:.#]*([+\d][\d\s\-().]{6,20}\d)/i);
      if (labeledPhone) base.phone = normalizePhoneNumber(labeledPhone[1]);
    }
  }
}

// Locate the Naukri header block (the container holding the candidate name and
// their contact details). Used only for email/phone extraction.
function naukriHeaderElement() {
  if (typeof document === "undefined") return null;
  const nameHit = findNaukriNameElement(document);
  if (!nameHit || !nameHit.el) return null;
  let node = nameHit.el;
  while (node && node !== document.body && node !== document.documentElement) {
    const txt = (node.textContent || "").toLowerCase();
    if (txt.includes("@") && (node.textContent || "").length < 4000) return node;
    if (node.querySelector && node.querySelector('a[href^="mailto:"]')) return node;
    node = node.parentElement;
  }
  if (nameHit.el.closest) {
    return nameHit.el.closest('section, [class*="card"], [class*="header"], [class*="profile"], [class*="detail"]') || nameHit.el.parentElement;
  }
  return nameHit.el.parentElement;
}

function naukriHeaderText() {
  const el = naukriHeaderElement();
  if (!el) return "";
  return (el.innerText || el.textContent || "");
}

// Return the first element matching any selector that lives inside <main>.
// Prevents a sidebar / recommendation card from being mistaken for the profile.
function firstInMain(selectors) {
  if (typeof document === "undefined") return null;
  const main = mainContainer();
  for (const sel of selectors) {
    let els;
    try {
      els = document.querySelectorAll(sel);
    } catch (e) {
      continue;
    }
    for (const el of els) {
      if (!el) continue;
      if (main && main !== document.body && !main.contains(el)) continue;
      const txt = getCleanText(el);
      if (txt) return { el, txt };
    }
  }
  return null;
}

// All candidate section/card containers within the main profile only.
function mainSections() {
  if (typeof document === "undefined") return [];
  const main = mainContainer();
  const scope = (main && main !== document.body) ? main : document;
  return scope.querySelectorAll('section, .artdeco-card, [data-view-name*="profile-card"], .pv-profile-card');
}

const MONTH_NAMES = {
  jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
  jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12",
  january: "01", february: "02", march: "03", april: "04", may: "05", june: "06",
  july: "07", august: "08", september: "09", october: "10", november: "11", december: "12"
};

function parseSingleDate(raw) {
  if (!raw) return "";
  const s = String(raw).trim();
  const mYr = s.match(/([A-Za-z]+)\.?\s+(\d{4})/);
  if (mYr) {
    const mm = MONTH_NAMES[mYr[1].toLowerCase()];
    if (mm) return `${mYr[2]}-${mm}-01`;
  }
  const yr = s.match(/\b(19\d\d|20\d\d)\b/);
  if (yr) return `${yr[1]}-01-01`;
  return "";
}

function parseDateDetails(durStr) {
  const result = {
    start_date: "",
    end_date: "",
    is_current: false,
    duration: String(durStr || "").trim(),
  };
  if (!durStr) return result;

  const clean = String(durStr).trim().replace(/–|—/g, "-");
  if (/present|current/i.test(clean)) {
    result.is_current = true;
    result.end_date = "Present";
  }

  const parts = clean.split("-").map((p) => p.trim());
  if (parts.length >= 1) {
    const sDate = parseSingleDate(parts[0]);
    if (sDate) result.start_date = sDate;
  }
  if (parts.length >= 2) {
    const endRaw = parts[1].split(/[·•|]/)[0].trim();
    if (/present|current/i.test(endRaw)) {
      result.is_current = true;
      result.end_date = "Present";
    } else {
      const eDate = parseSingleDate(endRaw);
      if (eDate) result.end_date = eDate;
    }
  } else if (!result.start_date) {
    const yr = clean.match(/\b(19\d\d|20\d\d)\b/);
    if (yr) result.end_date = yr[1];
  }
  return result;
}

function headingText(el) {
  if (!el) return "";
  return (el.innerText || el.textContent || "").toLowerCase();
}

function headingMatches(el, keywords) {
  const txt = headingText(el);
  return keywords.some((kw) => txt.includes(kw));
}

// Robust section finder by ID or <section> heading, scoped to the main profile.
function findSection(idAnchor, headingKeywords) {
  if (idAnchor && typeof document !== "undefined") {
    const el = document.getElementById(idAnchor);
    if (el) {
      const card = (el.closest && (el.closest('section') || el.closest('.artdeco-card') || el.closest('[data-view-name*="profile-card"]'))) || el;
      const main = mainContainer();
      if (main && main !== document.body && !main.contains(card)) return el;
      return card;
    }
  }

  if (typeof document === "undefined") return null;
  const main = mainContainer();
  const scope = (main && main !== document.body) ? main : document;
  const sections = scope.querySelectorAll('section, .artdeco-card');
  for (const sec of sections) {
    const heading = sec.querySelector('h1, h2, h3, h4, h5, h6, [role="heading"], .pvs-header__title, .title');
    if (heading && headingMatches(heading, headingKeywords)) return sec;
  }

  return null;
}

function elementChildren(parent) {
  if (!parent || !parent.children) return [];
  const out = [];
  for (let i = 0; i < parent.children.length; i++) {
    out.push(parent.children[i]);
  }
  return out;
}

function textContentLines(node) {
  if (!node) return [];
  // Prefer innerText (real browsers preserve block-level line breaks); jsdom
  // has no innerText so we walk leaf blocks instead so div-based entries still
  // yield one line per field.
  const inner = (typeof node.innerText === "string" && node.innerText.trim()) ? node.innerText : "";
  if (inner) {
    return inner
      .split(/\r?\n/)
      .map((l) => sanitizeString(l))
      .filter((l) => l.length > 0 && !NOISE_WORDS.test(l));
  }
  const out = [];
  const walk = (el) => {
    if (!el || !el.children) return;
    const kids = Array.from(el.children);
    if (!kids.length) {
      const t = sanitizeString(el.textContent || "");
      if (t && !NOISE_WORDS.test(t) && out.indexOf(t) === -1) out.push(t);
      return;
    }
    kids.forEach((c) => walk(c));
  };
  walk(node);
  return out;
}

// ---------------------------------------------------------------------------
// Header & Entity Extraction Engine
// ---------------------------------------------------------------------------
function findDescriptionElement(node) {
  if (!node) return null;
  // Dedicated description container used across modern LinkedIn
  const desc = node.querySelector(
    '.pv-shared-text-with-see-more, .pvs-list__outer-container .inline-show-more-text, .pvs-entity__sub-components .inline-show-more-text, .show-more-less-text'
  );
  if (desc) return desc;

  // If there's an inline-show-more-text that is genuinely a description paragraph
  // (outside the header column and not part of title/company/degree spans)
  const headerCol = node.querySelector(
    '.display-flex.flex-column, .pvs-entity__summary-info, .pvs-entity > div:first-child, .col'
  );
  const candidates = node.querySelectorAll('.inline-show-more-text');
  for (const c of candidates) {
    if (headerCol && headerCol.contains(c)) continue;
    if (c.closest && (c.closest('.t-bold') || c.closest('.t-14') || c.closest('.t-normal') || c.closest('a[href*="/company/"]') || c.closest('a[href*="/school/"]'))) continue;
    const txt = getCleanText(c);
    if (!txt || /^skills?:/i.test(txt)) continue;
    if (c.querySelector('button') || txt.length > 15) return c;
  }
  return null;
}

function collectHeaderLines(node) {
  if (!node) return [];
  const descEl = findDescriptionElement(node);
  const subLists = node.querySelectorAll('ul, ol, .pvs-list__outer-container');

  const lines = [];
  const push = (v) => {
    const t = sanitizeString(v);
    if (t && lines.indexOf(t) === -1) lines.push(t);
  };

  const isExcluded = (el) => {
    if (descEl && (descEl === el || descEl.contains(el))) return true;
    for (const sl of subLists) {
      if (sl === el || sl.contains(el)) return true;
    }
    return false;
  };

  // Strategy 1: leaf aria-hidden spans
  const ariaSpans = node.querySelectorAll('span[aria-hidden="true"]');
  ariaSpans.forEach((el) => {
    if (isExcluded(el)) return;
    if (el.querySelector && el.querySelector('span[aria-hidden="true"]')) return;
    push(getCleanText(el));
  });
  if (lines.length) return lines;

  // Strategy 2: leaf spans of any class, skipping screen-reader-only helpers
  const spans = node.querySelectorAll('span');
  spans.forEach((el) => {
    if (isExcluded(el)) return;
    const cls = (el.className && el.className.toString) ? el.className.toString() : (el.className || "");
    if (/visually-hidden|sr-only/i.test(cls)) return;
    if (el.querySelector && el.querySelector('span')) return;
    push(getCleanText(el));
  });
  if (lines.length) return lines;

  // Strategy 3: rendered text lines minus description and SR helpers
  const clone = node.cloneNode(true);
  clone.querySelectorAll('.visually-hidden, .sr-only, script, style, ul, ol, .pvs-list__outer-container').forEach((el) => el.remove());
  if (descEl) {
    clone.querySelectorAll('.pv-shared-text-with-see-more, .show-more-less-text').forEach((el) => el.remove());
  }
  return textContentLines(clone);
}

// Heuristic date/duration detection. Handles ranges, fragments, and single years.
function isDateFragment(str) {
  if (!str) return false;
  const s = String(str).trim();
  if (!s) return false;
  if (/^(present|current)$/i.test(s)) return true;
  if (/^\d+\s*(yrs?|years?|mos?|months?)/i.test(s)) return true; // "4 yrs 10 mos"
  if (/^(19|20)\d{2}$/.test(s)) return true; // "2016"
  if (/^[A-Za-z]{3,9}\.?\s+(19|20)\d{2}$/i.test(s)) return true; // "Jan 2022"
  if (/\b(19|20)\d{2}\b/.test(s) && /[-–—]/i.test(s)) return true; // "2018 - 2022"
  if (/present|current/i.test(s) && /\b(19|20)\d{2}\b/.test(s)) return true; // "Mar 2018 - Present"
  return false;
}

// Split raw lines into date/duration fragments, employment type, and remaining text.
function splitLines(lines) {
  const nonDate = [];
  const dateFragments = [];
  let detectedEmpType = "";

  (lines || []).forEach((line) => {
    const s = sanitizeString(line);
    if (!s || NOISE_WORDS.test(s)) return;
    if (/^skills?:/i.test(s)) return; // skip skills text

    if (isDateFragment(s)) {
      dateFragments.push(s);
      return;
    }

    if (EMPLOYMENT_TYPE_WORDS.test(s)) {
      if (!detectedEmpType) {
        detectedEmpType = employmentTypeOf(s);
      }
      const stripped = s.replace(EMPLOYMENT_TYPE_WORDS, "").replace(/[·•|]/g, "").trim();
      if (stripped && !isDateFragment(stripped) && !NOISE_WORDS.test(stripped) && !FORBIDDEN_WORDS.test(stripped)) {
        nonDate.push(stripped);
      }
      return;
    }

    if (!FORBIDDEN_WORDS.test(s)) {
      nonDate.push(s);
    }
  });

  return { nonDate, dateFragments, detectedEmpType };
}

// Rejoin split date fragments into one readable duration string
function mergeDateFragments(fragments) {
  if (!fragments || !fragments.length) return "";
  let out = fragments[0];
  for (let i = 1; i < fragments.length; i++) {
    const f = fragments[i];
    if (/yrs?|years?|mos?|months?/i.test(f)) {
      out += " · " + f;
    } else if (/[-–—]\s*$/.test(out)) {
      out = out.replace(/[-–—]\s*$/, "- ") + f;
    } else {
      out += " " + f;
    }
  }
  return out.replace(/\s+/g, " ").trim();
}

function detectEmploymentType(lines) {
  let result = "";
  (lines || []).forEach((line) => {
    if (!result) result = employmentTypeOf(line);
  });
  return result;
}

// Accurately determine if an item is a multi-role container (multiple positions at one company)
// rather than a single role with a nested skills/media list.
function isMultiRole(item) {
  if (!item) return false;
  const nested = item.querySelector('ul, ol');
  if (!nested) return false;
  const subLis = Array.from(nested.children).filter((c) => c.tagName && c.tagName.toLowerCase() === 'li');
  if (!subLis.length) return false;

  let rolesWithDatesAndTitles = 0;
  for (const sub of subLis) {
    const txt = (sub.textContent || "").trim();
    if (/^skills?:/i.test(txt)) continue;
    const lines = collectHeaderLines(sub);
    const { dateFragments, nonDate } = splitLines(lines);
    if (dateFragments.length > 0 && nonDate.length > 0) {
      rolesWithDatesAndTitles++;
    }
  }
  return rolesWithDatesAndTitles >= 1;
}

function nestedListOf(item) {
  if (!item) return null;
  if (!isMultiRole(item)) return null;
  return item.querySelector('ul, ol');
}

// Collect the top-level entry containers of a profile section
function entryContainers(section) {
  if (!section) return [];

  // Preferred: top-level <li> across all lists in the section
  const lis = [];
  section.querySelectorAll('li').forEach((li) => {
    let p = li.parentElement;
    let nested = false;
    while (p && p !== section) {
      if (p.tagName && p.tagName.toLowerCase() === 'li') {
        nested = true;
        break;
      }
      p = p.parentElement;
    }
    if (!nested) lis.push(li);
  });
  if (lis.length) return lis;

  // Fallback: div-based entity wrappers
  const out = [];
  section
    .querySelectorAll('.pvs-entity, .artdeco-list__item, [data-view-name="profile-component-entity"]')
    .forEach((e) => {
      let p = e.parentElement;
      let nested = false;
      while (p && p !== section) {
        if (p.classList && (p.classList.contains('pvs-entity') || p.classList.contains('artdeco-list__item'))) {
          nested = true;
          break;
        }
        p = p.parentElement;
      }
      if (!nested && out.indexOf(e) === -1) out.push(e);
    });
  return out;
}

// Read the company name from the header of a multi-role group
function extractGroupCompany(item) {
  const bold = item.querySelector('.t-bold, strong, b');
  const boldText = getCleanText(bold);
  if (boldText) return cleanCompanyName(boldText);

  const nested = item.querySelector('ul, ol');
  const spans = item.querySelectorAll('span[aria-hidden="true"]');
  for (const s of spans) {
    if (nested && nested.contains(s)) continue;
    const txt = getCleanText(s);
    if (txt) {
      const cleaned = cleanCompanyName(txt);
      if (cleaned) return cleaned;
    }
  }
  return "";
}

// Build a structured experience entry from an entity node.
function buildExperienceEntry(node, companyOverride) {
  if (!node) return null;
  const lines = collectHeaderLines(node);
  if (!lines.length) return null;

  const { nonDate, dateFragments, detectedEmpType } = splitLines(lines);
  const duration = mergeDateFragments(dateFragments);
  const employment_type = detectedEmpType || detectEmploymentType(lines);

  let designation = "";
  let company = "";
  let location = "";

  if (companyOverride) {
    company = companyOverride;
    designation = nonDate.shift() || "";
    location = nonDate.filter(Boolean).join(", ");
  } else {
    designation = nonDate.shift() || "";
    company = cleanCompanyName(nonDate.shift() || "");
    location = nonDate.filter(Boolean).join(", ");
  }

  if (FORBIDDEN_WORDS.test(designation)) designation = "";
  if (FORBIDDEN_WORDS.test(company)) company = "";

  if (!designation && !company) return null;

  const descEl = findDescriptionElement(node);
  const description = getCleanText(descEl);
  const dateDetails = parseDateDetails(duration);

  return {
    company_name: company,
    company: company,
    designation: designation,
    title: designation,
    employment_type: employment_type,
    duration: duration,
    dates: duration,
    start_date: dateDetails.start_date,
    end_date: dateDetails.end_date,
    is_current: dateDetails.is_current,
    location: location,
    description: description,
  };
}

function buildEducationEntry(node) {
  if (!node) return null;
  const lines = collectHeaderLines(node);
  if (!lines.length) return null;

  const { nonDate, dateFragments } = splitLines(lines);

  let institution = nonDate.shift() || "";
  let degree = "";
  let field = "";
  const dates = mergeDateFragments(dateFragments);

  if (nonDate.length) degree = nonDate.shift();
  if (nonDate.length && !field) field = nonDate.join(", ");

  if (degree && degree.includes(",")) {
    const parts = degree.split(",");
    degree = parts[0].trim();
    field = parts.slice(1).join(",").trim() || field;
  }

  if (FORBIDDEN_WORDS.test(institution)) institution = "";
  if (FORBIDDEN_WORDS.test(degree)) degree = "";

  if (!institution && !degree) return null;

  const dateDetails = parseDateDetails(dates);

  return {
    institution: institution,
    school: institution,
    degree: degree,
    field_of_study: field || null,
    field: field || null,
    dates: dates,
    duration: dates,
    start_date: dateDetails.start_date,
    end_date: dateDetails.end_date,
  };
}

function buildProjectEntry(node) {
  if (!node) return null;
  const descEl = findDescriptionElement(node);
  const desc = getCleanText(descEl);
  const lines = collectHeaderLines(node);
  if (!lines.length && !desc) return null;

  const { nonDate, dateFragments } = splitLines(lines);
  const title = nonDate.shift() || "";
  let role = "";
  if (nonDate.length) {
    const candidate = nonDate.join(", ");
    if (!candidate.toLowerCase().includes("see project") && !candidate.toLowerCase().includes("show project")) {
      role = candidate;
    }
  }
  const dates = mergeDateFragments(dateFragments);
  const dateDetails = parseDateDetails(dates);

  const linkEl = node.querySelector('a[href^="http"], a[href^="https"]');
  let link = linkEl ? linkEl.getAttribute("href") || "" : "";
  if (link && link.includes("linkedin.com")) link = "";

  if (!title) return null;

  return {
    title: title,
    name: title,
    role: role,
    dates: dates,
    duration: dates,
    start_date: dateDetails.start_date,
    end_date: dateDetails.end_date,
    description: desc,
    link: link,
  };
}

function buildCertificationEntry(node) {
  if (!node) return null;
  const lines = collectHeaderLines(node);
  if (!lines.length) return null;

  const { nonDate, dateFragments } = splitLines(lines);
  const name = nonDate.shift() || "";
  let issuer = "";
  if (nonDate.length) issuer = nonDate.shift() || "";

  let issueDate = "";
  for (const line of lines) {
    const match = line.match(/(?:issued|issue\s*date)[:\s]*([A-Za-z]+\s*\d{4}|\d{4})/i);
    if (match) {
      issueDate = match[1];
      break;
    }
  }
  if (!issueDate && dateFragments.length) {
    issueDate = dateFragments[0];
  }

  if (!name) return null;

  const dateDetails = parseDateDetails(issueDate);

  return {
    name: name,
    title: name,
    issuing_organization: issuer,
    issuer: issuer,
    issue_date: dateDetails.start_date || (dateDetails.end_date !== "Present" ? dateDetails.end_date : "") || issueDate,
    date: issueDate,
  };
}

// --- Debug helpers ---
function describeElement(el) {
  if (!el) return "null";
  try {
    const tag = (el.tagName || "").toLowerCase();
    const id = el.id ? "#" + el.id : "";
    const cls = (el.className && el.className.toString) ? "." + String(el.className).trim().replace(/\s+/g, ".") : "";
    const txt = ((el.innerText || el.textContent || "") || "").trim().slice(0, 40);
    return `<${tag}${id}${cls}> "${txt}"`;
  } catch (e) {
    return "unknown";
  }
}

const ENTRY_SELECTOR = 'li, .pvs-entity, .artdeco-list__item, [data-view-name="profile-component-entity"]';
const SECTION_TITLES = [
  'experience', 'work experience', 'employment',
  'education', 'skills', 'about', 'summary', 'overview',
  'activity', 'recommendations', 'interests', 'languages',
  'certifications', 'licenses', 'projects', 'honors', 'awards',
  'accomplishments', 'contact info', 'people also viewed', 'more insights',
];

function findSectionTitleElement(keywords) {
  if (typeof document === "undefined") return null;
  const main = mainContainer();
  const all = (main && main !== document.body ? main : document).querySelectorAll('*');
  const matches = [];
  for (let i = 0; i < all.length; i++) {
    const el = all[i];
    const text = (el.textContent || "").trim();
    if (!text || text.length > 40) continue;
    const low = text.toLowerCase();
    if (keywords.some((k) => low === k)) {
      let descendants = 0;
      try { descendants = el.querySelectorAll('*').length; } catch (e) {}
      matches.push({ el, descendants });
    }
  }
  if (!matches.length) return null;
  matches.sort((a, b) => a.descendants - b.descendants);
  return matches[0].el;
}

function resolveContainer(titleEl) {
  if (!titleEl) return null;
  const sec = titleEl.closest ? (titleEl.closest('section') || titleEl.closest('.artdeco-card') || titleEl.closest('[data-view-name*="profile-card"]')) : null;
  if (sec) return sec;

  let node = titleEl.parentElement;
  while (node && node !== document.body && node !== document.documentElement) {
    if (node.querySelector && node.querySelector(ENTRY_SELECTOR)) {
      return node;
    }
    node = node.parentElement;
  }
  return (titleEl.closest && titleEl.closest('main')) || null;
}

function topLevelNodes(nodes) {
  const out = [];
  nodes.forEach((n) => {
    let ancestorInSet = false;
    let p = n.parentElement;
    while (p) {
      if (nodes.indexOf(p) !== -1) {
        ancestorInSet = true;
        break;
      }
      p = p.parentElement;
    }
    if (!ancestorInSet && out.indexOf(n) === -1) out.push(n);
  });
  return out;
}

function findNextSectionTitleAfter(el) {
  if (!el || !el.compareDocumentPosition || typeof document === "undefined") return null;
  const headingEl = (el.closest && el.closest('h1, h2, h3, h4, [role="heading"], .pvs-header__title, .title')) || el;
  const main = mainContainer();
  const all = (main && main !== document.body ? main : document).querySelectorAll('*');
  for (let i = 0; i < all.length; i++) {
    const n = all[i];
    if (n === el || headingEl.contains(n)) continue;
    const text = (n.textContent || "").trim().toLowerCase();
    if (!text || text.length > 40) continue;
    if (SECTION_TITLES.indexOf(text) !== -1) {
      if (headingEl.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) {
        return n;
      }
    }
  }
  return null;
}

function regionEntryNodes(titleEl) {
  if (!titleEl || !titleEl.compareDocumentPosition || typeof document === "undefined") return [];
  const next = findNextSectionTitleAfter(titleEl);
  const main = mainContainer();
  const candidates = (main && main !== document.body ? main : document).querySelectorAll(ENTRY_SELECTOR);
  const nodes = [];
  candidates.forEach((c) => {
    if (!(titleEl.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
    if (next && (next.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
    nodes.push(c);
  });
  return topLevelNodes(nodes);
}

function collectSectionEntries(keywords) {
  const titleEl = findSectionTitleElement(keywords);
  if (!titleEl) return { titleEl: null, container: null, items: [] };

  let items = [];
  let container = null;

  // 1. If inside a card/section container
  const sec = titleEl.closest ? (titleEl.closest('section') || titleEl.closest('.artdeco-card') || titleEl.closest('[data-view-name*="profile-card"]')) : null;
  if (sec) {
    container = sec;
    items = entryContainers(sec);
  }

  // 2. Region scoping (for sibling layouts without dedicated section wrappers)
  if (!items.length) {
    items = regionEntryNodes(titleEl);
  }

  // 3. Fallback to container
  if (!items.length) {
    container = resolveContainer(titleEl);
    if (container) items = entryContainers(container);
  }

  return { titleEl, container, items };
}

// ---------------------------------------------------------------------------
// Source Adapters
// ---------------------------------------------------------------------------

function findLinkedInExperienceContainer() {
  if (typeof document === "undefined") return null;

  // 1. Stable data-section attribute (most reliable on modern LinkedIn).
  const dataSec = document.querySelector('section[data-section="experience"], div[data-section="experience"]');
  if (dataSec) return dataSec;

  // 2. By anchor ID
  const anchor = document.getElementById("experience") ||
                 document.querySelector('a[name="experience" i], [id="experience"]');
  if (anchor) {
    const card = anchor.closest('section, .artdeco-card, [data-view-name*="profile-card"], .pv-profile-card') ||
                 anchor.parentElement;
    if (card && card !== document.body) return card;
  }

  // 3. By card container containing an Experience heading
  const candidates = mainSections();
  for (const card of candidates) {
    const headings = card.querySelectorAll('h1, h2, h3, h4, [role="heading"], .pvs-header__title, .title');
    for (const h of headings) {
      const txt = getCleanText(h).toLowerCase();
      if (/^(work\s+)?experience$/i.test(txt) || txt === "experience") {
        return card;
      }
    }
  }

  // 4. Detail page support (/details/experience/)
  if (typeof window !== "undefined" && window.location && window.location.href.includes("/details/experience")) {
    const mainList = document.querySelector('main .pvs-list, .scaffold-layout__main .pvs-list, main');
    if (mainList) return mainList;
  }

  // 5. Fallback to generic section collector
  const fallback = collectSectionEntries(['experience', 'work experience', 'employment']);
  if (fallback.container) return fallback.container;

  return null;
}

function findLinkedInEducationContainer() {
  if (typeof document === "undefined") return null;

  // 1. Stable data-section attribute (most reliable on modern LinkedIn).
  const dataSec = document.querySelector('section[data-section="education"], div[data-section="education"]');
  if (dataSec) return dataSec;

  const anchor = document.getElementById("education") ||
                 document.querySelector('a[name="education" i], [id="education"]');
  if (anchor) {
    const card = anchor.closest('section, .artdeco-card, [data-view-name*="profile-card"], .pv-profile-card') ||
                 anchor.parentElement;
    if (card && card !== document.body) return card;
  }

  const candidates = mainSections();
  for (const card of candidates) {
    const headings = card.querySelectorAll('h1, h2, h3, h4, [role="heading"], .pvs-header__title, .title');
    for (const h of headings) {
      const txt = getCleanText(h).toLowerCase();
      if (/^(education|academics?|qualifications?)$/i.test(txt) || txt === "education") {
        return card;
      }
    }
  }

  // Detail page support (/details/education/)
  if (typeof window !== "undefined" && window.location && window.location.href.includes("/details/education")) {
    const mainList = document.querySelector('main .pvs-list, .scaffold-layout__main .pvs-list, main');
    if (mainList) return mainList;
  }

  const fallback = collectSectionEntries(['education', 'academic', 'qualification']);
  if (fallback.container) return fallback.container;

  return null;
}

function findLinkedInProjectsContainer() {
  if (typeof document === "undefined") return null;

  const anchor = document.getElementById("projects") ||
                 document.querySelector('a[name="projects" i], [id="projects"]');
  if (anchor) {
    const card = anchor.closest('section, .artdeco-card, [data-view-name*="profile-card"], .pv-profile-card') ||
                 anchor.parentElement;
    if (card && card !== document.body) return card;
  }

  const candidates = mainSections();
  for (const card of candidates) {
    const headings = card.querySelectorAll('h1, h2, h3, h4, [role="heading"], .pvs-header__title, .title');
    for (const h of headings) {
      const txt = getCleanText(h).toLowerCase();
      if (/^projects$/i.test(txt)) return card;
    }
  }

  const fallback = collectSectionEntries(['projects']);
  if (fallback.container) return fallback.container;

  return null;
}

function findLinkedInCertificationsContainer() {
  if (typeof document === "undefined") return null;

  const anchor = document.getElementById("licenses_and_certifications") ||
                 document.getElementById("certifications") ||
                 document.querySelector('a[name="licenses_and_certifications" i], a[name="certifications" i]');
  if (anchor) {
    const card = anchor.closest('section, .artdeco-card, [data-view-name*="profile-card"], .pv-profile-card') ||
                 anchor.parentElement;
    if (card && card !== document.body) return card;
  }

  const candidates = mainSections();
  for (const card of candidates) {
    const headings = card.querySelectorAll('h1, h2, h3, h4, [role="heading"], .pvs-header__title, .title');
    for (const h of headings) {
      const txt = getCleanText(h).toLowerCase();
      if (/^(licenses\s*(?:&|and)\s*certifications|certifications)$/i.test(txt)) return card;
    }
  }

  const fallback = collectSectionEntries(['licenses & certifications', 'certifications', 'licenses and certifications']);
  if (fallback.container) return fallback.container;

  return null;
}

// ---------------------------------------------------------------------------
// Diagnostic probes + DOM-agnostic LinkedIn fallback.
//
// LinkedIn's section/entry markup changes frequently and is not reliably
// detected by headings or ids on every layout. These helpers (a) dump the real
// DOM to the console so the actual structure can be inspected, and (b) recover
// Experience/Education entries through LinkedIn-stable /company/ and /school/
// links when the heading-based path returns nothing. No secrets are logged.
// ---------------------------------------------------------------------------
function outerHTMLShort(el, max) {
  if (!el) return "";
  try {
    const html = el.outerHTML || el.innerHTML || "";
    return html.length > max ? html.slice(0, max) + "…" : html;
  } catch (e) {
    return "";
  }
}

function dumpLinkedInDiagnostics() {
  if (typeof document === "undefined") return;
  try {
    console.log(`[Talent Vault Diagnostics] build=${TV_BUILD} url=${(window.location && window.location.href) || ""}`);
    ["experience", "education"].forEach((keyword) => {
      const matches = [];
      document.querySelectorAll('*').forEach((el) => {
        const t = (el.textContent || "").trim().toLowerCase();
        if (t === keyword && (!el.children || el.children.length === 0)) matches.push(el);
      });
      if (!matches.length) {
        console.log(`[Talent Vault Diagnostics] "${keyword}" heading: NONE (no exact-match leaf element)`);
        return;
      }
      matches.slice(0, 4).forEach((el, i) => {
        console.log(`[Talent Vault Diagnostics] "${keyword}" leaf #${i}: tag=<${(el.tagName || "").toLowerCase()}> cls="${el.className || ""}" id="${el.id || ""}"`);
        let p = el.parentElement;
        for (let up = 0; p && up < 4; up++, p = p.parentElement) {
          console.log(`[Talent Vault Diagnostics]   parent[${up}] <${(p.tagName || "").toLowerCase()}> cls="${p.className || ""}" id="${p.id || ""}": ${outerHTMLShort(p, 280)}`);
        }
      });
    });
    console.log(`[Talent Vault Diagnostics] companyLinks=${document.querySelectorAll('a[href*="/company/"]').length} schoolLinks=${document.querySelectorAll('a[href*="/school/"], a[href*="/edu/"]').length}`);
    console.log(`[Talent Vault Diagnostics] totalLi=${document.querySelectorAll('li').length} pvsEntity=${document.querySelectorAll('.pvs-entity').length} anchorExperience=${!!document.getElementById("experience")} anchorEducation=${!!document.getElementById("education")}`);
  } catch (e) {
    console.log("[Talent Vault Diagnostics] error", e && e.message);
  }
}

function outermostEntryLi(node) {
  if (!node || typeof document === "undefined") return null;
  let cur = node;
  let li = null;
  while (cur && cur !== document.body && cur !== document.documentElement) {
    if (cur.tagName && cur.tagName.toLowerCase() === 'li') li = cur;
    cur = cur.parentElement;
  }
  return li;
}

function hasDateSignal(node) {
  if (!node) return false;
  const txt = (node.innerText || node.textContent || "") || "";
  return /\b(19|20)\d{2}\b/.test(txt) || /present|current/i.test(txt) || /\d+\s*(yrs?|mos?|years?|months?)/i.test(txt);
}

function extractLinkedInExperienceFallback() {
  if (typeof document === "undefined") return [];
  const out = [];
  const seen = new Set();
  document.querySelectorAll('a[href*="/company/"]').forEach((a) => {
    const li = outermostEntryLi(a);
    if (!li || seen.has(li)) return;
    seen.add(li);
    if (!hasDateSignal(li)) return;
    if (isMultiRole(li)) {
      const company = extractGroupCompany(li) || cleanCompanyName(getCleanText(a));
      const nested = li.querySelector('ul, ol');
      if (nested) {
        elementChildren(nested)
          .filter((el) => el.tagName && el.tagName.toLowerCase() === 'li' && !/^skills?:/i.test((el.textContent || "").trim()))
          .forEach((sub) => {
            const entry = buildExperienceEntry(sub, company);
            if (entry) out.push(entry);
          });
      }
    } else {
      const entry = buildExperienceEntry(li, null);
      if (entry) out.push(entry);
    }
  });
  return out;
}

function extractLinkedInEducationFallback() {
  if (typeof document === "undefined") return [];
  const out = [];
  const seen = new Set();
  document.querySelectorAll('a[href*="/school/"], a[href*="/edu/"]').forEach((a) => {
    const li = outermostEntryLi(a);
    if (!li || seen.has(li)) return;
    seen.add(li);
    if (!hasDateSignal(li)) return;
    const entry = buildEducationEntry(li);
    if (entry) out.push(entry);
  });
  return out;
}

const LinkedInAdapter = {
  extract(base) {
    dumpLinkedInDiagnostics();

    // 1. Name — strictly scoped to <main>; never a sidebar / recommendation card.
    const nameHit = firstInMain([
      '[data-view-name="profile-topcard"] h1',
      'h1.text-heading-xlarge',
      '.pv-text-details__left-panel h1',
      '[data-anonymize="person-name"]',
      '.top-card-layout__title',
      'section.pv-top-card h1',
      'main h1',
      'h1'
    ]);
    if (nameHit) {
      const txt = nameHit.txt.replace(/\s+(1st|2nd|3rd|Premium|Member’s name)\b/gi, "").trim();
      if (txt && !txt.toLowerCase().includes("linkedin") && !txt.toLowerCase().includes("sign in") && !txt.toLowerCase().includes("feed")) {
        base.name = txt;
      }
    }

    // 2. Headline / Designation — scoped to <main>.
    const headlineHit = firstInMain([
      '.text-body-medium.break-words',
      '.pv-text-details__left-panel .text-body-medium',
      '[data-generated-suggestion-target]',
      '[data-anonymize="headline"]',
      '.top-card-layout__headline',
      'section.pv-top-card .text-body-medium',
      'div.text-body-medium'
    ]);
    if (headlineHit) {
      const txt = headlineHit.txt;
      if (txt && txt !== base.name && !FORBIDDEN_WORDS.test(txt)) {
        base.headline = txt;
        base.current_designation = txt;
      }
    }

    // 3. Location — scoped to <main>.
    const locationHit = firstInMain([
      'span.text-body-small.inline.t-black--light.break-words',
      '.pv-text-details__left-panel span.text-body-small',
      '.pv-top-card--list-bullet > li',
      '.pb2 .text-body-small',
      '[data-anonymize="location"]',
      '.top-card-layout__first-subtext'
    ]);
    if (locationHit) {
      const txt = locationHit.txt;
      if (txt && !txt.toLowerCase().includes("contact info") && !txt.toLowerCase().includes("connections") && !txt.toLowerCase().includes("followers")) {
        base.location = txt;
      }
    }

    // 4. Current Company (Top Card Header or Right Panel)
    const rightPanelButtons = document.querySelectorAll(
      'ul.pv-text-details__right-panel li button, .pv-text-details__right-panel button, ul.pv-text-details__right-panel li a'
    );
    for (const btn of rightPanelButtons) {
      const aria = (btn.getAttribute("aria-label") || "").toLowerCase();
      const href = (btn.getAttribute("href") || "").toLowerCase();
      if (aria.includes("current company") || aria.includes("company") || href.includes("/company/") || href.includes("#experience")) {
        const txt = cleanCompanyName(getCleanText(btn));
        if (txt && !FORBIDDEN_WORDS.test(txt)) {
          base.current_company = txt;
          break;
        }
      }
    }

    if (!base.current_company) {
      const firstRightItem = document.querySelector('ul.pv-text-details__right-panel li, .pv-text-details__right-panel li');
      if (firstRightItem) {
        const aria = (firstRightItem.querySelector('button, a')?.getAttribute("aria-label") || "").toLowerCase();
        if (!aria.includes("education") && !aria.includes("school")) {
          const txt = cleanCompanyName(getCleanText(firstRightItem));
          if (txt && !FORBIDDEN_WORDS.test(txt)) {
            base.current_company = txt;
          }
        }
      }
    }

    // If still missing, parse from headline (e.g. "Senior Engineer at Google" or "VP @ Acme")
    if (!base.current_company && base.headline) {
      const atMatch = base.headline.match(/(?:^|[\s|•·,-])(?:at|@)\s+([A-Za-z0-9&.\- ]+)/i);
      if (atMatch) {
        const candidateComp = cleanCompanyName(atMatch[1]);
        if (candidateComp && !FORBIDDEN_WORDS.test(candidateComp)) {
          base.current_company = candidateComp;
        }
      }
    }

    // 5. About / Summary
    const aboutSec = findSection('about', ['about', 'summary', 'overview']);
    if (aboutSec) {
      const aboutTextEl = aboutSec.querySelector('.pv-shared-text-with-see-more span[aria-hidden="true"]') ||
                          aboutSec.querySelector('.inline-show-more-text span[aria-hidden="true"]') ||
                          aboutSec.querySelector('.inline-show-more-text') ||
                          aboutSec.querySelector('.pv-shared-text-with-see-more') ||
                          aboutSec.querySelector('.pv-about-section');
      if (aboutTextEl) {
        base.summary = getCleanText(aboutTextEl);
      } else {
        const pArr = Array.from(aboutSec.querySelectorAll('p, span')).map((p) => getCleanText(p)).filter((t) => t.length > 20);
        if (pArr.length > 0) base.summary = pArr[0];
      }
    }

    // 6. Experience (ALL visible entries)
    const expContainer = findLinkedInExperienceContainer();
    const expSectionFound = !!expContainer;
    console.log(`[Talent Vault Debug] Experience section found: ${expSectionFound}`);

    let expItems = [];
    if (expContainer) {
      expItems = entryContainers(expContainer);
      console.log(`[Talent Vault Debug] experience: container=${describeElement(expContainer)} items=${expItems.length}`);
      expItems.forEach((item) => {
        if (isMultiRole(item)) {
          const companyName = extractGroupCompany(item);
          const nestedList = item.querySelector('ul, ol');
          if (nestedList) {
            elementChildren(nestedList)
              .filter((el) => el.tagName && el.tagName.toLowerCase() === 'li' && !/^skills?:/i.test((el.textContent || "").trim()))
              .forEach((subLi) => {
                const entry = buildExperienceEntry(subLi, companyName);
                if (entry) base.experience.push(entry);
              });
          }
        } else {
          const entry = buildExperienceEntry(item, null);
          if (entry) base.experience.push(entry);
        }
      });
    } else {
      const exp = collectSectionEntries(['experience', 'work experience', 'employment']);
      console.log(`[Talent Vault Debug] experience (fallback): title=${describeElement(exp.titleEl)} container=${describeElement(exp.container)} items=${exp.items.length}`);
      exp.items.forEach((item) => {
        if (isMultiRole(item)) {
          const companyName = extractGroupCompany(item);
          const nestedList = item.querySelector('ul, ol');
          if (nestedList) {
            elementChildren(nestedList)
              .filter((el) => el.tagName && el.tagName.toLowerCase() === 'li' && !/^skills?:/i.test((el.textContent || "").trim()))
              .forEach((subLi) => {
                const entry = buildExperienceEntry(subLi, companyName);
                if (entry) base.experience.push(entry);
              });
          }
        } else {
          const entry = buildExperienceEntry(item, null);
          if (entry) base.experience.push(entry);
        }
      });
    }

    if (base.experience.length === 0) {
      const fallbackExp = extractLinkedInExperienceFallback();
      console.log(`[Talent Vault Debug] experience (link fallback): extracted ${fallbackExp.length} entries`);
      base.experience = fallbackExp;
    }

    if (!base.current_company && base.experience.length > 0) {
      base.current_company = base.experience[0].company_name;
    }
    if (!base.headline && base.experience.length > 0) {
      base.headline = base.experience[0].designation;
      base.current_designation = base.experience[0].designation;
    }
    if (!base.location && base.experience.length > 0) {
      base.location = base.experience[0].location;
    }

    // 7. Education (ALL visible entries)
    const eduContainer = findLinkedInEducationContainer();
    const eduSectionFound = !!eduContainer;
    console.log(`[Talent Vault Debug] Education section found: ${eduSectionFound}`);

    let eduItems = [];
    if (eduContainer) {
      eduItems = entryContainers(eduContainer);
      console.log(`[Talent Vault Debug] education: container=${describeElement(eduContainer)} items=${eduItems.length}`);
      eduItems.forEach((item) => {
        const entry = buildEducationEntry(item);
        if (entry) base.education.push(entry);
      });
    } else {
      const edu = collectSectionEntries(['education', 'academic', 'qualification']);
      console.log(`[Talent Vault Debug] education (fallback): title=${describeElement(edu.titleEl)} container=${describeElement(edu.container)} items=${edu.items.length}`);
      edu.items.forEach((item) => {
        const entry = buildEducationEntry(item);
        if (entry) base.education.push(entry);
      });
    }

    if (base.education.length === 0) {
      const fallbackEdu = extractLinkedInEducationFallback();
      console.log(`[Talent Vault Debug] education (link fallback): extracted ${fallbackEdu.length} entries`);
      base.education = fallbackEdu;
    }

    // 8. Projects
    const projContainer = findLinkedInProjectsContainer();
    if (projContainer) {
      const projItems = entryContainers(projContainer);
      projItems.forEach((item) => {
        const entry = buildProjectEntry(item);
        if (entry) base.projects.push(entry);
      });
    }

    // 9. Certifications
    const certContainer = findLinkedInCertificationsContainer();
    if (certContainer) {
      const certItems = entryContainers(certContainer);
      certItems.forEach((item) => {
        const entry = buildCertificationEntry(item);
        if (entry) base.certifications.push(entry);
      });
    }

    // 10. Skills (ALL visible entries)
    const skillsSec = findSection('skills', ['skills', 'competencies', 'endorsement']);
    if (skillsSec) {
      const items = skillsSec.querySelectorAll('li, .skill-chip, [data-view-name*="skill"]');
      items.forEach((item) => {
        const sSpan = item.querySelector('span[aria-hidden="true"]') || item;
        const sName = getCleanText(sSpan);
        if (sName && !sName.toLowerCase().includes("endorse") && !sName.toLowerCase().includes("skill") && sName.length < 60) {
          if (!base.skills.includes(sName)) {
            base.skills.push(sName);
          }
        }
      });
    }

    console.log(`[Talent Vault Debug] result: experienceEntries=${base.experience.length} educationEntries=${base.education.length} projects=${base.projects.length} certs=${base.certifications.length} skills=${base.skills.length}`);
    return base;
  }
};

// ---------------------------------------------------------------------------
// Naukri (Resdex) adapter — scoped to the CURRENT candidate's main profile.
//
// Reuses the same DOM-agnostic entry extraction as LinkedIn (section-title
// discovery + entryContainers + build*Entry) so the two parsers behave
// consistently. It explicitly excludes sidebars / "similar profiles" /
// recommendation panels, derives a canonical profile URL from a stable id, and
// never lets one candidate's data leak into another.
// ---------------------------------------------------------------------------
const NAUKRI_SECTION_KEYWORDS = {
  experience: ['work experience', 'experience', 'employment', 'employment details', 'professional experience', 'employment history', 'work history'],
  education: ['education', 'academic', 'academics', 'qualification', 'educational qualification', 'qualifications', 'academic details'],
  projects: ['projects', 'project details', 'academic projects', 'project'],
  certifications: ['certifications', 'certification', 'licenses & certifications', 'certifications & licenses'],
  skills: ['key skills', 'skills', 'technical skills', 'it skills'],
  personal: ['personal details', 'personal information', 'personal', 'other details', 'additional details', 'other information'],
};

// Personal-detail markers that must NEVER be parsed as work experience /
// education (Naukri's "Personal details" / "Other details" sections contain
// DOB, gender, category, marital status, etc.).
const NAUKRI_PERSONAL_DETAIL_SIGNAL = /(date of birth|\bdob\b|gender|category|marital status|marital|nationality|religion|passport|visa status|personal details|other details|hobbies|languages known)/i;

const NAUKRI_EXCLUDED_ZONE = 'aside, nav, [class*="sidebar" i], [class*="similar" i], [class*="recommend" i], [class*="right-panel" i], [class*="right-pane" i], [class*="left-pane" i], [class*="prp" i], [class*="related" i], [class*="suggestion" i], [class*="people-also" i], [class*="other-candidates" i], [class*="right-rail" i], [class*="rail" i], [class*="widget" i], [class*="preview-card" i], [class*="similar-candidate" i], [class*="recommended-profile" i], [class*="recent-search" i], [class*="recently-viewed" i], [class*="viewed-profile" i]';

// Specific field selectors that identify a REAL Naukri experience entry. A
// block is only treated as experience when it contains one of these fields —
// the parser must never dump a whole container's innerText (that is exactly
// what leaks the "Professional Summary" paragraph and words like "Full" from
// "Full-time" into the Company/Designation fields).
const NAUKRI_EXP_FIELD_SEL = '.company, .company-name, .org, .employer, .employer-name, .designation, .role, .job-title, .exp-title, .exp-org, [class*="company"], [class*="employer"], [class*="designation"], [class*="role"], [class*="title"]';
const NAUKRI_EDU_FIELD_SEL = '.institute, .school-name, .edu-name, [class*="institute"], [class*="college"], [class*="university"], [class*="school"], [class*="edu"], [class*="qualification"], [class*="course"], .degree, [class*="degree"]';

function isNaukriExperienceBlock(el) {
  if (!el) return false;
  try {
    return !!el.querySelector(NAUKRI_EXP_FIELD_SEL);
  } catch (e) {
    return false;
  }
}

function isNaukriSectionBlock(el, fieldSel) {
  if (!el) return false;
  try {
    // Never treat "Personal details" / "Other details" (DOB, gender, category)
    // blocks as structured experience/education entries.
    if (NAUKRI_PERSONAL_DETAIL_SIGNAL.test((el.textContent || "").toLowerCase())) return false;
    if (el.querySelector(fieldSel || NAUKRI_EXP_FIELD_SEL)) return true;
    // Text-based fallback: a structured entry has multiple distinct short lines
    // (e.g. designation, company, duration), unlike a single summary paragraph.
    const lines = textContentLines(el);
    return lines.length >= 2;
  } catch (e) {
    return false;
  }
}

// Pick the field selector that identifies a real entry block for a section so
// div-based entries (not just <li> items) are recognized per section type.
function naukriEntryFieldSelector(keywords) {
  const low = (keywords || []).join(" ").toLowerCase();
  if (/(education|academic|qualification|institute|college|university|school|degree)/.test(low)) return NAUKRI_EDU_FIELD_SEL;
  return NAUKRI_EXP_FIELD_SEL;
}

const ALL_NAUKRI_TITLES = new Set();
Object.keys(NAUKRI_SECTION_KEYWORDS).forEach((k) => NAUKRI_SECTION_KEYWORDS[k].forEach((t) => ALL_NAUKRI_TITLES.add(t)));
const ALL_NAUKRI_TITLES_ARRAY = Array.from(ALL_NAUKRI_TITLES);

function isNaukriExcluded(el) {
  if (!el) return true;
  try {
    if (typeof el.matches === "function" && el.matches(NAUKRI_EXCLUDED_ZONE)) return true;
  } catch (e) {}
  return false;
}

function isNaukriExcludedZone(el) {
  if (!el) return true;
  let node = el;
  while (node && node !== document.body && node !== document.documentElement) {
    if (isNaukriExcluded(node)) return true;
    node = node.parentElement;
  }
  return false;
}

function canonicalNaukriProfileUrl() {
  try {
    const u = new URL(window.location.href);
    const stable = new Set(['sid', 'id', 'profileid', 'profile_id', 'candidateid', 'candidate_id', 'resumeid', 'resume_id']);
    const kept = [];
    u.searchParams.forEach((v, k) => {
      if (stable.has(k.toLowerCase()) && v) kept.push(k + "=" + encodeURIComponent(v));
    });
    const path = u.pathname.replace(/\/+$/, "");
    return u.origin + path + (kept.length ? "?" + kept.join("&") : "");
  } catch (e) {
    return (typeof window !== "undefined" && window.location && window.location.href)
      ? window.location.href.split("?")[0]
      : "";
  }
}

// ---- Main candidate container -------------------------------------------------
// Naukri Resdex renders the candidate in a dedicated panel while a right rail
// shows "similar profiles". We locate that panel first and extract ONLY from it
// so a similar-profile card can never contaminate the candidate's own data.

function findNaukriNameElement(root) {
  if (typeof document === "undefined") return null;
  const scope = root || document;

  const toName = (el) => {
    if (!el) return "";
    if (isNaukriExcludedZone(el)) return "";
    if (isInsideAnchor(el)) return "";
    const txt = getCleanText(el).replace(/\s+\(.+\)$/g, "").trim();
    if (!txt || txt.length < 2 || txt.length >= 80) return "";
    if (/^(resdex|naukri|profile|preview)$/i.test(txt)) return "";
    return txt;
  };

  // 1. Strict: h1 inside <main>/[role=main] — the candidate's own header.
  const mains = scope.querySelectorAll('main, [role="main"]');
  for (const m of mains) {
    for (const h of m.querySelectorAll('h1')) {
      const txt = toName(h);
      if (txt) return { el: h, txt };
    }
  }

  // 2. h1 inside a <section>/<article> (structural profile container). This is
  //    preferred over a page-wide scan so sidebar/recent-search names never win.
  const sections = scope.querySelectorAll('section, article');
  for (const s of sections) {
    for (const h of s.querySelectorAll('h1')) {
      const txt = toName(h);
      if (txt) return { el: h, txt };
    }
  }

  // 3. h1 anywhere (excluding zones/anchors) as a final h1 fallback.
  for (const h of scope.querySelectorAll('h1')) {
    const txt = toName(h);
    if (txt) return { el: h, txt };
  }

  // 4. h2 inside <main>/[role=main] (some Naukri layouts use h2 for the name).
  for (const m of mains) {
    for (const h of m.querySelectorAll('h2')) {
      const txt = toName(h);
      if (txt) return { el: h, txt };
    }
  }

  // 5. Last resort: name-like classes, but ONLY inside <main> — never the whole
  //    document, which is exactly what leaks a sidebar/recent-search name.
  const nameSelectors = ['.name', '.cand-name', '.candidate-name', '.profile-name', '[class*="candidate-name" i]', '[class*="profile-name" i]', '[class*="user-name" i]'];
  for (const m of mains) {
    for (const sel of nameSelectors) {
      let els;
      try { els = m.querySelectorAll(sel); } catch (e) { continue; }
      for (const el of els) {
        const txt = toName(el);
        if (txt) return { el, txt };
      }
    }
  }

  return null;
}

function naukriContainerScore(el) {
  let score = 0;
  try {
    const low = (el.textContent || "").toLowerCase();
    ALL_NAUKRI_TITLES_ARRAY.forEach((t) => { if (low.includes(t)) score += 2; });
    const nameHit = el.querySelector('h1, h2, .name, [class*="name" i]');
    if (nameHit) {
      const n = (nameHit.textContent || "").trim();
      if (n.length >= 2 && n.length < 80 && !isInsideAnchor(nameHit)) score += 3;
    }
    const anchors = el.querySelectorAll('a').length;
    if (anchors > 3) score -= anchors;
    if ((el.textContent || "").length > 400) score += 2;
  } catch (e) {}
  return score;
}

function naukriMainContainer() {
  if (typeof document === "undefined") return null;

  const containerSelectors = [
    '.profile-details', '.candidate-details', '.profile-detail', '.candidate-profile',
    '.profile-container', '.resume-details', '.resume-detail', '.resume-body',
    '.main-profile', '.candidate-card',
    '[class*="profile-details" i]', '[class*="candidate-details" i]',
    '[class*="profile-detail" i]', '[class*="candidate-profile" i]',
    '[class*="profile-container" i]', '[class*="candidate-card" i]',
  ];

  let best = null;
  let bestScore = -1;

  for (const sel of containerSelectors) {
    let els;
    try { els = document.querySelectorAll(sel); } catch (e) { continue; }
    els.forEach((el) => {
      if (!el || el === document.body || el === document.documentElement) return;
      if (isNaukriExcludedZone(el)) return;
      const score = naukriContainerScore(el);
      if (score > bestScore) { bestScore = score; best = el; }
    });
  }
  if (best && bestScore > 0) return best;

  // Fallback: derive the container from the candidate name + a section heading
  // common ancestor.
  const nameHit = findNaukriNameElement(document);
  if (nameHit) {
    let node = nameHit.el;
    while (node && node !== document.body && node !== document.documentElement) {
      const low = (node.textContent || "").toLowerCase();
      const hasSection = ALL_NAUKRI_TITLES_ARRAY.some((t) => low.includes(t));
      if (hasSection && !isNaukriExcludedZone(node)) return node;
      node = node.parentElement;
    }
  }
  return document.body;
}

// ---- Section discovery (scoped to the main container) -------------------------

function isNaukriHeadingEl(el) {
  if (!el) return false;
  const tag = (el.tagName || "").toLowerCase();
  if (/^h[1-6]$/.test(tag)) return true;
  let role = "";
  try { role = (el.getAttribute && el.getAttribute("role")) || ""; } catch (e) {}
  if (role.toLowerCase() === "heading") return true;
  let cls = "";
  try { cls = (typeof el.className === "string") ? el.className : ((el.className && el.className.toString) ? el.className.toString() : ""); } catch (e) {}
  return /\b(section-title|section-heading|section-header|card-title|title|heading)\b/i.test(cls);
}

function findNaukriSectionTitle(keywords, root) {
  if (typeof document === "undefined") return null;
  const scope = root || document;
  const matches = [];
  try {
    scope.querySelectorAll('*').forEach((el) => {
      if (isNaukriExcludedZone(el)) return;
      const text = (el.textContent || "").trim();
      if (!text || text.length > 80) return;
      const low = text.toLowerCase();
      const exact = keywords.some((k) => low === k);
      const headingMatch = isNaukriHeadingEl(el) && keywords.some((k) => low.includes(k));
      if (!exact && !headingMatch) return;
      let descendants = 0;
      try { descendants = el.querySelectorAll('*').length; } catch (e) {}
      matches.push({ el, descendants, exact: exact ? 1 : 0 });
    });
  } catch (e) {}
  if (!matches.length) return null;
  matches.sort((a, b) => (b.exact - a.exact) || (a.descendants - b.descendants));
  return matches[0].el;
}

function findNextNaukriSectionTitle(afterEl, root) {
  if (!afterEl || !afterEl.compareDocumentPosition || typeof document === "undefined") return null;
  const scope = root || document;
  const all = scope.querySelectorAll('*');
  for (let i = 0; i < all.length; i++) {
    const n = all[i];
    if (n === afterEl || (afterEl.contains && afterEl.contains(n))) continue;
    if (isNaukriExcludedZone(n)) continue;
    const text = (n.textContent || "").trim().toLowerCase();
    if (!text || text.length > 60) continue;
    if (!ALL_NAUKRI_TITLES.has(text)) continue;
    if (afterEl.compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) return n;
  }
  return null;
}

// Smallest block elements (div/li/article) that carry a date/year signal AND a
// real company/designation field. The date-signal alone is NOT enough (a
// "Professional Summary" paragraph containing "15 years" would otherwise be
// mistaken for a work-experience entry).
function naukriBlockEntries(container, fieldSel) {
  const blocks = [];
  const seen = new Set();
  container.querySelectorAll('div, li, article').forEach((el) => {
    if (isNaukriExcludedZone(el)) return;
    if (!hasDateSignal(el)) return;
    if (!isNaukriSectionBlock(el, fieldSel)) return;
    const txt = (el.textContent || "").trim();
    if (!txt || txt.length < 5 || txt.length > 6000) return;
    // Prefer the smallest meaningful block: skip when a descendant also qualifies.
    let childQualifies = false;
    el.querySelectorAll('div, li, article').forEach((c) => {
      if (c !== el && hasDateSignal(c) && (c.textContent || "").trim().length >= 5) childQualifies = true;
    });
    if (childQualifies) return;
    if (!seen.has(el)) { seen.add(el); blocks.push(el); }
  });
  return blocks;
}

function naukriSiblingContainer(titleEl) {
  if (!titleEl || typeof document === "undefined") return null;
  let sib = titleEl.nextElementSibling;
  while (sib) {
    if (isNaukriExcludedZone(sib)) { sib = sib.nextElementSibling; continue; }
    // Skip if the sibling is actually another section heading.
    const txt = (sib.textContent || "").trim();
    if (txt && txt.length <= 60 && ALL_NAUKRI_TITLES.has(txt.toLowerCase())) {
      sib = sib.nextElementSibling;
      continue;
    }
    // A container that holds entry blocks (or directly wraps entry markup).
    if (sib.querySelector && (sib.querySelector(ENTRY_SELECTOR) || sib.querySelector('div, li, article'))) {
      return sib;
    }
    sib = sib.nextElementSibling;
  }
  return null;
}

function collectNaukriSectionEntries(keywords, root) {
  const titleEl = findNaukriSectionTitle(keywords, root);
  if (!titleEl) return [];
  const scope = root || document;
  const fieldSel = naukriEntryFieldSelector(keywords);

  // 1. Use ONLY the sibling container that immediately follows the heading.
  //    We deliberately do NOT use `titleEl.closest('section'/'card')`: in
  //    Naukri that wrapper can span multiple sections (Experience + Education),
  //    which previously leaked Education institutes into the Experience list.
  const sibling = naukriSiblingContainer(titleEl);

  const containers = [sibling].filter((c) => c && c !== titleEl && !isNaukriExcludedZone(c));
  for (const container of containers) {
    if (titleEl.contains && titleEl.contains(container)) continue;
    const items = entryContainers(container);
    if (items.length) return items.filter((it) => !isNaukriExcludedZone(it));
    const blocks = naukriBlockEntries(container, fieldSel);
    if (blocks.length) return blocks;
  }

  // 2. Region: entries after the title until the next section title.
  const next = findNextNaukriSectionTitle(titleEl, scope);
  const listNodes = [];
  scope.querySelectorAll(ENTRY_SELECTOR).forEach((c) => {
    if (isNaukriExcludedZone(c)) return;
    if (!(titleEl.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
    if (next && (next.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
    listNodes.push(c);
  });
  const lists = topLevelNodes(listNodes);
  if (lists.length) return lists;

  // 3. Region with div-based entries (smallest date-bearing blocks that also
  // contain a real section field — never summary paragraphs).
  const regionNodes = [];
  scope.querySelectorAll('div, li, article').forEach((c) => {
    if (isNaukriExcludedZone(c)) return;
    if (!(titleEl.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
    if (next && (next.compareDocumentPosition(c) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
    if (!hasDateSignal(c)) return;
    if (!isNaukriSectionBlock(c, fieldSel)) return;
    regionNodes.push(c);
  });
  // Keep only the smallest qualifying blocks (exclude wrappers whose children also qualify).
  const result = [];
  regionNodes.forEach((el) => {
    if (regionNodes.some((other) => other !== el && el.contains(other))) return;
    if (result.indexOf(el) === -1) result.push(el);
  });
  return result;
}

// Strict "Work experience" extraction. Matches the EXACT "Work experience"
// heading (case-insensitive) and reuses the sibling + region collector so only
// the entries that follow that heading are returned — never the whole enclosing
// card (which is what previously let Education institutes leak in).
function collectNaukriExperienceEntries(root) {
  return collectNaukriSectionEntries(['work experience'], root);
}

function collectNaukriSkills(root) {
  const out = [];
  const seen = new Set();
  const titleEl = findNaukriSectionTitle(NAUKRI_SECTION_KEYWORDS.skills, root);
  if (!titleEl) return out; // never scan the whole page for skills
  let skillRoot = null;
  const sec = titleEl.closest
    ? (titleEl.closest('section') || titleEl.closest('.artdeco-card') || titleEl.closest('[class*="card"]'))
    : null;
  skillRoot = (sec && !isNaukriExcludedZone(sec)) ? sec : (titleEl.parentElement || titleEl);

  // Only leaf-ish spans/chips inside the skills section.
  skillRoot.querySelectorAll('span, li, .chip, [class*="skill"], .key-skill, [class*="keyword"]').forEach((el) => {
    if (isNaukriExcludedZone(el)) return;
    if (el.querySelector && el.querySelector('span')) return; // skip non-leaf wrappers
    const txt = getCleanText(el);
    if (!txt || txt.length > 80) return;
    if (txt.toLowerCase() === 'skills' || txt.toLowerCase() === 'key skills') return;
    const parts = txt.split(/[,·•|]+/).map((s) => s.trim()).filter((s) => s && s.length > 0 && s.length < 40 && !/skill/i.test(s));
    parts.forEach((p) => { if (!seen.has(p)) { seen.add(p); out.push(p); } });
  });
  return out;
}

function buildNaukriExperienceEntry(node, companyOverride) {
  if (!node) return null;
  // Guard: "Personal details"/"Other details" text is never an experience entry.
  if (NAUKRI_PERSONAL_DETAIL_SIGNAL.test((node.textContent || "").toLowerCase())) return null;
  const compEl = node.querySelector('.company, .company-name, .org, .employer, .employer-name, [class*="company"], [class*="employer"]');
  const desigEl = node.querySelector('.designation, .role, .job-title, .position, [class*="designation"], [class*="position"]');
  const durEl = node.querySelector('[class*="duration"], [class*="date"], [class*="period"], [class*="year"], .duration, .dates');
  const locEl = node.querySelector('[class*="location"], .loc');
  const descEl = node.querySelector('[class*="desc"], [class*="detail"], [class*="responsib"], .description');

  const company = companyOverride || (compEl ? cleanCompanyName(getCleanText(compEl)) : "");
  const designation = desigEl ? getCleanText(desigEl) : "";
  const duration = durEl ? getCleanText(durEl) : "";
  const location = locEl ? getCleanText(locEl) : "";
  const description = descEl ? getCleanText(descEl) : "";

  // A structured entry MUST have a company or designation. Never fall back to
  // parsing the whole node's innerText (that produces "Full" from "Full-time"
  // and huge summary paragraphs as bogus entries).
  if (!company && !designation) {
    // Naukri sometimes renders entries as plain divs without the dedicated
    // company/designation classes — recover via the line-based parser.
    return buildExperienceEntry(node, companyOverride);
  }

  const dd = parseDateDetails(duration);
  return {
    company_name: company,
    company: company,
    designation: designation,
    title: designation,
    employment_type: employmentTypeOf(duration),
    duration: duration,
    dates: duration,
    start_date: dd.start_date,
    end_date: dd.end_date,
    is_current: dd.is_current,
    location: location,
    description: description,
  };
}

function buildNaukriEducationEntry(node) {
  if (!node) return null;
  // Guard: "Personal details"/"Other details" text is never an education entry.
  if (NAUKRI_PERSONAL_DETAIL_SIGNAL.test((node.textContent || "").toLowerCase())) return null;
  const instEl = node.querySelector('[class*="institute"], [class*="college"], [class*="university"], [class*="school"], .institute, .school-name');
  const degEl = node.querySelector('[class*="degree"], [class*="qualification"], [class*="course"], .degree');
  const fieldEl = node.querySelector('[class*="specialization"], [class*="specialisation"], [class*="field"], .field');
  const durEl = node.querySelector('[class*="duration"], [class*="date"], [class*="year"], .dates, .passing-year');

  const inst = instEl ? getCleanText(instEl) : "";
  let degree = degEl ? getCleanText(degEl) : "";
  let field = fieldEl ? getCleanText(fieldEl) : "";
  const duration = durEl ? getCleanText(durEl) : "";

  if (degree && degree.includes(",") && !field) {
    const parts = degree.split(",");
    degree = parts[0].trim();
    field = parts.slice(1).join(",").trim();
  }

  if (inst || degree) {
    const dd = parseDateDetails(duration);
    return {
      institution: inst,
      school: inst,
      degree: degree,
      field_of_study: field || null,
      field: field || null,
      dates: duration,
      duration: duration,
      start_date: dd.start_date,
      end_date: dd.end_date,
    };
  }
  // Fall back to the line-based parser for plain div entries.
  return buildEducationEntry(node);
}

// ---- Current employment ("Current: <Role> at <Company>") ------------------------

// Boundary words that end a "Current"/"Previous" value in the header text. We cut
// the value here so education ("Highest degree", institutes) and other header
// fields ("Pref. location", CTC, notice) are NEVER treated as the designation.
const NAUKRI_EMPLOYMENT_BOUNDARY = /\b(highest degree|highest qualification|highest education|degree|qualification|pref(?:erred)?\.?\s*location|preferred location|current ctc|expected ctc|annual salary|salary|ctc|notice period|notice|work experience|employment history|education|key skills|technical skills|skills|profile summary|summary|certifications?|projects?)\b/i;

const NAUKRI_EDUCATION_SIGNAL = /(highest degree|highest qualification|qualification|institute|college|university|school|pref(?:erred)?\.?\s*location|preferred location)/i;

// Strict text-based header parse. Matches an explicit "Current:"/"Previous:"
// marker and reads only what follows it, stopping at the boundary words above.
function parseNaukriHeaderEmploymentText(text, base) {
  if (!text) return false;
  const flat = sanitizeString(text);
  const marker = /(?:^|[\s·•|])(current|previous)(?:\s+(?:designation|role|title|position|company|employer|organization|employment|org))?\s*[:|-]\s*/i;
  const re = new RegExp(marker.source, "gi");
  let found = false;
  let m;
  while ((m = re.exec(flat)) !== null) {
    let value = flat.slice(m.index + m[0].length);
    value = value.split(NAUKRI_EMPLOYMENT_BOUNDARY)[0];
    value = value.split(/\b(current|previous)\b/i)[0];
    value = value.replace(/[·•|,;]\s*$/, "").trim();
    if (value && value.length <= 200 && !NAUKRI_EDUCATION_SIGNAL.test(value)) {
      parseNaukriCompanyAndDesignation(value, base);
      found = true;
      if (base.current_company && base.current_designation) break;
    }
  }
  return found;
}

function parseNaukriCompanyAndDesignation(val, base) {
  const s = sanitizeString(val);
  if (!s) return;
  const at = s.match(/^(.*?)\s+(?:at|@)\s+(.+)$/i);
  let designation = "";
  let company = "";
  if (at) {
    designation = at[1].trim();
    company = at[2].trim();
  } else {
    const dash = s.match(/^(.*?)\s*[-–—|]\s*(.+)$/);
    if (dash) {
      designation = dash[1].trim();
      company = dash[2].trim();
    } else {
      company = s;
    }
  }
  if (designation && !base.current_designation && !FORBIDDEN_WORDS.test(designation)) {
    base.current_designation = designation;
  }
  if (company) {
    const cleaned = cleanCompanyName(company);
    if (cleaned && !base.current_company) base.current_company = cleaned;
  }
}

// Map a "Current"/"Previous" label + its value into the correct field(s).
function applyNaukriCurrentValue(label, value, base) {
  const v = sanitizeString(value);
  if (!v) return;
  if (NAUKRI_EDUCATION_SIGNAL.test(v)) return; // never treat education text as employment
  const l = (label || "").toLowerCase();
  if (/(designation|role|title|position|job)/.test(l)) {
    if (!base.current_designation && !FORBIDDEN_WORDS.test(v)) base.current_designation = v;
    return;
  }
  if (/(company|employer|organization|org)/.test(l)) {
    const c = cleanCompanyName(v);
    if (c && !base.current_company) base.current_company = c;
    return;
  }
  // Generic "current" -> "Designation at Company" / "Designation - Company" / "Company".
  parseNaukriCompanyAndDesignation(v, base);
}

// Find the value associated with a "Current" label element. Naukri often renders
// the label and value as sibling elements (e.g. a .mid-detail row with
// <span>Current</span> and a sibling <span>Full Stack Developer at Mediacile</span>).
function findAdjacentCurrentValue(labelEl) {
  if (!labelEl) return "";
  const tryText = (el) => {
    if (!el) return "";
    const t = getCleanText(el);
    if (!t || t.length > 200) return "";
    if (/^(current|previous)(ly)?\b/i.test(t)) return "";
    if (/^[-:|·•]+$/.test(t)) return "";
    if (/^(company|designation|role|organization|employer|employment|job)$/i.test(t.trim())) return "";
    if (NAUKRI_EDUCATION_SIGNAL.test(t)) return ""; // never accept "Highest degree" / institute text
    return t;
  };
  const parent = labelEl.parentElement;
  if (parent && parent.children) {
    for (const child of parent.children) {
      if (child === labelEl) continue;
      const t = tryText(child);
      if (t) return t;
    }
  }
  let sib = labelEl.nextElementSibling;
  while (sib) {
    const t = tryText(sib);
    if (t) return t;
    sib = sib.nextElementSibling;
  }
  sib = labelEl.previousElementSibling;
  while (sib) {
    const t = tryText(sib);
    if (t) return t;
    sib = sib.previousElementSibling;
  }
  return "";
}

function applyNaukriCurrentField(txt, base) {
  const clean = sanitizeString(txt);
  const labelMatch = clean.match(/(?:current|previous)\s+(company|employer|organization|org|designation|role|title|position)\s*[:|-]\s*(.{1,200})/i);
  if (labelMatch) {
    const label = labelMatch[1].toLowerCase();
    const val = labelMatch[2].trim().replace(/[·•|]\s*$/g, "").trim();
    applyNaukriCurrentValue(label, val, base);
    return;
  }
  const plain = clean.match(/(?:current|previous)(?:ly)?\s*[:|-]\s*(.{1,200})/i);
  if (plain) parseNaukriCompanyAndDesignation(plain[1], base);
}

function findNaukriCurrentEmployment(root, base) {
  const scope = root || document;

  // 1. Strict text-based header parse: an explicit "Current:"/"Previous:" line,
  //    read only up to the "Highest degree"/"Pref. location"/section boundary.
  //    This never pulls the candidate's education institute into the designation.
  if (parseNaukriHeaderEmploymentText(naukriHeaderText(), base)) {
    if (base.current_company && base.current_designation) return;
  }

  // 2. Structured fallback: a standalone "Current"/"Previous" LABEL whose value
  //    lives in an adjacent/sibling element (Naukri ".mid-detail" rows).
  scope.querySelectorAll('div, span, p, li, dt, dd, label, h1, h2, h3, h4, h5, h6').forEach((el) => {
    if (base.current_company && base.current_designation) return;
    if (isNaukriExcludedZone(el)) return;
    if (isInsideAnchor(el)) return;
    const label = getCleanText(el);
    if (!label || label.length > 40) return;
    if (!/^(current|previous)(ly)?( (company|designation|role|organization|employer|employment|job|org))?$/i.test(label.trim())) return;
    const value = findAdjacentCurrentValue(el);
    if (value) applyNaukriCurrentValue(label.trim(), value, base);
  });

  // 3. Single-element "Current: <Role> at <Company>" / "Previous: ...".
  scope.querySelectorAll('div, span, p, li, h1, h2, h3, h4, dt, dd').forEach((el) => {
    if (base.current_company && base.current_designation) return;
    if (isNaukriExcludedZone(el)) return;
    if (isInsideAnchor(el)) return;
    const txt = getCleanText(el);
    if (!txt || txt.length < 3 || txt.length > 220) return;
    if (!/\b(current|previous)\b/i.test(txt)) return;
    if (!/[:|-]/i.test(txt)) return;
    if (/ctc|salary|lpa|location|address|notice|prefer|highest degree|qualification|institute|college|university|school/i.test(txt)) return;
    applyNaukriCurrentField(txt, base);
  });
}

// Extract the candidate's professional summary from a genuine "Profile Summary" /
// "Summary" / "About" section, never from the headline or an experience block.
function findNaukriSummary(root) {
  const scope = root || document;
  const titleEl = findNaukriSectionTitle(['profile summary', 'summary', 'about'], scope);
  if (!titleEl) return "";
  const container = titleEl.closest
    ? (titleEl.closest('section') || titleEl.closest('[class*="card"]') || titleEl.closest('[class*="profile"]') || titleEl.parentElement)
    : (titleEl.parentElement || titleEl);
  if (!container) return "";
  const sel = '[class*="summary" i], [class*="about" i], [class*="objective" i], [class*="profile-text" i], .summary, .about';
  const els = container.querySelectorAll(sel);
  for (const el of els) {
    if (isNaukriExcludedZone(el)) continue;
    if (el === titleEl || (titleEl.contains && titleEl.contains(el))) continue;
    const txt = getCleanText(el);
    if (txt && txt.length > 20 && txt.length < 5000) return txt;
  }
  return "";
}

// ---- Adapter ---------------------------------------------------------------------

const NaukriAdapter = {
  extract(base) {
    base.profile_url = canonicalNaukriProfileUrl();

    // Locate the CURRENT candidate's main panel. Everything below reads from
    // this container only, so similar-profile cards can never contaminate data.
    const root = naukriMainContainer();
    console.log(`[Talent Vault Debug] Naukri main container: ${describeElement(root)}`);

    // 1. Name — the first real heading in the main panel that is not a link.
    const nameHit = findNaukriNameElement(root);
    if (nameHit) base.name = nameHit.txt;

    // 2. Headline — the candidate's own "Resume Headline" (header region only).
    const headlineSelectors = ['.resume-headline', '.resume-headline-text', '[class*="resume-headline" i]'];
    for (const sel of headlineSelectors) {
      const els = root.querySelectorAll(sel);
      for (const el of els) {
        if (isNaukriExcludedZone(el)) continue;
        if (isInsideAnchor(el)) continue;
        const txt = getCleanText(el);
        if (txt && txt !== base.name && txt.length < 300 && !FORBIDDEN_WORDS.test(txt)) {
          base.headline = txt;
          break;
        }
      }
      if (base.headline) break;
    }

    // 3. Location — header region only, and never a "prefers ..." similar-profile hint.
    const locSelectors = ['.loc', '.location', '[class*="location" i]', '.user-location', '.current-location', '[class*="current-location" i]'];
    for (const sel of locSelectors) {
      const els = root.querySelectorAll(sel);
      for (const el of els) {
        if (isNaukriExcludedZone(el)) continue;
        if (isInsideAnchor(el)) continue;
        const txt = getCleanText(el);
        if (txt && txt.length < 120 && !/^location$/i.test(txt) && !/prefer/i.test(txt)) {
          base.location = txt;
          break;
        }
      }
      if (base.location) break;
    }

    // 4. Current employment ("Current: Full Stack Developer at Mediacile").
    findNaukriCurrentEmployment(root, base);

    // 5. Summary — only from a genuine summary/about section, never the headline.
    const summary = findNaukriSummary(root);
    if (summary && summary !== base.headline) base.summary = summary;

    // 6. Experience (every visible entry, incl. multiple roles at one company).
    // Strict path first: exact "Work experience" heading + its immediate sibling
    // container, so Education entries can never leak into the Experience list.
    let expItems = collectNaukriExperienceEntries(root);
    if (!expItems.length) {
      expItems = collectNaukriSectionEntries(NAUKRI_SECTION_KEYWORDS.experience, root);
    }
    expItems.forEach((item) => {
      if (isMultiRole(item)) {
        const companyName = extractGroupCompany(item);
        const nestedList = item.querySelector('ul, ol');
        if (nestedList) {
          elementChildren(nestedList)
            .filter((el) => el.tagName && el.tagName.toLowerCase() === 'li' && !/^skills?:/i.test((el.textContent || "").trim()))
            .forEach((sub) => {
              const entry = buildNaukriExperienceEntry(sub, companyName);
              if (entry) base.experience.push(entry);
            });
        }
      } else {
        const entry = buildNaukriExperienceEntry(item, null);
        if (entry) base.experience.push(entry);
      }
    });

    // 7. Education
    const eduItems = collectNaukriSectionEntries(NAUKRI_SECTION_KEYWORDS.education, root);
    eduItems.forEach((item) => {
      const entry = buildNaukriEducationEntry(item);
      if (entry) base.education.push(entry);
    });

    // 8. Projects
    const projItems = collectNaukriSectionEntries(NAUKRI_SECTION_KEYWORDS.projects, root);
    projItems.forEach((item) => {
      const entry = buildProjectEntry(item);
      if (entry) base.projects.push(entry);
    });

    // 9. Certifications
    const certItems = collectNaukriSectionEntries(NAUKRI_SECTION_KEYWORDS.certifications, root);
    certItems.forEach((item) => {
      const entry = buildCertificationEntry(item);
      if (entry) base.certifications.push(entry);
    });

    // 10. Skills
    base.skills = collectNaukriSkills(root);

    // Derive current company/designation from the most recent role only when
    // they are not already known. Never reuse the (possibly multi-phrase)
    // headline as the current designation.
    if (!base.current_company && base.experience.length > 0) {
      base.current_company = base.experience[0].company_name || "";
    }
    if (!base.current_designation && base.experience.length > 0) {
      base.current_designation = base.experience[0].designation || "";
    }

    console.log(`[Talent Vault Debug] Naukri result: name="${base.name}" headline="${base.headline}" current_company="${base.current_company}" current_designation="${base.current_designation}" location="${base.location}" experience=${base.experience.length} education=${base.education.length} skills=${base.skills.length} profile=${base.profile_url}`);
    return base;
  }
};

const APNA_EXCLUDED_ZONE = 'aside, nav, header, footer, [class*="sidebar" i], [class*="similar" i], [class*="recommend" i], [class*="related" i], [class*="suggestion" i], [class*="people-also" i], [class*="other-candidates" i], [class*="right-panel" i], [class*="right-rail" i], [class*="rail" i], [class*="widget" i]';

function isApnaExcludedZone(el) {
  if (!el) return true;
  let node = el;
  while (node && node !== document.body && node !== document.documentElement) {
    try {
      if (node.matches && node.matches(APNA_EXCLUDED_ZONE)) return true;
    } catch (e) {}
    node = node.parentElement;
  }
  return false;
}

function isInsideAnchor(el) {
  let node = el;
  while (node && node !== document.body && node !== document.documentElement) {
    if (node.tagName && node.tagName.toLowerCase() === 'a') return true;
    node = node.parentElement;
  }
  return false;
}

const ApnaAdapter = {
  extract(base) {
    base.profile_url = (typeof window !== "undefined" && window.location && window.location.href)
      ? window.location.href.split("?")[0].split("#")[0]
      : "";

    // Name — main heading / name-like element, never a link, never a sidebar.
    const nameSelectors = ['h1', 'h2', '[class*="profile-name" i]', '[class*="candidate-name" i]', '[class*="user-name" i]', '[class*="name" i]'];
    for (const sel of nameSelectors) {
      const els = document.querySelectorAll(sel);
      for (const el of els) {
        if (isApnaExcludedZone(el)) continue;
        if (isInsideAnchor(el)) continue;
        const txt = getCleanText(el).replace(/\s+\(.+\)$/g, "").trim();
        if (txt && txt.length >= 2 && txt.length < 80 && !/^(apna|profile|jobs?)$/i.test(txt)) {
          base.name = txt;
          break;
        }
      }
      if (base.name) break;
    }

    // Headline / designation.
    const headlineSelectors = ['[class*="designation" i]', '[class*="headline" i]', '[class*="job-title" i]', '[class*="role" i]'];
    for (const sel of headlineSelectors) {
      const els = document.querySelectorAll(sel);
      for (const el of els) {
        if (isApnaExcludedZone(el)) continue;
        const txt = getCleanText(el);
        if (txt && txt !== base.name && txt.length < 300 && !FORBIDDEN_WORDS.test(txt)) {
          base.headline = txt;
          base.current_designation = txt;
          break;
        }
      }
      if (base.headline) break;
    }

    // Location.
    const locationSelectors = ['[class*="location" i]', '[class*="city" i]', '[class*="address" i]'];
    for (const sel of locationSelectors) {
      const els = document.querySelectorAll(sel);
      for (const el of els) {
        if (isApnaExcludedZone(el)) continue;
        const txt = getCleanText(el);
        if (txt && txt.length < 120 && !/^location$/i.test(txt)) {
          base.location = txt;
          break;
        }
      }
      if (base.location) break;
    }

    // Summary / about.
    const aboutSec = findSection('about', ['about', 'summary', 'profile summary', 'bio']);
    if (aboutSec) {
      const pArr = Array.from(aboutSec.querySelectorAll('p, span, div'))
        .map((p) => getCleanText(p))
        .filter((t) => t.length > 20);
      if (pArr.length) base.summary = pArr[0];
    }

    // Experience.
    const exp = collectSectionEntries(['experience', 'work experience', 'employment', 'employment history']);
    exp.items.forEach((item) => {
      if (isMultiRole(item)) {
        const companyName = extractGroupCompany(item);
        const nested = item.querySelector('ul, ol');
        if (nested) {
          elementChildren(nested)
            .filter((el) => el.tagName && el.tagName.toLowerCase() === 'li' && !/^skills?:/i.test((el.textContent || "").trim()))
            .forEach((sub) => {
              const entry = buildExperienceEntry(sub, companyName);
              if (entry) base.experience.push(entry);
            });
        }
      } else {
        const entry = buildExperienceEntry(item, null);
        if (entry) base.experience.push(entry);
      }
    });

    // Education.
    const edu = collectSectionEntries(['education', 'academics', 'qualification', 'education & qualifications']);
    edu.items.forEach((item) => {
      const entry = buildEducationEntry(item);
      if (entry) base.education.push(entry);
    });

    // Projects.
    const proj = collectSectionEntries(['projects', 'project details']);
    proj.items.forEach((item) => {
      const entry = buildProjectEntry(item);
      if (entry) base.projects.push(entry);
    });

    // Certifications.
    const cert = collectSectionEntries(['certifications', 'certification', 'licenses & certifications']);
    cert.items.forEach((item) => {
      const entry = buildCertificationEntry(item);
      if (entry) base.certifications.push(entry);
    });

    // Skills.
    const skillsSec = findSection('skills', ['skills', 'key skills', 'technical skills', 'it skills']);
    if (skillsSec) {
      skillsSec.querySelectorAll('li, [class*="skill" i], [class*="chip" i], span').forEach((item) => {
        if (isApnaExcludedZone(item)) return;
        if (item.querySelector && item.querySelector('span')) return;
        const sName = getCleanText(item);
        if (sName && sName.length < 60 && !/skill/i.test(sName) && !/endorse/i.test(sName)) {
          if (!base.skills.includes(sName)) base.skills.push(sName);
        }
      });
    }

    // Derive current company/designation from the most recent role.
    if (!base.current_company && base.experience.length > 0) {
      base.current_company = base.experience[0].company_name || "";
    }
    if (!base.current_designation && base.experience.length > 0) {
      base.current_designation = base.experience[0].designation || "";
    }

    console.log(`[Talent Vault Debug] Apna result: name="${base.name}" experience=${base.experience.length} education=${base.education.length} skills=${base.skills.length} profile=${base.profile_url}`);
    return base;
  }
};

const GenericAdapter = {
  extract(base) {
    const main = mainContainer();
    const h1 = main ? main.querySelector('h1') : document.querySelector('h1');
    if (h1) base.name = getCleanText(h1);

    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) base.summary = metaDesc.content.trim();

    return base;
  }
};

// Aliases for backwards compatibility with tests and callers
function extractLinkedInData(base) {
  return LinkedInAdapter.extract(base);
}

function extractNaukriData(base) {
  return NaukriAdapter.extract(base);
}

function extractGenericData(base) {
  return GenericAdapter.extract(base);
}

// ---------------------------------------------------------------------------
// Optional resume attachment.
// Detects real authorized, downloadable resumes and retrieves the true filename.
// ---------------------------------------------------------------------------
function detectResume() {
  const result = { resume_available: false, resume_url: "", resume_filename: "" };
  if (typeof document === "undefined") return result;

  // Prefer the resume URL already captured from the Naukri "Attached CV" /
  // resume iframe tab (see captureNaukriResumeUrl). Never forward a blob:/data:
  // URL — only a real http(s) endpoint is usable.
  if (typeof naukriResumeUrl === "string" && naukriResumeUrl) {
    const ru = normalizeResumeUrl(naukriResumeUrl);
    if (ru) {
      result.resume_available = true;
      result.resume_url = ru;
      result.resume_filename = filenameFromResumeUrl(ru) || "Candidate_Resume.pdf";
      return result;
    }
  }

  try {
    // Real clickable download links/buttons, plus iframe/embed whose src is a
    // direct file or a resume endpoint (a .pdf / resume viewer iframe is now
    // accepted so its src is captured rather than an HTML preview page).
    const nodes = document.querySelectorAll('a, button, [role="link"], [role="button"], [role="tab"], [data-url], iframe, embed, object');
    const candidates = [];

    const currentUrl = (() => {
      try { return (window.location.href || "").split("?")[0].split("#")[0]; } catch (e) { return ""; }
    })();

    nodes.forEach((el) => {
      // A tab/button that just says "Attached CV" but links nowhere is NOT a
      // resume file. Only a real href/data-url/src is a downloadable resume.
      const rawUrl = (el.getAttribute && (el.getAttribute("href") || el.getAttribute("data-url") || el.getAttribute("src") || "")) || "";
      const text = getCleanText(el);
      const label = (el.getAttribute && (el.getAttribute("aria-label") || el.getAttribute("title") || el.getAttribute("data-filename") || "")) || "";
      const downloadAttr = (el.getAttribute && el.getAttribute("download")) || "";
      const combined = (text + " " + rawUrl + " " + label + " " + downloadAttr).toLowerCase();

      if (!/resume|cv|download|attach/i.test(combined)) return;
      if (!rawUrl) return;

      let url;
      try {
        url = new URL(rawUrl, window.location.href).href;
      } catch (e) {
        return;
      }
      if (!/^https?:/i.test(url)) return;
      // Never treat the profile page itself (or a bare anchor) as a resume file.
      if (url.split("?")[0].split("#")[0] === currentUrl) return;

      // Only accept a DIRECT file, an explicit download control, or a resume
      // endpoint URL (Naukri embeds the resume in an iframe whose src points at
      // a `/resume/...` viewer; its bytes are fetched separately with cookies).
      const isResumeUrl = /resume|cv/i.test(rawUrl);
      const isDirectFile = /\.(pdf|docx?|rtf|txt)(\?|$)/i.test(rawUrl) || /\.(pdf|docx?|rtf|txt)$/i.test(downloadAttr);
      const hasDownloadSignal = /download/i.test(rawUrl) || /download/i.test(downloadAttr) || /download/i.test(text + " " + label);
      if (!isDirectFile && !hasDownloadSignal && !isResumeUrl) return;

      let score = 0;
      if (isDirectFile) score = 5;
      else if (isResumeUrl && /download/i.test(combined)) score = 4;
      else if (isResumeUrl) score = 3;
      else if (/resume|cv/i.test(combined) && /download/i.test(combined)) score = 3;
      else if (/resume|cv/i.test(combined)) score = 2;
      else if (/download/i.test(combined)) score = 1;
      if (score === 0) return;

      let filename = downloadAttr ? decodeURIComponent(downloadAttr) : "";
      if (!filename) {
        filename = filenameFromResumeUrl(url);
      }
      if (!filename) {
        const nearbyNameEl = el.closest(".resume-container, .resume-card, .attach-resume, div")?.querySelector(".resume-name, .filename, .file-name, [data-filename]");
        if (nearbyNameEl) {
          filename = getCleanText(nearbyNameEl);
        }
      }
      if (!filename) {
        const fileMatch = text.match(/[\w\-.]+\.(?:pdf|docx?|rtf|txt)\b/i) || label.match(/[\w\-.]+\.(?:pdf|docx?|rtf|txt)\b/i);
        if (fileMatch) filename = fileMatch[0];
      }

      candidates.push({ url, filename: filename || "Candidate_Resume.pdf", score });
    });

    if (!candidates.length) return result;

    candidates.sort((a, b) => b.score - a.score);
    const ru = normalizeResumeUrl(candidates[0].url);
    if (!ru) return result;
    result.resume_available = true;
    result.resume_url = ru;
    result.resume_filename = candidates[0].filename;
  } catch (e) {}
  return result;
}

function filenameFromResumeUrl(url) {
  try {
    const u = new URL(url);
    const queryName = u.searchParams.get("filename") || u.searchParams.get("file") || u.searchParams.get("name");
    if (queryName && /\.[a-z0-9]+$/i.test(queryName)) return decodeURIComponent(queryName);
    const base = (u.pathname || "").split("/").pop() || "";
    if (base && /\.[a-z0-9]+$/i.test(base)) return decodeURIComponent(base);
  } catch (e) {}
  return "";
}

async function fetchResumeAsBase64(url) {
  if (!url || !/^https?:/i.test(url)) {
    throw new Error("No valid resume URL available.");
  }

  const resp = await fetch(url, { credentials: "include" });
  if (!resp.ok) {
    throw new Error("Resume download failed (HTTP " + resp.status + ").");
  }

  const contentType = resp.headers ? (resp.headers.get("content-type") || "") : "";
  if (/text\/html/i.test(contentType)) {
    // Naukri returns an HTML login/preview page when the URL is not a direct
    // file download. Never attach that as a resume.
    throw new Error("Resume URL returned an HTML page (login or preview), not a resume file.");
  }

  let serverFilename = "";
  const contentDisp = resp.headers ? resp.headers.get("content-disposition") : null;
  if (contentDisp) {
    const fnMatch = contentDisp.match(/filename\*?=['"]?(?:UTF-\d['"]*)?([^;\r\n"']+)['"]?/i);
    if (fnMatch) serverFilename = decodeURIComponent(fnMatch[1].trim());
  }

  const blob = await resp.blob();
  const size = blob.size || 0;
  if (size > 15 * 1024 * 1024) {
    throw new Error("Resume is too large to attach (maximum 15MB).");
  }
  if (!size) {
    throw new Error("Resume file is empty.");
  }

  const mimeType = blob.type || "application/pdf";
  const buf = await blob.arrayBuffer();
  const bytes = new Uint8Array(buf);

  // Some Naukri/CDN endpoints serve an HTML preview/login page with a misleading
  // (or absent) content-type. Detect HTML by its leading bytes so we never send
  // an HTML page to the backend as a resume file.
  const headLen = Math.min(64, bytes.length);
  let head = "";
  for (let i = 0; i < headLen; i++) head += String.fromCharCode(bytes[i]);
  if (/^\s*<(?:!DOCTYPE|html|head|body|meta|title|script)/i.test(head)) {
    throw new Error("Resume URL returned an HTML page (login or preview), not a resume file.");
  }

  // Verify the bytes actually match the expected PDF format (signature check),
  // so a filename or content-type alone never passes as an uploaded PDF.
  const looksPdf = mimeType === "application/pdf" || /\.pdf$/i.test(url) || (serverFilename && /\.pdf$/i.test(serverFilename));
  if (looksPdf && !(bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46)) {
    throw new Error("Downloaded resume is not a valid PDF file.");
  }

  let binary = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }

  return {
    data_base64: btoa(binary),
    mime_type: mimeType,
    size: size,
    filename: serverFilename,
  };
}
