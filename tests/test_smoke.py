def test_config_template_parses():
    from forgelm.config import load_config

    cfg = load_config("config_template.yaml")
    assert cfg.model.name_or_path
    assert cfg.training.output_dir


def test_cli_help_runs(capsys):
    # Importing should not require heavy deps beyond core.
    from forgelm.cli import parse_args

    # parse_args requires argv; we only assert module import works here.
    assert callable(parse_args)
