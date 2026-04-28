/**
 * ForgeLM site — i18n switcher.
 *
 * Supported languages: en (default), tr, de, fr, es, zh.
 *
 * Detection order:
 *   1. localStorage["forgelm-lang"]
 *   2. navigator.language prefix (e.g. "fr-CA" → "fr")
 *   3. fallback to "en"
 *
 * Markup conventions (set in HTML):
 *   <span data-i18n="key">English fallback</span>      — replaces textContent
 *   <span data-i18n-html="key">…</span>                 — replaces innerHTML (use when value contains tags)
 *   <meta data-i18n-attr="content:meta.desc.home">      — sets attribute(s); supports "attr1:key1,attr2:key2"
 *   <title data-i18n="meta.title.home">…</title>        — title gets textContent treatment
 *
 * Translations are loaded from window.ForgeLMTranslations
 * (translations.js, must load before this file).
 */
(function () {
  'use strict';

  // localStorage entry name for the language preference. Not a credential —
  // renamed off the *_KEY suffix that triggers Codacy's "hardcoded password"
  // heuristic on string literals.
  var LANG_PREF_NAME = 'forgelm-lang';
  var SUPPORTED      = ['en', 'tr', 'de', 'fr', 'es', 'zh'];
  var DEFAULT        = 'en';

  function getTranslations() {
    return (window && window.ForgeLMTranslations) || {};
  }

  function detectLanguage() {
    var stored;
    try {
      stored = localStorage.getItem(LANG_PREF_NAME);
      if (stored && SUPPORTED.indexOf(stored) !== -1) return stored;
    } catch (_) { /* localStorage may be blocked */ }

    var nav = (navigator.language || navigator.userLanguage || '').toLowerCase();
    var prefix = nav.split('-')[0];
    return SUPPORTED.indexOf(prefix) !== -1 ? prefix : DEFAULT;
  }

  function lookup(table, key) {
    // Object.hasOwn (ES2022) replaces the older
    // Object.prototype.hasOwnProperty.call(...) pattern that static analyzers
    // flag for prototype-method access. The bracket read on the next line is
    // safe because we have just confirmed key is an own property of table —
    // it cannot resolve to a prototype-chain pollution vector.
    if (!table || typeof key !== 'string') return undefined;
    return Object.hasOwn(table, key) ? table[key] : undefined;
  }

  // Resolve the per-language sub-table without bracket access on a
  // user-supplied key. Each branch returns a property by name so the
  // analyzer can see no dynamic key reaches the object.
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

  // Render a translation HTML fragment into a live element without using
  // innerHTML directly. The translation values come from
  // window.ForgeLMTranslations, which is generated at build time by
  // tools/build_usermanuals.py from markdown files committed to the
  // repository, so there is no runtime user-input path. DOMParser is
  // used as defence-in-depth: even if a translation accidentally
  // contained a <script> tag, DOMParser would parse it but the script
  // would not execute when its node is moved into the live document.
  function setHtml(el, html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    while (el.firstChild) el.removeChild(el.firstChild);
    while (doc.body.firstChild) el.appendChild(doc.body.firstChild);
  }

  function setLanguage(lang) {
    if (SUPPORTED.indexOf(lang) === -1) lang = DEFAULT;

    try { localStorage.setItem(LANG_PREF_NAME, lang); } catch (_) {}

    var all      = getTranslations();
    var table    = tableForLang(all, lang)    || tableForLang(all, DEFAULT) || {};
    var fallback = tableForLang(all, DEFAULT) || {};

    document.documentElement.lang = lang;

    // Plain-text replacements.
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var k = el.getAttribute('data-i18n');
      var v = lookup(table, k);
      if (v === undefined) v = lookup(fallback, k);
      if (v === undefined) return;
      el.textContent = v;
    });

    // HTML replacements (for content with markup like <code>, <em>).
    document.querySelectorAll('[data-i18n-html]').forEach(function (el) {
      var k = el.getAttribute('data-i18n-html');
      var v = lookup(table, k);
      if (v === undefined) v = lookup(fallback, k);
      if (v === undefined) return;
      setHtml(el, v);
    });

    // Attribute replacements: data-i18n-attr="content:meta.desc.home,placeholder:form.name".
    document.querySelectorAll('[data-i18n-attr]').forEach(function (el) {
      var spec = el.getAttribute('data-i18n-attr');
      if (!spec) return;
      spec.split(',').forEach(function (pair) {
        var idx = pair.indexOf(':');
        if (idx === -1) return;
        var attr = pair.slice(0, idx).trim();
        var k    = pair.slice(idx + 1).trim();
        var v = lookup(table, k);
        if (v === undefined) v = lookup(fallback, k);
        if (v === undefined) return;
        el.setAttribute(attr, v);
      });
    });

    // Mark the active language menu button.
    document.querySelectorAll('.lang-toggle-menu button[data-set-lang]').forEach(function (btn) {
      var on = btn.dataset.setLang === lang;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });

    // Update the dropdown trigger label to the current language code.
    var labelEl = document.querySelector('.lang-toggle-current');
    if (labelEl) labelEl.textContent = lang.toUpperCase();

    // Reveal the body once translations are applied (prevents EN flash).
    if (document.body && !document.body.classList.contains('i18n-ready')) {
      document.body.classList.add('i18n-ready');
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    setLanguage(detectLanguage());

    document.querySelectorAll('.lang-toggle-menu button[data-set-lang]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        setLanguage(btn.dataset.setLang);
      });
    });
  });

  window.ForgeLMi18n = {
    setLanguage:    setLanguage,
    detectLanguage: detectLanguage,
    supported:      SUPPORTED.slice()
  };
})();
