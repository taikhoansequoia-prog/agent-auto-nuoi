# App version. build.ps1 rewrites __build_time__ (and __version__ if -Version passed)
# on every EXE packaging. Running from source (python ui_main.py) has no build stamp.
# NOTE: keep this file ASCII-only so PowerShell string-rewrites never corrupt it.
__version__ = "1.5.0"
__build_time__ = "20/10/2026 13:16"


def get_version_line():
    """e.g. 'v1.1.0 (build 13/10/2026 15:30)' or 'v1.1.0' when run from source."""
    if __build_time__:
        return f"v{__version__} (build {__build_time__})"
    return f"v{__version__}"
