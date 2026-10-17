"""Private Poolrad DOS oracle session streamed to the owner's authenticated desk."""

from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


class GameError(Exception):
    pass


class GameSession:
    KEYS = {"Up", "Down", "Left", "Right", "Return", "Escape", "space", "BackSpace", "Tab", "Delete", "Home", "End", "Page_Up", "Page_Down"}
    KEYS.update(chr(n) for n in range(ord("a"), ord("z") + 1))
    KEYS.update(str(n) for n in range(10))
    KEYS.update(f"F{n}" for n in range(1, 13))

    def __init__(self, repo: Path, data: Path):
        self.repo = repo
        self.data = data
        self.run_root = repo / "resources" / "oracle-runs"
        self.last_file = data / "poolrad-last-run.txt"
        self.lock = threading.RLock()
        self.display: str | None = None
        self.run_dir: Path | None = None
        self.xvfb: subprocess.Popen | None = None
        self.tmux_session: str | None = None
        self.sink_module: str | None = None
        self.sink_name: str | None = None
        self.log_files = []

    def _run(self, cmd: list[str], **kwargs):
        return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=70, **kwargs)

    def _valid_run(self, name: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
            raise GameError("Invalid run name")
        path = self.run_root / name
        if not (path / ".oracle-input-sha256").is_file() or not (path / "POOLRAD" / "START.EXE").is_file():
            raise GameError("Prepared Poolrad run is unavailable")
        return path

    def status(self) -> dict:
        with self.lock:
            if self.tmux_session and not self._game_running():
                self._stop_locked()
            last = self.last_file.read_text().strip() if self.last_file.exists() else None
            return {"running": self.tmux_session is not None, "audio": self.sink_name is not None,
                    "run_name": self.run_dir.name if self.run_dir else last}

    def _game_running(self) -> bool:
        return bool(self.tmux_session and subprocess.run(
            ["tmux", "-L", "vp-poolrad", "has-session", "-t", self.tmux_session],
            capture_output=True, timeout=2).returncode == 0)

    def recover_orphans(self):
        """Clear only the dedicated game's terminal and Pulse sinks after a crash."""
        subprocess.run(["tmux", "-L", "vp-poolrad", "kill-server"], capture_output=True, timeout=5)
        try:
            result = subprocess.run(["pactl", "list", "short", "modules"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.splitlines():
                fields = line.split("\t", 3)
                if len(fields) >= 3 and fields[1] == "module-null-sink" and re.search(r"\bsink_name=vp_poolrad_\d+\b", fields[2]):
                    subprocess.run(["pactl", "unload-module", fields[0]], capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            pass

    def start(self, fresh: bool = False) -> dict:
        with self.lock:
            if self._game_running():
                return self.status()
            self._stop_locked()
            if not self.repo.is_dir():
                raise GameError("Poolrad checkout is unavailable")
            if fresh or not self.last_file.exists():
                name = "vp-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
                try:
                    self._run([str(self.repo / "tools/oracle/prepare_run.sh"), name], cwd=self.repo)
                except (OSError, subprocess.SubprocessError) as exc:
                    raise GameError(f"Could not prepare verified game copy: {exc}") from exc
            else:
                name = self.last_file.read_text().strip()
            run_dir = self._valid_run(name)
            self.run_dir = run_dir
            self.last_file.write_text(name + "\n")
            self.last_file.chmod(0o600)
            try:
                for n in range(90, 130):
                    if Path(f"/tmp/.X{n}-lock").exists() or Path(f"/tmp/.X11-unix/X{n}").exists():
                        continue
                    display = f":{n}"
                    auth = run_dir / ".vp-xauthority"
                    auth.touch(mode=0o600, exist_ok=True)
                    self._run(["xauth", "-f", str(auth), "add", display, ".", secrets.token_hex(16)])
                    log = (run_dir / "vp-xvfb.log").open("ab")
                    self.log_files.append(log)
                    xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "800x600x24", "-nolisten", "tcp", "-auth", str(auth)],
                                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    for _ in range(30):
                        if xvfb.poll() is not None:
                            break
                        if self._x_ready(display, auth):
                            self.xvfb = xvfb
                            self.display = display
                            break
                        time.sleep(0.1)
                    if self.xvfb:
                        break
                    xvfb.terminate()
                if not self.xvfb:
                    raise GameError("Could not start private display")
                sink = "vp_poolrad_" + str(os.getpid())
                try:
                    result = self._run(["pactl", "load-module", "module-null-sink", f"sink_name={sink}", "rate=48000", "channels=2"])
                    self.sink_module = result.stdout.strip()
                    self.sink_name = sink
                except (OSError, subprocess.SubprocessError):
                    pass  # Video remains usable on a host without PulseAudio.
                env = os.environ.copy()
                env.update({"DISPLAY": self.display, "XAUTHORITY": str(auth),
                            "SDL_AUDIODRIVER": "pulse" if self.sink_name else "dummy",
                            "XDG_CONFIG_HOME": str(run_dir / ".config"),
                            "XDG_CACHE_HOME": str(run_dir / ".cache"),
                            "XDG_DATA_HOME": str(run_dir / ".local" / "share")})
                if self.sink_name:
                    env["PULSE_SINK"] = self.sink_name
                for key in (".config", ".cache", ".local/share", ".dosbox-saves"):
                    (run_dir / key).mkdir(parents=True, exist_ok=True)
                cmd = ["bwrap", "--unshare-net", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                       "--bind", str(run_dir), str(run_dir), "--chdir", str(run_dir),
                       "dosbox-x", "-defaultconf", "-defaultmapper", "-nogui", "-nomenu", "-fastlaunch", "-fullscreen",
                       "-savedir", str(run_dir / ".dosbox-saves"),
                       "-c", f"mount c {run_dir}", "-c", "c:", "-c", "cd \\POOLRAD", "-c", "START"]
                session = "oracle"
                env_args = [f"{key}={env[key]}" for key in ("DISPLAY", "XAUTHORITY", "SDL_AUDIODRIVER", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")]
                if self.sink_name:
                    env_args.append(f"PULSE_SINK={self.sink_name}")
                command = "exec " + shlex.join(["env", *env_args, *cmd])
                self._run(["tmux", "-L", "vp-poolrad", "new-session", "-d", "-s", session, "-x", "140", "-y", "40", command])
                self.tmux_session = session
                self._run(["tmux", "-L", "vp-poolrad", "pipe-pane", "-o", "-t", session, f"cat >> {shlex.quote(str(run_dir / 'vp-dosbox-terminal.log'))}"])
                time.sleep(1)
                if not self._game_running():
                    raise GameError("DOSBox-X exited during startup; inspect private vp-dosbox-terminal.log")
                return self.status()
            except Exception as exc:
                self._stop_locked()
                if isinstance(exc, GameError):
                    raise
                raise GameError(f"Could not start Poolrad: {exc}") from exc

    @staticmethod
    def _x_ready(display: str, auth: Path) -> bool:
        try:
            subprocess.run(["xdotool", "getdisplaygeometry"], env={**os.environ, "DISPLAY": display, "XAUTHORITY": str(auth)},
                           capture_output=True, check=True, timeout=1)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _terminate(process: subprocess.Popen | None):
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=4)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)

    def _stop_locked(self):
        if self.tmux_session:
            subprocess.run(["tmux", "-L", "vp-poolrad", "kill-session", "-t", self.tmux_session], capture_output=True, timeout=5)
        self._terminate(self.xvfb)
        if self.sink_module:
            try:
                subprocess.run(["pactl", "unload-module", self.sink_module], capture_output=True, timeout=5)
            except (OSError, subprocess.SubprocessError):
                pass
        for log in self.log_files:
            log.close()
        self.log_files.clear()
        self.xvfb = None
        self.tmux_session = None
        self.display = self.sink_module = self.sink_name = None
        self.run_dir = None

    def stop(self) -> dict:
        with self.lock:
            self._stop_locked()
            return self.status()

    def key(self, key: str):
        if key not in self.KEYS:
            raise GameError("Unsupported game key")
        with self.lock:
            if not self._game_running() or not self.display or not self.run_dir:
                raise GameError("Poolrad is not running")
            env = {**os.environ, "DISPLAY": self.display, "XAUTHORITY": str(self.run_dir / ".vp-xauthority")}
            self._run(["xdotool", "key", "--clearmodifiers", "--delay", "70", key], env=env)
            with (self.run_dir / "vp-input.jsonl").open("a") as output:
                output.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "key": key}) + "\n")

    def stream(self, kind: str):
        with self.lock:
            if not self._game_running() or not self.run_dir:
                raise GameError("Poolrad is not running")
            if kind == "audio" and not self.sink_name:
                raise GameError("Audio capture is unavailable")
            env = {**os.environ, "DISPLAY": self.display or "", "XAUTHORITY": str(self.run_dir / ".vp-xauthority")}
            if kind == "video":
                cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "x11grab", "-framerate", "12",
                       "-video_size", "800x600", "-i", self.display or "", "-vf", "scale=800:600",
                       "-q:v", "5", "-f", "mpjpeg", "pipe:1"]
            else:
                cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "pulse", "-i", f"{self.sink_name}.monitor",
                       "-ac", "2", "-ar", "48000", "-c:a", "libopus", "-b:a", "64k", "-page_duration", "200000", "-flush_packets", "1", "-f", "ogg", "pipe:1"]
            proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            while data := proc.stdout.read1(8192):
                yield data
        finally:
            self._terminate(proc)
