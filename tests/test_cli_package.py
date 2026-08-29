import pytest


@pytest.mark.parametrize(
    "argv,expected_func",
    [
        (["status"], "cmd_status"),
        (["backup", "--source", "collection"], "cmd_backup"),
        (["graph", "rebuild"], "cmd_graph_rebuild"),
        (["search", "index"], "cmd_search_index"),
        (["account", "plan", "--mode", "prune", "--source", "following"], "cmd_account_plan"),
    ],
)
def test_parser_subcommands_have_callable_func(argv, expected_func):
    from cli import build_parser

    args = build_parser().parse_args(argv)
    assert callable(args.func)
    assert args.func.__name__ == expected_func
