"""Runs INSIDE the disposable container; never import a candidate module on the host."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
import sys


def main():
    print("CODELAB-RUNNER-READY/2", flush=True)
    envelope = json.load(sys.stdin)
    req = envelope["instruction"]
    with tempfile.TemporaryDirectory(prefix="job-", dir="/tmp") as tmp:
        root = Path(tmp)
        for relative, content in envelope["project"].items():
            target = (root / relative).resolve()
            if not target.is_relative_to(root) or target == root:
                raise ValueError("工程文件路径无效")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        os.chdir(root)
        Path(os.environ["HOME"]).mkdir(parents=True, exist_ok=True)
        if envelope["runtime"] == "node" or (req["action"] == "preview"):
            # Vite writes caches under node_modules. Expose installed immutable dependencies
            # individually so those caches can be written inside this job's own workspace.
            modules = root / "node_modules"
            modules.mkdir(exist_ok=True)
            for dependency in Path("/opt/codelab/js/node_modules").iterdir():
                target = modules / dependency.name
                if not target.exists():
                    target.symlink_to(dependency)
            os.environ["PATH"] = str(modules / ".bin") + os.pathsep + os.environ["PATH"]
        if req["action"] == "command":
            return subprocess.run(req["argv"], stdin=subprocess.DEVNULL).returncode
        if req["action"] == "preview":
            # Release the bundler and its helper threads before starting Chromium.
            with tempfile.TemporaryDirectory(prefix="page-", dir="/tmp") as dist:
                build = subprocess.run(["node", "/opt/codelab/js/js-entry.mjs", dist], input=json.dumps(req).encode())
                if build.returncode:
                    return build.returncode
                render = subprocess.run(["node", "/opt/codelab/preview.cjs", dist], input=json.dumps(req["input"]).encode())
                return render.returncode
        raise ValueError("未知的运行器操作。")


if __name__ == "__main__":
    sys.exit(main())
