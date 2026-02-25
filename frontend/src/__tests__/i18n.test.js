import { describe, it, expect } from "vitest";
import en from "src/i18n/en.js";
import fr from "src/i18n/fr.js";

// All keys present in the English locale must also exist in every other locale.
const REQUIRED_KEYS = Object.keys(en);

describe("i18n — en", () => {
  it("has all required keys", () => {
    for (const key of REQUIRED_KEYS) {
      expect(en[key], `en.${key} should be defined`).toBeDefined();
    }
  });

  it("has no empty values", () => {
    for (const key of REQUIRED_KEYS) {
      expect(en[key].trim(), `en.${key} should not be empty`).not.toBe("");
    }
  });
});

describe("i18n — fr", () => {
  it("has all required keys", () => {
    for (const key of REQUIRED_KEYS) {
      expect(fr[key], `fr.${key} should be defined`).toBeDefined();
    }
  });

  it("has no empty values", () => {
    for (const key of REQUIRED_KEYS) {
      expect(fr[key].trim(), `fr.${key} should not be empty`).not.toBe("");
    }
  });

  it("has the same key count as en", () => {
    expect(Object.keys(fr).length).toBe(REQUIRED_KEYS.length);
  });
});
