import { test } from "node:test";
import assert from "node:assert/strict";

import {
  createChromeMock,
  createDocument,
  createFetchSpy,
  loadPanel,
  flushAsync,
  LINKEDIN_TAB,
  NAUKRI_TAB,
  SAMPLE_DATA,
} from "./harness.mjs";

function setup(options = {}) {
  const document = createDocument();
  const fetch = options.fetch || createFetchSpy();
  const chrome = createChromeMock(options);
  const sandbox = loadPanel({ chrome, document, fetch });

  // Seed the initial UI state to mirror sidepanel.html.
  document.getElementById("parsingModeBtn").classList.add("active");
  document.getElementById("candidateForm").classList.add("hidden");
  document.getElementById("parsingStatus").classList.add("hidden");
  document.getElementById("parseError").classList.add("hidden");
  document.getElementById("retryBtn").classList.add("hidden");

  const fireDomReady = () => {
    const listeners = document._listeners.DOMContentLoaded || [];
    listeners.forEach((cb) => cb());
  };
  return { sandbox, document, chrome, fetch, fireDomReady };
}

function clickButton(document, id) {
  const el = document.getElementById(id);
  const fn = el && el._listeners && el._listeners.click;
  if (fn) fn();
  return el;
}

test("isSupportedSource accepts LinkedIn and Naukri, rejects others", () => {
  const { sandbox } = setup();
  assert.equal(sandbox.isSupportedSource(LINKEDIN_TAB.url), true);
  assert.equal(sandbox.isSupportedSource(NAUKRI_TAB.url), true);
  assert.equal(sandbox.isSupportedSource("https://example.com/profile"), false);
  assert.equal(sandbox.isSupportedSource("https://talent-vault.in/jobs"), false);
  assert.equal(sandbox.isSupportedSource(""), false);
  assert.equal(sandbox.isSupportedSource(null), false);
});

test("parse button parses a LinkedIn profile and populates the form", async () => {
  const { document, fireDomReady } = setup({
    activeTab: LINKEDIN_TAB,
    onSendMessage: () => ({ status: "success", data: SAMPLE_DATA }),
  });

  fireDomReady();
  await flushAsync();

  // Stealth: opening the panel must NOT auto-parse.
  assert.equal(document.getElementById("fieldName").value, "");

  clickButton(document, "parseBtn");
  await flushAsync();

  assert.equal(document.getElementById("fieldName").value, "Ananya Deshmukh");
  assert.equal(document.getElementById("fieldCurrentCompany").value, "NVIDIA");
  // Success: the form is shown and the parsing card is collapsed.
  assert.equal(document.getElementById("candidateForm").classList.contains("hidden"), false);
  assert.equal(document.getElementById("extractCard").classList.contains("hidden"), true);
  // Loading/error/retry controls are all cleared after a successful parse.
  assert.equal(document.getElementById("parsingStatus").classList.contains("hidden"), true);
  assert.equal(document.getElementById("parseError").classList.contains("hidden"), true);
  assert.equal(document.getElementById("retryBtn").classList.contains("hidden"), true);
});

test("loading indicator is shown while parsing is in flight", async () => {
  let finishSend;
  const { document, fireDomReady } = setup({
    activeTab: LINKEDIN_TAB,
    sendMessageImpl: (_tabId, _msg, cb, mock) => {
      finishSend = () => {
        mock.runtime.lastError = null;
        cb({ status: "success", data: SAMPLE_DATA });
      };
    },
  });

  fireDomReady();
  await flushAsync();

  clickButton(document, "parseBtn");
  await flushAsync();

  // While the content script response is pending, the loading state is visible.
  assert.equal(document.getElementById("parsingStatus").classList.contains("hidden"), false);
  assert.equal(document.getElementById("parseError").classList.contains("hidden"), true);

  finishSend();
  await flushAsync();

  assert.equal(document.getElementById("parsingStatus").classList.contains("hidden"), true);
  assert.equal(document.getElementById("fieldName").value, "Ananya Deshmukh");
});

test("unsupported page falls back to Manual Mode without contacting the content script", async () => {
  let sendMessageCalls = 0;
  const { document, fireDomReady } = setup({
    activeTab: { id: 99, url: "https://example.com/someone" },
    onSendMessage: () => {
      sendMessageCalls += 1;
      return { status: "success", data: SAMPLE_DATA };
    },
  });

  fireDomReady();
  await flushAsync();

  clickButton(document, "parseBtn");
  await flushAsync();

  assert.equal(sendMessageCalls, 0);
  assert.equal(document.getElementById("manualModeBtn").classList.contains("active"), true);
  assert.equal(document.getElementById("parsingModeBtn").classList.contains("active"), false);
  assert.equal(document.getElementById("extractCard").classList.contains("hidden"), true);
  assert.equal(document.getElementById("candidateForm").classList.contains("hidden"), false);
  assert.match(
    document.getElementById("statusAlert").textContent,
    /isn't supported/i
  );
});

test("parsing failure shows a clear error, stays in Parsing Mode and does not auto-save", async () => {
  const { document, fetch, fireDomReady } = setup({
    activeTab: LINKEDIN_TAB,
    onSendMessage: () => ({ __noReceiver: "Receiving end does not exist" }),
    onExecuteScript: () => "Cannot access a chrome:// URL",
  });

  fireDomReady();
  await flushAsync();

  clickButton(document, "parseBtn");
  await flushAsync();

  // Still in Parsing Mode (not silently flipped to Manual), with an error + retry.
  assert.equal(document.getElementById("parsingModeBtn").classList.contains("active"), true);
  assert.equal(document.getElementById("manualModeBtn").classList.contains("active"), false);
  assert.equal(document.getElementById("extractCard").classList.contains("hidden"), false);
  assert.equal(document.getElementById("parseError").classList.contains("hidden"), false);
  assert.equal(document.getElementById("retryBtn").classList.contains("hidden"), false);
  assert.equal(document.getElementById("candidateForm").classList.contains("hidden"), true);
  assert.match(
    document.getElementById("parseError").textContent,
    /could not extract/i
  );
  // Save was never triggered: no fetch (POST) call and the form stayed empty.
  assert.equal(fetch.calls.length, 0);
  assert.equal(document.getElementById("fieldName").value, "");
});

test("retry button re-parses the active profile after a failure", async () => {
  let shouldFail = true;
  const { document, fireDomReady } = setup({
    activeTab: LINKEDIN_TAB,
    onSendMessage: () =>
      shouldFail
        ? { __noReceiver: "Receiving end does not exist" }
        : { status: "success", data: SAMPLE_DATA },
    onExecuteScript: () => (shouldFail ? "Cannot access this page" : null),
  });

  fireDomReady();
  await flushAsync();

  clickButton(document, "parseBtn");
  await flushAsync();

  assert.equal(document.getElementById("retryBtn").classList.contains("hidden"), false);
  assert.equal(document.getElementById("fieldName").value, "");

  shouldFail = false;
  clickButton(document, "retryBtn");
  await flushAsync();

  assert.equal(document.getElementById("fieldName").value, "Ananya Deshmukh");
  assert.equal(document.getElementById("parseError").classList.contains("hidden"), true);
  assert.equal(document.getElementById("retryBtn").classList.contains("hidden"), true);
});

test("panel open does not auto-parse; only an explicit click parses once", async () => {
  let sendMessageCalls = 0;
  const { document, fireDomReady } = setup({
    activeTab: LINKEDIN_TAB,
    onSendMessage: () => {
      sendMessageCalls += 1;
      return { status: "success", data: SAMPLE_DATA };
    },
  });

  // Opening/updating the panel must not trigger any parse (manual trigger only).
  fireDomReady();
  fireDomReady();
  await flushAsync();

  assert.equal(sendMessageCalls, 0);
  assert.equal(document.getElementById("fieldName").value, "");

  clickButton(document, "parseBtn");
  await flushAsync();

  assert.equal(sendMessageCalls, 1);
  assert.equal(document.getElementById("fieldName").value, "Ananya Deshmukh");
});

test("overlapping parse calls are ignored (parseInFlight guard)", async () => {
  let sendMessageCalls = 0;
  let finishSend;
  const { sandbox, document } = setup({
    activeTab: LINKEDIN_TAB,
    sendMessageImpl: (_tabId, _msg, cb, mock) => {
      sendMessageCalls += 1;
      finishSend = () => {
        mock.runtime.lastError = null;
        cb({ status: "success", data: SAMPLE_DATA });
      };
    },
  });

  const first = sandbox.parseActivePage();
  sandbox.parseActivePage(); // ignored while the first run is in flight
  await flushAsync(2);

  assert.equal(sendMessageCalls, 1);

  finishSend();
  await first;
  await flushAsync();

  assert.equal(document.getElementById("fieldName").value, "Ananya Deshmukh");
});

test("sidepanel populates projects, certifications, and sends matching structured payload on save", async () => {
  const fullData = {
    name: "Arjun Verma",
    email: "arjun@example.com",
    phone: "+91 9876543210",
    headline: "Staff Cloud Engineer",
    current_company: "Kubernetes Corp",
    location: "Bengaluru, India",
    summary: "Cloud infrastructure architect.",
    profile_url: "https://www.linkedin.com/in/arjun-verma/",
    source: "linkedin",
    skills: ["Go", "Kubernetes", "AWS"],
    total_experience: 10.0,
    current_salary: 30.0,
    expected_salary: 40.0,
    notice_period: 15,
    experience: [
      { company_name: "Kubernetes Corp", designation: "Staff Cloud Engineer", duration: "2020 - Present", location: "Bengaluru", description: "Infra lead" }
    ],
    education: [
      { institution: "IIT Madras", degree: "B.Tech", field_of_study: "CS", dates: "2010 - 2014" }
    ],
    projects: [
      { name: "Cluster Autoscaler", role: "Maintainer", duration: "2021 - 2023", description: "Core maintainer of autoscaler." }
    ],
    certifications: [
      { name: "CKA: Certified Kubernetes Administrator", issuer: "CNCF", issue_date: "2021", expiration_date: "2024" }
    ]
  };

  const fetchCalls = [];
  const fetch = async (url, options = {}) => {
    fetchCalls.push({ url, options });
    const method = (options.method || "GET").toUpperCase();
    if (method === "GET") {
      return { ok: true, status: 200, json: async () => ({ csrfToken: "tok123" }) };
    }
    return { ok: true, status: 201, json: async () => ({ status: "success", action: "created", candidate_id: "abc-123" }) };
  };
  fetch.calls = fetchCalls;

  const { sandbox, document, fireDomReady } = setup({
    fetch,
    activeTab: LINKEDIN_TAB,
    onSendMessage: () => ({ status: "success", data: fullData }),
  });

  fireDomReady();
  await flushAsync();

  clickButton(document, "parseBtn");
  await flushAsync();

  assert.equal(document.getElementById("fieldName").value, "Arjun Verma");
  assert.equal(document.getElementById("fieldCurrentCompany").value, "Kubernetes Corp");
  assert.equal(document.getElementById("fieldTotalExperience").value, "10");
  assert.equal(document.getElementById("fieldCurrentSalary").value, "30");
  assert.equal(document.getElementById("fieldNoticePeriod").value, "15");

  // Save the candidate
  await sandbox.handleSaveCandidate();
  await flushAsync();

  // Verify fetch call to importEndpoint
  assert.ok(fetch.calls.length >= 1);
  const saveCall = fetch.calls.find(
    (c) => c.url.includes("/api/v1/candidates/import/") && ((c.options.method || "GET").toUpperCase() === "POST")
  );
  assert.ok(saveCall);
  const sentPayload = JSON.parse(saveCall.options.body);

  assert.equal(sentPayload.full_name, "Arjun Verma");
  assert.equal(sentPayload.current_company, "Kubernetes Corp");
  assert.equal(sentPayload.total_experience, 10.0);
  assert.equal(sentPayload.current_salary, 30.0);
  assert.equal(sentPayload.expected_salary, 40.0);
  assert.equal(sentPayload.notice_period, 15);
  assert.equal(sentPayload.experience.length, 1);
  assert.equal(sentPayload.experience[0].company_name, "Kubernetes Corp");
  assert.equal(sentPayload.education.length, 1);
  assert.equal(sentPayload.education[0].institution, "IIT Madras");
  assert.equal(sentPayload.projects.length, 1);
  assert.equal(sentPayload.projects[0].name, "Cluster Autoscaler");
  assert.equal(sentPayload.certifications.length, 1);
  assert.equal(sentPayload.certifications[0].name, "CKA: Certified Kubernetes Administrator");

  // Verify nested personal_info
  assert.ok(sentPayload.personal_info);
  assert.equal(sentPayload.personal_info.name, "Arjun Verma");
  assert.equal(sentPayload.personal_info.current_company, "Kubernetes Corp");
});
