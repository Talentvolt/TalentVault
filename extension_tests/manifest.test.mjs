import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";

import { MANIFEST_PATH, EXTENSION_DIR } from "./harness.mjs";

function readExtensionFile(name) {
  return readFileSync(path.join(EXTENSION_DIR, name), "utf8");
}

test("manifest name is exactly 'Talent Vault' and stale branding is removed", () => {
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));
  assert.equal(manifest.name, "Talent Vault");
  assert.doesNotMatch(manifest.description, /Candidate Importer/i);
  assert.match(manifest.description, /Talent Vault/);
  assert.equal(manifest.action.default_title, "Open Talent Vault");

  // The floating widget is wired into the content scripts alongside content.js.
  const js = manifest.content_scripts[0].js;
  assert.ok(js.includes("content.js"));
  assert.ok(js.includes("widget.js"));

  // The stable extension ID is preserved by the Chrome Web Store, not by a
  // manifest "key" checked into source. No key is present in the repo manifest.
  assert.equal(manifest.key, undefined);
});

test("no visible 'TalentVault' (one word) or 'Candidate Importer' branding remains", () => {
  const sidepanelHtml = readExtensionFile("sidepanel.html");
  assert.doesNotMatch(sidepanelHtml, /Candidate Importer/);
  assert.doesNotMatch(sidepanelHtml, /TalentVault/);
  assert.match(sidepanelHtml, /<title>Talent Vault<\/title>/);

  const sidepanelJs = readExtensionFile("sidepanel.js");
  assert.doesNotMatch(sidepanelJs, /TalentVault/);
  assert.doesNotMatch(sidepanelJs, /Candidate Importer/);

  const widgetJs = readExtensionFile("widget.js");
  assert.doesNotMatch(widgetJs, /Candidate Importer/);
  assert.doesNotMatch(widgetJs, /TalentVault/);
  assert.match(widgetJs, /Talent Vault/);

  const contentJs = readExtensionFile("content.js");
  assert.doesNotMatch(contentJs, /TalentVault/);

  const backgroundJs = readExtensionFile("background.js");
  assert.doesNotMatch(backgroundJs, /TalentVault/);
  assert.doesNotMatch(backgroundJs, /Candidate Importer/);
});

test("floating widget is the only interface (no side panel or popup)", () => {
  const manifest = JSON.parse(readFileSync(MANIFEST_PATH, "utf8"));

  // No Chrome side panel and no toolbar popup: the in-page floating widget is
  // the single primary interface.
  assert.equal(manifest.side_panel, undefined);
  assert.equal(manifest.action.default_popup, undefined);
  assert.equal(manifest.permissions.includes("sidePanel"), false);

  const backgroundJs = readExtensionFile("background.js");
  assert.doesNotMatch(backgroundJs, /setPanelBehavior/);
  assert.doesNotMatch(backgroundJs, /openPanelOnActionClick/);
});
