/**
 * Schema-derived wizard defaults — DO NOT EDIT BY HAND.
 * Regenerate via: python tools/generate_wizard_defaults.py
 * CI guard: tools/check_wizard_defaults_sync.py rejects manual drift.
 *
 * Consumed by site/js/wizard.js's defaultState() so the web
 * wizard's accept-all-defaults YAML matches ForgeConfig() byte-
 * for-byte.  Loaded BEFORE wizard.js in the HTML pages that
 * mount the wizard modal.
 */
window.WIZARD_DEFAULTS = {
  "model": {
    "max_length": 2048
  },
  "lora": {
    "alpha": 16,
    "dropout": 0.1,
    "r": 8
  },
  "training": {
    "gradient_accumulation_steps": 2,
    "learning_rate": 2e-05,
    "num_train_epochs": 3,
    "per_device_train_batch_size": 4
  }
};
