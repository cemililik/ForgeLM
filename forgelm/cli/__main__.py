"""Entry point for ``python -m forgelm.cli``.

Load-bearing for the quickstart subprocess flow: ``_run_quickstart_train_subprocess``
and ``_run_quickstart_chat_subprocess`` spawn ``[sys.executable, "-m", "forgelm.cli", ...]``,
so this file MUST exist for the package form of the CLI to be invokable.
"""

from forgelm.cli import main

if __name__ == "__main__":
    main()
