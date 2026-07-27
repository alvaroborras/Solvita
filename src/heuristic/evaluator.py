"""Docker-only candidate compilation/execution and trusted host scoring."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .bundle import CandidateBundleV1
from .contracts import EvaluationRecord, Fidelity, ProblemManifestV1
from .storage import ArtifactStore, HeuristicStore


class DockerUnavailable(RuntimeError):
    pass


class DockerEvaluator:
    def __init__(
        self,
        manifest: ProblemManifestV1,
        adapter,
        *,
        image: str = "solvita-heuristic-cpp23:latest",
        docker: str = "docker",
        sdk_dir: str | Path | None = None,
        cache_dir: str | Path = ".solvita/heuristic/compile",
        artifacts: ArtifactStore | None = None,
        store: HeuristicStore | None = None,
    ):
        self.manifest, self.adapter, self.image, self.docker = (
            manifest,
            adapter,
            image,
            docker,
        )
        self.sdk_dir = Path(sdk_dir).resolve() if sdk_dir else None
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts, self.store = artifacts, store
        self.scorer_cache_version = (
            f"{manifest.scorer_version}:{adapter.hash()[:16]}:{manifest.digest()[:16]}"
        )
        self._image_digest: str | None = None
        self._locks: dict[str, threading.Lock] = {}

    def preflight(self) -> dict[str, str]:
        if shutil.which(self.docker) is None:
            raise DockerUnavailable(
                "Docker is required for heuristic candidate evaluation"
            )
        probe = subprocess.run(
            [
                self.docker,
                "inspect",
                "--type",
                "image",
                "--format",
                "{{.Id}}",
                self.image,
            ],
            capture_output=True,
            text=True,
        )
        if probe.returncode:
            raise DockerUnavailable(
                f"Docker image {self.image!r} is unavailable; build docker/heuristic-cpp23.Dockerfile"
            )
        self._image_digest = probe.stdout.strip()
        if not self._image_digest.startswith("sha256:"):
            raise DockerUnavailable(
                f"Docker did not return an immutable digest for {self.image!r}"
            )
        return {"image": self.image, "image_digest": self._image_digest}

    def compilation_key(self, bundle: CandidateBundleV1) -> str:
        sdk_hash = hashlib.sha256()
        if self.sdk_dir:
            for path in sorted(self.sdk_dir.rglob("*")):
                if path.is_file():
                    sdk_hash.update(path.relative_to(self.sdk_dir).as_posix().encode())
                    sdk_hash.update(path.read_bytes())
        data = {
            "bundle": bundle.digest,
            "sdk": sdk_hash.hexdigest(),
            "image": self._image_digest or self.image,
            "standard": self.manifest.default_standard,
            "flags": ["-O2", "-pipe", "-I/sdk", "-I/work/include"],
            "platform": os.uname().machine,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    def compile(self, bundle: CandidateBundleV1) -> tuple[Path | None, str | None]:
        if self._image_digest is None:
            self.preflight()
        key = self.compilation_key(bundle)
        binary = self.cache_dir / key / "candidate"
        if binary.is_file():
            self._record_binary_artifact(binary)
            return binary, None
        lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            if binary.is_file():
                self._record_binary_artifact(binary)
                return binary, None
            with tempfile.TemporaryDirectory(prefix="solvita-compile-") as temporary:
                root = Path(temporary)
                bundle.write(root)
                sources = [
                    f"/work/{name}" for name in bundle.files if name.endswith(".cpp")
                ]
                command = [
                    self.docker,
                    "run",
                    "--rm",
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    "--pids-limit",
                    "64",
                    "--memory",
                    "2g",
                    "--cpus",
                    "1",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,size=256m",
                    "-v",
                    f"{root}:/work:rw",
                ]
                if self.sdk_dir:
                    command += ["-v", f"{self.sdk_dir}:/sdk:ro"]
                command += [
                    self._image_digest or self.image,
                    "g++",
                    f"-std={self.manifest.default_standard}",
                    "-O2",
                    "-pipe",
                    "-I/sdk",
                    "-I/work/include",
                    *sources,
                    "-o",
                    "/work/candidate",
                ]
                try:
                    process = subprocess.run(command, capture_output=True, timeout=120)
                except subprocess.TimeoutExpired:
                    return None, "compile_timeout"
                if process.returncode:
                    detail = process.stderr.decode("utf-8", "replace")[-4000:]
                    return None, f"compile:{detail}"
                binary.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / "candidate", binary)
                binary.chmod(0o555)
                self._record_binary_artifact(binary)
        return binary, None

    def _record_binary_artifact(self, binary: Path) -> None:
        if self.artifacts is None:
            return
        digest = self.artifacts.put_bytes(binary.read_bytes(), ".binary")
        sidecar = binary.parent / "artifact.digest"
        if not sidecar.exists():
            sidecar.write_text(digest + "\n", encoding="ascii")

    def evaluate(
        self,
        bundle: CandidateBundleV1,
        instance_id: str,
        fidelity: Fidelity,
        seed: int = 0,
    ) -> EvaluationRecord:
        cached = None
        if self.store:
            cached = self.store.get_evaluation(
                bundle.digest,
                self.manifest.problem_id,
                instance_id,
                fidelity.value,
                seed,
                self.scorer_cache_version,
            )
        if cached:
            cached["fidelity"] = Fidelity(cached["fidelity"])
            return EvaluationRecord(**cached)
        started = time.monotonic()
        limit = (
            self.manifest.final_limits
            if fidelity is Fidelity.PROMOTION
            else self.manifest.search_limits
        )
        binary, compile_failure = self.compile(bundle)
        if binary is None:
            return self._failure(
                bundle,
                instance_id,
                fidelity,
                seed,
                started,
                compile_failure or "compile",
            )
        run = self.runtime_command(binary, limit, seed)
        returncode, stdout, run_failure = self._run_limited(
            run,
            self.adapter.instance_stdin(instance_id),
            timeout_seconds=limit.time_limit_ms / 1000 + 2,
            output_bytes=limit.output_bytes,
        )
        if run_failure == "timeout":
            return self._failure(
                bundle, instance_id, fidelity, seed, started, "timeout"
            )
        if run_failure == "output_limit":
            return self._failure(
                bundle, instance_id, fidelity, seed, started, "output_limit"
            )
        if returncode:
            return self._failure(
                bundle, instance_id, fidelity, seed, started, "runtime"
            )
        artifact = (
            self.artifacts.put_bytes(stdout, ".stdout") if self.artifacts else None
        )
        try:
            result = self.adapter.validate(
                instance_id, self.adapter.parse_output(stdout)
            )
            feasible = bool(result.get("feasible", result.get("valid", False)))
            objective = result.get("objective")
            components = {
                key: float(value)
                for key, value in result.items()
                if key in {"obj1", "obj2", "obj3"} and value is not None
            }
        except Exception:
            return self._failure(
                bundle, instance_id, fidelity, seed, started, "invalid_output", artifact
            )
        record = EvaluationRecord(
            bundle.digest,
            self.manifest.problem_id,
            instance_id,
            fidelity,
            seed,
            self.scorer_cache_version,
            feasible,
            float(objective) if objective is not None else None,
            components,
            int((time.monotonic() - started) * 1000),
            artifact,
            None if feasible else "infeasible",
        )
        if self.store:
            self.store.save_evaluation(record)
        return record

    @staticmethod
    def _run_limited(
        command: list[str],
        stdin: bytes,
        *,
        timeout_seconds: float,
        output_bytes: int,
    ) -> tuple[int, bytes, str | None]:
        """Run Docker without buffering unbounded candidate output in host RAM."""
        with tempfile.TemporaryDirectory(prefix="solvita-output-") as temporary:
            stdout_path = Path(temporary) / "stdout"
            stderr_path = Path(temporary) / "stderr"
            with (
                stdout_path.open("wb") as stdout_handle,
                stderr_path.open("wb") as stderr_handle,
            ):
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                )
                assert process.stdin is not None
                try:
                    process.stdin.write(stdin)
                except BrokenPipeError:
                    pass
                finally:
                    process.stdin.close()
                deadline = time.monotonic() + timeout_seconds
                failure = None
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        failure = "timeout"
                        break
                    if (
                        stdout_path.stat().st_size + stderr_path.stat().st_size
                        > output_bytes
                    ):
                        failure = "output_limit"
                        break
                    time.sleep(0.01)
                if failure is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                returncode = process.wait()
            stdout = stdout_path.read_bytes()[: output_bytes + 1]
            if len(stdout) > output_bytes:
                failure = "output_limit"
            return returncode, stdout, failure

    def runtime_command(self, binary: Path, limit, seed: int) -> list[str]:
        """Return the auditable candidate jail command.

        Only the executable is mounted. Instances arrive on stdin and trusted
        scorer/BKS/validation stores therefore have no container path.
        """
        return [
            self.docker,
            "run",
            "--rm",
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--pids-limit",
            str(limit.pids),
            "--memory",
            f"{limit.memory_mb}m",
            "--cpus",
            "1",
            "--stop-timeout",
            "2",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "-e",
            f"SOLVITA_SEED={seed}",
            "-e",
            f"SOLVITA_TIME_LIMIT_MS={limit.time_limit_ms}",
            "-i",
            "-v",
            f"{binary}:/candidate:ro",
            self._image_digest or self.image,
            "/candidate",
        ]

    def _failure(
        self,
        bundle: CandidateBundleV1,
        instance_id: str,
        fidelity: Fidelity,
        seed: int,
        started: float,
        failure: str,
        artifact: str | None = None,
    ) -> EvaluationRecord:
        record = EvaluationRecord(
            bundle.digest,
            self.manifest.problem_id,
            instance_id,
            fidelity,
            seed,
            self.scorer_cache_version,
            False,
            runtime_ms=int((time.monotonic() - started) * 1000),
            output_artifact=artifact,
            failure=failure,
        )
        if self.store:
            self.store.save_evaluation(record)
        return record
