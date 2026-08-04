import ctypes
import os
import subprocess
import sys

APP_VERSION = "1.1.0"


def is_admin():
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    if sys.platform != "win32":
        return
    exe = sys.executable
    params = subprocess.list2cmdline(sys.argv[1:])
    cwd = os.path.dirname(os.path.abspath(exe))
    if ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, cwd, 1) > 32:
        sys.exit(0)


def main():
    app_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    os.chdir(app_dir)
    debug = os.environ.get("NIDUS_DEBUG") == "1" or "--debug" in sys.argv
    if sys.platform == "win32" and not is_admin() and not debug:
        relaunch_as_admin()
    from src.ui.window import launch
    launch(app_dir, APP_VERSION, debug)


if __name__ == "__main__":
    main()
