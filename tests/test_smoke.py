def test_config_template_parses():
    from forgelm.config import load_config

    cfg = load_config("config_template.yaml")
    assert cfg.model.name_or_path
    assert cfg.training.output_dir


def test_cli_help_runs(monkeypatch, capsys):
    """Invoking ``forgelm --help`` exits 0 and prints the documented usage."""
    import pytest

    from forgelm.cli import main

    monkeypatch.setattr("sys.argv", ["forgelm", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    # argparse ``--help`` exits 0 by design.
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out
    assert "--config" in captured.out
