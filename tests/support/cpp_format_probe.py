"""Compile a native format consumer and feed it isolated byte-exact fixtures.

The supplied C++ main receives a fixture path as argv[1]. No shell, original
media, running service, or installed emulator is involved. Call close() or
register it with unittest cleanup. A missing compiler is a failure, not a skip.
"""
from pathlib import Path
import os
import subprocess
import tempfile


class CppFormatProbe:
    def __init__(self, source: str, include_dir: Path):
        self.temp = tempfile.TemporaryDirectory(prefix="format-agreement-")
        self.root = Path(self.temp.name)
        self.binary = self.root / "probe"
        cpp = self.root / "probe.cpp"
        cpp.write_text(source)
        try:
            subprocess.run(["c++", "-std=c++11", "-O0", "-I", str(include_dir),
                            str(cpp), "-o", str(self.binary)],
                           check=True, capture_output=True, timeout=60)
        except BaseException:
            self.close()
            raise

    def run(self, data: bytes) -> bytes:
        fixture = self.root / "input"
        fixture.write_bytes(data)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("PR_HYBRID_", "PR_PARITY_"))}
        return subprocess.run([str(self.binary), str(fixture)], cwd=self.root,
                              env=env, check=True, capture_output=True,
                              timeout=10).stdout

    def close(self):
        self.temp.cleanup()
