import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";

import { BACKGROUND_PATH } from "./harness.mjs";

function fetchMock() {
  const calls = [];
  const impl = async (url, opts) => {
    calls.push({ url, opts });
    const method = (opts && opts.method) || "GET";
    if (method === "GET") {
      return { ok: true, status: 200, json: async () => ({ csrfToken: "tok123" }) };
    }
    return { ok: true, status: 201, json: async () => ({ status: "success", action: "created", candidate_id: "abc-123" }) };
  };
  impl.calls = calls;
  return impl;
}

function setupBackground({ fetch } = {}) {
  const chrome = {
    sidePanel: { setPanelBehavior: () => Promise.resolve() },
    runtime: {
      onInstalled: { addListener() {} },
      onMessage: { addListener(fn) { chrome.runtime._listener = fn; } },
    },
    storage: { local: { get(_key, cb) { cb({}); } } },
  };
  const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    setImmediate,
    URL,
    Date,
    chrome,
    fetch: fetch || fetchMock(),
  };
  vm.createContext(sandbox);
  vm.runInContext(readFileSync(BACKGROUND_PATH, "utf8"), sandbox, { filename: "background.js" });
  return { chrome, fetch: sandbox.fetch };
}

test("background proxies a candidate save with a valid CSRF token", async () => {
  const fetch = fetchMock();
  const { chrome } = setupBackground({ fetch });
  const listener = chrome.runtime._listener;
  assert.equal(typeof listener, "function");

  const responsePromise = new Promise((resolve) => {
    const keepChannelOpen = listener(
      { action: "tv_api_request", method: "POST", path: "/api/v1/candidates/import/", body: { full_name: "Ananya Deshmukh", name: "Ananya Deshmukh" } },
      {},
      (resp) => resolve(resp)
    );
    assert.equal(keepChannelOpen, true);
  });

  const resp = await responsePromise;
  assert.equal(resp.ok, true);
  assert.equal(resp.status, 201);
  assert.equal(resp.data.status, "success");

  const postCall = fetch.calls.find((c) => (c.opts.method || "GET") === "POST");
  assert.ok(postCall);
  assert.equal(postCall.url, "http://127.0.0.1:8000/api/v1/candidates/import/");
  assert.equal(postCall.opts.headers["X-CSRFToken"], "tok123");
  assert.equal(postCall.opts.credentials, "include");
});

test("background GET returns the CSRF token without an X-CSRFToken header", async () => {
  const fetch = fetchMock();
  const { chrome } = setupBackground({ fetch });
  const listener = chrome.runtime._listener;

  const responsePromise = new Promise((resolve) => {
    listener({ action: "tv_api_request", method: "GET", path: "/api/v1/candidates/import/" }, {}, (resp) => resolve(resp));
  });

  const resp = await responsePromise;
  assert.equal(resp.ok, true);
  assert.equal(resp.data.csrfToken, "tok123");

  const getCall = fetch.calls[0];
  assert.equal(getCall.opts.method, "GET");
  assert.equal(getCall.opts.headers, undefined);
});
