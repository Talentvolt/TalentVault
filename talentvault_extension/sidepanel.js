// ---------------------------------------------------------------------------
// API configuration (single source of truth).
//
// The production build ALWAYS talks to the hosted TalentVault backend and never
// to a local development server. Authentication, authorization, CORS and CSRF
// are all handled server-side; the extension never ships a secret or API key.
//
// For local development you may override the base URL at runtime without
// editing this file, e.g. from the extension's DevTools console:
//   chrome.storage.local.set({ apiBaseUrl: "http://<your-local-dev-host>" });
// The override is read from chrome.storage.local each time the panel opens.
// ---------------------------------------------------------------------------
const DEFAULT_API_BASE_URL = "https://talent-vault.in";
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
let csrfToken = null;

document.addEventListener("DOMContentLoaded", () => {
  const parsingModeBtn = document.getElementById("parsingModeBtn");
  const manualModeBtn = document.getElementById("manualModeBtn");
  const importBtn = document.getElementById("importBtn");
  const saveBtn = document.getElementById("saveBtn");
  const addExpBtn = document.getElementById("addExpBtn");
  const addEduBtn = document.getElementById("addEduBtn");
  const findEmailBtn = document.getElementById("findEmailBtn");
  const findPhoneBtn = document.getElementById("findPhoneBtn");
  const enrichBtn = document.getElementById("enrichBtn");

  parsingModeBtn.addEventListener("click", () => setMode("parsing"));
  manualModeBtn.addEventListener("click", () => setMode("manual"));

  importBtn.addEventListener("click", handleExtractCandidate);
  saveBtn.addEventListener("click", handleSaveCandidate);
  addExpBtn.addEventListener("click", () => addExperienceItem());
  addEduBtn.addEventListener("click", () => addEducationItem());
  findEmailBtn.addEventListener("click", () => handleEnrich("email"));
  findPhoneBtn.addEventListener("click", () => handleEnrich("phone"));
  enrichBtn.addEventListener("click", () => handleEnrich("all"));

  // Resolve the API base URL (production default, storage override for dev)
  // before making any network call, then prefetch the CSRF token.
  loadApiBaseUrl().then(() => {
    fetchCsrfToken();
  });
});

async function fetchCsrfToken() {
  try {
    const res = await fetch(importEndpoint(), { method: "GET", credentials: "include" });
    if (res.ok) {
      const data = await res.json();
      if (data.csrfToken) {
        csrfToken = data.csrfToken;
      }
    }
  } catch (e) {
    console.warn("Could not prefetch CSRF token:", e);
  }
}

function setMode(mode) {
  currentMode = mode;
  const parsingBtn = document.getElementById("parsingModeBtn");
  const manualBtn = document.getElementById("manualModeBtn");
  const extractCard = document.getElementById("extractCard");
  const candidateForm = document.getElementById("candidateForm");
  const sourceBadge = document.getElementById("sourceBadge");

  if (mode === "parsing") {
    parsingBtn.classList.add("active");
    manualBtn.classList.remove("active");
    extractCard.classList.remove("hidden");
    if (!currentExtractedData) {
      candidateForm.classList.add("hidden");
    } else {
      candidateForm.classList.remove("hidden");
    }
    sourceBadge.textContent = `Source: ${(currentExtractedData?.source || "LINKEDIN").toUpperCase()}`;
    sourceBadge.className = `source-tag source-${currentExtractedData?.source || "linkedin"}`;
  } else {
    manualBtn.classList.add("active");
    parsingBtn.classList.remove("active");
    extractCard.classList.add("hidden");
    candidateForm.classList.remove("hidden");
    sourceBadge.textContent = "Source: MANUAL";
    sourceBadge.className = "source-tag source-manual";
  }
}

function showAlert(message, type = "info") {
  const alertEl = document.getElementById("statusAlert");
  alertEl.className = `alert alert-${type}`;
  alertEl.textContent = message;
  alertEl.classList.remove("hidden");
}

function handleExtractCandidate() {
  showAlert("Querying active tab for candidate data...", "info");

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || tabs.length === 0) {
      showAlert("No active tab detected.", "error");
      return;
    }

    const activeTab = tabs[0];
    const tabUrl = activeTab.url || "";

    if (!tabUrl.includes("linkedin.com") && !tabUrl.includes("naukri.com")) {
      showAlert(`Active page is not LinkedIn or Naukri. Attempting extraction...`, "warning");
    }

    chrome.tabs.sendMessage(activeTab.id, { action: "extract_candidate_data" }, (response) => {
      if (chrome.runtime.lastError) {
        chrome.scripting.executeScript({
          target: { tabId: activeTab.id },
          files: ["content.js"]
        }, () => {
          if (chrome.runtime.lastError) {
            showAlert("Failed to inject content script: " + chrome.runtime.lastError.message, "error");
            return;
          }
          setTimeout(() => {
            chrome.tabs.sendMessage(activeTab.id, { action: "extract_candidate_data" }, (retryResponse) => {
              if (chrome.runtime.lastError || !retryResponse) {
                showAlert("Could not extract data from page. Please refresh the candidate page and try again.", "error");
              } else {
                populateForm(retryResponse.data);
              }
            });
          }, 300);
        });
      } else if (response && response.status === "success") {
        populateForm(response.data);
      } else {
        showAlert("Failed to extract data: " + (response?.error || "Unknown error"), "error");
      }
    });
  });
}

function populateForm(data) {
  currentExtractedData = data;

  document.getElementById("fieldName").value = data.name || "";
  document.getElementById("fieldEmail").value = data.email || "";
  document.getElementById("fieldPhone").value = normalizePhoneNumber(data.phone);
  document.getElementById("fieldHeadline").value = data.headline || "";
  document.getElementById("fieldCurrentCompany").value = data.current_company || "";
  document.getElementById("fieldLocation").value = data.location || "";
  document.getElementById("fieldSummary").value = data.summary || "";
  document.getElementById("fieldProfileUrl").value = data.profile_url || "";
  document.getElementById("fieldSkills").value = Array.isArray(data.skills) ? data.skills.join(", ") : "";

  if (data.total_experience) {
    document.getElementById("fieldTotalExperience").value = data.total_experience;
  }
  if (data.current_salary) {
    document.getElementById("fieldCurrentSalary").value = data.current_salary;
  }
  if (data.expected_salary) {
    document.getElementById("fieldExpectedSalary").value = data.expected_salary;
  }
  if (data.notice_period !== undefined && data.notice_period !== null) {
    document.getElementById("fieldNoticePeriod").value = data.notice_period;
  }

  experiencesData = data.experience || [];
  educationsData = data.education || [];

  renderExperienceList();
  renderEducationList();

  const sourceBadge = document.getElementById("sourceBadge");
  sourceBadge.textContent = `Source: ${(data.source || "linkedin").toUpperCase()}`;
  sourceBadge.className = `source-tag source-${data.source || "linkedin"}`;

  document.getElementById("candidateForm").classList.remove("hidden");
  showAlert(`Extracted data for "${data.name || 'Candidate'}". Review and edit fields before saving.`, "success");
}

function renderExperienceList() {
  const container = document.getElementById("experienceList");
  container.innerHTML = "";
  document.getElementById("expCount").textContent = experiencesData.length;

  experiencesData.forEach((exp, idx) => {
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
          <label>Dates / Duration</label>
          <input type="text" class="exp-dur" value="${escapeHtml(exp.duration || exp.dates || '')}" placeholder="Jan 2021 - Present">
        </div>
        <div class="form-group flex-1">
          <label>Location</label>
          <input type="text" class="exp-loc" value="${escapeHtml(exp.location || '')}" placeholder="City, Country">
        </div>
      </div>
      <div class="form-group">
        <label>Description</label>
        <textarea class="exp-desc" rows="2" placeholder="Experience details...">${escapeHtml(exp.description || '')}</textarea>
      </div>
    `;
    container.appendChild(card);
  });
}

function addExperienceItem() {
  syncExperienceFromUI();
  experiencesData.push({
    company_name: "",
    designation: "",
    duration: "",
    location: "",
    description: ""
  });
  renderExperienceList();
}

function syncExperienceFromUI() {
  const cards = document.querySelectorAll("#experienceList .dynamic-card");
  const newExpList = [];
  cards.forEach(card => {
    newExpList.push({
      company_name: card.querySelector(".exp-company").value.trim(),
      designation: card.querySelector(".exp-desig").value.trim(),
      duration: card.querySelector(".exp-dur").value.trim(),
      dates: card.querySelector(".exp-dur").value.trim(),
      location: card.querySelector(".exp-loc").value.trim(),
      description: card.querySelector(".exp-desc").value.trim()
    });
  });
  experiencesData = newExpList;
}

function renderEducationList() {
  const container = document.getElementById("educationList");
  container.innerHTML = "";
  document.getElementById("eduCount").textContent = educationsData.length;

  educationsData.forEach((edu, idx) => {
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
      <div class="form-group">
        <label>Dates / Years</label>
        <input type="text" class="edu-dur" value="${escapeHtml(edu.dates || edu.duration || '')}" placeholder="2016 - 2020">
      </div>
    `;
    container.appendChild(card);
  });
}

function addEducationItem() {
  syncEducationFromUI();
  educationsData.push({
    institution: "",
    degree: "",
    field_of_study: "",
    dates: ""
  });
  renderEducationList();
}

function syncEducationFromUI() {
  const cards = document.querySelectorAll("#educationList .dynamic-card");
  const newEduList = [];
  cards.forEach(card => {
    newEduList.push({
      institution: card.querySelector(".edu-inst").value.trim(),
      degree: card.querySelector(".edu-deg").value.trim(),
      field_of_study: card.querySelector(".edu-field").value.trim(),
      dates: card.querySelector(".edu-dur").value.trim(),
      duration: card.querySelector(".edu-dur").value.trim()
    });
  });
  educationsData = newEduList;
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
  showAlert("Contacting TalentVault enrichment service...", "info");

  try {
    if (!csrfToken) {
      await fetchCsrfToken();
    }

    const headers = {
      "Content-Type": "application/json",
      "Accept": "application/json"
    };
    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken;
    }

    const body = Object.assign({}, person, { scope: scope, save: scope === "all" });

    const response = await fetch(enrichmentEndpoint(), {
      method: "POST",
      headers: headers,
      credentials: "include",
      body: JSON.stringify(body)
    });

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
  saveBtn.textContent = "Saving to TalentVault...";
  showAlert("Saving candidate to TalentVault...", "info");

  syncExperienceFromUI();
  syncEducationFromUI();

  const rawSkills = document.getElementById("fieldSkills").value || "";
  const skillsArray = rawSkills.split(",").map(s => s.trim()).filter(Boolean);

  const payload = {
    full_name: nameInput,
    name: nameInput,
    email: document.getElementById("fieldEmail").value.trim(),
    phone: normalizePhoneNumber(document.getElementById("fieldPhone").value),
    headline: document.getElementById("fieldHeadline").value.trim(),
    current_designation: document.getElementById("fieldHeadline").value.trim(),
    current_company: document.getElementById("fieldCurrentCompany").value.trim(),
    location: document.getElementById("fieldLocation").value.trim(),
    summary: document.getElementById("fieldSummary").value.trim(),
    linkedin_url: document.getElementById("fieldProfileUrl").value.trim(),
    profile_url: document.getElementById("fieldProfileUrl").value.trim(),
    total_experience: document.getElementById("fieldTotalExperience").value || null,
    current_salary: document.getElementById("fieldCurrentSalary").value || null,
    expected_salary: document.getElementById("fieldExpectedSalary").value || null,
    notice_period: document.getElementById("fieldNoticePeriod").value || null,
    skills: skillsArray,
    experience: experiencesData,
    education: educationsData,
    source: currentMode === "parsing" ? (currentExtractedData?.source || "linkedin") : "manual"
  };

  try {
    if (!csrfToken) {
      await fetchCsrfToken();
    }

    const headers = {
      "Content-Type": "application/json",
      "Accept": "application/json"
    };
    if (csrfToken) {
      headers["X-CSRFToken"] = csrfToken;
    }

    const response = await fetch(importEndpoint(), {
      method: "POST",
      headers: headers,
      credentials: "include",
      body: JSON.stringify(payload)
    });

    const result = await response.json();

    if (response.ok && result.status === "success") {
      const isNew = result.action === "created";
      const statusMsg = isNew
        ? `Candidate Saved Successfully! (ID: ${result.candidate_id})`
        : `Candidate Record Updated Successfully! (ID: ${result.candidate_id})`;
      showAlert(statusMsg, "success");
    } else {
      const errDetail = result.error || (typeof result === "object" ? JSON.stringify(result) : "Save failed");
      showAlert(`Save Error: ${errDetail}`, "error");
    }
  } catch (err) {
    console.error("Save error:", err);
    showAlert(`Network Error: Could not reach TalentVault API at ${importEndpoint()}.`, "error");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = "Save Candidate";
  }
}
