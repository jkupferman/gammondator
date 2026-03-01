from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass

from app.analysis import analyze_move, analyze_with_explicit_equities
from app.schemas import AnalyzeMoveRequest, AnalyzeMoveResponse


class BackendUnavailableError(RuntimeError):
    pass


class AnalyzerBackend:
    name = "base"

    def analyze_move(self, request: AnalyzeMoveRequest) -> AnalyzeMoveResponse:
        raise NotImplementedError

    def details(self) -> str:
        return ""


class HeuristicBackend(AnalyzerBackend):
    name = "heuristic"

    def analyze_move(self, request: AnalyzeMoveRequest) -> AnalyzeMoveResponse:
        return analyze_move(request)

    def details(self) -> str:
        return "Built-in heuristic evaluator."


class GnuBGBridgeBackend(AnalyzerBackend):
    name = "gnubg"

    def __init__(self, bridge_cmd: str, timeout_seconds: float = 10.0) -> None:
        self.bridge_cmd = bridge_cmd
        self.timeout_seconds = timeout_seconds

    def _command_parts(self) -> list[str]:
        parts = shlex.split(self.bridge_cmd)
        if not parts:
            raise BackendUnavailableError("empty GNUbg bridge command")
        return parts

    def _validate_binary(self) -> None:
        parts = self._command_parts()
        executable = parts[0]
        if os.path.sep in executable:
            if not os.path.exists(executable):
                raise BackendUnavailableError(f"GNUbg bridge executable not found: {executable}")
            return

        if shutil.which(executable) is None:
            raise BackendUnavailableError(f"GNUbg bridge executable not found in PATH: {executable}")

    def analyze_move(self, request: AnalyzeMoveRequest) -> AnalyzeMoveResponse:
        self._validate_binary()
        parts = self._command_parts()

        try:
            proc = subprocess.run(
                parts,
                input=request.model_dump_json(),
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise BackendUnavailableError(
                f"GNUbg bridge timed out after {self.timeout_seconds:.1f}s"
            ) from exc
        except OSError as exc:
            raise BackendUnavailableError(f"GNUbg bridge invocation failed: {exc}") from exc

        if proc.returncode != 0:
            stderr = proc.stderr.strip() or "unknown bridge error"
            raise BackendUnavailableError(f"GNUbg bridge failed: {stderr}")

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise BackendUnavailableError("GNUbg bridge returned invalid JSON") from exc

        equities = payload.get("equities")
        reasons = payload.get("reasons")

        if not isinstance(equities, dict):
            raise BackendUnavailableError("GNUbg bridge payload must include an 'equities' object")

        normalized_equities: dict[str, float] = {}
        for key, value in equities.items():
            try:
                normalized_equities[str(key)] = float(value)
            except (TypeError, ValueError) as exc:
                raise BackendUnavailableError(f"invalid equity for move '{key}'") from exc

        normalized_reasons: dict[str, list[str]] = {}
        if isinstance(reasons, dict):
            for key, value in reasons.items():
                if isinstance(value, list):
                    normalized_reasons[str(key)] = [str(item) for item in value]

        return analyze_with_explicit_equities(
            request=request,
            move_equities=normalized_equities,
            move_reasons=normalized_reasons,
        )

    def details(self) -> str:
        return f"External GNUbg bridge command: {self.bridge_cmd}"


@dataclass
class BackendRuntime:
    backend: AnalyzerBackend
    configured: str
    fallback_active: bool
    details: str
    fallback_backend: AnalyzerBackend | None = None

    def analyze_move(self, request: AnalyzeMoveRequest) -> AnalyzeMoveResponse:
        try:
            return self.backend.analyze_move(request)
        except BackendUnavailableError:
            if self.fallback_backend is None:
                raise
            return self.fallback_backend.analyze_move(request)


def load_backend() -> BackendRuntime:
    configured = os.getenv("GAMMONDATOR_ANALYZER", "heuristic").strip().lower()
    fallback_enabled = os.getenv("GAMMONDATOR_FALLBACK_TO_HEURISTIC", "1") != "0"

    if configured == "heuristic":
        backend = HeuristicBackend()
        return BackendRuntime(
            backend=backend,
            configured=configured,
            fallback_active=False,
            details=backend.details(),
            fallback_backend=None,
        )

    if configured == "gnubg":
        bridge_cmd = os.getenv("GAMMONDATOR_GNUBG_BRIDGE_CMD", "gnubg-bridge")
        timeout_seconds = float(os.getenv("GAMMONDATOR_GNUBG_TIMEOUT", "15"))
        gnubg_backend = GnuBGBridgeBackend(bridge_cmd=bridge_cmd, timeout_seconds=timeout_seconds)
        heuristic_fallback = HeuristicBackend() if fallback_enabled else None

        try:
            gnubg_backend._validate_binary()
            return BackendRuntime(
                backend=gnubg_backend,
                configured=configured,
                fallback_active=False,
                details=f"{gnubg_backend.details()} timeout={timeout_seconds}s",
                fallback_backend=heuristic_fallback,
            )
        except BackendUnavailableError as exc:
            if not fallback_enabled:
                raise

            return BackendRuntime(
                backend=heuristic_fallback or HeuristicBackend(),
                configured=configured,
                fallback_active=True,
                details=(
                    "Built-in heuristic evaluator. "
                    f"Requested gnubg backend unavailable: {exc}"
                ),
                fallback_backend=None,
            )

    raise BackendUnavailableError(
        f"unsupported GAMMONDATOR_ANALYZER '{configured}', expected 'heuristic' or 'gnubg'"
    )
