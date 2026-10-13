#!/usr/bin/env python3
"""Run real tests and emit a bounded machine-readable report to stdout."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import io
import json
import platform
import sys
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from dualweb import __version__


class Recorder(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []
    def addSuccess(self, test):
        super().addSuccess(test)
        self.cases.append({"test": test.id(), "outcome": "passed"})
    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.cases.append({"test": test.id(), "outcome": "failed"})
    def addError(self, test, err):
        super().addError(test, err)
        self.cases.append({"test": test.id(), "outcome": "error"})
    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.cases.append({"test": test.id(), "outcome": "skipped", "reason": reason})


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(HERE / "tests"))
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=Recorder).run(suite)
    source_hashes = {p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in HERE.rglob("*.py") if "__pycache__" not in p.parts}
    report = {"version": __version__, "executed_at_environment_clock": datetime.now(timezone.utc).isoformat(),
              "python": sys.version, "platform": platform.platform(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skips": len(result.skipped), "passed": result.wasSuccessful() and result.testsRun > 0 and not result.skipped,
              "cases": result.cases, "source_sha256": source_hashes, "log": output.getvalue(),
              "scope": "same-author local unit/integration and actual loopback HTTP tests; not independent certification",
              "not_run": ["Original PowerShell validator", "Windows/macOS execution", "Production deployment/CDN/WAF", "Real LLM behavior/accuracy", "Source truth verification"]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
