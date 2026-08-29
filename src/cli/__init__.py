from __future__ import annotations

from typer.exceptions import Abort, Exit, TyperException

from .app import app
from .common import require_max_depth_mvp, resolve_embed_provider


def main(argv: list[str] | None = None) -> int:
    # standalone_mode=False so we return int for tests; Typer's Click then raises
    # instead of sys.exit — map those to exit codes (bare `zhvault` → NoArgsIsHelpError).
    try:
        result = app(args=argv, prog_name="zhvault", standalone_mode=False)
        return 0 if result is None else int(result)
    except Exit as e:
        return int(e.exit_code)
    except Abort:
        return 1
    except TyperException as e:
        # NoArgsIsHelpError: rich help already printed via ctx.get_help() in the ctor
        if type(e).__name__ != "NoArgsIsHelpError" and hasattr(e, "show"):
            e.show()
        return int(getattr(e, "exit_code", 1))


__all__ = ["app", "main", "require_max_depth_mvp", "resolve_embed_provider"]
