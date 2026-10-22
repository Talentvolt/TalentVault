import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

import {
  createChromeMock,
  createDocument,
  createFetchSpy,
  CONTENT_PATH,
  WIDGET_PATH,
  SAMPLE_DATA,
} from "./harness.mjs";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function setupWidget({ getExtract = () => SAMPLE_DATA, runtimeMessageHandler } = {}) {
  const document = createDocument();
  const chrome = createChromeMock({ runtimeMessageHandler });
  const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    setImmediate,
    URL,
    Date,
    chrome,
    document,
    fetch: createFetchSpy(),
  };
  vm.createContext(sandbox);
  vm.runInContext(readFileSync(CONTENT_PATH, "utf8"), sandbox, { filename: "content.js" });
  sandbox.extractPageData = () => getExtract();
  sandbox.preparePage = () => {};
  vm.runInContext(readFileSync(WIDGET_PATH, "utf8"), sandbox, { filename: "widget.js" });
  return { sandbox, document, chrome, widget: sandbox.__talentVaultWidget };
}

// Widget setup with a fake location/history so SPA navigation can be simulated.
function setupWidgetWithNav({ getExtract = () => SAMPLE_DATA, initialUrl = "https://www.linkedin.com/in/ananya/" } = {}) {
  const document = createDocument();
  const chrome = createChromeMock();
  const loc = { href: initialUrl };
  const history = {
    pushState(_state, _title, url) { loc.href = url; },
    replaceState(_state, _title, url) { loc.href = url; },
  };
  const windowObj = {
    location: loc,
    history,
    _listeners: {},
    addEventListener(type, cb) { (this._listeners[type] = this._listeners[type] || []).push(cb); },
  };
  const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    setImmediate,
    URL,
    Date,
    chrome,
    document,
    fetch: createFetchSpy(),
    window: windowObj,
    location: loc,
  };
  vm.createContext(sandbox);
  vm.runInContext(readFileSync(CONTENT_PATH, "utf8"), sandbox, { filename: "content.js" });
  sandbox.extractPageData = () => getExtract();
  sandbox.preparePage = () => {};
  vm.runInContext(readFileSync(WIDGET_PATH, "utf8"), sandbox, { filename: "widget.js" });
  return { sandbox, document, chrome, widget: sandbox.__talentVaultWidget, loc, history, window: windowObj };
}

test("injects a single floating icon and panel (no duplicates)", () => {
  const { document, widget, sandbox } = setupWidget();

  assert.equal(document.body.children.length, 1);
  const host = document.body.children[0];
  assert.equal(host.id, "talent-vault-widget");
  assert.ok(host.shadowRoot);
  assert.equal(host.shadowRoot.children.length, 3); // style + icon + panel
  assert.ok(widget.iconEl);
  assert.ok(widget.panelEl);
  assert.equal(widget.isOpen(), false);

  // Re-injecting the content script must not create a second widget.
  vm.runInContext(readFileSync(WIDGET_PATH, "utf8"), sandbox, { filename: "widget.js" });
  assert.equal(document.body.children.length, 1);
});

test("clicking the floating icon opens the panel and auto-parses the profile", async () => {
  const { widget } = setupWidget();

  assert.equal(widget.isOpen(), false);
  widget.iconEl.click();
  await sleep(5);

  assert.equal(widget.isOpen(), true);
  const fields = widget.getFields();
  assert.equal(fields.name, "Ananya Deshmukh");
  assert.equal(fields.headline, "Principal AI Architect");
  assert.equal(fields.company, "NVIDIA");
  assert.equal(fields.location, "Bengaluru, Karnataka, India");
  assert.equal(fields.skills, "Python, PyTorch");
  assert.equal(widget.getState().extracted.name, "Ananya Deshmukh");
});

test("shows a loading spinner while parsing", async () => {
  const { widget } = setupWidget();

  const pending = widget.parse();
  assert.equal(widget.loadingEl.classList.contains("hidden"), false);

  await pending;
  assert.equal(widget.loadingEl.classList.contains("hidden"), true);
  assert.equal(widget.getFields().name, "Ananya Deshmukh");
});

test("close control hides the panel", async () => {
  const { widget } = setupWidget();

  widget.iconEl.click();
  await sleep(5);
  assert.equal(widget.isOpen(), true);

  widget.closeEl.click();
  assert.equal(widget.isOpen(), false);
});

test("minimize control collapses and restores the panel body", async () => {
  const { widget } = setupWidget();

  widget.iconEl.click();
  await sleep(5);
  assert.equal(widget.isMinimized(), false);

  widget.minEl.click();
  assert.equal(widget.isMinimized(), true);
  assert.equal(widget.bodyEl.classList.contains("hidden"), true);

  widget.minEl.click();
  assert.equal(widget.isMinimized(), false);
  assert.equal(widget.bodyEl.classList.contains("hidden"), false);
});

test("shows a clear message and Retry when no profile is found", async () => {
  const { widget } = setupWidget({ getExtract: () => ({ name: "" }) });

  widget.iconEl.click();
  await sleep(5);

  assert.equal(widget.isOpen(), true);
  assert.equal(widget.retryEl.classList.contains("hidden"), false);
  assert.match(widget.parseErrorEl.textContent, /no candidate profile/i);
  assert.equal(widget.getState().extracted, null);
});

test("Retry re-parses and populates after a failure", async () => {
  let result = { name: "" };
  const { widget } = setupWidget({ getExtract: () => result });

  widget.iconEl.click();
  await sleep(5);
  assert.equal(widget.retryEl.classList.contains("hidden"), false);
  assert.equal(widget.getFields().name, "");

  result = SAMPLE_DATA;
  widget.retryEl.click();
  await sleep(5);

  assert.equal(widget.getFields().name, "Ananya Deshmukh");
  assert.equal(widget.retryEl.classList.contains("hidden"), true);
});

test("Save Candidate sends the parsed payload through the background proxy", async () => {
  let sent;
  const { widget } = setupWidget({
    runtimeMessageHandler: (msg) => {
      sent = msg;
      return { ok: true, status: 201, data: { status: "success", action: "created", candidate_id: "abc-123" } };
    },
  });

  widget.iconEl.click();
  await sleep(5);

  await widget.save();

  assert.ok(sent);
  assert.equal(sent.action, "tv_api_request");
  assert.equal(sent.method, "POST");
  assert.equal(sent.path, "/api/v1/candidates/import/");
  assert.equal(sent.body.full_name, "Ananya Deshmukh");
  assert.equal(sent.body.current_company, "NVIDIA");
  assert.equal(sent.body.source, "linkedin");
  assert.equal(sent.body.experience.length, 1);
  assert.match(widget.statusEl.textContent, /saved successfully/i);
});

test("Save Candidate persists every extracted experience, education and skill entry", async () => {
  let sent;
  const { widget } = setupWidget({
    getExtract: () => MULTI_DATA,
    runtimeMessageHandler: (msg) => {
      sent = msg;
      return { ok: true, status: 201, data: { status: "success", action: "created", candidate_id: "abc-456" } };
    },
  });

  widget.iconEl.click();
  await sleep(5);
  await widget.save();

  assert.ok(sent);
  assert.equal(sent.body.experience.length, 2);
  assert.equal(sent.body.experience[0].company_name, "NVIDIA");
  assert.equal(sent.body.experience[0].designation, "Principal AI Architect");
  assert.equal(sent.body.experience[1].company_name, "Google");
  assert.equal(sent.body.experience[1].description, "Cloud TPU");

  assert.equal(sent.body.education.length, 2);
  assert.equal(sent.body.education[0].institution, "IISc");
  assert.equal(sent.body.education[1].institution, "IIT Madras");
  assert.equal(sent.body.education[1].field_of_study, "CS");

  assert.deepEqual(Array.from(sent.body.skills), ["Python", "PyTorch"]);
});

test("Save is blocked when the name is empty", async () => {
  let sent = false;
  const { widget } = setupWidget({
    getExtract: () => ({ name: "" }),
    runtimeMessageHandler: () => {
      sent = true;
      return { ok: true, data: { status: "success" } };
    },
  });

  widget.iconEl.click();
  await sleep(5);

  widget.setMode("manual");
  await widget.save();

  assert.equal(sent, false);
  assert.match(widget.statusEl.textContent, /full name is required/i);
});

test("buildPayload serializes experience and education", () => {
  const { widget } = setupWidget();
  widget.populateForm(SAMPLE_DATA);
  const payload = widget.buildPayload();
  assert.equal(payload.experience[0].company_name, "NVIDIA");
  assert.equal(payload.experience[0].designation, "Principal AI Architect");
  assert.equal(payload.education[0].institution, "IISc");
  assert.equal(payload.skills[0], "Python");
});

const MULTI_DATA = {
  name: "Ananya Deshmukh",
  headline: "Principal AI Architect",
  current_company: "NVIDIA",
  location: "Bengaluru, Karnataka, India",
  email: "ananya@example.com",
  phone: "+91 9876543210",
  summary: "14+ years of experience.",
  profile_url: "https://www.linkedin.com/in/ananya-deshmukh-ai/",
  source: "linkedin",
  skills: ["Python", "PyTorch"],
  experience: [
    { company_name: "NVIDIA", designation: "Principal AI Architect", duration: "Jan 2022 - Present", location: "Bengaluru", description: "AI infra" },
    { company_name: "Google", designation: "Senior SWE", duration: "2018 - 2021", location: "Hyderabad", description: "Cloud TPU" },
  ],
  education: [
    { institution: "IISc", degree: "Ph.D.", field_of_study: "CS", dates: "2008 - 2012" },
    { institution: "IIT Madras", degree: "B.Tech", field_of_study: "CS", dates: "2004 - 2008" },
  ],
};

test("populates all experience and education entries plus email/phone", () => {
  const { widget } = setupWidget({ getExtract: () => MULTI_DATA });
  widget.populateForm(MULTI_DATA);

  const fields = widget.getFields();
  assert.equal(fields.email, "ananya@example.com");
  assert.equal(fields.phone, "+91 9876543210");
  assert.equal(fields.experience.length, 2);
  assert.equal(fields.experience[0].company_name, "NVIDIA");
  assert.equal(fields.experience[1].company_name, "Google");
  assert.equal(fields.experience[1].location, "Hyderabad");
  assert.equal(fields.education.length, 2);
  assert.equal(fields.education[1].institution, "IIT Madras");
});

test("Add Entry buttons append blank editable entries", () => {
  const { widget } = setupWidget();
  widget.setMode("manual");

  widget.expAddEl.click();
  widget.eduAddEl.click();

  assert.equal(widget.getState().experiences.length, 1);
  assert.equal(widget.getState().educations.length, 1);
  assert.equal(widget.expEmptyEl.classList.contains("hidden"), true);
});

test("removing an entry keeps the remaining entries", () => {
  const { widget } = setupWidget({ getExtract: () => MULTI_DATA });
  widget.populateForm(MULTI_DATA);
  widget.setMode("manual");
  assert.equal(widget.getState().experiences.length, 2);

  const firstCard = widget.expListEl.querySelector(".tv-entry");
  const removeBtn = firstCard.querySelector(".tv-entry-remove");
  removeBtn.click();

  assert.equal(widget.getState().experiences.length, 1);
  assert.equal(widget.getState().experiences[0].company_name, "Google");
});

test("shows 'No information available' when sections are empty", () => {
  const { widget } = setupWidget();
  widget.populateForm({ name: "Sparse Person", experience: [], education: [], skills: [] });

  assert.equal(widget.expEmptyEl.classList.contains("hidden"), false);
  assert.equal(widget.eduEmptyEl.classList.contains("hidden"), false);
});

test("recruiter can edit extracted fields before saving", () => {
  const { widget } = setupWidget({ getExtract: () => MULTI_DATA });
  widget.populateForm(MULTI_DATA);

  widget.inputs.nameInput.value = "Edited Name";
  widget.inputs.skillsInput.value = "Go, Rust";

  const payload = widget.buildPayload();
  assert.equal(payload.full_name, "Edited Name");
  assert.deepEqual(Array.from(payload.skills), ["Go", "Rust"]);
  assert.equal(payload.experience.length, 2);
});

test("Add Entry controls are shown only in Manual Mode", () => {
  const { widget } = setupWidget();

  widget.setMode("parsing");
  assert.equal(widget.expAddEl.classList.contains("hidden"), true);
  assert.equal(widget.eduAddEl.classList.contains("hidden"), true);

  // Clicking the (hidden) add buttons in Parsing Mode must not add entries.
  widget.expAddEl.click();
  widget.eduAddEl.click();
  assert.equal(widget.getState().experiences.length, 0);
  assert.equal(widget.getState().educations.length, 0);

  widget.setMode("manual");
  assert.equal(widget.expAddEl.classList.contains("hidden"), false);
  assert.equal(widget.eduAddEl.classList.contains("hidden"), false);
});

test("Parsing Mode renders experience and education as read-only entries", () => {
  const { widget } = setupWidget({ getExtract: () => MULTI_DATA });
  widget.populateForm(MULTI_DATA);

  const expCards = widget.expListEl.querySelectorAll(".tv-entry");
  assert.equal(expCards.length, 2);
  assert.equal(expCards[0].querySelector(".tv-entry-remove"), null);
  assert.equal(expCards[0].querySelector(".tv-exp-company"), null);
  assert.equal(expCards[0].classList.contains("tv-entry-readonly"), true);

  const eduCards = widget.eduListEl.querySelectorAll(".tv-entry");
  assert.equal(eduCards.length, 2);
  assert.equal(eduCards[0].querySelector(".tv-entry-remove"), null);
  assert.equal(eduCards[0].classList.contains("tv-entry-readonly"), true);
});

const DATA_B = {
  name: "Rohan Sharma",
  headline: "Staff Frontend Engineer",
  current_company: "Atlassian",
  location: "Bengaluru, India",
  summary: "Frontend engineer.",
  profile_url: "https://www.linkedin.com/in/rohan-sharma-dev/",
  source: "linkedin",
  skills: ["React", "TypeScript"],
  experience: [{ company_name: "Atlassian", designation: "Staff Frontend Engineer", duration: "Jan 2021 - Present" }],
  education: [{ institution: "BITS Pilani", degree: "B.E.", dates: "2012 - 2016" }],
};

test("navigating to another profile clears stale data and re-parses on open", async () => {
  let current = SAMPLE_DATA;
  const { widget, loc } = setupWidgetWithNav({
    getExtract: () => current,
    initialUrl: "https://www.linkedin.com/in/ananya-deshmukh-ai/",
  });

  widget.iconEl.click();
  await sleep(5);
  assert.equal(widget.getFields().name, "Ananya Deshmukh");

  widget.iconEl.click(); // close the panel
  assert.equal(widget.isOpen(), false);

  loc.href = "https://www.linkedin.com/in/rohan-sharma-dev/";
  current = DATA_B;
  widget.handleNavigation();

  // Stale data must never surface for the newly opened profile.
  assert.equal(widget.getState().extracted, null);
  assert.equal(widget.getFields().name, "");

  widget.iconEl.click();
  await sleep(5);

  assert.equal(widget.getFields().name, "Rohan Sharma");
  assert.equal(widget.getFields().company, "Atlassian");
  assert.notEqual(widget.getFields().name, "Ananya Deshmukh");
});

test("SPA history.pushState URL change clears an open panel and re-parses on reopen", async () => {
  let current = SAMPLE_DATA;
  const { widget, history } = setupWidgetWithNav({
    getExtract: () => current,
    initialUrl: "https://www.linkedin.com/in/ananya-deshmukh-ai/",
  });

  widget.iconEl.click();
  await sleep(5);
  assert.equal(widget.getFields().name, "Ananya Deshmukh");

  current = DATA_B;
  history.pushState({}, "", "https://www.linkedin.com/in/rohan-sharma-dev/");
  await sleep(5);

  // Stealth: navigation clears stale data but must NOT auto-parse.
  assert.equal(widget.getState().extracted, null);
  assert.equal(widget.getFields().name, "");

  // Re-parsing happens only on an explicit user action (toggle the panel).
  widget.iconEl.click(); // close
  widget.iconEl.click(); // open -> parse
  await sleep(5);

  assert.equal(widget.getFields().name, "Rohan Sharma");
  assert.equal(widget.getFields().company, "Atlassian");
});

test("switching modes preserves experience and education without duplicates", () => {
  const { widget } = setupWidget({ getExtract: () => MULTI_DATA });
  widget.populateForm(MULTI_DATA);
  assert.equal(widget.getState().experiences.length, 2);
  assert.equal(widget.getState().educations.length, 2);

  widget.setMode("manual");
  widget.setMode("parsing");
  widget.setMode("manual");

  assert.equal(widget.getState().experiences.length, 2);
  assert.equal(widget.getState().educations.length, 2);
  assert.equal(widget.getState().experiences[0].company_name, "NVIDIA");
  assert.equal(widget.getState().experiences[1].company_name, "Google");
});

test("resume checkbox is shown only when a resume is available", () => {
  const { widget } = setupWidget();

  widget.populateForm({ ...SAMPLE_DATA, resume_available: true, resume_url: "https://www.naukri.com/download-resume.pdf", resume_filename: "download-resume.pdf" });
  assert.equal(widget.resumeSection.classList.contains("hidden"), false);
  assert.equal(widget.resumeCheckbox.checked, false);

  widget.populateForm(SAMPLE_DATA);
  assert.equal(widget.resumeSection.classList.contains("hidden"), true);
});

const COMPREHENSIVE_DATA = {
  name: "Vikram Malhotra",
  headline: "Lead Architect",
  current_company: "Acme Corp",
  location: "Bengaluru, India",
  email: "vikram@example.com",
  phone: "+91 9123456789",
  summary: "Enterprise systems architect.",
  profile_url: "https://www.linkedin.com/in/vikram-malhotra/",
  source: "linkedin",
  total_experience: 12.5,
  current_salary: 35.0,
  expected_salary: 45.0,
  notice_period: 30,
  skills: ["Java", "Spring", "AWS", "Kafka"],
  experience: [
    { company_name: "Acme Corp", designation: "Lead Architect", duration: "2021 - Present", location: "Bengaluru", description: "Architecture lead" }
  ],
  education: [
    { institution: "IIT Bombay", degree: "M.Tech", field_of_study: "CS", dates: "2010 - 2012" }
  ],
  projects: [
    { name: "Global Payment Gateway", role: "Principal Architect", duration: "2022 - 2023", description: "High-throughput payment gateway." }
  ],
  certifications: [
    { name: "AWS Solutions Architect Professional", issuer: "AWS", issue_date: "2022", expiration_date: "2025" }
  ]
};

test("buildPayload serializes all candidate fields, projects, certifications, and personal_info", () => {
  const { widget } = setupWidget({ getExtract: () => COMPREHENSIVE_DATA });
  widget.populateForm(COMPREHENSIVE_DATA);

  const payload = widget.buildPayload();
  assert.equal(payload.name, "Vikram Malhotra");
  assert.equal(payload.full_name, "Vikram Malhotra");
  assert.equal(payload.current_company, "Acme Corp");
  assert.equal(payload.total_experience, 12.5);
  assert.equal(payload.current_salary, 35.0);
  assert.equal(payload.expected_salary, 45.0);
  assert.equal(payload.notice_period, 30);
  assert.equal(payload.projects.length, 1);
  assert.equal(payload.projects[0].name, "Global Payment Gateway");
  assert.equal(payload.certifications.length, 1);
  assert.equal(payload.certifications[0].name, "AWS Solutions Architect Professional");

  // Verify nested personal_info
  assert.ok(payload.personal_info);
  assert.equal(payload.personal_info.name, "Vikram Malhotra");
  assert.equal(payload.personal_info.current_company, "Acme Corp");
  assert.equal(payload.personal_info.total_experience, 12.5);
});

test("Parsing Mode renders projects and certifications as read-only cards", () => {
  const { widget } = setupWidget({ getExtract: () => COMPREHENSIVE_DATA });
  widget.populateForm(COMPREHENSIVE_DATA);

  const projCards = widget.projListEl.querySelectorAll(".tv-entry");
  assert.equal(projCards.length, 1);
  assert.equal(projCards[0].classList.contains("tv-entry-readonly"), true);
  assert.equal(projCards[0].querySelector(".tv-entry-remove"), null);

  const certCards = widget.certListEl.querySelectorAll(".tv-entry");
  assert.equal(certCards.length, 1);
  assert.equal(certCards[0].classList.contains("tv-entry-readonly"), true);
  assert.equal(certCards[0].querySelector(".tv-entry-remove"), null);
});

test("Manual Mode allows adding and removing projects and certifications", () => {
  const { widget } = setupWidget({ getExtract: () => COMPREHENSIVE_DATA });
  widget.populateForm(COMPREHENSIVE_DATA);
  widget.setMode("manual");

  assert.equal(widget.getState().projects.length, 1);
  assert.equal(widget.getState().certifications.length, 1);

  widget.projAddEl.click();
  widget.certAddEl.click();

  assert.equal(widget.getState().projects.length, 2);
  assert.equal(widget.getState().certifications.length, 2);

  const firstProjCard = widget.projListEl.querySelector(".tv-entry");
  firstProjCard.querySelector(".tv-entry-remove").click();
  assert.equal(widget.getState().projects.length, 1);

  const firstCertCard = widget.certListEl.querySelector(".tv-entry");
  firstCertCard.querySelector(".tv-entry-remove").click();
  assert.equal(widget.getState().certifications.length, 1);
});

test("switching modes preserves projects and certifications without duplicates", () => {
  const { widget } = setupWidget({ getExtract: () => COMPREHENSIVE_DATA });
  widget.populateForm(COMPREHENSIVE_DATA);

  assert.equal(widget.getState().projects.length, 1);
  assert.equal(widget.getState().certifications.length, 1);

  widget.setMode("manual");
  widget.setMode("parsing");
  widget.setMode("manual");

  assert.equal(widget.getState().projects.length, 1);
  assert.equal(widget.getState().certifications.length, 1);
  assert.equal(widget.getState().projects[0].name, "Global Payment Gateway");
  assert.equal(widget.getState().certifications[0].name, "AWS Solutions Architect Professional");
});

test("parse retries when sections render after a short delay", async () => {
  let calls = 0;
  const { widget } = setupWidget({
    getExtract: () => {
      calls += 1;
      return calls === 1
        ? { name: "Ananya Deshmukh", headline: "", current_company: "", location: "", skills: [], experience: [], education: [] }
        : SAMPLE_DATA;
    },
  });

  widget.iconEl.click();
  await sleep(1500);

  assert.ok(calls >= 2);
  assert.equal(widget.getFields().name, "Ananya Deshmukh");
  assert.equal(widget.getState().experiences.length, 1);
  assert.equal(widget.getState().educations.length, 1);
});

test("Save is blocked when the profile changed after parsing", async () => {
  const { widget, loc } = setupWidgetWithNav({
    getExtract: () => SAMPLE_DATA,
    initialUrl: "https://www.linkedin.com/in/ananya-deshmukh-ai/",
  });

  widget.iconEl.click();
  await sleep(5);
  assert.equal(widget.getFields().name, "Ananya Deshmukh");

  loc.href = "https://www.linkedin.com/in/rohan-sharma-dev/";
  await widget.save();

  assert.match(widget.statusEl.textContent, /profile changed/i);
});
