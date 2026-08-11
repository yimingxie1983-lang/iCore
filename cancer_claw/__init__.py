

__version__ = "0.1.0"

def _force_utf8_stdio() -> None:

    import sys

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):

            pass

_force_utf8_stdio()
