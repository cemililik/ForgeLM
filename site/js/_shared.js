/* ForgeLM site shared helpers — single source of truth for the small
   utilities that previously lived inline in main.js, wizard.js,
   i18n.js, and guide.js. Loaded BEFORE translations.js so consumers
   can rely on ``window.ForgeLMShared`` from any module-init path. */
(function () {
  'use strict';
  if (window.ForgeLMShared) return; // idempotent

  /* ── Locale lookup ─────────────────────────────────────────
     Returns the translation table for the requested language, or
     undefined when the language code is unknown. ``all`` is the
     ``window.ForgeLMTranslations`` payload (split into per-locale
     sub-objects). The switch keeps the lookup branchless for the
     six declared locales. */
  function tableForLang(all, lang) {
    if (!all) return undefined;
    switch (lang) {
      case 'en': return all.en;
      case 'tr': return all.tr;
      case 'de': return all.de;
      case 'fr': return all.fr;
      case 'es': return all.es;
      case 'zh': return all.zh;
      default:   return undefined;
    }
  }

  /* ── tr(key) ───────────────────────────────────────────────
     Look up an i18n key against ``document.documentElement.lang``.
     Falls back to English if the active locale is missing the key,
     and finally to the key itself if neither resolves — that way a
     missing key is visible in the UI rather than rendering blank. */
  function tr(key) {
    if (typeof key !== 'string') return key;
    var lang = document.documentElement.lang || 'en';
    var all = window.ForgeLMTranslations || {};
    var table = tableForLang(all, lang) || all.en || {};
    if (Object.prototype.hasOwnProperty.call(table, key)) return table[key];
    var en = all.en || {};
    if (Object.prototype.hasOwnProperty.call(en, key)) return en[key];
    return key;
  }

  /* ── escapeHtml ────────────────────────────────────────────
     Defense-in-depth HTML entity escape for any string that ends up
     concatenated into innerHTML. Most renderers prefer textContent
     or DOMParser, but a few (YAML syntax tinting, comment headers)
     build HTML directly — this helper keeps those XSS-safe. */
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  window.ForgeLMShared = {
    tableForLang: tableForLang,
    tr: tr,
    escapeHtml: escapeHtml
  };
})();
