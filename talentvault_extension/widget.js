// Talent Vault — In-page profile widget with Parsing Mode and Manual Mode.
(function () {
  "use strict";
  if (globalThis.__talentVaultWidgetLoaded) return;
  globalThis.__talentVaultWidgetLoaded = true;

  const TV_BUILD = "tv-1.0.6-20261021";
  try {
    const extId = (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id) || "unknown";
    const url = (typeof location !== "undefined" && location.href) || "";
    console.log(`[Talent Vault Debug] widget.js loaded | build=${TV_BUILD} | extId=${extId} | profile=${url}`);
    console.log(`[Talent Vault Debug] extractPageData defined=${typeof extractPageData === "function"} | preparePage defined=${typeof preparePage === "function"}`);
  } catch (e) {}

  const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
  const IMPORT_PATH = "/api/v1/candidates/import/";

  const WIDGET_CSS = `
    :host { all: initial; }
    .tv-icon {
      position: fixed; right: 16px; top: 50%; transform: translateY(-50%);
      width: 44px; height: 44px; border-radius: 50%;
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
      color: #fff; font-weight: 800; font-size: 16px; line-height: 1;
      display: flex; align-items: center; justify-content: center;
      cursor: pointer; border: none; box-shadow: 0 6px 16px rgba(0,0,0,0.25);
      z-index: 2147483000; transition: transform 0.15s ease;
    }
    .tv-icon:hover { transform: translateY(-50%) scale(1.08); }
    .tv-panel {
      position: fixed; right: 72px; top: 60px; width: 380px;
      max-height: calc(100vh - 80px); display: flex; flex-direction: column;
      background: #fff; color: #1e293b; border: 1px solid #cbd5e1;
      border-radius: 12px; box-shadow: 0 12px 40px rgba(15,23,42,0.28);
      z-index: 2147483000; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      font-size: 13px; line-height: 1.4; overflow: hidden;
    }
    .tv-panel.hidden, .hidden { display: none !important; }
    .tv-panel.tv-minimized { max-height: 48px; }
    .tv-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 14px; background: #0f172a; color: #fff; flex-shrink: 0;
      border-radius: 12px 12px 0 0;
    }
    .tv-brand { font-weight: 700; font-size: 14px; letter-spacing: 0.3px; }
    .tv-ctrl { display: flex; gap: 6px; }
    .tv-btn-ctl {
      background: transparent; border: 1px solid #334155; color: #e2e8f0;
      width: 24px; height: 24px; border-radius: 5px; cursor: pointer;
      font-size: 13px; line-height: 1; display: flex; align-items: center; justify-content: center;
    }
    .tv-btn-ctl:hover { background: #1e293b; color: #fff; }
    .tv-tabs-bar {
      display: flex; background: #f8fafc; padding: 8px 12px; border-bottom: 1px solid #e2e8f0;
      gap: 8px; flex-shrink: 0;
    }
    .tv-tab {
      flex: 1; border: 1px solid #cbd5e1; background: #fff; cursor: pointer;
      font-size: 12px; font-weight: 600; color: #64748b; padding: 7px 10px; border-radius: 6px;
      text-align: center; transition: all 0.15s ease; outline: none;
    }
    .tv-tab:hover { color: #1e293b; border-color: #94a3b8; }
    .tv-tab.active {
      background: #2563eb; color: #fff; border-color: #1d4ed8;
      box-shadow: 0 1px 3px rgba(37,99,235,0.3);
    }
    .tv-body {
      flex: 1; overflow-y: auto; padding: 12px; min-height: 0;
    }
    .tv-status { padding: 8px 10px; border-radius: 6px; font-size: 12px; margin-bottom: 10px; }
    .tv-info { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
    .tv-success { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
    .tv-warning { background: #fefce8; color: #a16207; border: 1px solid #fef08a; }
    .tv-error { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
    .tv-parse { display: flex; flex-direction: column; gap: 8px; }
    .tv-loading { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 18px 0; color: #2563eb; font-weight: 600; }
    .tv-spinner {
      width: 16px; height: 16px; border: 2px solid #bfdbfe; border-top-color: #2563eb;
      border-radius: 50%; animation: tv-spin 0.7s linear infinite;
    }
    @keyframes tv-spin { to { transform: rotate(360deg); } }
    .tv-parse-error { padding: 8px 10px; border-radius: 6px; background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; font-size: 12px; }
    .tv-retry {
      padding: 8px; border: 1px solid #2563eb; color: #2563eb; background: #fff;
      border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 12px;
    }
    .tv-retry:hover { background: #eff6ff; }
    .tv-field { margin-bottom: 10px; }
    .tv-field label { display: block; font-size: 11px; font-weight: 600; color: #475569; margin-bottom: 3px; }
    .tv-field input, .tv-field textarea {
      width: 100%; box-sizing: border-box; padding: 6px 8px; font-size: 12px;
      border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #1e293b; font-family: inherit;
    }
    .tv-field input:focus, .tv-field textarea:focus {
      outline: none; border-color: #2563eb; box-shadow: 0 0 0 2px rgba(37,99,235,0.15);
    }
    .tv-field textarea { resize: vertical; }
    .tv-row { display: flex; gap: 8px; margin-bottom: 10px; }
    .tv-col { flex: 1; min-width: 0; }
    .tv-col .tv-field { margin-bottom: 0; }
    .tv-save {
      width: 100%; padding: 10px; border: none; border-radius: 6px; cursor: pointer;
      background: #16a34a; color: #fff; font-weight: 700; font-size: 13px; margin-top: 14px;
      transition: background 0.15s ease;
    }
    .tv-save:hover { background: #15803d; }
    .tv-save:disabled { opacity: 0.6; cursor: not-allowed; }
    .tv-section { margin-top: 14px; border-top: 1px solid #e2e8f0; padding-top: 10px; }
    .tv-section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; font-weight: 700; font-size: 12px; color: #0f172a; }
    .tv-add {
      border: 1px solid #2563eb; color: #2563eb; background: #fff; border-radius: 5px;
      padding: 3px 8px; font-size: 11px; font-weight: 600; cursor: pointer;
    }
    .tv-add:hover { background: #eff6ff; }
    .tv-empty { padding: 8px; border-radius: 6px; background: #f8fafc; color: #64748b; font-size: 12px; text-align: center; }
    .tv-entry { position: relative; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px; margin-bottom: 8px; background: #f8fafc; }
    .tv-entry-remove { position: absolute; top: 6px; right: 6px; border: none; background: transparent; color: #ef4444; font-size: 14px; cursor: pointer; font-weight: 700; padding: 2px 4px; }
    .tv-entry-remove:hover { color: #b91c1c; }
    .tv-entry-field { margin-bottom: 6px; }
    .tv-entry-field:last-child { margin-bottom: 0; }
    .tv-entry-field label { display: block; font-size: 10px; font-weight: 600; color: #64748b; margin-bottom: 2px; }
    .tv-entry-field input, .tv-entry-field textarea {
      width: 100%; box-sizing: border-box; padding: 5px 7px; font-size: 12px;
      border: 1px solid #cbd5e1; border-radius: 5px; background: #fff; color: #1e293b; font-family: inherit;
    }
    .tv-entry-field textarea { resize: vertical; }
    .tv-entry-readonly { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px; margin-bottom: 8px; }
    .tv-entry-readonly-row { display: flex; gap: 6px; font-size: 12px; margin-bottom: 3px; }
    .tv-entry-readonly-row:last-child { margin-bottom: 0; }
    .tv-entry-readonly-label { font-weight: 700; color: #475569; min-width: 90px; flex-shrink: 0; }
    .tv-entry-readonly-value { color: #1e293b; white-space: pre-wrap; word-break: break-word; }
    .tv-check { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px; font-weight: 600; color: #1e293b; padding: 6px 0; }
    .tv-check input { width: 16px; height: 16px; accent-color: #2563eb; }
    .tv-resume-badge { display: inline-block; font-size: 11px; color: #1d4ed8; background: #eff6ff; border: 1px solid #bfdbfe; padding: 3px 6px; border-radius: 4px; word-break: break-all; margin-top: 4px; }
    .tv-manual-upload { padding: 8px 0; }
    .tv-manual-upload label { display: block; font-size: 11px; font-weight: 600; color: #475569; margin-bottom: 3px; }
    .tv-manual-upload input[type="file"] {
      width: 100%; box-sizing: border-box; padding: 6px 8px; font-size: 12px;
      border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #1e293b; font-family: inherit;
    }
  `;

  const state = {
    mode: "parsing", // "parsing" | "manual"
    extracted: null,
    parseInFlight: false,
    minimized: false,
    experiences: [],
    educations: [],
    projects: [],
    certifications: [],
    profileKey: "",
  };

  let currentParseToken = 0;

  function makeEl(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = text;
    return el;
  }

  function tick() {
    return new Promise((resolve) => setTimeout(resolve, 0));
  }

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

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

  // ---- Host + shadow root ----
  const host = makeEl("div");
  host.id = "talent-vault-widget";
  const shadow = host.attachShadow({ mode: "open" });

  const styleEl = makeEl("style");
  styleEl.textContent = WIDGET_CSS;
  shadow.appendChild(styleEl);

  // ---- Floating TV icon ----
  const iconEl = makeEl("button", "tv-icon", "TV");
  iconEl.type = "button";
  iconEl.setAttribute("aria-label", "Open Talent Vault");
  iconEl.title = "Open Talent Vault";
  shadow.appendChild(iconEl);

  // ---- Main Panel ----
  const panelEl = makeEl("div", "tv-panel hidden");
  panelEl.setAttribute("role", "dialog");
  panelEl.setAttribute("aria-label", "Talent Vault");
  shadow.appendChild(panelEl);

  // 1. Header (fixed at top)
  const headerEl = makeEl("div", "tv-header");
  const brandEl = makeEl("span", "tv-brand", "Talent Vault");
  const ctrlEl = makeEl("div", "tv-ctrl");
  const minEl = makeEl("button", "tv-btn-ctl", "—");
  minEl.type = "button"; minEl.title = "Minimize"; minEl.setAttribute("aria-label", "Minimize");
  const closeEl = makeEl("button", "tv-btn-ctl", "✕");
  closeEl.type = "button"; closeEl.title = "Close"; closeEl.setAttribute("aria-label", "Close");
  ctrlEl.appendChild(minEl);
  ctrlEl.appendChild(closeEl);
  headerEl.appendChild(brandEl);
  headerEl.appendChild(ctrlEl);
  panelEl.appendChild(headerEl);

  // 2. Mode Switcher (pinned visibly near the top, directly under header)
  const tabsBarEl = makeEl("div", "tv-tabs-bar");
  const parsingTab = makeEl("button", "tv-tab active", "Parsing Mode");
  parsingTab.type = "button";
  const manualTab = makeEl("button", "tv-tab", "Manual Mode");
  manualTab.type = "button";
  tabsBarEl.appendChild(parsingTab);
  tabsBarEl.appendChild(manualTab);
  panelEl.appendChild(tabsBarEl);

  // 3. Scrollable Body
  const bodyEl = makeEl("div", "tv-body");
  panelEl.appendChild(bodyEl);

  const statusEl = makeEl("div", "tv-status hidden");
  bodyEl.appendChild(statusEl);

  // Parse area
  const parseAreaEl = makeEl("div", "tv-parse");
  const loadingEl = makeEl("div", "tv-loading hidden");
  loadingEl.appendChild(makeEl("span", "tv-spinner"));
  loadingEl.appendChild(makeEl("span", "", "Parsing profile…"));
  const parseErrorEl = makeEl("div", "tv-parse-error hidden");
  const retryEl = makeEl("button", "tv-retry hidden", "Retry Parse");
  retryEl.type = "button";
  parseAreaEl.appendChild(loadingEl);
  parseAreaEl.appendChild(parseErrorEl);
  parseAreaEl.appendChild(retryEl);
  bodyEl.appendChild(parseAreaEl);

  // Form container
  const formEl = makeEl("div", "tv-form hidden");

  function addField(id, label, type, container, step) {
    const parent = container || formEl;
    const group = makeEl("div", "tv-field");
    const lbl = makeEl("label", "", label);
    lbl.setAttribute("for", "tv-" + id);
    let input;
    if (type === "textarea") {
      input = makeEl("textarea");
    } else {
      input = makeEl("input");
      input.type = type;
      if (step) input.step = step;
    }
    input.id = "tv-" + id;
    group.appendChild(lbl);
    group.appendChild(input);
    parent.appendChild(group);
    return input;
  }

  function addRow(id1, label1, type1, step1, id2, label2, type2, step2) {
    const row = makeEl("div", "tv-row");
    const col1 = makeEl("div", "tv-col");
    const col2 = makeEl("div", "tv-col");
    const inp1 = addField(id1, label1, type1, col1, step1);
    const inp2 = addField(id2, label2, type2, col2, step2);
    row.appendChild(col1);
    row.appendChild(col2);
    formEl.appendChild(row);
    return [inp1, inp2];
  }

  // --- Personal Information Section ---
  const recruiterEmailInput = addField("recruiter-email", "Recruiter Email (your login)", "email");
  const nameInput = addField("name", "Full Name *", "text");
  const [headlineInput, companyInput] = addRow("headline", "Designation", "text", null, "company", "Company", "text", null);
  const locationInput = addField("location", "Location", "text");
  const [emailInput, phoneInput] = addRow("email", "Email", "email", null, "phone", "Phone", "text", null);
  const [totalExpInput, noticePeriodInput] = addRow("total-exp", "Total Experience (years)", "number", "0.1", "notice-period", "Notice Period (days)", "number", "1");
  const [currentCtcInput, expectedCtcInput] = addRow("current-ctc", "Current CTC (LPA)", "number", "0.1", "expected-ctc", "Expected CTC (LPA)", "number", "0.1");
  const summaryInput = addField("summary", "Profile Summary", "textarea");
  const profileUrlInput = addField("profile_url", "LinkedIn/Naukri Profile URL", "text");
  const skillsInput = addField("skills", "Skills (comma-separated)", "text");

  // Optional resume attachment section (shown only when a real downloadable resume is detected).
  const resumeSection = makeEl("div", "tv-section tv-resume hidden");
  const resumeHead = makeEl("div", "tv-section-head");
  resumeHead.appendChild(makeEl("span", "", "Resume"));
  resumeSection.appendChild(resumeHead);
  const resumeLabel = makeEl("label", "tv-check");
  const resumeCheckbox = makeEl("input");
  resumeCheckbox.type = "checkbox";
  resumeCheckbox.id = "tv-resume-check";
  const resumeCheckText = makeEl("span", "tv-check-text", "Attach Available Resume");
  resumeLabel.appendChild(resumeCheckbox);
  resumeLabel.appendChild(resumeCheckText);
  resumeSection.appendChild(resumeLabel);
  const resumeHint = makeEl("div", "tv-empty", "No resume available");
  resumeSection.appendChild(resumeHint);
  formEl.appendChild(resumeSection);

  // Manual resume upload section (always visible, even when no resume was
  // auto-detected). The recruiter downloads the CV from Naukri and attaches it here.
  const manualUploadSection = makeEl("div", "tv-section tv-manual-upload");
  const manualUploadHead = makeEl("div", "tv-section-head");
  manualUploadHead.appendChild(makeEl("span", "", "Manual Resume Upload"));
  manualUploadSection.appendChild(manualUploadHead);
  const manualUploadLabel = makeEl("label", "", "Or upload a resume file (PDF / DOC / DOCX)");
  manualUploadSection.appendChild(manualUploadLabel);
  const manualUploadInput = makeEl("input");
  manualUploadInput.type = "file";
  manualUploadInput.accept = ".pdf,.doc,.docx";
  manualUploadInput.id = "tv-manual-resume";
  manualUploadSection.appendChild(manualUploadInput);
  const manualUploadFileName = makeEl("div", "tv-resume-badge hidden", "");
  manualUploadSection.appendChild(manualUploadFileName);
  formEl.appendChild(manualUploadSection);

  // Work Experience section
  const expSection = makeEl("div", "tv-section");
  const expHead = makeEl("div", "tv-section-head");
  expHead.appendChild(makeEl("span", "", "Work Experience"));
  const expAddEl = makeEl("button", "tv-add", "+ Add Entry");
  expAddEl.type = "button";
  expHead.appendChild(expAddEl);
  expSection.appendChild(expHead);
  const expEmptyEl = makeEl("div", "tv-empty hidden", "No information available");
  expSection.appendChild(expEmptyEl);
  const expListEl = makeEl("div", "tv-list");
  expSection.appendChild(expListEl);
  formEl.appendChild(expSection);

  // Education section
  const eduSection = makeEl("div", "tv-section");
  const eduHead = makeEl("div", "tv-section-head");
  eduHead.appendChild(makeEl("span", "", "Education History"));
  const eduAddEl = makeEl("button", "tv-add", "+ Add Entry");
  eduAddEl.type = "button";
  eduHead.appendChild(eduAddEl);
  eduSection.appendChild(eduHead);
  const eduEmptyEl = makeEl("div", "tv-empty hidden", "No information available");
  eduSection.appendChild(eduEmptyEl);
  const eduListEl = makeEl("div", "tv-list");
  eduSection.appendChild(eduListEl);
  formEl.appendChild(eduSection);

  // Projects section
  const projSection = makeEl("div", "tv-section");
  const projHead = makeEl("div", "tv-section-head");
  projHead.appendChild(makeEl("span", "", "Projects"));
  const projAddEl = makeEl("button", "tv-add", "+ Add Entry");
  projAddEl.type = "button";
  projHead.appendChild(projAddEl);
  projSection.appendChild(projHead);
  const projEmptyEl = makeEl("div", "tv-empty hidden", "No projects listed");
  projSection.appendChild(projEmptyEl);
  const projListEl = makeEl("div", "tv-list");
  projSection.appendChild(projListEl);
  formEl.appendChild(projSection);

  // Certifications section
  const certSection = makeEl("div", "tv-section");
  const certHead = makeEl("div", "tv-section-head");
  certHead.appendChild(makeEl("span", "", "Certifications"));
  const certAddEl = makeEl("button", "tv-add", "+ Add Entry");
  certAddEl.type = "button";
  certHead.appendChild(certAddEl);
  certSection.appendChild(certHead);
  const certEmptyEl = makeEl("div", "tv-empty hidden", "No certifications listed");
  certSection.appendChild(certEmptyEl);
  const certListEl = makeEl("div", "tv-list");
  certSection.appendChild(certListEl);
  formEl.appendChild(certSection);

  const saveEl = makeEl("button", "tv-save", "Save Candidate");
  saveEl.type = "button";
  formEl.appendChild(saveEl);

  bodyEl.appendChild(formEl);

  // Attach host to the document
  if (typeof document !== "undefined" && document.body) {
    document.body.appendChild(host);
  }

  // Persist the recruiter's email so they enter it only once.
  const RECRUITER_EMAIL_KEY = "recruiterEmail";
  function loadRecruiterEmail() {
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
  }
  function saveRecruiterEmail() {
    try {
      const email = (recruiterEmailInput.value || "").trim();
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ [RECRUITER_EMAIL_KEY]: email });
      }
    } catch (e) {}
  }
  recruiterEmailInput.addEventListener("change", saveRecruiterEmail);
  recruiterEmailInput.addEventListener("blur", saveRecruiterEmail);
  loadRecruiterEmail();

  // ---- Status & parse state helpers ----
  function setStatus(message, type) {
    statusEl.textContent = message || "";
    if (message) {
      statusEl.className = "tv-status tv-" + (type || "info");
    } else {
      statusEl.className = "tv-status hidden";
    }
  }

  function setLoading(active) {
    if (active) {
      loadingEl.classList.remove("hidden");
      clearParseError();
    } else {
      loadingEl.classList.add("hidden");
    }
  }

  function showParseError(message) {
    parseErrorEl.textContent = message;
    parseErrorEl.classList.remove("hidden");
    retryEl.classList.remove("hidden");
  }

  function clearParseError() {
    parseErrorEl.classList.add("hidden");
    retryEl.classList.add("hidden");
  }

  function currentProfileKey() {
    try {
      const loc =
        (typeof location !== "undefined" && location) ||
        (typeof window !== "undefined" && window.location) ||
        null;
      if (!loc || !loc.href) return "";
      const u = new URL(loc.href);
      const host = u.hostname.toLowerCase();
      const path = u.pathname.replace(/\/+$/, "");
      // Naukri identifies a candidate by `sid` (or a stable id) in the URL, not
      // just the generic /v3/preview path. Keep those params so two different
      // candidates on the same path are treated as different profiles and the
      // old candidate's data is correctly cleared on navigation.
      if (host.includes("naukri.com")) {
        const stable = ["sid", "id", "profileid", "profile_id", "candidateid", "candidate_id", "resumeid", "resume_id"];
        const kept = [];
        u.searchParams.forEach((v, k) => {
          if (stable.indexOf(k.toLowerCase()) !== -1 && v) kept.push(k + "=" + encodeURIComponent(v));
        });
        return u.origin + path + (kept.length ? "?" + kept.join("&") : "");
      }
      return u.origin + path;
    } catch (e) {
      return "";
    }
  }

  // Clear previous candidate's data immediately upon navigation or reset
  function clearParsedData() {
    state.extracted = null;
    state.profileKey = "";
    state.experiences = [];
    state.educations = [];
    state.projects = [];
    state.certifications = [];
    nameInput.value = "";
    headlineInput.value = "";
    companyInput.value = "";
    locationInput.value = "";
    emailInput.value = "";
    phoneInput.value = "";
    totalExpInput.value = "";
    currentCtcInput.value = "";
    expectedCtcInput.value = "";
    noticePeriodInput.value = "";
    summaryInput.value = "";
    profileUrlInput.value = currentProfileKey();
    skillsInput.value = "";
    resumeCheckbox.checked = false;
    resumeSection.classList.add("hidden");
    resumeHint.textContent = "No resume available";
    manualUploadInput.value = "";
    manualUploadFileName.textContent = "";
    manualUploadFileName.classList.add("hidden");
    clearParseError();
    renderExperience();
    renderEducation();
    renderProjects();
    renderCertifications();
  }

  function updateSectionControls() {
    const manual = state.mode === "manual";
    expAddEl.classList.toggle("hidden", !manual);
    eduAddEl.classList.toggle("hidden", !manual);
    projAddEl.classList.toggle("hidden", !manual);
    certAddEl.classList.toggle("hidden", !manual);
  }

  function setMode(mode) {
    const prev = state.mode;
    state.mode = mode;
    parsingTab.classList.toggle("active", mode === "parsing");
    manualTab.classList.toggle("active", mode === "manual");

    if (mode === "manual") {
      formEl.classList.remove("hidden");
      parseAreaEl.classList.add("hidden");
    } else {
      if (prev === "manual") {
        syncExperienceFromUI();
        syncEducationFromUI();
        syncProjectsFromUI();
        syncCertificationsFromUI();
      }
      if (state.extracted) {
        formEl.classList.remove("hidden");
        parseAreaEl.classList.add("hidden");
      } else {
        formEl.classList.add("hidden");
        parseAreaEl.classList.remove("hidden");
      }
    }

    renderExperience();
    renderEducation();
    renderProjects();
    renderCertifications();
    updateSectionControls();
  }

  function entryField(cls, label, value, isTextarea) {
    const group = makeEl("div", "tv-entry-field");
    group.appendChild(makeEl("label", "", label));
    const input = makeEl(isTextarea ? "textarea" : "input");
    input.className = cls;
    input.value = value || "";
    if (!isTextarea) input.type = "text";
    group.appendChild(input);
    return group;
  }

  function readEntry(el, cls) {
    const input = el.querySelector("." + cls);
    return input ? (input.value || "").trim() : "";
  }

  function addReadonlyRow(card, label, value) {
    if (!value && value !== 0) return;
    const row = makeEl("div", "tv-entry-readonly-row");
    row.appendChild(makeEl("span", "tv-entry-readonly-label", label));
    row.appendChild(makeEl("span", "tv-entry-readonly-value", String(value)));
    card.appendChild(row);
  }

  function readonlyExperienceCard(exp) {
    const card = makeEl("div", "tv-entry tv-entry-readonly");
    addReadonlyRow(card, "Company", exp.company_name || exp.company || "");
    addReadonlyRow(card, "Designation", exp.designation || exp.title || "");
    if (exp.employment_type) addReadonlyRow(card, "Employment", exp.employment_type);
    const datesDisp = (exp.start_date || exp.end_date)
      ? `${exp.start_date || ''} - ${exp.end_date || (exp.is_current ? 'Present' : '')}`.trim().replace(/^ - | - $/g, '')
      : (exp.duration || exp.dates || "");
    addReadonlyRow(card, "Duration", datesDisp);
    addReadonlyRow(card, "Location", exp.location || "");
    addReadonlyRow(card, "Description", exp.description || "");
    return card;
  }

  function readonlyEducationCard(edu) {
    const card = makeEl("div", "tv-entry tv-entry-readonly");
    addReadonlyRow(card, "Institution", edu.institution || edu.school || "");
    addReadonlyRow(card, "Degree", edu.degree || "");
    addReadonlyRow(card, "Field of Study", edu.field_of_study || edu.field || "");
    const datesDisp = (edu.start_date || edu.end_date)
      ? `${edu.start_date || ''} - ${edu.end_date || ''}`.trim().replace(/^ - | - $/g, '')
      : (edu.dates || edu.duration || "");
    addReadonlyRow(card, "Dates", datesDisp);
    return card;
  }

  function readonlyProjectCard(proj) {
    const card = makeEl("div", "tv-entry tv-entry-readonly");
    addReadonlyRow(card, "Project Title", proj.title || proj.name || "");
    if (proj.role) addReadonlyRow(card, "Role", proj.role);
    if (proj.dates || proj.duration) addReadonlyRow(card, "Dates", proj.dates || proj.duration);
    if (proj.link) addReadonlyRow(card, "Link", proj.link);
    if (proj.description) addReadonlyRow(card, "Description", proj.description);
    return card;
  }

  function readonlyCertificationCard(cert) {
    const card = makeEl("div", "tv-entry tv-entry-readonly");
    addReadonlyRow(card, "Certification", cert.name || cert.title || "");
    if (cert.issuing_organization || cert.issuer) {
      addReadonlyRow(card, "Issuer", cert.issuing_organization || cert.issuer);
    }
    if (cert.issue_date || cert.date) {
      addReadonlyRow(card, "Date", cert.issue_date || cert.date);
    }
    return card;
  }

  function renderExperience() {
    expListEl.textContent = "";
    expEmptyEl.classList.toggle("hidden", state.experiences.length > 0);
    state.experiences.forEach((exp, idx) => {
      if (state.mode === "manual") {
        const card = makeEl("div", "tv-entry");
        const remove = makeEl("button", "tv-entry-remove", "✕");
        remove.type = "button";
        remove.setAttribute("aria-label", "Remove entry");
        remove.addEventListener("click", () => {
          syncExperienceFromUI();
          state.experiences.splice(idx, 1);
          renderExperience();
        });
        card.appendChild(remove);
        card.appendChild(entryField("tv-exp-company", "Company Name", exp.company_name || exp.company || ""));
        card.appendChild(entryField("tv-exp-designation", "Job Title / Designation", exp.designation || exp.title || ""));
        card.appendChild(entryField("tv-exp-emp-type", "Employment Type", exp.employment_type || ""));
        card.appendChild(entryField("tv-exp-start", "Start Date", exp.start_date || ""));
        card.appendChild(entryField("tv-exp-end", "End Date / Present", exp.end_date || (exp.is_current ? "Present" : "")));
        card.appendChild(entryField("tv-exp-duration", "Duration", exp.duration || exp.dates || ""));
        card.appendChild(entryField("tv-exp-location", "Location", exp.location || ""));
        card.appendChild(entryField("tv-exp-description", "Job Description / Responsibilities", exp.description || "", true));
        expListEl.appendChild(card);
      } else {
        expListEl.appendChild(readonlyExperienceCard(exp));
      }
    });
  }

  function renderEducation() {
    eduListEl.textContent = "";
    eduEmptyEl.classList.toggle("hidden", state.educations.length > 0);
    state.educations.forEach((edu, idx) => {
      if (state.mode === "manual") {
        const card = makeEl("div", "tv-entry");
        const remove = makeEl("button", "tv-entry-remove", "✕");
        remove.type = "button";
        remove.setAttribute("aria-label", "Remove entry");
        remove.addEventListener("click", () => {
          syncEducationFromUI();
          state.educations.splice(idx, 1);
          renderEducation();
        });
        card.appendChild(remove);
        card.appendChild(entryField("tv-edu-institution", "Institution / University", edu.institution || edu.school || ""));
        card.appendChild(entryField("tv-edu-degree", "Degree", edu.degree || ""));
        card.appendChild(entryField("tv-edu-field", "Field of Study", edu.field_of_study || edu.field || ""));
        card.appendChild(entryField("tv-edu-start", "Start Date", edu.start_date || ""));
        card.appendChild(entryField("tv-edu-end", "End Date / Graduation Year", edu.end_date || ""));
        card.appendChild(entryField("tv-edu-dates", "Dates", edu.dates || edu.duration || ""));
        eduListEl.appendChild(card);
      } else {
        eduListEl.appendChild(readonlyEducationCard(edu));
      }
    });
  }

  function renderProjects() {
    projListEl.textContent = "";
    projEmptyEl.classList.toggle("hidden", state.projects.length > 0);
    state.projects.forEach((proj, idx) => {
      if (state.mode === "manual") {
        const card = makeEl("div", "tv-entry");
        const remove = makeEl("button", "tv-entry-remove", "✕");
        remove.type = "button";
        remove.setAttribute("aria-label", "Remove entry");
        remove.addEventListener("click", () => {
          syncProjectsFromUI();
          state.projects.splice(idx, 1);
          renderProjects();
        });
        card.appendChild(remove);
        card.appendChild(entryField("tv-proj-title", "Project Name / Title", proj.title || proj.name || ""));
        card.appendChild(entryField("tv-proj-role", "Role", proj.role || ""));
        card.appendChild(entryField("tv-proj-dates", "Dates", proj.dates || proj.duration || ""));
        card.appendChild(entryField("tv-proj-link", "Project Link", proj.link || ""));
        card.appendChild(entryField("tv-proj-description", "Project Description", proj.description || "", true));
        projListEl.appendChild(card);
      } else {
        projListEl.appendChild(readonlyProjectCard(proj));
      }
    });
  }

  function renderCertifications() {
    certListEl.textContent = "";
    certEmptyEl.classList.toggle("hidden", state.certifications.length > 0);
    state.certifications.forEach((cert, idx) => {
      if (state.mode === "manual") {
        const card = makeEl("div", "tv-entry");
        const remove = makeEl("button", "tv-entry-remove", "✕");
        remove.type = "button";
        remove.setAttribute("aria-label", "Remove entry");
        remove.addEventListener("click", () => {
          syncCertificationsFromUI();
          state.certifications.splice(idx, 1);
          renderCertifications();
        });
        card.appendChild(remove);
        card.appendChild(entryField("tv-cert-name", "Certification Name", cert.name || cert.title || ""));
        card.appendChild(entryField("tv-cert-org", "Issuing Organization / Issuer", cert.issuing_organization || cert.issuer || ""));
        card.appendChild(entryField("tv-cert-date", "Date / Issue Date", cert.issue_date || cert.date || ""));
        certListEl.appendChild(card);
      } else {
        certListEl.appendChild(readonlyCertificationCard(cert));
      }
    });
  }

  function syncExperienceFromUI() {
    const cards = expListEl.querySelectorAll(".tv-entry:not(.tv-entry-readonly)");
    if (!cards.length) return state.experiences;
    const out = [];
    cards.forEach((card) => {
      const cName = readEntry(card, "tv-exp-company");
      const desig = readEntry(card, "tv-exp-designation");
      const empType = readEntry(card, "tv-exp-emp-type");
      const sDate = readEntry(card, "tv-exp-start");
      const eDate = readEntry(card, "tv-exp-end");
      const dur = readEntry(card, "tv-exp-duration") || (sDate || eDate ? `${sDate} - ${eDate}`.trim().replace(/^ - | - $/g, '') : "");
      const loc = readEntry(card, "tv-exp-location");
      const desc = readEntry(card, "tv-exp-description");
      const isCurr = /present|current/i.test(eDate) || /present|current/i.test(dur);
      out.push({
        company_name: cName,
        company: cName,
        designation: desig,
        title: desig,
        employment_type: empType,
        start_date: sDate,
        end_date: eDate,
        duration: dur,
        dates: dur,
        is_current: isCurr,
        location: loc,
        description: desc,
      });
    });
    state.experiences = out;
    return out;
  }

  function syncEducationFromUI() {
    const cards = eduListEl.querySelectorAll(".tv-entry:not(.tv-entry-readonly)");
    if (!cards.length) return state.educations;
    const out = [];
    cards.forEach((card) => {
      const inst = readEntry(card, "tv-edu-institution");
      const deg = readEntry(card, "tv-edu-degree");
      const field = readEntry(card, "tv-edu-field");
      const sDate = readEntry(card, "tv-edu-start");
      const eDate = readEntry(card, "tv-edu-end");
      const dates = readEntry(card, "tv-edu-dates") || (sDate || eDate ? `${sDate} - ${eDate}`.trim().replace(/^ - | - $/g, '') : "");
      out.push({
        institution: inst,
        school: inst,
        degree: deg,
        field_of_study: field,
        field: field,
        start_date: sDate,
        end_date: eDate,
        dates: dates,
        duration: dates,
      });
    });
    state.educations = out;
    return out;
  }

  function syncProjectsFromUI() {
    const cards = projListEl.querySelectorAll(".tv-entry:not(.tv-entry-readonly)");
    if (!cards.length) return state.projects;
    const out = [];
    cards.forEach((card) => {
      const title = readEntry(card, "tv-proj-title");
      const role = readEntry(card, "tv-proj-role");
      const dates = readEntry(card, "tv-proj-dates");
      const link = readEntry(card, "tv-proj-link");
      const desc = readEntry(card, "tv-proj-description");
      out.push({
        title: title,
        name: title,
        role: role,
        dates: dates,
        duration: dates,
        link: link,
        description: desc,
      });
    });
    state.projects = out;
    return out;
  }

  function syncCertificationsFromUI() {
    const cards = certListEl.querySelectorAll(".tv-entry:not(.tv-entry-readonly)");
    if (!cards.length) return state.certifications;
    const out = [];
    cards.forEach((card) => {
      const name = readEntry(card, "tv-cert-name");
      const org = readEntry(card, "tv-cert-org");
      const date = readEntry(card, "tv-cert-date");
      out.push({
        name: name,
        title: name,
        issuing_organization: org,
        issuer: org,
        issue_date: date,
        date: date,
      });
    });
    state.certifications = out;
    return out;
  }

  function populateForm(data) {
    state.extracted = data;
    state.profileKey = currentProfileKey();
    nameInput.value = data.name || data.full_name || "";
    headlineInput.value = data.headline || data.current_designation || "";
    companyInput.value = data.current_company || "";
    locationInput.value = data.location || "";
    emailInput.value = data.email || "";
    phoneInput.value = data.phone || "";
    totalExpInput.value = data.total_experience != null ? data.total_experience : "";
    currentCtcInput.value = (data.current_salary != null ? data.current_salary : (data.current_ctc != null ? data.current_ctc : ""));
    expectedCtcInput.value = (data.expected_salary != null ? data.expected_salary : (data.expected_ctc != null ? data.expected_ctc : ""));
    noticePeriodInput.value = data.notice_period != null ? data.notice_period : "";
    summaryInput.value = data.summary || data.about || "";
    profileUrlInput.value = data.profile_url || data.linkedin_url || currentProfileKey();
    skillsInput.value = Array.isArray(data.skills) ? data.skills.join(", ") : "";

    state.experiences = Array.isArray(data.experience) ? data.experience.slice() : [];
    state.educations = Array.isArray(data.education) ? data.education.slice() : [];
    state.projects = Array.isArray(data.projects) ? data.projects.slice() : [];
    state.certifications = Array.isArray(data.certifications) ? data.certifications.slice() : [];

    resumeCheckbox.checked = false;
    if (data.resume_available && data.resume_url) {
      resumeSection.classList.remove("hidden");
      const fn = data.resume_filename || "Candidate_Resume.pdf";
      resumeHint.textContent = `Resume detected: ${fn}`;
    } else {
      resumeSection.classList.add("hidden");
      resumeHint.textContent = "No resume available";
    }

    setMode("parsing");
  }

  function currentExperiences() {
    return state.mode === "manual" ? syncExperienceFromUI() : state.experiences;
  }

  function currentEducations() {
    return state.mode === "manual" ? syncEducationFromUI() : state.educations;
  }

  function currentProjects() {
    return state.mode === "manual" ? syncProjectsFromUI() : state.projects;
  }

  function currentCertifications() {
    return state.mode === "manual" ? syncCertificationsFromUI() : state.certifications;
  }

  function buildPayload() {
    const experiences = currentExperiences();
    const educations = currentEducations();
    const projects = currentProjects();
    const certs = currentCertifications();
    const skills = String(skillsInput.value || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const source = (state.extracted && state.extracted.source) || (state.mode === "manual" ? "manual" : "linkedin");
    const name = nameInput.value.trim();
    const headline = headlineInput.value.trim();
    const company = companyInput.value.trim();
    const location = locationInput.value.trim();
    const email = emailInput.value.trim();
    const phone = phoneInput.value.trim();
    const summary = summaryInput.value.trim();
    const profileUrl = profileUrlInput.value.trim();

    const rawTotalExp = totalExpInput.value ? parseFloat(totalExpInput.value) : (state.extracted && state.extracted.total_experience != null ? state.extracted.total_experience : null);
    const rawCurrentCtc = currentCtcInput.value ? parseFloat(currentCtcInput.value) : (state.extracted && state.extracted.current_salary != null ? state.extracted.current_salary : null);
    const rawExpectedCtc = expectedCtcInput.value ? parseFloat(expectedCtcInput.value) : (state.extracted && state.extracted.expected_salary != null ? state.extracted.expected_salary : null);
    const rawNotice = noticePeriodInput.value ? parseInt(noticePeriodInput.value, 10) : (state.extracted && state.extracted.notice_period != null ? state.extracted.notice_period : null);

    return {
      personal_info: {
        name: name,
        email: email,
        phone: phone,
        location: location,
        current_company: company,
        current_designation: headline,
        total_experience: rawTotalExp,
        current_salary: rawCurrentCtc,
        expected_salary: rawExpectedCtc,
        notice_period: rawNotice,
        profile_url: profileUrl,
      },
      full_name: name,
      name: name,
      headline: headline,
      current_designation: headline,
      current_company: company,
      location: location,
      email: email,
      phone: phone,
      summary: summary,
      linkedin_url: profileUrl,
      profile_url: profileUrl,
      total_experience: rawTotalExp,
      current_salary: rawCurrentCtc,
      current_ctc: rawCurrentCtc,
      expected_salary: rawExpectedCtc,
      expected_ctc: rawExpectedCtc,
      notice_period: rawNotice,
      skills: skills,
      experience: experiences,
      education: educations,
      projects: projects,
      certifications: certs,
      source: source,
      uploaded_by_email: recruiterEmailInput.value.trim(),
    };
  }

  async function safePrepare() {
    try {
      if (typeof preparePage === "function") await preparePage();
    } catch (e) {}
  }

  function safeExtract() {
    try {
      return typeof extractPageData === "function" ? extractPageData() : null;
    } catch (e) {
      return null;
    }
  }

  async function parse() {
    if (state.parseInFlight) return;
    state.parseInFlight = true;
    setLoading(true);
    setStatus("Parsing profile…", "info");

    const token = ++currentParseToken;
    const keyAtStart = currentProfileKey();
    console.log(`[Talent Vault Debug] parse() started | profile=${keyAtStart}`);

    await tick();

    // Concurrency check: discard if navigation happened during tick
    if (token !== currentParseToken || currentProfileKey() !== keyAtStart) {
      console.log(`[Talent Vault Debug] parse() aborted (profile changed ${keyAtStart} -> ${currentProfileKey()})`);
      setLoading(false);
      state.parseInFlight = false;
      return;
    }

    try {
      // Bounded wait/retry: LinkedIn/Naukri may lazy-render sections a moment
      // after the initial paint. We never scroll or poll in the background — we
      // only re-read the already-rendered DOM a few times after a manual click.
      const MAX_ATTEMPTS = 4;
      let data = null;
      for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        await safePrepare();
        data = safeExtract();

        if (token !== currentParseToken || currentProfileKey() !== keyAtStart) {
          console.log("[Talent Vault Debug] parse() discarded late response");
          return;
        }

        // No candidate found yet — nothing to wait for.
        if (!data || !data.name) break;

        const expCount = (data && Array.isArray(data.experience)) ? data.experience.length : 0;
        const eduCount = (data && Array.isArray(data.education)) ? data.education.length : 0;
        const skillCount = (data && Array.isArray(data.skills)) ? data.skills.length : 0;
        if (expCount > 0 || eduCount > 0 || skillCount > 0) {
          break; // content rendered
        }
        if (attempt < MAX_ATTEMPTS - 1) {
          console.log(`[Talent Vault Debug] parse() attempt ${attempt + 1}: no sections yet, waiting for lazy render…`);
          await delay(600);
        }
      }

      // Concurrency check: discard a response for a previous profile.
      if (token !== currentParseToken || currentProfileKey() !== keyAtStart) {
        console.log("[Talent Vault Debug] parse() discarded late response");
        return;
      }

      if (data) {
        console.log(`[Talent Vault Debug] parse() extracted: name="${data.name}" experience=${(data.experience || []).length} education=${(data.education || []).length}`);
      } else {
        console.log("[Talent Vault Debug] parse() extractPageData returned null/undefined");
      }

      if (data && data.name) {
        state.profileKey = currentProfileKey();
        populateForm(data);
        setStatus(`Loaded "${data.name}". Review the details and save.`, "success");
      } else {
        clearParsedData();
        showParseError("No candidate profile found on this page. Switch to Manual Mode or open a profile and retry.");
        setStatus("No candidate profile found on this page.", "error");
      }
    } catch (err) {
      clearParsedData();
      showParseError("Parsing failed: " + (err && err.message ? err.message : "unknown error"));
      setStatus("Parsing failed.", "error");
      console.error("[Talent Vault Debug] parse() error", err);
    } finally {
      setLoading(false);
      state.parseInFlight = false;
    }
  }

  async function save() {
    // Guard against saving a candidate whose profile has since changed.
    const key = currentProfileKey();
    if (key && state.profileKey && key !== state.profileKey) {
      setStatus("The profile changed since it was parsed. Re-open this profile and parse again before saving.", "error");
      return;
    }

    const payload = buildPayload();
    if (!payload.full_name) {
      setStatus("Full Name is required before saving.", "error");
      return;
    }

    saveEl.disabled = true;
    const original = saveEl.textContent;
    saveEl.textContent = "Saving…";

    // Resume attachment priority:
    //   1. Manually selected file (always wins)
    //   2. Stealthy human-like click + blob: capture, then direct fetch, then URL
    let attachedFilename = "";

    const manualFile = manualUploadInput.files && manualUploadInput.files[0];
    if (manualFile) {
      try {
        const manualBase64 = await readFileAsBase64(manualFile);
        payload.resume = {
          filename: manualFile.name,
          resume_base64: manualBase64,
          mime_type: manualFile.type || "application/pdf",
        };
      } catch (err) {
        console.error("[Talent Vault] Manual resume read failed:", err);
        setStatus("Could not read the selected resume file.", "warning");
      }
    } else if (
      resumeCheckbox.checked &&
      state.extracted &&
      state.extracted.resume_url
    ) {
      setStatus("Downloading Resume...", "info");
      let captured = null;
      if (typeof captureNaukriResumeViaClick === "function") {
        try {
          captured = await captureNaukriResumeViaClick();
        } catch (e) {
          captured = null;
        }
      }
      if (captured && captured.ok && captured.data_base64) {
        attachedFilename = captured.filename || state.extracted.resume_filename || "Candidate_Resume.pdf";
        payload.resume = {
          filename: attachedFilename,
          resume_base64: captured.data_base64,
          mime_type: captured.mime_type || "application/pdf",
        };
      } else if (typeof fetchResumeAsBase64 === "function") {
        try {
          const fetched = await fetchResumeAsBase64(state.extracted.resume_url);
          attachedFilename = fetched.filename || state.extracted.resume_filename || "Candidate_Resume.pdf";
          payload.resume = {
            filename: attachedFilename,
            data_base64: fetched.data_base64,
            mime_type: fetched.mime_type,
          };
        } catch (err) {
          // Fallback: the resume URL could not be downloaded (HTML preview / CORS).
          // Send the URL so the backend can surface it as a link.
          payload.resume = {
            filename: state.extracted.resume_filename || "Candidate_Resume.pdf",
            resume_url: state.extracted.resume_url,
          };
          setStatus("Could not download resume; it will be saved as a link.", "warning");
        }
      }
    }

    setStatus("Saving candidate…", "info");

    let resp = null;
    try {
      console.log("PAYLOAD_SENT_TO_DJANGO:", JSON.stringify(payload));
      resp = await chrome.runtime.sendMessage({
        action: "tv_api_request",
        method: "POST",
        path: IMPORT_PATH,
        body: payload,
      });

      console.log("[Talent Vault Debug] Save response:", JSON.stringify(resp));
      console.log(
        `[Talent Vault Debug] Resume filename: "${payload.resume ? payload.resume.filename : 'none'}" | actual attachment result: attached=${resp?.data?.resume_attached} | message="${resp?.data?.resume_message || ''}"`
      );

      if (resp && resp.ok && resp.data && resp.data.status === "success") {
        const id = resp.data.candidate_id || "";
        const isNew = resp.data.action === "created";
        let msg = isNew ? `Candidate Saved Successfully! (ID: ${id})` : `Candidate Updated Successfully! (ID: ${id})`;
        if (payload.resume) {
          if (resp.data.resume_attached) {
            msg += " | Resume attached.";
          } else if (resp.data.resume_message) {
            msg += ` | Resume: ${resp.data.resume_message}`;
          }
        }
        setStatus(msg, "success");
      } else {
        const detail = (resp && resp.data && resp.data.error) || (resp && resp.error) || "Request failed";
        setStatus("Save Error: " + detail, "error");
      }
    } catch (err) {
      // A response DID come back -> this is NOT a network failure.
      if (resp) {
        const detail = (resp.data && resp.data.error) || resp.error || "Request failed";
        setStatus("Save Error: " + detail, "error");
      } else {
        console.error("[Talent Vault] Widget save network error:", err);
        console.error("[Talent Vault] Widget save network error detail:", {
          path: IMPORT_PATH,
          name: err && err.name,
          message: err && err.message,
          cause: err && err.cause,
          online: (typeof navigator !== "undefined" && navigator.onLine),
        });
        setStatus("Network Error: Could not reach Talent Vault API.", "error");
      }
    } finally {
      saveEl.disabled = false;
      saveEl.textContent = original;
    }
  }

  function open() {
    panelEl.classList.remove("hidden");
    setMode(state.mode);

    if (state.mode !== "parsing") return;
    const key = currentProfileKey();
    console.log(`[Talent Vault Debug] open(): mode=${state.mode} extracted=${!!state.extracted} key=${key} storedKey=${state.profileKey}`);
    if (!state.extracted || state.profileKey !== key) {
      clearParsedData();
      parse();
    }
  }

  function close() {
    panelEl.classList.add("hidden");
  }

  function toggleMinimize() {
    state.minimized = !state.minimized;
    if (state.minimized) {
      panelEl.classList.add("tv-minimized");
      bodyEl.classList.add("hidden");
      tabsBarEl.classList.add("hidden");
    } else {
      panelEl.classList.remove("tv-minimized");
      bodyEl.classList.remove("hidden");
      tabsBarEl.classList.remove("hidden");
    }
  }

  function isOpen() {
    return !panelEl.classList.contains("hidden");
  }

  function isMinimized() {
    return state.minimized;
  }

  function handleNavigation() {
    const key = currentProfileKey();
    if (!key || key === state.profileKey) return;
    clearParsedData();
    // Stealth: never auto-parse on navigation. We only clear the previous
    // candidate's data; extraction runs exclusively on a manual TV-icon/Parse
    // click.
  }

  // ---- Wire events ----
  iconEl.addEventListener("click", () => {
    const action = isOpen() ? "close" : "open";
    console.log(`[Talent Vault Debug] TV icon handler ran (action=${action}) | profile=${currentProfileKey()}`);
    if (isOpen()) close();
    else open();
  });

  closeEl.addEventListener("click", close);
  minEl.addEventListener("click", toggleMinimize);
  parsingTab.addEventListener("click", () => setMode("parsing"));
  manualTab.addEventListener("click", () => setMode("manual"));
  retryEl.addEventListener("click", parse);
  saveEl.addEventListener("click", save);

  manualUploadInput.addEventListener("change", () => {
    const file = manualUploadInput.files && manualUploadInput.files[0];
    if (file) {
      manualUploadFileName.textContent = `Selected: ${file.name}`;
      manualUploadFileName.classList.remove("hidden");
    } else {
      manualUploadFileName.textContent = "";
      manualUploadFileName.classList.add("hidden");
    }
  });

  expAddEl.addEventListener("click", () => {
    if (state.mode !== "manual") return;
    syncExperienceFromUI();
    state.experiences.push({
      company_name: "",
      company: "",
      designation: "",
      title: "",
      employment_type: "",
      start_date: "",
      end_date: "",
      duration: "",
      location: "",
      description: "",
    });
    renderExperience();
  });

  eduAddEl.addEventListener("click", () => {
    if (state.mode !== "manual") return;
    syncEducationFromUI();
    state.educations.push({
      institution: "",
      school: "",
      degree: "",
      field_of_study: "",
      start_date: "",
      end_date: "",
      dates: "",
    });
    renderEducation();
  });

  projAddEl.addEventListener("click", () => {
    if (state.mode !== "manual") return;
    syncProjectsFromUI();
    state.projects.push({
      title: "",
      name: "",
      role: "",
      dates: "",
      link: "",
      description: "",
    });
    renderProjects();
  });

  certAddEl.addEventListener("click", () => {
    if (state.mode !== "manual") return;
    syncCertificationsFromUI();
    state.certifications.push({
      name: "",
      title: "",
      issuing_organization: "",
      issuer: "",
      issue_date: "",
      date: "",
    });
    renderCertifications();
  });

  // Listen for background toolbar icon click to toggle widget
  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((request) => {
      if (request && request.action === "tv_toggle_widget") {
        if (isOpen()) close();
        else open();
      }
    });
  }

  // ---- Navigation tracking (SPA URL/history changes) ----
  function wireNavigation() {
    try {
      const w = (typeof window !== "undefined" && window) || (typeof globalThis !== "undefined" && globalThis) || null;
      if (!w || typeof w.addEventListener !== "function") return;
      w.addEventListener("popstate", handleNavigation);
      w.addEventListener("tv:navigate", handleNavigation);

      const h = w.history;
      if (h && typeof h.pushState === "function" && typeof h.replaceState === "function") {
        const origPush = h.pushState.bind(h);
        const origReplace = h.replaceState.bind(h);
        h.pushState = function (...args) {
          const result = origPush(...args);
          handleNavigation();
          return result;
        };
        h.replaceState = function (...args) {
          const result = origReplace(...args);
          handleNavigation();
          return result;
        };
      }

      // No MutationObserver, no setInterval polling: navigation is tracked only
      // via history/popstate events so the page never sees background scraping.
    } catch (e) {}
  }
  wireNavigation();

  // ---- Test/introspection surface ----
  globalThis.__talentVaultWidget = {
    host,
    shadow,
    iconEl,
    panelEl,
    closeEl,
    minEl,
    retryEl,
    saveEl,
    loadingEl,
    parseErrorEl,
    statusEl,
    bodyEl,
    expAddEl,
    eduAddEl,
    projAddEl,
    certAddEl,
    expListEl,
    eduListEl,
    projListEl,
    certListEl,
    expEmptyEl,
    eduEmptyEl,
    projEmptyEl,
    certEmptyEl,
    resumeSection,
    resumeCheckbox,
    resumeHint,
    open,
    close,
    toggleMinimize,
    parse,
    save,
    buildPayload,
    populateForm,
    setMode,
    renderExperience,
    renderEducation,
    renderProjects,
    renderCertifications,
    syncExperienceFromUI,
    syncEducationFromUI,
    syncProjectsFromUI,
    syncCertificationsFromUI,
    clearParsedData,
    handleNavigation,
    currentProfileKey,
    isOpen,
    isMinimized,
    inputs: {
      recruiterEmailInput,
      nameInput,
      headlineInput,
      companyInput,
      locationInput,
      emailInput,
      phoneInput,
      totalExpInput,
      currentCtcInput,
      expectedCtcInput,
      noticePeriodInput,
      summaryInput,
      profileUrlInput,
      skillsInput,
    },
    getFields: () => ({
      name: nameInput.value,
      headline: headlineInput.value,
      company: companyInput.value,
      location: locationInput.value,
      email: emailInput.value,
      phone: phoneInput.value,
      total_experience: totalExpInput.value,
      current_salary: currentCtcInput.value,
      expected_salary: expectedCtcInput.value,
      notice_period: noticePeriodInput.value,
      summary: summaryInput.value,
      profile_url: profileUrlInput.value,
      skills: skillsInput.value,
      experience: currentExperiences(),
      education: currentEducations(),
      projects: currentProjects(),
      certifications: currentCertifications(),
    }),
    getState: () => ({
      mode: state.mode,
      extracted: state.extracted,
      minimized: state.minimized,
      experiences: state.experiences,
      educations: state.educations,
      projects: state.projects,
      certifications: state.certifications,
      profileKey: state.profileKey,
    }),
  };
})();
