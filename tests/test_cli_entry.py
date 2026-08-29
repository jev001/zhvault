def test_cli_main_importable():
    from cli import main, build_parser
    assert callable(main)
    assert callable(build_parser)
