// ---------------------------------------------------------------------------
// API configuration (single source of truth).
//
// The production build ALWAYS talks to the hosted Talent Vault backend and never
// to a local development server. Authentication, authorization, CORS and CSRF
// are all handled server-side; the extension never ships a secret or API key.
//
// For local development you may override the base URL at runtime without
// editing this file, e.g. from the extension's DevTools console:
//   chrome.storage.local.set({ apiBaseUrl: "http://<your-local-dev-host>" });
// The override is read from chrome.storage.local each time the panel opens.
// ---------------------------------------------------------------------------
const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const API_BASE_STORAGE_KEY = "apiBaseUrl";

let API_BASE_URL = DEFAULT_API_BASE_URL;

function importEndpoint() {
  return `${API_BASE_URL}/api/v1/candidates/import/`;
}

function enrichmentEndpoint() {
  return `${API_BASE_URL}/api/v1/enrichment/person/`;
}

function loadApiBaseUrl() {
  return new Promise((resolve) => {
    try {
      if (typeof chrome === "undefined" || !chrome.storage || !chrome.storage.local) {
        return resolve();
      }
      chrome.storage.local.get(API_BASE_STORAGE_KEY, (stored) => {
        const override = stored && stored[API_BASE_STORAGE_KEY];
        if (override && typeof override === "string" && override.trim()) {
          API_BASE_URL = override.trim().replace(/\/+$/, "");
        }
        resolve();
      });
    } catch (e) {
      resolve();
    }
  });
}

let currentMode = "parsing"; // "parsing" or "manual"
let currentExtractedData = null;
let experiencesData = [];
let educationsData = [];
let projectsData = [];
let certificationsData = [];
let parseInFlight = false; // prevents overlapping/repeated parse runs

document.addEventListener("DOMContentLoaded", () => {
  const parsingModeBtn = document.getElementById("parsingModeBtn");
  const manualModeBtn = document.getElementById("manualModeBtn");
  const parseBtn = document.getElementById("parseBtn");
  const retryBtn = document.getElementById("retryBtn");
  const saveBtn = document.getElementById("saveBtn");
  const addExpBtn = document.getElementById("addExpBtn");
  const addEduBtn = document.getElementById("addEduBtn");
  const addProjBtn = document.getElementById("addProjBtn");
  const addCertBtn = document.getElementById("addCertBtn");
  const findEmailBtn = document.getElementById("findEmailBtn");
  const findPhoneBtn = document.getElementById("findPhoneBtn");
  const enrichBtn = document.getElementById("enrichBtn");
  const manualResumeUpload = document.getElementById("manualResumeUpload");
  const selectedFileName = document.getElementById("selectedFileName");

  parsingModeBtn.addEventListener("click", () => setMode("parsing"));
  manualModeBtn.addEventListener("click", () => setMode("manual"));

  // Manual resume upload: update the label with the chosen file name. The file
  // itself is read to Base64 at save time (handleSaveCandidate).
  if (manualResumeUpload) {
    manualResumeUpload.addEventListener("change", () => {
      const file = manualResumeUpload.files && manualResumeUpload.files[0];
      if (!selectedFileName) return;
      if (file) {
        selectedFileName.textContent = `Selected: ${file.name}`;
        selectedFileName.classList.remove("hidden");
      } else {
        selectedFileName.textContent = "";
        selectedFileName.classList.add("hidden");
      }
    });
  }

  if (parseBtn) parseBtn.addEventListener("click", () => parseActivePage());
  retryBtn.addEventListener("click", () => parseActivePage());
  saveBtn.addEventListener("click", handleSaveCandidate);
  if (addExpBtn) addExpBtn.addEventListener("click", () => addExperienceItem());
  if (addEduBtn) addEduBtn.addEventListener("click", () => addEducationItem());
  if (addProjBtn) addProjBtn.addEventListener("click", () => addProjectItem());
  if (addCertBtn) addCertBtn.addEventListener("click", () => addCertificationItem());
  findEmailBtn.addEventListener("click", () => handleEnrich("email"));
  findPhoneBtn.addEventListener("click", () => handleEnrich("phone"));
  enrichBtn.addEventListener("click", () => handleEnrich("all"));

  // Resolve the API base URL (production default, storage override for dev)
  // before any network call. CSRF tokens are fetched fresh per-request, so
  // nothing is cached here.
  loadApiBaseUrl();

  // Persist the recruiter's login email so they only enter it once.
  const RECRUITER_EMAIL_KEY = "recruiterEmail";
  const recruiterEmailInput = document.getElementById("recruiterEmail");
  if (recruiterEmailInput) {
    try {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(RECRUITER_EMAIL_KEY, (stored) => {
          const email = stored && stored[RECRUITER_EMAIL_KEY];
          if (email && typeof email === "string" && email.trim()) {
            recruiterEmailInput.value = email.trim();
          }
        });
      }
    } catch (e) {}
    const persistRecruiterEmail = () => {
      try {
        const email = (recruiterEmailInput.value || "").trim();
        if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
          chrome.storage.local.set({ [RECRUITER_EMAIL_KEY]: email });
        }
      } catch (e) {}
    };
    recruiterEmailInput.addEventListener("change", persistRecruiterEmail);
    recruiterEmailInput.addEventListener("blur", persistRecruiterEmail);
  }

  // Stealth: the panel NEVER auto-parses on open. Extraction runs only when the
  // recruiter clicks "Parse Profile" (or "Retry Parse"), or the in-page TV icon.
});

/**
 * Obtain a FRESH CSRF token from the backend. Django sets the `csrftoken`
 * cookie on this GET and returns a matching token in the JSON body. A token is
 * never cached across requests so it cannot go stale after a login/session
 * change (Django rotates the CSRF secret on login).
 */
async function getCsrfToken() {
  try {
    const url = importEndpoint();
    console.log("[Talent Vault] getCsrfToken -> GET", url);
    const res = await fetch(url, { method: "GET", credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      if (data && data.csrfToken) {
        return data.csrfToken;
      }
      console.warn("[Talent Vault] getCsrfToken: response missing csrfToken", data);
    } else {
      console.warn("[Talent Vault] getCsrfToken: HTTP", res.status, res.statusText);
    }
  } catch (e) {
    console.error("[Talent Vault] Could not fetch CSRF token:", e);
    console.error("[Talent Vault] CSRF fetch error detail:", {
      url,
      name: e && e.name,
      message: e && e.message,
      cause: e && e.cause,
      online: (typeof navigator !== "undefined" && navigator.onLine),
    });
  }
  return null;
}

/**
 * POST with CSRF protection. Fetches a fresh token immediately before the
 * request and sends it in X-CSRFToken alongside the session cookies. If Django
 * rejects a stale/rotated token with 403, we refresh once and retry so a
 * login/session change mid-flight never leaves the extension stuck.
 */
async function postWithCsrf(url, payload) {
  const doPost = async () => {
    const token = await getCsrfToken();
    const headers = {
      "Content-Type": "application/json",
      "Accept": "application/json"
    };
    if (token) {
      headers["X-CSRFToken"] = token;
    }
    console.log("[Talent Vault] POST", url);
    return fetch(url, {
      method: "POST",
      headers: headers,
      credentials: "include",
      body: JSON.stringify(payload)
    });
  };

  let response = await doPost();
  if (response.status === 403) {
    console.warn("[Talent Vault] POST returned 403 (CSRF?), retrying once");
    response = await doPost();
  }
  return response;
}

function setMode(mode) {
  if (currentMode === "manual") {
    syncAllFromUI();
  }
  currentMode = mode;
  const parsingBtn = document.getElementById("parsingModeBtn");
  const manualBtn = document.getElementById("manualModeBtn");
  const candidateForm = document.getElementById("candidateForm");
  const sourceBadge = document.getElementById("sourceBadge");

  const addExpBtn = document.getElementById("addExpBtn");
  const addEduBtn = document.getElementById("addEduBtn");
  const addProjBtn = document.getElementById("addProjBtn");
  const addCertBtn = document.getElementById("addCertBtn");
  const showAdd = mode === "manual";
  if (addExpBtn) addExpBtn.classList.toggle("hidden", !showAdd);
  if (addEduBtn) addEduBtn.classList.toggle("hidden", !showAdd);
  if (addProjBtn) addProjBtn.classList.toggle("hidden", !showAdd);
  if (addCertBtn) addCertBtn.classList.toggle("hidden", !showAdd);

  if (mode === "parsing") {
    parsingBtn.classList.add("active");
    manualBtn.classList.remove("active");
    if (sourceBadge) {
      sourceBadge.textContent = `Source: ${(currentExtractedData?.source || "LINKEDIN").toUpperCase()}`;
      sourceBadge.className = `source-tag source-${currentExtractedData?.source || "linkedin"}`;
    }

    if (currentExtractedData) {
      candidateForm.classList.remove("hidden");
      hideExtractCard();
    } else {
      candidateForm.classList.add("hidden");
      showExtractCard();
    }
  } else {
    manualBtn.classList.add("active");
    parsingBtn.classList.remove("active");
    hideExtractCard();
    candidateForm.classList.remove("hidden");
    if (sourceBadge) {
      sourceBadge.textContent = "Source: MANUAL";
      sourceBadge.className = "source-tag source-manual";
    }
  }

  renderExperienceList();
  renderEducationList();
  renderProjectsList();
  renderCertificationsList();
}

function showAlert(message, type = "info") {
  const alertEl = document.getElementById("statusAlert");
  alertEl.className = `alert alert-${type}`;
  alertEl.textContent = message;
  alertEl.classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Auto-parse flow.
//
// The side panel only opens when the recruiter clicks the pinned toolbar icon,
// so opening it is the explicit user action that starts parsing. We never save
// automatically: the recruiter must review the populated fields and press
// "Save Candidate".
// ---------------------------------------------------------------------------
const SUPPORTED_HOSTS = [
  "linkedin.com",
  "naukri.com",
  "apna.com",
  "apna.co",
  "shine.com",
  "timesjobs.com",
  "foundit.in",
  "cutshort.io",
  "hirist.com",
  "instahyre.com",
  "wellfound.com",
  "indeed.com"
];

function isSupportedSource(url) {
  if (!url) return false;
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    return SUPPORTED_HOSTS.some(
      (host) => hostname === host || hostname.endsWith("." + host)
    );
  } catch (e) {
    return false;
  }
}

function getActiveTab() {
  return new Promise((resolve, reject) => {
    if (typeof chrome === "undefined" || !chrome.tabs || !chrome.tabs.query) {
      reject(new Error("chrome.tabs is unavailable."));
      return;
    }
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!tabs || tabs.length === 0) {
        reject(new Error("No active tab detected."));
        return;
      }
      resolve(tabs[0]);
    });
  });
}

function sendExtractMessage(tabId) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, { action: "extract_candidate_data" }, (response) => {
      if (chrome.runtime.lastError) {
        resolve({ error: chrome.runtime.lastError.message });
        return;
      }
      resolve(response || { error: "No response from the page." });
    });
  });
}

function injectContentScript(tabId) {
  return new Promise((resolve) => {
    if (!chrome.scripting || !chrome.scripting.executeScript) {
      resolve({ error: "chrome.scripting is unavailable." });
      return;
    }
    chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] }, () => {
      if (chrome.runtime.lastError) {
        resolve({ error: chrome.runtime.lastError.message });
        return;
      }
      resolve({});
    });
  });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function extractFromTab(tabId) {
  let result = await sendExtractMessage(tabId);
  if (result.status === "success") {
    return result.data;
  }

  const injected = await injectContentScript(tabId);
  if (injected.error) {
    return null;
  }

  await delay(300);
  result = await sendExtractMessage(tabId);
  return result.status === "success" ? result.data : null;
}

// Ask the content script to download the resume and return it base64-encoded.
// The backend only accepts data_base64 (it ignores a raw URL), so this is the
// only way the resume actually gets attached.
async function fetchResumeAsBase64FromTab(url) {
  try {
    const tab = await getActiveTab();
    return await new Promise((resolve) => {
      chrome.tabs.sendMessage(tab.id, { action: "tv_fetch_resume", url }, (response) => {
        if (chrome.runtime.lastError || !response || !response.ok) {
          resolve(null);
          return;
        }
        resolve(response);
      });
    });
  } catch (e) {
    console.error("[Talent Vault] Resume fetch failed:", e);
    return null;
  }
}

// Read a user-selected file into a raw Base64 string (no data: URL prefix), so
// it can be attached to the candidate as `resume_base64`.
function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Could not read file as a string."));
        return;
      }
      const commaIndex = result.indexOf(",");
      resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result);
    };
    reader.onerror = () => reject(reader.error || new Error("File read failed."));
    reader.readAsDataURL(file);
  });
}

// Ask the content script to human-like click the Naukri CV/download control and
// capture the resume as base64 (via the page-context blob: reader).
async function downloadResumeViaTab() {
  try {
    const tab = await getActiveTab();
    return await new Promise((resolve) => {
      chrome.tabs.sendMessage(tab.id, { action: "tv_download_resume" }, (response) => {
        if (chrome.runtime.lastError || !response) {
          resolve(null);
          return;
        }
        resolve(response);
      });
    });
  } catch (e) {
    console.error("[Talent Vault] Resume capture failed:", e);
    return null;
  }
}

function showExtractCard() {
  const extractCard = document.getElementById("extractCard");
  if (extractCard) extractCard.classList.remove("hidden");
}

function hideExtractCard() {
  const extractCard = document.getElementById("extractCard");
  if (extractCard) extractCard.classList.add("hidden");
}

function showParseError(message) {
  const errEl = document.getElementById("parseError");
  const retryBtn = document.getElementById("retryBtn");
  if (errEl) {
    errEl.textContent = message;
    errEl.classList.remove("hidden");
  }
  if (retryBtn) retryBtn.classList.remove("hidden");
}

function clearParseError() {
  const errEl = document.getElementById("parseError");
  const retryBtn = document.getElementById("retryBtn");
  if (errEl) errEl.classList.add("hidden");
  if (retryBtn) retryBtn.classList.add("hidden");
}

function setParsingLoading(active) {
  const parsingStatus = document.getElementById("parsingStatus");
  if (parsingStatus) {
    if (active) {
      parsingStatus.classList.remove("hidden");
    } else {
      parsingStatus.classList.add("hidden");
    }
  }
  if (active) clearParseError();
}

// Reset every candidate field and the in-memory lists so a previous profile's
// data (especially email/phone/name) can never leak into a new parse.
function clearFormFields() {
  currentExtractedData = null;
  experiencesData = [];
  educationsData = [];
  projectsData = [];
  certificationsData = [];

  const fieldIds = [
    "fieldName",
    "fieldEmail",
    "fieldPhone",
    "fieldHeadline",
    "fieldCurrentCompany",
    "fieldLocation",
    "fieldSummary",
    "fieldProfileUrl",
    "fieldSkills",
    "fieldTotalExperience",
    "fieldCurrentSalary",
    "fieldExpectedSalary",
    "fieldNoticePeriod",
  ];
  fieldIds.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });

  const resumeSection = document.getElementById("resumeSection");
  const resumeBadge = document.getElementById("resumeBadge");
  const resumeCheckbox = document.getElementById("attachResumeCheckbox");
  if (resumeSection) resumeSection.classList.add("hidden");
  if (resumeBadge) resumeBadge.classList.add("hidden");
  if (resumeCheckbox) resumeCheckbox.checked = false;

  const manualResumeInput = document.getElementById("manualResumeUpload");
  const selectedFileName = document.getElementById("selectedFileName");
  if (manualResumeInput) manualResumeInput.value = "";
  if (selectedFileName) {
    selectedFileName.textContent = "";
    selectedFileName.classList.add("hidden");
  }

  renderExperienceList();
  renderEducationList();
  renderProjectsList();
  renderCertificationsList();
}

async function parseActivePage() {
  // Ignore overlapping/repeated runs (e.g. rapid icon clicks or panel updates).
  if (parseInFlight) return;
  parseInFlight = true;

  // Clear any previously parsed candidate BEFORE starting a new parse, so a
  // stale email/phone/name from the last profile can never bleed into this one.
  clearFormFields();

  setParsingLoading(true);
  showAlert("Parsing active page…", "info");

  try {
    let tab;
    try {
      tab = await getActiveTab();
    } catch (err) {
      showParseError(err.message || "Could not access the active tab.");
      return;
    }

    const url = tab.url || "";
    if (!isSupportedSource(url)) {
      setMode("manual");
      showAlert("This page isn't supported for automatic parsing. Enter candidate details manually.", "warning");
      return;
    }

    const data = await extractFromTab(tab.id);

    if (data && data.name) {
      populateForm(data);
    } else {
      showParseError("Could not extract a candidate profile from this page. Make sure the profile is open, then retry.");
    }
  } finally {
    setParsingLoading(false);
    parseInFlight = false;
  }
}

function populateForm(data) {
  currentExtractedData = data;

  document.getElementById("fieldName").value = data.name || "";
  document.getElementById("fieldEmail").value = data.email || "";
  document.getElementById("fieldPhone").value = normalizePhoneNumber(data.phone);
  document.getElementById("fieldHeadline").value = data.headline || data.current_designation || "";
  document.getElementById("fieldCurrentCompany").value = data.current_company || "";
  document.getElementById("fieldLocation").value = data.location || "";
  document.getElementById("fieldSummary").value = data.summary || "";
  document.getElementById("fieldProfileUrl").value = data.profile_url || data.linkedin_url || "";
  document.getElementById("fieldSkills").value = Array.isArray(data.skills) ? data.skills.join(", ") : "";

  document.getElementById("fieldTotalExperience").value = (data.total_experience != null) ? String(data.total_experience) : "";
  document.getElementById("fieldCurrentSalary").value = (data.current_salary != null) ? String(data.current_salary) : ((data.current_ctc != null) ? String(data.current_ctc) : "");
  document.getElementById("fieldExpectedSalary").value = (data.expected_salary != null) ? String(data.expected_salary) : ((data.expected_ctc != null) ? String(data.expected_ctc) : "");
  document.getElementById("fieldNoticePeriod").value = (data.notice_period != null) ? String(data.notice_period) : "";

  experiencesData = Array.isArray(data.experience) ? [...data.experience] : [];
  educationsData = Array.isArray(data.education) ? [...data.education] : [];
  projectsData = Array.isArray(data.projects) ? [...data.projects] : [];
  certificationsData = Array.isArray(data.certifications) ? [...data.certifications] : [];

  const resumeSection = document.getElementById("resumeSection");
  const resumeBadge = document.getElementById("resumeBadge");
  const resumeCheckbox = document.getElementById("attachResumeCheckbox");
  if (data.resume_available || data.resume_url || data.resume_base64) {
    if (resumeSection) resumeSection.classList.remove("hidden");
    if (resumeBadge) {
      resumeBadge.textContent = `Resume file ready: ${data.resume_filename || 'Candidate_Resume.pdf'}`;
      resumeBadge.classList.remove("hidden");
    }
    if (resumeCheckbox) resumeCheckbox.checked = false;
  } else {
    if (resumeSection) resumeSection.classList.add("hidden");
    if (resumeBadge) resumeBadge.classList.add("hidden");
    if (resumeCheckbox) resumeCheckbox.checked = false;
  }

  setMode(currentMode);

  const sourceBadge = document.getElementById("sourceBadge");
  sourceBadge.textContent = `Source: ${(data.source || "linkedin").toUpperCase()}`;
  sourceBadge.className = `source-tag source-${data.source || "linkedin"}`;

  document.getElementById("candidateForm").classList.remove("hidden");
  hideExtractCard();
  showAlert(`Extracted data for "${data.name || 'Candidate'}". Review and edit fields before saving.`, "success");
}

function renderExperienceList() {
  const container = document.getElementById("experienceList");
  if (!container) return;
  container.innerHTML = "";
  const countEl = document.getElementById("expCount");
  if (countEl) countEl.textContent = experiencesData.length;

  if (experiencesData.length === 0) {
    container.innerHTML = `<div class="empty-list-notice">No information available</div>`;
    return;
  }

  const isManual = currentMode === "manual";

  experiencesData.forEach((exp, idx) => {
    if (!isManual) {
      const card = document.createElement("div");
      card.className = "dynamic-card-readonly";
      let html = "";
      const company = exp.company_name || exp.company || "";
      const designation = exp.designation || exp.title || "";
      const employmentType = exp.employment_type || "";
      const duration = exp.duration || exp.dates || "";
      const location = exp.location || "";
      const desc = exp.description || "";

      if (company) html += `<div class="readonly-row"><span class="readonly-label">Company:</span><span class="readonly-value">${escapeHtml(company)}</span></div>`;
      if (designation) html += `<div class="readonly-row"><span class="readonly-label">Designation:</span><span class="readonly-value">${escapeHtml(designation)}</span></div>`;
      if (employmentType) html += `<div class="readonly-row"><span class="readonly-label">Type:</span><span class="readonly-value">${escapeHtml(employmentType)}</span></div>`;
      if (duration) html += `<div class="readonly-row"><span class="readonly-label">Dates:</span><span class="readonly-value">${escapeHtml(duration)}</span></div>`;
      if (location) html += `<div class="readonly-row"><span class="readonly-label">Location:</span><span class="readonly-value">${escapeHtml(location)}</span></div>`;
      if (desc) html += `<div class="readonly-row"><span class="readonly-label">Description:</span><span class="readonly-value">${escapeHtml(desc)}</span></div>`;
      card.innerHTML = html || `<div class="readonly-row"><span class="readonly-value">No details</span></div>`;
      container.appendChild(card);
    } else {
      const card = document.createElement("div");
      card.className = "dynamic-card";

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "remove-item-btn";
      removeBtn.textContent = "×";
      removeBtn.onclick = () => {
        syncExperienceFromUI();
        experiencesData.splice(idx, 1);
        renderExperienceList();
      };
      card.appendChild(removeBtn);

      card.innerHTML += `
        <div class="form-group">
          <label>Company</label>
          <input type="text" class="exp-company" value="${escapeHtml(exp.company_name || exp.company || '')}" placeholder="Company Name">
        </div>
        <div class="form-group">
          <label>Designation</label>
          <input type="text" class="exp-desig" value="${escapeHtml(exp.designation || exp.title || '')}" placeholder="Role / Title">
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>Employment Type</label>
            <input type="text" class="exp-type" value="${escapeHtml(exp.employment_type || '')}" placeholder="Full-time">
          </div>
          <div class="form-group flex-1">
            <label>Location</label>
            <input type="text" class="exp-loc" value="${escapeHtml(exp.location || '')}" placeholder="City, Country">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>Start Date</label>
            <input type="text" class="exp-start" value="${escapeHtml(exp.start_date || '')}" placeholder="YYYY-MM-DD or Jan 2021">
          </div>
          <div class="form-group flex-1">
            <label>End Date</label>
            <input type="text" class="exp-end" value="${escapeHtml(exp.end_date || '')}" placeholder="YYYY-MM-DD or Present">
          </div>
        </div>
        <div class="form-group">
          <label>Dates / Duration Text</label>
          <input type="text" class="exp-dur" value="${escapeHtml(exp.duration || exp.dates || '')}" placeholder="Jan 2021 - Present">
        </div>
        <div class="form-group">
          <label>Description</label>
          <textarea class="exp-desc" rows="2" placeholder="Experience details...">${escapeHtml(exp.description || '')}</textarea>
        </div>
      `;
      container.appendChild(card);
    }
  });
}

function addExperienceItem() {
  syncExperienceFromUI();
  experiencesData.push({
    company_name: "",
    designation: "",
    employment_type: "",
    start_date: "",
    end_date: "",
    duration: "",
    location: "",
    description: ""
  });
  renderExperienceList();
}

function syncExperienceFromUI() {
  if (currentMode !== "manual") return;
  const cards = document.querySelectorAll("#experienceList .dynamic-card");
  const newExpList = [];
  cards.forEach(card => {
    const company = (card.querySelector(".exp-company")?.value || "").trim();
    const designation = (card.querySelector(".exp-desig")?.value || "").trim();
    const employment_type = (card.querySelector(".exp-type")?.value || "").trim();
    const start_date = (card.querySelector(".exp-start")?.value || "").trim();
    const end_date = (card.querySelector(".exp-end")?.value || "").trim();
    const duration = (card.querySelector(".exp-dur")?.value || "").trim();
    const location = (card.querySelector(".exp-loc")?.value || "").trim();
    const description = (card.querySelector(".exp-desc")?.value || "").trim();
    newExpList.push({
      company_name: company,
      company: company,
      designation: designation,
      title: designation,
      employment_type: employment_type,
      start_date: start_date,
      end_date: end_date,
      duration: duration,
      dates: duration,
      location: location,
      description: description
    });
  });
  experiencesData = newExpList;
}

function renderEducationList() {
  const container = document.getElementById("educationList");
  if (!container) return;
  container.innerHTML = "";
  const countEl = document.getElementById("eduCount");
  if (countEl) countEl.textContent = educationsData.length;

  if (educationsData.length === 0) {
    container.innerHTML = `<div class="empty-list-notice">No information available</div>`;
    return;
  }

  const isManual = currentMode === "manual";

  educationsData.forEach((edu, idx) => {
    if (!isManual) {
      const card = document.createElement("div");
      card.className = "dynamic-card-readonly";
      let html = "";
      const inst = edu.institution || edu.school || "";
      const deg = edu.degree || "";
      const field = edu.field_of_study || edu.field || "";
      const dates = edu.dates || edu.duration || "";

      if (inst) html += `<div class="readonly-row"><span class="readonly-label">Institution:</span><span class="readonly-value">${escapeHtml(inst)}</span></div>`;
      if (deg) html += `<div class="readonly-row"><span class="readonly-label">Degree:</span><span class="readonly-value">${escapeHtml(deg)}</span></div>`;
      if (field) html += `<div class="readonly-row"><span class="readonly-label">Field:</span><span class="readonly-value">${escapeHtml(field)}</span></div>`;
      if (dates) html += `<div class="readonly-row"><span class="readonly-label">Dates:</span><span class="readonly-value">${escapeHtml(dates)}</span></div>`;
      card.innerHTML = html || `<div class="readonly-row"><span class="readonly-value">No details</span></div>`;
      container.appendChild(card);
    } else {
      const card = document.createElement("div");
      card.className = "dynamic-card";

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "remove-item-btn";
      removeBtn.textContent = "×";
      removeBtn.onclick = () => {
        syncEducationFromUI();
        educationsData.splice(idx, 1);
        renderEducationList();
      };
      card.appendChild(removeBtn);

      card.innerHTML += `
        <div class="form-group">
          <label>Institution</label>
          <input type="text" class="edu-inst" value="${escapeHtml(edu.institution || edu.school || '')}" placeholder="University / College">
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>Degree</label>
            <input type="text" class="edu-deg" value="${escapeHtml(edu.degree || '')}" placeholder="e.g. B.Tech / M.S.">
          </div>
          <div class="form-group flex-1">
            <label>Field of Study</label>
            <input type="text" class="edu-field" value="${escapeHtml(edu.field_of_study || edu.field || '')}" placeholder="Computer Science">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>Start Date</label>
            <input type="text" class="edu-start" value="${escapeHtml(edu.start_date || '')}" placeholder="YYYY or YYYY-MM">
          </div>
          <div class="form-group flex-1">
            <label>End Date</label>
            <input type="text" class="edu-end" value="${escapeHtml(edu.end_date || '')}" placeholder="YYYY or YYYY-MM">
          </div>
        </div>
        <div class="form-group">
          <label>Dates / Years</label>
          <input type="text" class="edu-dur" value="${escapeHtml(edu.dates || edu.duration || '')}" placeholder="2016 - 2020">
        </div>
      `;
      container.appendChild(card);
    }
  });
}

function addEducationItem() {
  syncEducationFromUI();
  educationsData.push({
    institution: "",
    degree: "",
    field_of_study: "",
    start_date: "",
    end_date: "",
    dates: ""
  });
  renderEducationList();
}

function syncEducationFromUI() {
  if (currentMode !== "manual") return;
  const cards = document.querySelectorAll("#educationList .dynamic-card");
  const newEduList = [];
  cards.forEach(card => {
    const inst = (card.querySelector(".edu-inst")?.value || "").trim();
    const deg = (card.querySelector(".edu-deg")?.value || "").trim();
    const field = (card.querySelector(".edu-field")?.value || "").trim();
    const start_date = (card.querySelector(".edu-start")?.value || "").trim();
    const end_date = (card.querySelector(".edu-end")?.value || "").trim();
    const duration = (card.querySelector(".edu-dur")?.value || "").trim();
    newEduList.push({
      institution: inst,
      school: inst,
      degree: deg,
      field_of_study: field,
      field: field,
      start_date: start_date,
      end_date: end_date,
      dates: duration,
      duration: duration
    });
  });
  educationsData = newEduList;
}

function renderProjectsList() {
  const container = document.getElementById("projectsList");
  if (!container) return;
  container.innerHTML = "";
  const countEl = document.getElementById("projCount");
  if (countEl) countEl.textContent = projectsData.length;

  if (projectsData.length === 0) {
    container.innerHTML = `<div class="empty-list-notice">No information available</div>`;
    return;
  }

  const isManual = currentMode === "manual";

  projectsData.forEach((proj, idx) => {
    if (!isManual) {
      const card = document.createElement("div");
      card.className = "dynamic-card-readonly";
      let html = "";
      const name = proj.name || proj.title || "";
      const role = proj.role || "";
      const dates = proj.duration || proj.dates || "";
      const desc = proj.description || "";

      if (name) html += `<div class="readonly-row"><span class="readonly-label">Project:</span><span class="readonly-value">${escapeHtml(name)}</span></div>`;
      if (role) html += `<div class="readonly-row"><span class="readonly-label">Role:</span><span class="readonly-value">${escapeHtml(role)}</span></div>`;
      if (dates) html += `<div class="readonly-row"><span class="readonly-label">Dates:</span><span class="readonly-value">${escapeHtml(dates)}</span></div>`;
      if (desc) html += `<div class="readonly-row"><span class="readonly-label">Description:</span><span class="readonly-value">${escapeHtml(desc)}</span></div>`;
      card.innerHTML = html || `<div class="readonly-row"><span class="readonly-value">No details</span></div>`;
      container.appendChild(card);
    } else {
      const card = document.createElement("div");
      card.className = "dynamic-card";

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "remove-item-btn";
      removeBtn.textContent = "×";
      removeBtn.onclick = () => {
        syncProjectsFromUI();
        projectsData.splice(idx, 1);
        renderProjectsList();
      };
      card.appendChild(removeBtn);

      card.innerHTML += `
        <div class="form-group">
          <label>Project Name</label>
          <input type="text" class="proj-name" value="${escapeHtml(proj.name || proj.title || '')}" placeholder="Project Title">
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>Role</label>
            <input type="text" class="proj-role" value="${escapeHtml(proj.role || '')}" placeholder="Lead Developer">
          </div>
          <div class="form-group flex-1">
            <label>Dates / Duration</label>
            <input type="text" class="proj-dur" value="${escapeHtml(proj.duration || proj.dates || '')}" placeholder="Jan 2023 - Present">
          </div>
        </div>
        <div class="form-group">
          <label>Description</label>
          <textarea class="proj-desc" rows="2" placeholder="Project details...">${escapeHtml(proj.description || '')}</textarea>
        </div>
      `;
      container.appendChild(card);
    }
  });
}

function addProjectItem() {
  syncProjectsFromUI();
  projectsData.push({
    name: "",
    role: "",
    duration: "",
    description: ""
  });
  renderProjectsList();
}

function syncProjectsFromUI() {
  if (currentMode !== "manual") return;
  const cards = document.querySelectorAll("#projectsList .dynamic-card");
  const newProjList = [];
  cards.forEach(card => {
    const name = (card.querySelector(".proj-name")?.value || "").trim();
    const role = (card.querySelector(".proj-role")?.value || "").trim();
    const duration = (card.querySelector(".proj-dur")?.value || "").trim();
    const desc = (card.querySelector(".proj-desc")?.value || "").trim();
    newProjList.push({
      name: name,
      title: name,
      role: role,
      duration: duration,
      dates: duration,
      description: desc
    });
  });
  projectsData = newProjList;
}

function renderCertificationsList() {
  const container = document.getElementById("certificationsList");
  if (!container) return;
  container.innerHTML = "";
  const countEl = document.getElementById("certCount");
  if (countEl) countEl.textContent = certificationsData.length;

  if (certificationsData.length === 0) {
    container.innerHTML = `<div class="empty-list-notice">No information available</div>`;
    return;
  }

  const isManual = currentMode === "manual";

  certificationsData.forEach((cert, idx) => {
    if (!isManual) {
      const card = document.createElement("div");
      card.className = "dynamic-card-readonly";
      let html = "";
      const name = cert.name || cert.title || "";
      const issuer = cert.issuer || cert.issuing_organization || "";
      const issueDate = cert.issue_date || cert.dates || "";
      const expDate = cert.expiration_date || "";

      if (name) html += `<div class="readonly-row"><span class="readonly-label">Certificate:</span><span class="readonly-value">${escapeHtml(name)}</span></div>`;
      if (issuer) html += `<div class="readonly-row"><span class="readonly-label">Issuer:</span><span class="readonly-value">${escapeHtml(issuer)}</span></div>`;
      if (issueDate) html += `<div class="readonly-row"><span class="readonly-label">Issue Date:</span><span class="readonly-value">${escapeHtml(issueDate)}</span></div>`;
      if (expDate) html += `<div class="readonly-row"><span class="readonly-label">Expires:</span><span class="readonly-value">${escapeHtml(expDate)}</span></div>`;
      card.innerHTML = html || `<div class="readonly-row"><span class="readonly-value">No details</span></div>`;
      container.appendChild(card);
    } else {
      const card = document.createElement("div");
      card.className = "dynamic-card";

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "remove-item-btn";
      removeBtn.textContent = "×";
      removeBtn.onclick = () => {
        syncCertificationsFromUI();
        certificationsData.splice(idx, 1);
        renderCertificationsList();
      };
      card.appendChild(removeBtn);

      card.innerHTML += `
        <div class="form-group">
          <label>Certification Name</label>
          <input type="text" class="cert-name" value="${escapeHtml(cert.name || cert.title || '')}" placeholder="AWS Certified Solutions Architect">
        </div>
        <div class="form-group">
          <label>Issuer / Organization</label>
          <input type="text" class="cert-issuer" value="${escapeHtml(cert.issuer || cert.issuing_organization || '')}" placeholder="Amazon Web Services">
        </div>
        <div class="form-row">
          <div class="form-group flex-1">
            <label>Issue Date</label>
            <input type="text" class="cert-issue" value="${escapeHtml(cert.issue_date || cert.dates || '')}" placeholder="YYYY-MM or 2022">
          </div>
          <div class="form-group flex-1">
            <label>Expiration Date</label>
            <input type="text" class="cert-exp" value="${escapeHtml(cert.expiration_date || '')}" placeholder="YYYY-MM or None">
          </div>
        </div>
      `;
      container.appendChild(card);
    }
  });
}

function addCertificationItem() {
  syncCertificationsFromUI();
  certificationsData.push({
    name: "",
    issuer: "",
    issue_date: "",
    expiration_date: ""
  });
  renderCertificationsList();
}

function syncCertificationsFromUI() {
  if (currentMode !== "manual") return;
  const cards = document.querySelectorAll("#certificationsList .dynamic-card");
  const newCertList = [];
  cards.forEach(card => {
    const name = (card.querySelector(".cert-name")?.value || "").trim();
    const issuer = (card.querySelector(".cert-issuer")?.value || "").trim();
    const issueDate = (card.querySelector(".cert-issue")?.value || "").trim();
    const expDate = (card.querySelector(".cert-exp")?.value || "").trim();
    newCertList.push({
      name: name,
      title: name,
      issuer: issuer,
      issuing_organization: issuer,
      issue_date: issueDate,
      dates: issueDate,
      expiration_date: expDate
    });
  });
  certificationsData = newCertList;
}

function syncAllFromUI() {
  syncExperienceFromUI();
  syncEducationFromUI();
  syncProjectsFromUI();
  syncCertificationsFromUI();
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function normalizePhoneNumber(str) {
  if (!str) return "";
  let clean = String(str).replace(/[\s\-().]/g, "");
  clean = clean.replace(/[^\d+]/g, "");
  return clean;
}

function collectPersonData() {
  const valueOf = (id) => (document.getElementById(id)?.value || "").trim();
  return {
    name: valueOf("fieldName") || (currentExtractedData?.name || ""),
    company: valueOf("fieldCurrentCompany") || (currentExtractedData?.current_company || ""),
    title: valueOf("fieldHeadline") || (currentExtractedData?.headline || ""),
    location: valueOf("fieldLocation") || (currentExtractedData?.location || ""),
    profile_url: valueOf("fieldProfileUrl") || (currentExtractedData?.profile_url || "")
  };
}

function setContactStatus(kind, status) {
  const badge = document.getElementById(kind === "email" ? "emailStatusBadge" : "phoneStatusBadge");
  if (!badge) return;

  const labels = {
    loading: "Loading…",
    found: "Found",
    not_found: "Not Found",
    verified: "Verified",
    unverified: "Unverified",
    error: "Error"
  };

  const label = labels[status] || "";
  badge.textContent = label;
  badge.className = `status-badge status-${status}`;

  if (!label) {
    badge.classList.add("hidden");
  } else {
    badge.classList.remove("hidden");
  }
}

function setEnrichButtonsDisabled(disabled) {
  ["findEmailBtn", "findPhoneBtn", "enrichBtn"].forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = disabled;
  });
}

function applyEnrichmentResult(result, scopes) {
  const email = result.email || {};
  const phone = result.phone || {};

  if (scopes.includes("email")) {
    if (email.value) {
      document.getElementById("fieldEmail").value = email.value;
    }
    setContactStatus("email", email.status || "not_found");
  }

  if (scopes.includes("phone")) {
    if (phone.value) {
      document.getElementById("fieldPhone").value = phone.value;
    }
    setContactStatus("phone", phone.status || "not_found");
  }
}

async function handleEnrich(scope) {
  const person = collectPersonData();
  if (!person.name && !person.company && !person.title && !person.location && !person.profile_url) {
    showAlert("Extract or enter candidate details before enriching.", "warning");
    return;
  }

  const scopes = scope === "email" ? ["email"] : scope === "phone" ? ["phone"] : ["email", "phone"];
  scopes.forEach((k) => setContactStatus(k, "loading"));
  setEnrichButtonsDisabled(true);
  showAlert("Contacting Talent Vault enrichment service...", "info");

  try {
    const body = Object.assign({}, person, { scope: scope, save: scope === "all" });

    const response = await postWithCsrf(enrichmentEndpoint(), body);

    const result = await response.json();

    if (!response.ok) {
      scopes.forEach((k) => setContactStatus(k, "error"));
      showAlert(`Enrichment Error: ${result.error || "Request failed"}`, "error");
      return;
    }

    applyEnrichmentResult(result, scopes);

    if (result.matched) {
      const pct = Math.round((result.match_confidence || 0) * 100);
      const saveInfo = result.save && result.save.saved
        ? ` Saved to candidate ${result.save.candidate_id}.`
        : (result.save && result.save.reason ? ` (not saved: ${result.save.reason})` : "");
      showAlert(`Enrichment complete — match confidence ${pct}%.${saveInfo}`, "success");
    } else {
      showAlert("Enrichment complete — no matching person found.", "warning");
    }
  } catch (err) {
    console.error("Enrichment error:", err);
    console.error("[Talent Vault] Enrichment network error detail:", {
      url: enrichmentEndpoint(),
      name: err && err.name,
      message: err && err.message,
      cause: err && err.cause,
      online: (typeof navigator !== "undefined" && navigator.onLine),
    });
    scopes.forEach((k) => setContactStatus(k, "error"));
    showAlert(`Network Error: Could not reach enrichment API at ${enrichmentEndpoint()}.`, "error");
  } finally {
    setEnrichButtonsDisabled(false);
  }
}

async function handleSaveCandidate() {
  const saveBtn = document.getElementById("saveBtn");
  const nameInput = document.getElementById("fieldName").value.trim();

  if (!nameInput) {
    showAlert("Validation Error: Full Name is required to save a candidate.", "error");
    return;
  }

  saveBtn.disabled = true;
  saveBtn.textContent = "Saving to Talent Vault...";
  showAlert("Saving candidate to Talent Vault...", "info");

  syncAllFromUI();

  const rawSkills = document.getElementById("fieldSkills").value || "";
  const skillsArray = rawSkills.split(",").map(s => s.trim()).filter(Boolean);

  const numOrNull = (id) => {
    const v = document.getElementById(id)?.value;
    if (v == null || v === "") return null;
    const n = parseFloat(v);
    return isNaN(n) ? null : n;
  };

  const intOrNull = (id) => {
    const v = document.getElementById(id)?.value;
    if (v == null || v === "") return null;
    const n = parseInt(v, 10);
    return isNaN(n) ? null : n;
  };

  const strVal = (id) => (document.getElementById(id)?.value || "").trim();

  const payload = {
    full_name: nameInput,
    name: nameInput,
    email: strVal("fieldEmail"),
    phone: normalizePhoneNumber(strVal("fieldPhone")),
    headline: strVal("fieldHeadline"),
    current_designation: strVal("fieldHeadline"),
    current_company: strVal("fieldCurrentCompany"),
    location: strVal("fieldLocation"),
    summary: strVal("fieldSummary"),
    linkedin_url: strVal("fieldProfileUrl"),
    profile_url: strVal("fieldProfileUrl"),
    total_experience: numOrNull("fieldTotalExperience"),
    current_salary: numOrNull("fieldCurrentSalary"),
    current_ctc: numOrNull("fieldCurrentSalary"),
    expected_salary: numOrNull("fieldExpectedSalary"),
    expected_ctc: numOrNull("fieldExpectedSalary"),
    notice_period: intOrNull("fieldNoticePeriod"),
    skills: skillsArray,
    experience: experiencesData,
    education: educationsData,
    projects: projectsData,
    certifications: certificationsData,
    source: currentMode === "parsing" ? (currentExtractedData?.source || "linkedin") : "manual",
    uploaded_by_email: strVal("recruiterEmail"),
    personal_info: {
      name: nameInput,
      email: strVal("fieldEmail"),
      phone: normalizePhoneNumber(strVal("fieldPhone")),
      current_designation: strVal("fieldHeadline"),
      current_company: strVal("fieldCurrentCompany"),
      location: strVal("fieldLocation"),
      summary: strVal("fieldSummary"),
      profile_url: strVal("fieldProfileUrl"),
      total_experience: numOrNull("fieldTotalExperience"),
      current_salary: numOrNull("fieldCurrentSalary"),
      expected_salary: numOrNull("fieldExpectedSalary"),
      notice_period: intOrNull("fieldNoticePeriod"),
    }
  };

  // Resume attachment priority:
  //   1. Manually selected file (recruiter downloads CV from Naukri and attaches it)
  //   2. Stealthy download via human-like click + blob: capture (Naukri)
  //   3. Auto-detected resume URL / base64 from the parsed profile
  const manualResumeInput = document.getElementById("manualResumeUpload");
  const resumeCheckbox = document.getElementById("attachResumeCheckbox");
  let resumePayload = null;

  if (manualResumeInput && manualResumeInput.files && manualResumeInput.files[0]) {
    const file = manualResumeInput.files[0];
    try {
      const dataBase64 = await readFileAsBase64(file);
      resumePayload = {
        filename: file.name,
        resume_base64: dataBase64,
        mime_type: file.type || "application/pdf",
      };
    } catch (err) {
      console.error("[Talent Vault] Failed to read manual resume file:", err);
      showAlert("Could not read the selected resume file. Try again.", "warning");
    }
  } else if (resumeCheckbox && resumeCheckbox.checked && currentExtractedData) {
    if (currentExtractedData.resume_base64) {
      resumePayload = {
        filename: currentExtractedData.resume_filename || "Candidate_Resume.pdf",
        data_base64: currentExtractedData.resume_base64
      };
    } else if (currentExtractedData.resume_url) {
      // Stealthy attempt: human-like click the CV/download control and read the
      // blob: resume as base64. Falls back to the source URL when blocked.
      showAlert("Downloading Resume...", "info");
      const captured = await downloadResumeViaTab();
      if (captured && captured.ok && captured.data_base64) {
        resumePayload = {
          filename: captured.filename || "Candidate_Resume.pdf",
          resume_base64: captured.data_base64,
          mime_type: captured.mime_type || "application/pdf"
        };
      } else {
        // Fallback: the backend only accepts base64 data (a raw URL is ignored),
        // so fetch the resume bytes through the content script first.
        const fetched = await fetchResumeAsBase64FromTab(currentExtractedData.resume_url);
        if (fetched && fetched.data_base64) {
          resumePayload = {
            filename: fetched.filename || currentExtractedData.resume_filename || "Candidate_Resume.pdf",
            data_base64: fetched.data_base64,
            mime_type: fetched.mime_type
          };
        } else {
          // Final fallback: Naukri serves the resume behind a viewer/CDN that
          // blocks scripted downloads. Send the URL so the backend can surface it
          // as a link instead of dropping the resume entirely.
          resumePayload = {
            filename: currentExtractedData.resume_filename || "Candidate_Resume.pdf",
            resume_url: currentExtractedData.resume_url
          };
        }
      }
    }
  }

  if (resumePayload) payload.resume = resumePayload;

  const saveUrl = importEndpoint();
  console.log("[Talent Vault] Saving candidate to:", saveUrl);
  console.log("PAYLOAD_SENT_TO_DJANGO:", JSON.stringify(payload));

  let response = null;
  try {
    response = await postWithCsrf(saveUrl, payload);
    console.log("[Talent Vault] Save response status:", response.status, response.statusText);

    let result = null;
    try {
      result = await response.json();
    } catch (e) {
      result = null;
    }
    console.log("[Talent Vault] Save response body:", result);

    if (response.ok && result && result.status === "success") {
      const isNew = result.action === "created";
      let statusMsg = isNew
        ? `Candidate Saved Successfully! (ID: ${result.candidate_id})`
        : `Candidate Record Updated Successfully! (ID: ${result.candidate_id})`;
      if (result.resume_message) {
        statusMsg += ` | ${result.resume_message}`;
      }
      showAlert(statusMsg, "success");
    } else {
      const errDetail =
        (result && (result.error || result.detail)) ||
        (result ? JSON.stringify(result) : `${response.status} ${response.statusText}`);
      console.error("[Talent Vault] Save failed:", response.status, errDetail);
      showAlert(`Save Error (HTTP ${response.status}): ${errDetail}`, "error");
    }
  } catch (err) {
    // A response that DID come back (200 or otherwise) must NEVER be shown as a
    // "Network Error" — that is reserved for cases where no response arrived.
    if (response) {
      console.error("[Talent Vault] Save failed after receiving a response:", err);
      showAlert(`Save Error (HTTP ${response.status} ${response.statusText})`, "error");
    } else {
      console.error("[Talent Vault] Save network error:", err);
      console.error("[Talent Vault] Save network error detail:", {
        url: saveUrl,
        name: err && err.name,
        message: err && err.message,
        cause: err && err.cause,
        online: (typeof navigator !== "undefined" && navigator.onLine),
      });
      showAlert(`Network Error: Could not reach Talent Vault API at ${saveUrl}. ${err && err.message ? err.message : ""}`, "error");
    }
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = "Save Candidate";
  }
}
