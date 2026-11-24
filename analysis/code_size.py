#!/usr/bin/env python3
"""Count the lines of code of pltrs and of matplotlib 3.11.2.

Input:  the pltrs repository (read only, ~/dev/plt-rs or PLTRS_REPO),
        the source distribution of matplotlib 3.11.2 from PyPI
Output: results/paper/code_size.json

A line count includes blank lines and comments. For pltrs, the script
counts the files that git tracks. For matplotlib, it counts the library
(`lib/`, without tests), the tests (`lib/**/tests/`) and the extension
modules (`src/`). It does not count the bundled libraries in `extern/`
and `subprojects/`.
"""
import io
import json
import os
import subprocess
import sys
import tarfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

REPO = os.environ.get("PLTRS_REPO", os.path.expanduser("~/dev/plt-rs"))
SDIST = ("https://files.pythonhosted.org/packages/e7/c8/"
         "9aa712a0afb882649424dd8de8ad9aa6235e796e84c6052e8f6dc1598d0d/matplotlib-3.11.2.tar.gz")
NATIVE = (".cpp", ".h", ".c", ".hpp", ".m")


def pltrs():
    files = subprocess.run(["git", "-C", REPO, "ls-files", "-z"], capture_output=True, check=True).stdout
    out = {"rust": 0, "rust_in_crates": 0, "python": 0, "python_package": 0, "files": 0}
    for name in files.decode().split("\0"):
        if not name:
            continue
        out["files"] += 1
        if not name.endswith((".rs", ".py")):
            continue
        with open(os.path.join(REPO, name), "rb") as f:
            n = f.read().count(b"\n")
        if name.endswith(".rs"):
            out["rust"] += n
            out["rust_in_crates"] += n if name.startswith("crates/") else 0
        else:
            out["python"] += n
            out["python_package"] += n if name.startswith("python/pltrs/") else 0
    out["commits"] = int(subprocess.run(["git", "-C", REPO, "rev-list", "--count", "HEAD"],
                                        capture_output=True, text=True, check=True).stdout)
    return out


def matplotlib():
    data = urllib.request.urlopen(SDIST, timeout=120).read()
    out = {"python_library": 0, "python_tests": 0, "native_extension": 0, "test_functions": 0}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar:
            if not m.isfile():
                continue
            parts = m.name.split("/")[1:]
            if not parts:
                continue
            text = None
            if parts[0] == "lib" and m.name.endswith(".py"):
                text = tar.extractfile(m).read()
                if "tests" in parts:
                    out["python_tests"] += text.count(b"\n")
                    out["test_functions"] += sum(1 for l in text.split(b"\n") if l.lstrip().startswith(b"def test_"))
                else:
                    out["python_library"] += text.count(b"\n")
            elif parts[0] == "src" and m.name.endswith(NATIVE):
                out["native_extension"] += tar.extractfile(m).read().count(b"\n")
    return out


def main():
    out = {"pltrs": pltrs(), "matplotlib_3_11_2": matplotlib()}
    os.makedirs(os.path.join(lib.RESULTS, "paper"), exist_ok=True)
    with open(os.path.join(lib.RESULTS, "paper", "code_size.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
