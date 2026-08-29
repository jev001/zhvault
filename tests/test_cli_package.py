import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def test_main_no_args_shows_help_without_traceback():
    """Bare `zhvault` must not raise; Typer NoArgsIsHelpError → exit code."""
    from cli import main

    assert main([]) == 2


def test_main_help_flag_exits_zero():
    from cli import main

    assert main(["--help"]) == 0


@pytest.mark.parametrize(
    "argv",
    [
        ["status", "--help"],
        ["backup", "--help"],
        ["graph", "rebuild", "--help"],
        ["search", "index", "--help"],
        ["account", "plan", "--help"],
    ],
)
def test_cli_subcommands_help(runner, argv):
    from cli.app import app

    result = runner.invoke(app, argv, prog_name="zhvault")
    assert result.exit_code == 0
    assert "Usage:" in result.stdout or "Options" in result.stdout
