"""The free-model sandbox must actually isolate: no host sockets, no foreign credentials, no writes
outside the output dir, subject repo read-only. Skipped where bwrap is unavailable."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[1] / "tools" / "free_sandbox.sh"
AUTH = Path.home() / ".pi" / "agent" / "auth.json"


@unittest.skipUnless(shutil.which("bwrap") and AUTH.exists(), "needs bwrap and a pi auth file")
class SandboxTests(unittest.TestCase):
    def setUp(self):
        base = Path.home() / ".cache"
        base.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=base, prefix="sbx-test-"))
        self.repo = self.tmp / "repo"; self.repo.mkdir()
        self.out = self.tmp / "out"
        self.env = dict(os.environ, POOLRAD_REPO=str(self.repo))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sandbox(self, *cmd):
        return subprocess.run([str(SANDBOX), str(self.out), *cmd], capture_output=True, text=True, env=self.env)

    def test_host_unix_socket_is_unreachable(self):
        path = self.tmp / "host.sock"
        srv = socket.socket(socket.AF_UNIX); srv.bind(str(path)); srv.listen(1); srv.settimeout(3)
        try:
            r = self.sandbox("python3", "-c",
                             f"import socket;s=socket.socket(socket.AF_UNIX);s.connect({str(path)!r})")
            self.assertNotEqual(r.returncode, 0, "sandbox reached a host unix socket")
            with self.assertRaises(socket.timeout):
                srv.accept()                      # nothing connected
        finally:
            srv.close()

    def test_only_the_openrouter_credential_is_visible(self):
        r = self.sandbox("python3", "-c",
                         "import json,os;print(json.dumps(sorted(json.load(open(os.path.expanduser('~/.pi/agent/auth.json'))))))")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(set(json.loads(r.stdout)) <= {"openrouter"}, r.stdout)

    def test_repo_is_read_only_and_out_dir_is_writable(self):
        r = self.sandbox("bash", "-c", f"touch {self.repo}/x; echo repo_rc=$?; touch {self.out}/y; echo out_rc=$?")
        self.assertIn("out_rc=0", r.stdout)
        self.assertNotIn("repo_rc=0", r.stdout)
        self.assertFalse((self.repo / "x").exists())
        self.assertTrue((self.out / "y").exists())

    def test_user_files_outside_the_allowlist_are_invisible(self):
        r = self.sandbox("bash", "-c", "ls -A ~ | tr '\\n' ' '")
        self.assertNotIn(".ssh", r.stdout)
        self.assertNotIn(".claude", r.stdout)
        self.assertNotIn(".config", r.stdout)


if __name__ == "__main__":
    unittest.main()
