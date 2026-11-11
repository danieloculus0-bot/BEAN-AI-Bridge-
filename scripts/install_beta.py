"""Install a downloaded BEAN Operations beta wheel without internet access.

Usage: python scripts/install_beta.py --wheel dist/bean_ai_bridge-*.whl --home <private folder>

The installer creates a local virtual environment, installs the wheel with
--no-index, and runs the fictional demo as a smoke test. A source-control
checkout or any hosted model is not needed to operate the installed package.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import venv


def install(wheel: Path, home: Path) -> dict:
    wheel = wheel.resolve()
    if not wheel.is_file() or wheel.suffix.lower() != ".whl":
        raise ValueError("Supply a previously downloaded local .whl file")
    home = home.resolve()
    home.mkdir(parents=True, exist_ok=True)
    env = home / ".venv"
    venv.EnvBuilder(with_pip=True, clear=False).create(str(env))
    python = env / ("Scripts/python.exe" if __import__("os").name == "nt"
                    else "bin/python")
    runner = env / ("Scripts/bean-run.exe" if __import__("os").name == "nt"
                    else "bin/bean-run")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-index", "--no-deps",
         str(wheel)], check=True, capture_output=True, text=True
    )
    out = home / "demo" / "morning.html"
    done = subprocess.run(
        [str(runner), "--demo", "--out", str(out)],
        cwd=home, check=True, capture_output=True, text=True
    )
    receipt = json.loads(done.stdout)
    if not receipt.get("synthetic") or len(receipt.get("source_status", [])) != 3:
        raise AssertionError("Installed synthetic demo did not complete")
    if not out.is_file() or not out.with_suffix(".json").is_file():
        raise AssertionError("Installed BEAN operator report was not written")
    return {
        "install_status": "PASS",
        "offline_wheel_install": True,
        "fictional_smoke_test": True,
        "wheel": wheel.name,
        "workspace": str(home),
        "command": str(runner),
        "html_report": str(out),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Install BEAN Operations offline beta")
    parser.add_argument("--wheel", required=True, type=Path,
                        help="Local package wheel built and downloaded from GitHub Actions")
    parser.add_argument("--home", required=True, type=Path,
                        help="Private writable folder for this installation")
    args = parser.parse_args()
    print(json.dumps(install(args.wheel, args.home), indent=2))


if __name__ == "__main__":
    main()
