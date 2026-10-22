import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const EXTENSION_DIR = path.resolve(__dirname, "..", "talentvault_extension");
export const PANEL_PATH = path.join(EXTENSION_DIR, "sidepanel.js");
export const CONTENT_PATH = path.join(EXTENSION_DIR, "content.js");
export const WIDGET_PATH = path.join(EXTENSION_DIR, "widget.js");
export const BACKGROUND_PATH = path.join(EXTENSION_DIR, "background.js");
export const MANIFEST_PATH = path.join(EXTENSION_DIR, "manifest.json");

function matchesSelector(el, selector) {
  selector = String(selector).trim();
  if (!selector) return false;
  const idMatch = selector.match(/#([\w-]+)/);
  const clsMatches = [...selector.matchAll(/\.([\w-]+)/g)].map((m) => m[1]);
  const attrMatches = [...selector.matchAll(/\[([\w-]+)(?:=["']?([^"'\]]*)["']?)?\]/g)];
  const tagMatch = selector.match(/^([a-zA-Z][\w-]*)/);
  const tag = tagMatch ? tagMatch[1].toLowerCase() : null;

  if (idMatch && el.id !== idMatch[1]) return false;
  if (tag && el.tagName && el.tagName.toLowerCase() !== tag) return false;
  for (const c of clsMatches) if (!el.classList.contains(c)) return false;
  for (const [, name, val] of attrMatches) {
    if (el.getAttribute(name) === undefined) return false;
    if (val !== undefined && el.getAttribute(name) !== val) return false;
  }
  return true;
}

function findFirst(root, selector) {
  if (!root.children) return null;
  for (const child of root.children) {
    if (matchesSelector(child, selector)) return child;
    const found = findFirst(child, selector);
    if (found) return found;
  }
  return null;
}

function findAll(root, selector, out) {
  out = out || [];
  if (!root.children) return out;
  for (const child of root.children) {
    if (matchesSelector(child, selector)) out.push(child);
    findAll(child, selector, out);
  }
  return out;
}

export function createFakeElement(tag) {
  const classSet = new Set();
  const attributes = {};
  const listeners = {};
  const el = {
    tagName: String(tag || "div").toUpperCase(),
    id: "",
    children: [],
    parentElement: null,
    shadowRoot: null,
    value: "",
    _textContent: "",
    get textContent() {
      return this._textContent;
    },
    set textContent(v) {
      this._textContent = String(v);
      this.children.length = 0;
    },
    innerHTML: "",
    disabled: false,
    type: "",
    title: "",
    style: {},
    get firstChild() {
      return this.children[0] || null;
    },
    replaceChildren(...nodes) {
      this.children.length = 0;
      nodes.forEach((n) => this.appendChild(n));
    },
    get className() {
      return Array.from(classSet).join(" ");
    },
    set className(v) {
      classSet.clear();
      String(v || "").split(/\s+/).filter(Boolean).forEach((c) => classSet.add(c));
    },
    classList: {
      _set: classSet,
      add: (...names) => names.forEach((n) => classSet.add(n)),
      remove: (...names) => names.forEach((n) => classSet.delete(n)),
      contains: (n) => classSet.has(n),
      toggle: (n, force) => {
        if (force === undefined) {
          if (classSet.has(n)) {
            classSet.delete(n);
            return false;
          }
          classSet.add(n);
          return true;
        }
        if (force) {
          classSet.add(n);
          return true;
        }
        classSet.delete(n);
        return false;
      },
    },
    addEventListener(type, fn) {
      listeners[type] = fn;
    },
    _listeners: listeners,
    setAttribute(name, value) {
      attributes[name] = String(value);
    },
    getAttribute(name) {
      return attributes[name];
    },
    removeAttribute(name) {
      delete attributes[name];
    },
    appendChild(child) {
      child.parentElement = el;
      el.children.push(child);
      return child;
    },
    removeChild(child) {
      const i = el.children.indexOf(child);
      if (i >= 0) el.children.splice(i, 1);
      child.parentElement = null;
      return child;
    },
    attachShadow() {
      const root = createFakeElement("shadow-root");
      root.host = el;
      el.shadowRoot = root;
      return root;
    },
    querySelector(sel) {
      return findFirst(el, sel);
    },
    querySelectorAll(sel) {
      return findAll(el, sel);
    },
    click() {
      const fn = listeners.click;
      if (fn) fn({ target: el });
    },
  };
  return el;
}

export function createDocument() {
  const elements = {};
  const docListeners = {};
  const body = createFakeElement("body");
  const doc = {
    elements,
    body,
    _listeners: docListeners,
    getElementById(id) {
      if (!elements[id]) elements[id] = createFakeElement("div");
      return elements[id];
    },
    addEventListener(type, cb) {
      (docListeners[type] = docListeners[type] || []).push(cb);
    },
    createElement(tag) {
      return createFakeElement(tag);
    },
    querySelectorAll() {
      return [];
    },
    querySelector() {
      return null;
    },
  };
  return doc;
}

export function createFetchSpy() {
  const calls = [];
  const spy = async (...args) => {
    calls.push(args);
    throw new Error("fetch should not be called in these tests");
  };
  spy.calls = calls;
  return spy;
}

export function createChromeMock({
  activeTab = null,
  onSendMessage = null,
  sendMessageImpl = null,
  onExecuteScript = null,
  onStorageGet = null,
  runtimeMessageResponse = undefined,
  runtimeMessageHandler = null,
} = {}) {
  const mock = {
    runtime: {
      lastError: null,
      _onMessageListener: null,
      _onInstalledListener: null,
      sendMessage(msg, callback) {
        if (runtimeMessageHandler) {
          const resp = runtimeMessageHandler(msg);
          if (callback) return callback(resp);
          return Promise.resolve(resp);
        }
        const resp = runtimeMessageResponse;
        if (callback) return callback(resp);
        return Promise.resolve(resp);
      },
      onMessage: {
        addListener(fn) {
          mock.runtime._onMessageListener = fn;
        },
      },
      onInstalled: {
        addListener(fn) {
          mock.runtime._onInstalledListener = fn;
        },
      },
    },
    sidePanel: {
      setPanelBehavior() {
        return Promise.resolve();
      },
    },
    storage: {
      local: {
        get(key, cb) {
          if (onStorageGet) return onStorageGet(key, cb);
          cb({});
        },
      },
    },
    tabs: {
      query(_params, cb) {
        mock.runtime.lastError = null;
        cb(activeTab ? [activeTab] : []);
      },
      sendMessage(tabId, msg, cb) {
        if (sendMessageImpl) {
          sendMessageImpl(tabId, msg, cb, mock);
          return;
        }
        if (onSendMessage) {
          const result = onSendMessage(tabId, msg);
          if (result && result.__noReceiver) {
            mock.runtime.lastError = { message: result.__noReceiver };
            cb(undefined);
          } else {
            mock.runtime.lastError = null;
            cb(result);
          }
          return;
        }
        mock.runtime.lastError = { message: "Receiving end does not exist" };
        cb(undefined);
      },
    },
    scripting: {
      executeScript(_opts, cb) {
        if (onExecuteScript) {
          const err = onExecuteScript(_opts);
          mock.runtime.lastError = err ? { message: err } : null;
          cb();
          return;
        }
        mock.runtime.lastError = null;
        cb();
      },
    },
  };
  return mock;
}

function baseSandbox() {
  return {
    console,
    setTimeout,
    clearTimeout,
    setImmediate,
    URL,
    Date,
  };
}

export function loadScript(source, sandbox, filename) {
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename });
  return sandbox;
}

function readPath(p) {
  return readFileSync(p, "utf8");
}

export function loadPanel({ chrome, document, fetch }) {
  const sandbox = {
    ...baseSandbox(),
    chrome,
    document,
    window: {},
    fetch: fetch || createFetchSpy(),
  };
  return loadScript(readPath(PANEL_PATH), sandbox, "sidepanel.js");
}

export function loadContent({ chrome, document, window = {}, fetch }) {
  const sandbox = {
    ...baseSandbox(),
    chrome,
    document,
    window,
    fetch: fetch || createFetchSpy(),
  };
  return loadScript(readPath(CONTENT_PATH), sandbox, "content.js");
}

export function loadWidget({ chrome, document, window = {}, fetch }) {
  const sandbox = {
    ...baseSandbox(),
    chrome,
    document,
    window,
    fetch: fetch || createFetchSpy(),
  };
  return loadScript(readPath(WIDGET_PATH), sandbox, "widget.js");
}

export function loadBackground({ chrome, fetch }) {
  const sandbox = {
    ...baseSandbox(),
    chrome,
    fetch: fetch || createFetchSpy(),
  };
  return loadScript(readPath(BACKGROUND_PATH), sandbox, "background.js");
}

export async function flushAsync(iterations = 6) {
  for (let i = 0; i < iterations; i++) {
    await new Promise((resolve) => setImmediate(resolve));
  }
}

export const LINKEDIN_TAB = {
  id: 42,
  url: "https://www.linkedin.com/in/ananya-deshmukh-ai/",
};

export const NAUKRI_TAB = {
  id: 43,
  url: "https://www.naukri.com/mnjuser/profile?id=123",
};

export const SAMPLE_DATA = {
  name: "Ananya Deshmukh",
  email: "",
  phone: "",
  headline: "Principal AI Architect",
  current_company: "NVIDIA",
  location: "Bengaluru, Karnataka, India",
  summary: "14+ years of experience building AI systems.",
  profile_url: "https://www.linkedin.com/in/ananya-deshmukh-ai/",
  source: "linkedin",
  skills: ["Python", "PyTorch"],
  experience: [{ company_name: "NVIDIA", designation: "Principal AI Architect", duration: "Jan 2022 - Present" }],
  education: [{ institution: "IISc", degree: "Ph.D.", dates: "2008 - 2012" }],
};
