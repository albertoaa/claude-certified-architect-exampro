from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import IO

_log_file: IO[str] | None = None


def _open_log_file() -> IO[str]:
    main = sys.modules.get("__main__")
    if main and getattr(main, "__file__", None):
        project_dir = Path(main.__file__).resolve().parent
    else:
        project_dir = Path.cwd()

    log_dir = project_dir / "logs"
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    return (log_dir / f"{timestamp}.log").open("w", encoding="utf-8", buffering=1)


def log(text: str) -> None:
    global _log_file
    if _log_file is None:
        _log_file = _open_log_file()
    _log_file.write(text + "\n")
