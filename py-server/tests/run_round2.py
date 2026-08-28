"""Runner script for Round 2 regression tests."""
import subprocess
import sys
import os

os.chdir(r"E:\Program\MARL\study-help-pro\py-server")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_audit_fixes.py", "-v", "--tb=short"],
    capture_output=True,
    text=True,
    timeout=180,
)
print(result.stdout)
print(result.stderr)
print(f"returncode: {result.returncode}")
