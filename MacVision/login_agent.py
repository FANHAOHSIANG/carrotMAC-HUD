"""Install the Mac Vision worker into the current graphical login session."""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from install import write_file

LABEL = "io.carrot.machud.vision"


def configure(remove=False):
    home = Path.home()
    state = home / "Library/Application Support/CarrotMacVision"
    plist = home / "Library/LaunchAgents" / (LABEL + ".plist")
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{LABEL}"

    def ctl(*args, check=True):
        return subprocess.run(["launchctl", *args], check=check, capture_output=not check)

    if ctl("print", target, check=False).returncode == 0:
        ctl("bootout", target)
    if remove:
        plist.unlink(missing_ok=True)
        print("Mac Vision 登入自動啟動已關閉。")
        return
    runtime = state / "worker"
    runtime.mkdir(parents=True, exist_ok=True)
    for name in ("vision.py", "preview.py", "crosswalk.py"):
        write_file(runtime / name, Path(__file__).with_name(name).read_bytes())
    spec = dict(Label=LABEL, RunAtLoad=True, KeepAlive=dict(SuccessfulExit=False),
                ThrottleInterval=15, Nice=10, WorkingDirectory=str(state),
                ProgramArguments=[str(state / "env/bin/python"), str(runtime / "vision.py"), "--background"],
                StandardErrorPath=str(state / "worker-error.log"))
    plist.parent.mkdir(parents=True, exist_ok=True)
    write_file(plist, plistlib.dumps(spec))
    ctl("bootstrap", domain, str(plist))
    print("Mac Vision 已設為登入時啟動。現在可以關閉終端機並開啟 Jetlink。")


if __name__ == "__main__":
    configure("--remove" in sys.argv[1:])
