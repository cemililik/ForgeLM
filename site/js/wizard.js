/**
 * ForgeLM site — in-browser YAML wizard.
 *
 * Mirrors the CLI ``forgelm --wizard`` flow but lives entirely in the
 * browser: walks the operator through 7 steps (welcome / use-case /
 * model / dataset / training / eval+compliance / review) and emits a
 * working ``quickstart-generated.yaml`` they can copy, download, or
 * paste into a shell command. Every transition + every input change
 * is persisted to ``localStorage`` so a refresh resumes the same
 * step. Behaviour summary:
 *
 * - Triggers: ``[data-wizard-open]`` clicks + the ``?wizard=open``
 *   URL parameter (set by the home-page Beginner-slide CTA).
 * - State: in-memory object mirrored to ``localStorage`` under
 *   ``forgelm.wizard.state``. Schema versioning via ``state.v``
 *   so a future shape change can clear stale snapshots.
 * - YAML preview: rebuilt on every state change; both desktop
 *   sidebar and mobile accordion bind to the same string.
 * - i18n: every string fetched via ``window.tr(key)`` (helper
 *   exposed by main.js); fallback chain is current locale → EN → key.
 * - Accessibility: role=dialog, aria-modal, focus trap, Esc to
 *   close, return-focus to trigger button on close, aria-live on
 *   the step pane so screen readers announce step transitions.
 * - Reduced-motion: detected once at init and used to skip step
 *   slide animations + progress-bar transitions.
 */
(function () {
  'use strict';

  /* ── Helpers (translation + DOM utilities) ────────────── */

  // Resolve a translation key. main.js owns the canonical helper but
  // doesn't export it on window; mirror the lookup here so wizard.js
  // is self-sufficient (avoids cross-file ordering issues if scripts
  // load in unexpected sequence).
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
  function tr(key) {
    if (typeof key !== 'string') return key;
    var lang = document.documentElement.lang || 'en';
    var all = (window && window.ForgeLMTranslations) || {};
    var table = tableForLang(all, lang) || (all && all.en) || {};
    if (Object.hasOwn(table, key)) return table[key];
    var en = (all && all.en) || {};
    if (Object.hasOwn(en, key)) return en[key];
    return key;
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'class') node.className = v;
        else if (k === 'text') node.textContent = v;
        else if (k === 'html') node.innerHTML = v;
        else if (k === 'on') {
          Object.keys(v).forEach(function (evt) {
            node.addEventListener(evt, v[evt]);
          });
        } else if (k.startsWith('data-')) node.setAttribute(k, v);
        else if (k === 'i18nKey') node.setAttribute('data-i18n', v);
        else node.setAttribute(k, v);
      });
    }
    if (children) {
      (Array.isArray(children) ? children : [children]).forEach(function (c) {
        if (c == null) return;
        if (typeof c === 'string') node.appendChild(document.createTextNode(c));
        else node.appendChild(c);
      });
    }
    return node;
  }

  /* ── State + persistence ──────────────────────────────── */

  var STORAGE_KEY = 'forgelm.wizard.state';
  // Schema version 2 drops the data.format / prompt_field / response_field
  // and the compliance audit_log / annex_iv_export toggles — those fields
  // do not exist in forgelm/config.py (DataConfig + ComplianceMetadataConfig
  // both use ``extra="forbid"``). Any v1 snapshot is discarded on load.
  var STATE_VERSION = 2;

  function defaultState() {
    return {
      v: STATE_VERSION,
      step: 0,
      experience: 'beginner',  // 'beginner' | 'expert'
      detailsVisible: true,    // toggle for inline tutorial paragraphs
      useCase: null,           // 'customer-support' | 'code-copilot' | 'domain-expert' | 'grpo-math' | 'medical-tr' | 'custom'
      model: 'meta-llama/Llama-3.1-8B-Instruct',
      modelPreset: 'llama3-8b',
      datasetKind: 'huggingface',  // 'huggingface' | 'local-jsonl' | 'local-pdf'
      datasetName: '',
      // ``data.format`` / ``data.prompt_field`` / ``data.response_field`` are
      // intentionally absent — DataConfig auto-detects the row shape from
      // the JSONL fields (``messages`` array → chat; ``prompt`` + ``response``
      // → instruction). Forcing them in the YAML would trigger
      // ``extra="forbid"`` on DataConfig.
      qlora: true,
      loraR: 8,
      loraAlpha: 16,
      epochs: 3,
      learningRate: '1e-4',
      batchSize: 2,
      gradientAccumulation: 2,
      // EU AI Act risk + evaluation toggles. Audit log + Annex IV export
      // are NOT YAML toggles — the audit log is always emitted, and the
      // Annex IV bundle is produced whenever ``compliance.*`` metadata is
      // populated. The "human approval" gate maps to
      // ``evaluation.require_human_approval`` (Article 14).
      riskClassification: 'limited-risk',
      autoRevert: true,
      maxAcceptableLoss: 2.0,
      safetyEval: true,
      humanApproval: false,
      // Optional Annex IV provider metadata (ComplianceMetadataConfig).
      // Empty defaults are valid; the wizard exposes them for high-risk
      // tiers where the EU AI Act requires named provider info.
      providerName: '',
      systemName: '',
      intendedPurpose: ''
    };
  }

  function loadState() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || parsed.v !== STATE_VERSION) return null;
      // Merge with defaults so newly-added fields don't break old saves.
      var merged = defaultState();
      Object.keys(parsed).forEach(function (k) {
        if (Object.hasOwn(merged, k)) merged[k] = parsed[k];
      });
      return merged;
    } catch (e) {
      return null;
    }
  }

  function saveState(state) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      /* private mode / quota — non-fatal, in-memory state still works */
    }
  }

  function clearState() {
    try { window.localStorage.removeItem(STORAGE_KEY); } catch (e) { /* noop */ }
  }

  /* ── High-risk auto-coercion (EU AI Act Art. 9-17 obligations) */
  // When the operator picks ``high-risk`` or ``unacceptable`` on Step 6
  // we force-enable the human approval gate + Llama Guard safety eval —
  // those are not optional under Articles 9-17. The audit log is always
  // emitted regardless of YAML (no toggle) and the Annex IV bundle is
  // produced from the populated ``compliance.*`` metadata, so neither
  // appears here. Selecting back to a lower tier leaves the toggles
  // where the operator left them; we only override on the upward
  // transition.
  var STRICT_RISK_TIERS = ['high-risk', 'unacceptable'];
  function isStrictRisk(state) {
    return STRICT_RISK_TIERS.indexOf(state.riskClassification) !== -1;
  }
  function coerceForRisk(state) {
    if (isStrictRisk(state)) {
      state.humanApproval = true;
      state.safetyEval = true;
    }
  }

  /* ── Use-case templates (Step 2 → preselect Step 3-5) ─── */

  var USE_CASE_PRESETS = {
    'customer-support': {
      model: 'meta-llama/Llama-3.1-8B-Instruct',
      modelPreset: 'llama3-8b',
      datasetKind: 'huggingface',
      datasetName: 'argilla/Capybara-Preferences'
    },
    'code-copilot': {
      model: 'Qwen/Qwen2.5-Coder-7B-Instruct',
      modelPreset: 'custom',
      datasetKind: 'huggingface',
      datasetName: 'bigcode/the-stack-smol-xs'
    },
    'domain-expert': {
      model: 'meta-llama/Llama-3.1-8B-Instruct',
      modelPreset: 'llama3-8b',
      datasetKind: 'local-pdf',
      datasetName: './policies/'
    },
    'grpo-math': {
      model: 'Qwen/Qwen2.5-7B-Instruct',
      modelPreset: 'qwen-7b',
      datasetKind: 'huggingface',
      datasetName: 'openai/gsm8k'
    },
    'medical-tr': {
      model: 'meta-llama/Llama-3.1-8B-Instruct',
      modelPreset: 'llama3-8b',
      datasetKind: 'huggingface',
      datasetName: 'forgelm/medical-qa-tr'
    },
    'custom': {
      /* leave the existing values intact — user wants explicit control */
    }
  };

  // Map use-case → trainer (reflected in the YAML's ``training.trainer_type``).
  function trainerForUseCase(useCase) {
    switch (useCase) {
      case 'customer-support': return 'dpo';
      case 'code-copilot':     return 'orpo';
      case 'domain-expert':    return 'sft';
      case 'grpo-math':        return 'grpo';
      case 'medical-tr':       return 'sft';
      default:                  return 'sft';
    }
  }

  function applyUseCasePreset(state, useCase) {
    var preset = USE_CASE_PRESETS[useCase] || {};
    Object.keys(preset).forEach(function (k) { state[k] = preset[k]; });
    state.useCase = useCase;
  }

  /* ── YAML serialisation ───────────────────────────────── */

  // Build a syntax-highlighted YAML string. We intentionally avoid a
  // YAML library — the schema we emit is small enough that a manual
  // line-builder is auditable + dependency-free. The output is
  // structurally aligned with ``forgelm/config.py`` (Pydantic models
  // with ``extra="forbid"`` on every block), so it passes
  // ``forgelm --config quickstart-generated.yaml --dry-run`` cleanly.
  //
  // Audit notes (deliberately NOT emitted, despite operator intuition):
  //
  // * ``data.format`` / ``data.prompt_field`` / ``data.response_field``
  //   — DataConfig auto-detects the row shape from the JSONL fields
  //   themselves; emitting these triggers ``extra="forbid"``.
  // * ``compliance.audit_log`` / ``compliance.annex_iv_export`` —
  //   ComplianceMetadataConfig has no such toggles. The audit log is
  //   always written; the Annex IV bundle is produced whenever the
  //   ``compliance.*`` metadata block is present.
  // * Human-approval gate lives at ``evaluation.require_human_approval``
  //   (Article 14), not under ``compliance``.
  // * ``evaluation.safety.classifier`` (not ``classifier_path``).
  function buildYaml(state) {
    var lines = [];
    function comment(s) { lines.push('# ' + s); }
    function blank() { lines.push(''); }
    function k(indent, key, value) {
      var pad = '';
      for (var i = 0; i < indent; i++) pad += '  ';
      lines.push(pad + key + ': ' + value);
    }
    function header(indent, key) {
      var pad = '';
      for (var i = 0; i < indent; i++) pad += '  ';
      lines.push(pad + key + ':');
    }

    comment('Generated by the ForgeLM site wizard.');
    comment('Validate: forgelm --config quickstart-generated.yaml --dry-run');
    blank();

    header(0, 'model');
    k(1, 'name_or_path', JSON.stringify(state.model));
    k(1, 'load_in_4bit', state.qlora ? 'true' : 'false');
    if (state.qlora) {
      k(1, 'bnb_4bit_quant_type', '"nf4"');
      k(1, 'bnb_4bit_compute_dtype', '"auto"');
    }
    blank();

    header(0, 'lora');
    k(1, 'r', String(state.loraR));
    k(1, 'alpha', String(state.loraAlpha));
    k(1, 'dropout', '0.1');  // schema default
    k(1, 'bias', '"none"');
    k(1, 'target_modules', '["q_proj", "v_proj"]');
    blank();

    header(0, 'data');
    if (state.datasetKind === 'local-pdf') {
      comment(' PDFs need ingestion first — run before training:');
      comment('   forgelm ingest ' + (state.datasetName || './documents/') + ' --recursive --output data/corpus.jsonl');
      k(1, 'dataset_name_or_path', '"./data/corpus.jsonl"');
    } else {
      var defaultPath = state.datasetKind === 'huggingface'
        ? 'org/dataset-name'
        : './data/train.jsonl';
      k(1, 'dataset_name_or_path', JSON.stringify(state.datasetName || defaultPath));
    }
    comment(' DataConfig auto-detects row shape: { "messages": [...] } → chat;');
    comment(' { "prompt": ..., "response": ... } → instruction-following.');
    blank();

    header(0, 'training');
    k(1, 'trainer_type', JSON.stringify(trainerForUseCase(state.useCase)));
    k(1, 'output_dir', '"./checkpoints"');
    k(1, 'final_model_dir', '"final_model"');
    k(1, 'num_train_epochs', String(state.epochs));
    k(1, 'learning_rate', state.learningRate);
    k(1, 'per_device_train_batch_size', String(state.batchSize));
    k(1, 'gradient_accumulation_steps', String(state.gradientAccumulation));
    k(1, 'merge_adapters', 'false');
    blank();

    header(0, 'evaluation');
    k(1, 'auto_revert', state.autoRevert ? 'true' : 'false');
    if (state.autoRevert) {
      k(1, 'max_acceptable_loss', String(state.maxAcceptableLoss));
    }
    // Article 14: require_human_approval stages the model under
    // ``final_model.staging.<run_id>/`` and exits 4. The CLI then
    // expects ``forgelm approve <run_id>`` before promoting to
    // ``final_model/``.
    if (state.humanApproval) {
      k(1, 'require_human_approval', 'true');
    }
    if (state.safetyEval) {
      header(1, 'safety');
      k(2, 'enabled', 'true');
      k(2, 'classifier', '"meta-llama/Llama-Guard-3-8B"');
      k(2, 'min_classifier_confidence', '0.7');
      k(2, 'max_safety_regression', '0.05');
    }
    blank();

    // ComplianceMetadataConfig — Annex IV §1 provider + system info.
    // Always emit risk_classification; provider/system fields stay
    // empty unless the operator filled them in (high-risk tiers
    // surface the inputs in Step 6).
    header(0, 'compliance');
    k(1, 'risk_classification', JSON.stringify(state.riskClassification));
    if (state.providerName) k(1, 'provider_name', JSON.stringify(state.providerName));
    if (state.systemName) k(1, 'system_name', JSON.stringify(state.systemName));
    if (state.intendedPurpose) k(1, 'intended_purpose', JSON.stringify(state.intendedPurpose));
    blank();

    // Friendly closing comment so an operator reading the YAML cold
    // knows the audit log + Annex IV bundle land on disk regardless
    // of whether they show up as toggles here.
    comment(' Audit log (audit_log.jsonl) is always emitted — no YAML toggle.');
    comment(' Annex IV bundle is produced from the compliance.* metadata above.');

    return lines.join('\n');
  }

  // Lightweight YAML syntax tinting: paint comments + keys + strings
  // + booleans + numbers in different colours. The output is HTML so
  // it lives inside the ``<code>`` element directly — no heavy
  // tokeniser, just a series of targeted replacements with HTML
  // escaping done first to avoid XSS.
  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function tintYaml(yaml) {
    var lines = yaml.split('\n');
    return lines.map(function (line) {
      var trimmed = line.replace(/^\s*/, '');
      if (trimmed.startsWith('#')) {
        return '<span class="yaml-comment">' + escapeHtml(line) + '</span>';
      }
      // key: value match — split on the first colon
      var match = line.match(/^(\s*)([A-Za-z_][A-Za-z0-9_]*)(:)(\s*)(.*)$/);
      if (!match) return escapeHtml(line);
      var indent = match[1];
      var key = match[2];
      var rest = match[5];
      var tinted;
      if (rest === '') {
        tinted = '';
      } else if (rest === 'true' || rest === 'false') {
        tinted = '<span class="yaml-bool">' + escapeHtml(rest) + '</span>';
      } else if (rest === 'null' || rest === '~') {
        tinted = '<span class="yaml-null">' + escapeHtml(rest) + '</span>';
      } else if (/^-?\d+(\.\d+)?(e-?\d+)?$/i.test(rest)) {
        tinted = '<span class="yaml-number">' + escapeHtml(rest) + '</span>';
      } else if (rest.startsWith('"') || rest.startsWith("'")) {
        tinted = '<span class="yaml-string">' + escapeHtml(rest) + '</span>';
      } else if (rest.startsWith('[')) {
        // Inline list — colour quoted entries as strings.
        tinted = escapeHtml(rest).replace(
          /(&quot;[^&]*?&quot;)/g,
          '<span class="yaml-string">$1</span>'
        );
      } else {
        tinted = escapeHtml(rest);
      }
      return escapeHtml(indent) + '<span class="yaml-key">' + escapeHtml(key) + '</span><span>:</span>' +
        (rest === '' ? '' : ' ' + tinted);
    }).join('\n');
  }

  /* ── Step definitions ─────────────────────────────────── */

  var STEPS = [
    { id: 'welcome',    titleKey: 'wizard.step.welcome.title',     nameKey: 'wizard.step.welcome.name' },
    { id: 'use-case',   titleKey: 'wizard.step.usecase.title',     nameKey: 'wizard.step.usecase.name' },
    { id: 'model',      titleKey: 'wizard.step.model.title',       nameKey: 'wizard.step.model.name' },
    { id: 'dataset',    titleKey: 'wizard.step.dataset.title',     nameKey: 'wizard.step.dataset.name' },
    { id: 'training',   titleKey: 'wizard.step.training.title',    nameKey: 'wizard.step.training.name' },
    { id: 'compliance', titleKey: 'wizard.step.compliance.title',  nameKey: 'wizard.step.compliance.name' },
    { id: 'review',     titleKey: 'wizard.step.review.title',      nameKey: 'wizard.step.review.name' }
  ];

  /* ── Wizard controller ────────────────────────────────── */

  function initWizard() {
    var modal = document.querySelector('[data-wizard-modal]');
    if (!modal) return;
    var dialog = modal.querySelector('.wizard-dialog');
    var pane = modal.querySelector('[data-wizard-pane]');
    var yamlOutput = modal.querySelector('[data-wizard-yaml-output]');
    var yamlPane = modal.querySelector('[data-wizard-yaml-pane]');
    var yamlToggle = modal.querySelector('[data-wizard-yaml-toggle]');
    var yamlCopy = modal.querySelector('[data-wizard-yaml-copy]');
    var progress = modal.querySelector('[data-wizard-progress]');
    var counterCurrent = modal.querySelector('[data-wizard-counter-current]');
    var counterTotal = modal.querySelector('[data-wizard-counter-total]');
    var stepName = modal.querySelector('[data-wizard-step-name]');
    var prevBtn = modal.querySelector('[data-wizard-prev]');
    var nextBtn = modal.querySelector('[data-wizard-next]');
    var detailToggle = modal.querySelector('[data-wizard-detail-toggle]');
    var closeButtons = modal.querySelectorAll('[data-wizard-close]');

    var state = loadState() || defaultState();
    var triggerEl = null;       // element that opened the modal — focus returns here on close
    var wasResumed = !!loadState();

    if (counterTotal) counterTotal.textContent = String(STEPS.length);

    /* ── Modal lifecycle ──────────────────────────────── */

    function openModal(opts) {
      opts = opts || {};
      triggerEl = opts.trigger || document.activeElement;
      modal.removeAttribute('hidden');
      // Mark the rest of the page inert so keyboard / AT can't reach
      // the underlying content.
      var pageRoot = document.querySelector('nav.navbar') ? document.body : null;
      if (pageRoot) {
        Array.prototype.forEach.call(pageRoot.children, function (child) {
          if (child !== modal && !child.contains(modal)) {
            child.setAttribute('aria-hidden', 'true');
          }
        });
      }
      document.body.style.overflow = 'hidden';
      render();
      // Push ?wizard=open onto the URL without reloading so a refresh /
      // share-link round-trips back into the wizard at the same step.
      try {
        var params = new URLSearchParams(window.location.search);
        params.set('wizard', 'open');
        window.history.replaceState({ wizard: 'open' }, '', window.location.pathname + '?' + params.toString());
      } catch (e) { /* noop */ }
      setTimeout(function () {
        if (dialog) dialog.focus();
        var firstFocusable = pane && pane.querySelector('button, input, select, textarea, [tabindex="0"]');
        if (firstFocusable) firstFocusable.focus();
      }, 50);
    }

    function closeModal() {
      modal.setAttribute('hidden', '');
      document.body.style.overflow = '';
      Array.prototype.forEach.call(document.body.children, function (child) {
        if (child !== modal) child.removeAttribute('aria-hidden');
      });
      try {
        var params = new URLSearchParams(window.location.search);
        params.delete('wizard');
        var qs = params.toString();
        window.history.replaceState({}, '', window.location.pathname + (qs ? '?' + qs : ''));
      } catch (e) { /* noop */ }
      if (triggerEl && typeof triggerEl.focus === 'function') {
        try { triggerEl.focus(); } catch (e) { /* noop */ }
      }
    }

    /* ── Focus trap (Tab / Shift+Tab cycle inside dialog) */

    dialog.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        closeModal();
        e.preventDefault();
        return;
      }
      if (e.key !== 'Tab') return;
      var focusables = dialog.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (focusables.length === 0) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        last.focus();
        e.preventDefault();
      } else if (!e.shiftKey && document.activeElement === last) {
        first.focus();
        e.preventDefault();
      }
    });

    /* ── State + render ───────────────────────────────── */

    function persist() { saveState(state); }

    function render() {
      var idx = state.step;
      if (idx < 0) idx = 0;
      if (idx >= STEPS.length) idx = STEPS.length - 1;
      state.step = idx;

      coerceForRisk(state);

      var stepDef = STEPS[idx];
      pane.innerHTML = '';
      var renderer = STEP_RENDERERS[stepDef.id];
      if (renderer) renderer(pane, state, render, persist);

      // Progress + counter
      var pct = Math.round(((idx + 1) / STEPS.length) * 100);
      if (progress) progress.style.width = pct + '%';
      if (counterCurrent) counterCurrent.textContent = String(idx + 1);
      if (stepName) stepName.textContent = tr(stepDef.nameKey);

      // Prev / Next
      prevBtn.disabled = idx === 0;
      var isLast = idx === STEPS.length - 1;
      var nextLabel = nextBtn.querySelector('span');
      if (nextLabel) {
        nextLabel.textContent = isLast ? tr('wizard.nav.done') : tr('wizard.nav.next');
      }

      // Detail toggle visibility — only steps that ship a tutorial
      // paragraph need the toggle.
      if (detailToggle) {
        var showsTutorial = stepDef.id !== 'welcome' && stepDef.id !== 'review';
        if (showsTutorial) {
          detailToggle.removeAttribute('hidden');
          detailToggle.classList.toggle('is-active', state.detailsVisible);
          var detailLabel = detailToggle.querySelector('span');
          if (detailLabel) {
            detailLabel.textContent = state.detailsVisible
              ? tr('wizard.detail.hide')
              : tr('wizard.detail.show');
          }
        } else {
          detailToggle.setAttribute('hidden', '');
        }
      }

      // YAML preview
      var yamlText = buildYaml(state);
      if (yamlOutput) yamlOutput.innerHTML = tintYaml(yamlText);

      persist();
    }

    function goNext() {
      if (state.step < STEPS.length - 1) {
        state.step += 1;
        render();
        pane.scrollTop = 0;
      } else {
        // Final step: "Done" closes the modal but keeps state.
        closeModal();
      }
    }
    function goPrev() {
      if (state.step > 0) {
        state.step -= 1;
        render();
        pane.scrollTop = 0;
      }
    }

    /* ── Triggers + buttons ───────────────────────────── */

    document.querySelectorAll('[data-wizard-open]').forEach(function (btn) {
      btn.addEventListener('click', function () { openModal({ trigger: btn }); });
    });
    closeButtons.forEach(function (btn) {
      btn.addEventListener('click', closeModal);
    });
    prevBtn.addEventListener('click', goPrev);
    nextBtn.addEventListener('click', goNext);

    if (detailToggle) {
      detailToggle.addEventListener('click', function () {
        state.detailsVisible = !state.detailsVisible;
        render();
      });
    }

    /* ── YAML pane: copy + mobile accordion toggle ────── */

    if (yamlCopy && yamlOutput) {
      yamlCopy.addEventListener('click', function () {
        var text = yamlOutput.innerText || yamlOutput.textContent || '';
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(function () {
            yamlCopy.classList.add('is-copied');
            var label = yamlCopy.querySelector('span');
            if (label) {
              var prev = label.textContent;
              label.textContent = tr('common.copy.done');
              setTimeout(function () {
                yamlCopy.classList.remove('is-copied');
                if (label) label.textContent = prev;
              }, 1600);
            }
          });
        }
      });
    }
    if (yamlToggle && yamlPane) {
      yamlToggle.addEventListener('click', function () {
        var expanded = yamlPane.classList.toggle('is-expanded');
        yamlToggle.setAttribute('aria-expanded', String(expanded));
      });
    }

    /* ── URL parameter: ?wizard=open auto-opens ───────── */

    try {
      var params = new URLSearchParams(window.location.search);
      if (params.get('wizard') === 'open') {
        // Defer so the rest of the page (lang dropdown, theme,
        // translations) finishes initialising before the dialog
        // pulls focus.
        setTimeout(function () { openModal({ trigger: null }); }, 200);
      }
    } catch (e) { /* noop */ }

    // Close on browser back when the modal is open.
    window.addEventListener('popstate', function () {
      if (!modal.hasAttribute('hidden')) closeModal();
    });

    // Surface a resume banner in the welcome step the first time the
    // operator reopens with a saved session.
    if (wasResumed) {
      modal.dataset.resumed = 'true';
    }
  }

  /* ── Step renderers ───────────────────────────────────── */

  // Each renderer takes the pane element + the state object + a
  // re-render callback + a persist callback. They build the step
  // content via DOM construction rather than templating so we don't
  // need a templating library and the resulting nodes own typed
  // event handlers (no innerHTML interpolation of state values).
  var STEP_RENDERERS = {};

  function stepHeader(state, titleKey, descKey, tutorialKey) {
    var nodes = [];
    nodes.push(el('h2', { class: 'wizard-step-title', text: tr(titleKey) }));
    if (descKey) nodes.push(el('p', { class: 'wizard-step-desc', text: tr(descKey) }));
    if (tutorialKey && state.detailsVisible) {
      nodes.push(el('div', { class: 'wizard-step-tutorial', text: tr(tutorialKey) }));
    }
    return nodes;
  }

  /* Step 1: Welcome / experience level */
  STEP_RENDERERS['welcome'] = function (pane, state, rerender, persist) {
    pane.appendChild(el('h2', { class: 'wizard-step-title', text: tr('wizard.step.welcome.title') }));
    pane.appendChild(el('p', { class: 'wizard-step-desc', text: tr('wizard.step.welcome.desc') }));
    pane.appendChild(el('div', { class: 'wizard-step-tutorial', text: tr('wizard.step.welcome.tutorial') }));

    var cards = el('div', { class: 'wizard-cards' });
    [
      { id: 'beginner', titleKey: 'wizard.exp.beginner.title', descKey: 'wizard.exp.beginner.desc' },
      { id: 'expert',   titleKey: 'wizard.exp.expert.title',   descKey: 'wizard.exp.expert.desc' }
    ].forEach(function (opt) {
      var card = el('button', {
        type: 'button',
        class: 'wizard-card' + (state.experience === opt.id ? ' is-selected' : ''),
        on: {
          click: function () {
            state.experience = opt.id;
            state.detailsVisible = (opt.id === 'beginner');
            persist();
            rerender();
          }
        }
      }, [
        el('span', { class: 'wizard-card-title', text: tr(opt.titleKey) }),
        el('span', { class: 'wizard-card-desc',  text: tr(opt.descKey) })
      ]);
      cards.appendChild(card);
    });
    pane.appendChild(cards);
  };

  /* Step 2: Use case */
  STEP_RENDERERS['use-case'] = function (pane, state, rerender, persist) {
    stepHeader(state, 'wizard.step.usecase.title', 'wizard.step.usecase.desc', 'wizard.step.usecase.tutorial')
      .forEach(function (n) { pane.appendChild(n); });

    var grid = el('div', { class: 'wizard-cards' });
    [
      { id: 'customer-support', titleKey: 'wizard.usecase.support.title', badgeKey: 'wizard.usecase.support.badge', descKey: 'wizard.usecase.support.desc' },
      { id: 'code-copilot',     titleKey: 'wizard.usecase.code.title',    badgeKey: 'wizard.usecase.code.badge',    descKey: 'wizard.usecase.code.desc' },
      { id: 'domain-expert',    titleKey: 'wizard.usecase.domain.title',  badgeKey: 'wizard.usecase.domain.badge',  descKey: 'wizard.usecase.domain.desc' },
      { id: 'grpo-math',        titleKey: 'wizard.usecase.math.title',    badgeKey: 'wizard.usecase.math.badge',    descKey: 'wizard.usecase.math.desc' },
      { id: 'medical-tr',       titleKey: 'wizard.usecase.medical.title', badgeKey: 'wizard.usecase.medical.badge', descKey: 'wizard.usecase.medical.desc' },
      { id: 'custom',           titleKey: 'wizard.usecase.custom.title',  badgeKey: '',                              descKey: 'wizard.usecase.custom.desc' }
    ].forEach(function (opt) {
      var titleNode = el('span', { class: 'wizard-card-title' }, [tr(opt.titleKey)]);
      if (opt.badgeKey) {
        titleNode.appendChild(el('span', { class: 'badge', text: tr(opt.badgeKey) }));
      }
      var card = el('button', {
        type: 'button',
        class: 'wizard-card' + (state.useCase === opt.id ? ' is-selected' : ''),
        on: {
          click: function () {
            applyUseCasePreset(state, opt.id);
            persist();
            rerender();
          }
        }
      }, [
        titleNode,
        el('span', { class: 'wizard-card-desc', text: tr(opt.descKey) })
      ]);
      grid.appendChild(card);
    });
    pane.appendChild(grid);
  };

  /* Step 3: Base model */
  STEP_RENDERERS['model'] = function (pane, state, rerender, persist) {
    stepHeader(state, 'wizard.step.model.title', 'wizard.step.model.desc', 'wizard.step.model.tutorial')
      .forEach(function (n) { pane.appendChild(n); });

    var presets = [
      { id: 'llama3-8b',   path: 'meta-llama/Llama-3.1-8B-Instruct',     titleKey: 'wizard.model.llama3.title',   badgeKey: 'wizard.model.llama3.badge',   descKey: 'wizard.model.llama3.desc' },
      { id: 'qwen-7b',     path: 'Qwen/Qwen2.5-7B-Instruct',              titleKey: 'wizard.model.qwen.title',     badgeKey: '',                            descKey: 'wizard.model.qwen.desc' },
      { id: 'mistral-7b',  path: 'mistralai/Mistral-7B-Instruct-v0.3',   titleKey: 'wizard.model.mistral.title',  badgeKey: '',                            descKey: 'wizard.model.mistral.desc' },
      { id: 'phi3-mini',   path: 'microsoft/Phi-3-mini-4k-instruct',      titleKey: 'wizard.model.phi.title',      badgeKey: 'wizard.model.phi.badge',      descKey: 'wizard.model.phi.desc' },
      { id: 'custom',      path: '',                                      titleKey: 'wizard.model.custom.title',   badgeKey: '',                            descKey: 'wizard.model.custom.desc' }
    ];

    var grid = el('div', { class: 'wizard-cards' });
    presets.forEach(function (preset) {
      var titleNode = el('span', { class: 'wizard-card-title' }, [tr(preset.titleKey)]);
      if (preset.badgeKey) titleNode.appendChild(el('span', { class: 'badge', text: tr(preset.badgeKey) }));
      var card = el('button', {
        type: 'button',
        class: 'wizard-card' + (state.modelPreset === preset.id ? ' is-selected' : ''),
        on: {
          click: function () {
            state.modelPreset = preset.id;
            if (preset.id !== 'custom') state.model = preset.path;
            persist();
            rerender();
          }
        }
      }, [
        titleNode,
        el('span', { class: 'wizard-card-desc', text: tr(preset.descKey) })
      ]);
      grid.appendChild(card);
    });
    pane.appendChild(grid);

    if (state.modelPreset === 'custom') {
      var input = el('input', {
        type: 'text',
        class: 'wizard-input',
        placeholder: 'huggingface-org/your-model',
        value: state.model || ''
      });
      input.addEventListener('input', function () {
        state.model = input.value.trim();
        persist();
        // Re-run YAML preview without re-rendering the pane (so the
        // input keeps focus + caret position).
        var yamlOutput = document.querySelector('[data-wizard-yaml-output]');
        if (yamlOutput) yamlOutput.innerHTML = tintYaml(buildYaml(state));
      });
      var row = el('div', { class: 'wizard-row' }, [
        el('label', { class: 'wizard-row-label', text: tr('wizard.model.custom.label') }),
        input,
        el('span', { class: 'wizard-row-hint', text: tr('wizard.model.custom.hint') })
      ]);
      pane.appendChild(row);
    }
  };

  /* Step 4: Dataset */
  STEP_RENDERERS['dataset'] = function (pane, state, rerender, persist) {
    stepHeader(state, 'wizard.step.dataset.title', 'wizard.step.dataset.desc', 'wizard.step.dataset.tutorial')
      .forEach(function (n) { pane.appendChild(n); });

    var grid = el('div', { class: 'wizard-cards' });
    [
      { id: 'huggingface', titleKey: 'wizard.dataset.hf.title',    descKey: 'wizard.dataset.hf.desc' },
      { id: 'local-jsonl', titleKey: 'wizard.dataset.jsonl.title', descKey: 'wizard.dataset.jsonl.desc' },
      { id: 'local-pdf',   titleKey: 'wizard.dataset.pdf.title',   descKey: 'wizard.dataset.pdf.desc' }
    ].forEach(function (opt) {
      var card = el('button', {
        type: 'button',
        class: 'wizard-card' + (state.datasetKind === opt.id ? ' is-selected' : ''),
        on: {
          click: function () {
            state.datasetKind = opt.id;
            persist();
            rerender();
          }
        }
      }, [
        el('span', { class: 'wizard-card-title', text: tr(opt.titleKey) }),
        el('span', { class: 'wizard-card-desc',  text: tr(opt.descKey) })
      ]);
      grid.appendChild(card);
    });
    pane.appendChild(grid);

    var nameInput = el('input', {
      type: 'text',
      class: 'wizard-input',
      placeholder: state.datasetKind === 'huggingface'
        ? 'org/dataset-name'
        : (state.datasetKind === 'local-pdf' ? './documents/' : './data/train.jsonl'),
      value: state.datasetName
    });
    nameInput.addEventListener('input', function () {
      state.datasetName = nameInput.value.trim();
      persist();
      var yamlOutput = document.querySelector('[data-wizard-yaml-output]');
      if (yamlOutput) yamlOutput.innerHTML = tintYaml(buildYaml(state));
    });
    pane.appendChild(el('div', { class: 'wizard-row' }, [
      el('label', { class: 'wizard-row-label', text: tr('wizard.dataset.name.label') }),
      nameInput,
      el('span', { class: 'wizard-row-hint', text: tr('wizard.dataset.name.hint') })
    ]));

    // Format auto-detection note (replaces the prior format / prompt_field
    // / response_field manual UI). DataConfig in forgelm/config.py infers
    // the row shape from the JSONL fields, so no schema field is exposed
    // for it — the wizard previously emitted these as YAML keys, which
    // ``extra="forbid"`` rejected at dry-run.
    pane.appendChild(el('div', {
      class: 'wizard-step-tutorial',
      html: '<strong>' + tr('wizard.dataset.autodetect.title') + '</strong> ' + tr('wizard.dataset.autodetect.body')
    }));
  };

  /* Step 5: Training params */
  STEP_RENDERERS['training'] = function (pane, state, rerender, persist) {
    stepHeader(state, 'wizard.step.training.title', 'wizard.step.training.desc', 'wizard.step.training.tutorial')
      .forEach(function (n) { pane.appendChild(n); });

    function liveYaml() {
      var yamlOutput = document.querySelector('[data-wizard-yaml-output]');
      if (yamlOutput) yamlOutput.innerHTML = tintYaml(buildYaml(state));
    }

    // Append a per-field detail paragraph beneath a row when the
    // operator is in beginner mode (state.detailsVisible). The paragraph
    // expands what the hint glosses — 2-3 sentences explaining what the
    // value MEANS, not just what range to pick.
    function appendDetail(rowEl, detailKey) {
      if (state.detailsVisible && detailKey) {
        rowEl.appendChild(el('p', { class: 'wizard-row-detail', text: tr(detailKey) }));
      }
    }

    // QLoRA toggle
    var qloraInput = el('input', { type: 'checkbox' });
    qloraInput.checked = state.qlora;
    qloraInput.addEventListener('change', function () {
      state.qlora = qloraInput.checked;
      persist();
      liveYaml();
    });
    var qloraRow = el('div', { class: 'wizard-row' }, [
      el('label', { class: 'wizard-toggle' }, [
        qloraInput,
        el('span', { class: 'wizard-toggle-label', text: tr('wizard.training.qlora.label') })
      ]),
      el('span', { class: 'wizard-row-hint', text: tr('wizard.training.qlora.hint') })
    ]);
    appendDetail(qloraRow, 'wizard.training.qlora.detail');
    pane.appendChild(qloraRow);

    // LoRA r / alpha sliders
    function makeSlider(field, min, max, hintKey, labelKey, detailKey) {
      var slider = el('input', {
        type: 'range',
        class: 'wizard-slider',
        min: String(min),
        max: String(max),
        value: String(state[field])
      });
      var valueOut = el('span', { class: 'wizard-slider-value', text: String(state[field]) });
      slider.addEventListener('input', function () {
        var v = parseInt(slider.value, 10);
        state[field] = v;
        valueOut.textContent = String(v);
        persist();
        liveYaml();
      });
      var row = el('div', { class: 'wizard-row' }, [
        el('label', { class: 'wizard-row-label', text: tr(labelKey) }),
        el('div', { class: 'wizard-slider-row' }, [slider, valueOut]),
        el('span', { class: 'wizard-row-hint', text: tr(hintKey) })
      ]);
      appendDetail(row, detailKey);
      return row;
    }
    pane.appendChild(makeSlider('loraR',     4,  64, 'wizard.training.lora_r.hint',     'wizard.training.lora_r.label',     'wizard.training.lora_r.detail'));
    pane.appendChild(makeSlider('loraAlpha', 8, 128, 'wizard.training.lora_alpha.hint', 'wizard.training.lora_alpha.label', 'wizard.training.lora_alpha.detail'));

    // Epochs
    var epochsInput = el('input', {
      type: 'number',
      class: 'wizard-input',
      min: '1',
      max: '5',
      value: String(state.epochs)
    });
    epochsInput.addEventListener('input', function () {
      var v = parseInt(epochsInput.value, 10);
      if (!isNaN(v) && v >= 1 && v <= 5) {
        state.epochs = v;
        persist();
        liveYaml();
      }
    });
    var epochsRow = el('div', { class: 'wizard-row' }, [
      el('label', { class: 'wizard-row-label', text: tr('wizard.training.epochs.label') }),
      epochsInput,
      el('span', { class: 'wizard-row-hint', text: tr('wizard.training.epochs.hint') })
    ]);
    appendDetail(epochsRow, 'wizard.training.epochs.detail');
    pane.appendChild(epochsRow);

    // Learning rate
    var lrSelect = el('select', { class: 'wizard-select' });
    ['1e-4', '5e-5', '3e-5', '1e-5'].forEach(function (lr) {
      var option = el('option', { value: lr, text: lr });
      if (state.learningRate === lr) option.selected = true;
      lrSelect.appendChild(option);
    });
    lrSelect.addEventListener('change', function () {
      state.learningRate = lrSelect.value;
      persist();
      liveYaml();
    });
    var lrRow = el('div', { class: 'wizard-row' }, [
      el('label', { class: 'wizard-row-label', text: tr('wizard.training.lr.label') }),
      lrSelect,
      el('span', { class: 'wizard-row-hint', text: tr('wizard.training.lr.hint') })
    ]);
    appendDetail(lrRow, 'wizard.training.lr.detail');
    pane.appendChild(lrRow);

    // Batch size
    var batchSelect = el('select', { class: 'wizard-select' });
    [1, 2, 4, 8].forEach(function (bs) {
      var option = el('option', { value: String(bs), text: String(bs) });
      if (state.batchSize === bs) option.selected = true;
      batchSelect.appendChild(option);
    });
    batchSelect.addEventListener('change', function () {
      state.batchSize = parseInt(batchSelect.value, 10);
      persist();
      liveYaml();
    });
    var batchRow = el('div', { class: 'wizard-row' }, [
      el('label', { class: 'wizard-row-label', text: tr('wizard.training.batch.label') }),
      batchSelect,
      el('span', { class: 'wizard-row-hint', text: tr('wizard.training.batch.hint') })
    ]);
    appendDetail(batchRow, 'wizard.training.batch.detail');
    pane.appendChild(batchRow);
  };

  /* Step 6: Evaluation + EU AI Act compliance */
  STEP_RENDERERS['compliance'] = function (pane, state, rerender, persist) {
    stepHeader(state, 'wizard.step.compliance.title', 'wizard.step.compliance.desc', 'wizard.step.compliance.tutorial')
      .forEach(function (n) { pane.appendChild(n); });

    function liveYaml() {
      var yamlOutput = document.querySelector('[data-wizard-yaml-output]');
      if (yamlOutput) yamlOutput.innerHTML = tintYaml(buildYaml(state));
    }

    // Risk classification
    var riskSelect = el('select', { class: 'wizard-select' });
    [
      { id: 'unknown',       labelKey: 'wizard.risk.unknown' },
      { id: 'minimal-risk',  labelKey: 'wizard.risk.minimal' },
      { id: 'limited-risk',  labelKey: 'wizard.risk.limited' },
      { id: 'high-risk',     labelKey: 'wizard.risk.high' },
      { id: 'unacceptable',  labelKey: 'wizard.risk.unacceptable' }
    ].forEach(function (opt) {
      var option = el('option', { value: opt.id, text: tr(opt.labelKey) });
      if (state.riskClassification === opt.id) option.selected = true;
      riskSelect.appendChild(option);
    });
    riskSelect.addEventListener('change', function () {
      state.riskClassification = riskSelect.value;
      coerceForRisk(state);
      persist();
      rerender();
    });
    pane.appendChild(el('div', { class: 'wizard-row' }, [
      el('label', { class: 'wizard-row-label', text: tr('wizard.risk.label') }),
      riskSelect,
      el('span', { class: 'wizard-row-hint', text: tr('wizard.risk.hint') })
    ]));

    // High-risk callout
    if (state.riskClassification === 'high-risk') {
      pane.appendChild(el('div', {
        class: 'wizard-callout',
        html: '<strong>' + tr('wizard.risk.high.callout.title') + '</strong> ' + tr('wizard.risk.high.callout.body')
      }));
    } else if (state.riskClassification === 'unacceptable') {
      pane.appendChild(el('div', {
        class: 'wizard-callout',
        html: '<strong>' + tr('wizard.risk.unacceptable.callout.title') + '</strong> ' + tr('wizard.risk.unacceptable.callout.body')
      }));
    }

    // Toggles. ``locked`` disables the input and adds a "required for risk
    // tier" badge — used for fields the EU AI Act forces under high-risk
    // / unacceptable tiers (Articles 9-17).
    function makeToggle(field, labelKey, hintKey, locked, detailKey) {
      var input = el('input', { type: 'checkbox' });
      input.checked = state[field];
      if (locked) input.disabled = true;
      input.addEventListener('change', function () {
        state[field] = input.checked;
        persist();
        liveYaml();
      });
      var labelEl = el('span', { class: 'wizard-toggle-label', text: tr(labelKey) });
      if (locked) {
        labelEl.appendChild(el('span', {
          class: 'badge',
          text: tr('wizard.locked.badge'),
          style: 'margin-left: 0.4rem;'
        }));
      }
      var children = [
        el('label', { class: 'wizard-toggle' }, [input, labelEl]),
        el('span', { class: 'wizard-row-hint', text: tr(hintKey) })
      ];
      if (detailKey && state.detailsVisible) {
        children.push(el('p', { class: 'wizard-row-detail', text: tr(detailKey) }));
      }
      return el('div', { class: 'wizard-row' }, children);
    }
    var highRisk = isStrictRisk(state);
    pane.appendChild(makeToggle('autoRevert', 'wizard.eval.auto_revert.label', 'wizard.eval.auto_revert.hint', false, 'wizard.eval.auto_revert.detail'));

    if (state.autoRevert) {
      var lossInput = el('input', {
        type: 'number',
        class: 'wizard-input',
        min: '0.1',
        step: '0.1',
        value: String(state.maxAcceptableLoss)
      });
      lossInput.addEventListener('input', function () {
        var v = parseFloat(lossInput.value);
        if (!isNaN(v) && v > 0) {
          state.maxAcceptableLoss = v;
          persist();
          liveYaml();
        }
      });
      var lossRowChildren = [
        el('label', { class: 'wizard-row-label', text: tr('wizard.eval.max_loss.label') }),
        lossInput,
        el('span', { class: 'wizard-row-hint', text: tr('wizard.eval.max_loss.hint') })
      ];
      if (state.detailsVisible) {
        lossRowChildren.push(el('p', { class: 'wizard-row-detail', text: tr('wizard.eval.max_loss.detail') }));
      }
      pane.appendChild(el('div', { class: 'wizard-row' }, lossRowChildren));
    }

    pane.appendChild(makeToggle('safetyEval', 'wizard.eval.safety.label', 'wizard.eval.safety.hint', highRisk, 'wizard.eval.safety.detail'));
    pane.appendChild(makeToggle('humanApproval', 'wizard.compliance.approval.label', 'wizard.compliance.approval.hint', highRisk, 'wizard.compliance.approval.detail'));

    // Informational block: the audit log + Annex IV bundle are not YAML
    // toggles — they are produced as side-effects of the run. Surface
    // this fact instead of pretending the operator has a control they
    // don't actually have.
    pane.appendChild(el('div', {
      class: 'wizard-step-tutorial',
      html: '<strong>' + tr('wizard.compliance.always.title') + '</strong> ' + tr('wizard.compliance.always.body')
    }));

    // Annex IV §1 provider metadata. Surface ALWAYS (any tier benefits
    // from named provider info) but tag the inputs as "required for
    // high-risk" so the operator knows the obligation rises with the
    // tier. Empty values are valid; ComplianceMetadataConfig has
    // string defaults of "".
    function makeMetaInput(field, labelKey, hintKey, placeholderKey) {
      var input = el('input', {
        type: 'text',
        class: 'wizard-input',
        value: state[field] || '',
        placeholder: tr(placeholderKey)
      });
      input.addEventListener('input', function () {
        state[field] = input.value;
        persist();
        liveYaml();
      });
      return el('div', { class: 'wizard-row' }, [
        el('label', { class: 'wizard-row-label' }, [
          tr(labelKey),
          highRisk ? el('span', { class: 'badge', text: tr('wizard.locked.badge'), style: 'margin-left: 0.4rem;' }) : null
        ]),
        input,
        el('span', { class: 'wizard-row-hint', text: tr(hintKey) })
      ]);
    }
    if (highRisk) {
      pane.appendChild(makeMetaInput('providerName', 'wizard.compliance.provider_name.label', 'wizard.compliance.provider_name.hint', 'wizard.compliance.provider_name.placeholder'));
      pane.appendChild(makeMetaInput('systemName', 'wizard.compliance.system_name.label', 'wizard.compliance.system_name.hint', 'wizard.compliance.system_name.placeholder'));
      pane.appendChild(makeMetaInput('intendedPurpose', 'wizard.compliance.intended_purpose.label', 'wizard.compliance.intended_purpose.hint', 'wizard.compliance.intended_purpose.placeholder'));
    }
  };

  /* Step 7: Review + download */
  STEP_RENDERERS['review'] = function (pane, state, rerender, persist) {
    pane.appendChild(el('h2', { class: 'wizard-step-title', text: tr('wizard.step.review.title') }));
    pane.appendChild(el('p', { class: 'wizard-step-desc', text: tr('wizard.step.review.desc') }));
    pane.appendChild(el('div', { class: 'wizard-step-tutorial', text: tr('wizard.step.review.tutorial') }));

    var yamlText = buildYaml(state);

    // Action buttons row
    var actions = el('div', { class: 'wizard-actions' });

    var copyBtn = el('button', {
      type: 'button',
      class: 'btn btn-primary'
    }, [
      el('svg', { width: '16', height: '16', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', html: '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>' }),
      el('span', { text: tr('wizard.review.copy') })
    ]);
    copyBtn.addEventListener('click', function () {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(yamlText).then(function () {
          copyBtn.classList.add('is-copied');
          var label = copyBtn.querySelector('span');
          if (label) {
            var prev = label.textContent;
            label.textContent = tr('common.copy.done');
            setTimeout(function () {
              copyBtn.classList.remove('is-copied');
              label.textContent = prev;
            }, 1600);
          }
        });
      }
    });
    actions.appendChild(copyBtn);

    var downloadBtn = el('button', {
      type: 'button',
      class: 'btn btn-secondary'
    }, [
      el('svg', { width: '16', height: '16', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', html: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line>' }),
      el('span', { text: tr('wizard.review.download') })
    ]);
    downloadBtn.addEventListener('click', function () {
      var blob = new Blob([yamlText], { type: 'text/yaml' });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'quickstart-generated.yaml';
      a.click();
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    });
    actions.appendChild(downloadBtn);

    var resetBtn = el('button', {
      type: 'button',
      class: 'btn btn-ghost'
    }, [
      el('svg', { width: '16', height: '16', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', html: '<polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>' }),
      el('span', { text: tr('wizard.review.reset') })
    ]);
    resetBtn.addEventListener('click', function () {
      if (window.confirm(tr('wizard.review.reset.confirm'))) {
        clearState();
        var fresh = defaultState();
        Object.keys(fresh).forEach(function (k) { state[k] = fresh[k]; });
        rerender();
      }
    });
    actions.appendChild(resetBtn);

    pane.appendChild(actions);

    // Run snippet
    var snippet = el('pre', { class: 'wizard-run-snippet' }, [
      el('span', { class: 'prompt', text: '$ ' }),
      el('span', { text: 'forgelm ' }),
      el('span', { class: 'flag', text: '--config ' }),
      el('span', { class: 'arg', text: 'quickstart-generated.yaml ' }),
      el('span', { class: 'flag', text: '--dry-run' })
    ]);
    pane.appendChild(el('p', {
      class: 'wizard-step-desc',
      style: 'margin-top: 1.4rem; font-size: 0.86rem;',
      text: tr('wizard.review.run_label')
    }));
    pane.appendChild(snippet);
  };

  /* ── Boot ─────────────────────────────────────────────── */

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initWizard);
  } else {
    initWizard();
  }
})();
