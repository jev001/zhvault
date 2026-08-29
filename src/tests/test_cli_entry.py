def test_cli_main_importable():
    from cli import main
    from cli.app import app

    assert callable(main)
    assert app is not None
