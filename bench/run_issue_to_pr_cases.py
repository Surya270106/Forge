"""Run versioned workflow invariants without changing Forge Bench's coding-task scores."""

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

CATALOG = Path(__file__).with_name("issue-to-pr-cases-v1.json")
ROOT = CATALOG.parent.parent


def main() -> int:
    raw = CATALOG.read_bytes()
    catalog = json.loads(raw)
    cases = catalog["cases"]
    ids = [case["id"] for case in cases]
    if catalog["version"] != 1 or len(cases) != 10 or len(set(ids)) != 10:
        raise ValueError("Expected ten unique version-one workflow cases")
    print(f"{catalog['id']} sha256={hashlib.sha256(raw).hexdigest()}", flush=True)
    failures = 0
    with tempfile.TemporaryDirectory(prefix="forge-issue-bench-") as temporary:
        for case in cases:
            selectors = [case["test"], *case.get("also", [])]
            for selector in selectors:
                path = selector.split("::", 1)[0]
                if not re.fullmatch(r"tests/[A-Za-z0-9_./-]+\.py::test_[A-Za-z0-9_]+(?:\[[A-Za-z0-9_-]+\])?", selector):
                    raise ValueError(f"Unsafe or invalid case selector: {case['id']}")
                if not (ROOT / path).is_file():
                    raise ValueError(f"Missing test for {case['id']}")
            report = Path(temporary) / f"{case['id']}.xml"
            run = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=short",
                                  f"--junitxml={report}", *selectors], cwd=ROOT, capture_output=True, text=True)
            if report.exists():
                suite = ET.parse(report).getroot()
                if suite.tag == "testsuites":
                    suite = suite.find("testsuite")
                count = int(suite.get("tests", "0")) if suite is not None else 0
                skipped = int(suite.get("skipped", "0")) if suite is not None else 0
                failed = int(suite.get("failures", "0")) + int(suite.get("errors", "0")) if suite is not None else 1
            else:
                count, skipped, failed = 0, 0, 1
            passed = run.returncode == 0 and count > 0 and skipped == 0 and failed == 0
            print(f"{case['id']}: {'PASS' if passed else 'FAIL'} ({count} tests, {skipped} skipped, {failed} failed)", flush=True)
            if not passed:
                failures += 1
                print(run.stdout[-4000:] + run.stderr[-2000:], flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
