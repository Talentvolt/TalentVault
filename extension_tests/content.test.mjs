import { test } from "node:test";
import assert from "node:assert/strict";

import { loadContent, createDocument } from "./harness.mjs";

function load() {
  const chrome = {
    runtime: {
      onMessage: { addListener() {} },
      lastError: null,
    },
  };
  const document = createDocument();
  return loadContent({ chrome, document });
}

test("extractEmailFromText finds an email address", () => {
  const s = load();
  assert.equal(
    s.extractEmailFromText("Contact me at ananya@nvidia.com please"),
    "ananya@nvidia.com"
  );
  assert.equal(s.extractEmailFromText("no email here"), "");
});

test("normalizePhoneNumber strips formatting characters", () => {
  const s = load();
  assert.equal(s.normalizePhoneNumber("+91 98765-43210"), "+919876543210");
  assert.equal(s.normalizePhoneNumber("(987) 654-3210"), "9876543210");
  assert.equal(s.normalizePhoneNumber(""), "");
});

test("extractPhoneFromText finds a labeled phone number", () => {
  const s = load();
  assert.equal(s.extractPhoneFromText("Phone: +91 98765 43210"), "+919876543210");
  assert.equal(s.extractPhoneFromText("Mobile: 9876543210"), "9876543210");
});

test("sanitizeString collapses whitespace and de-duplicates splits", () => {
  const s = load();
  assert.equal(s.sanitizeString("  Hello\tWorld\nAgain  "), "Hello World Again");
  assert.equal(s.sanitizeString("Foo • Foo"), "Foo");
});

test("cleanCompanyName strips employment-type suffixes", () => {
  const s = load();
  assert.equal(s.cleanCompanyName("NVIDIA · Full-time"), "NVIDIA");
  assert.equal(s.cleanCompanyName("Google • Part-time"), "Google");
});

test("calculateTotalExperienceYears sums mixed durations", () => {
  const s = load();
  const total = s.calculateTotalExperienceYears([
    { duration: "4 yrs 10 mos" },
    { duration: "2 yrs" },
  ]);
  assert.equal(total, 6.8);
});
