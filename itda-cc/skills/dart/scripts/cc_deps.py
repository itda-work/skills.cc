"""cc_deps — itda-cc 스킬의 pip 의존성 확보. uv 가 있으면 격리 실행, 없으면 pip 안내 (Claude Code 전용).

스크립트 진입점이 의존 모듈을 import 하기 **전에** :func:`ensure` 를 부른다.

- 모듈이 다 있으면 아무것도 하지 않는다.
- 없고 ``uv`` 가 PATH 에 있으면 같은 인터프리터(``sys.executable``)를 기준으로
  ``uv run --no-project --with-requirements <requirements.txt>`` 로 **자기 자신을 다시 실행**하고 그 종료 코드로 끝난다.
  uv 는 실행마다 캐시(``uv cache dir``) 아래 임시 환경을 만들고 지운다 — 사용자 Python 의 site-packages 를 건드리지 않으므로
  PEP 668(관리형 Python)·쓰기 권한 벽을 만나지 않는다. 받은 패키지는 uv 캐시에 남아 다음 실행부터 재사용된다.
- uv 도 없으면 설치 명령(이 인터프리터에 맞는 pip 옵션 · uv 설치)을 담은 오류를 내고 끝난다. 사용자 환경을 스스로 바꾸지 않는다.

SKILL.md 명령은 ``python3 "$SKILL_DIR/scripts/x.py"`` 하나로 둔다 — 두 경로는 이 모듈 안에서만 갈린다.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Iterable, Sequence

# 다시 실행한 자식 프로세스 표시 — uv 환경에서도 모듈이 없으면 또 다시 실행하지 않고 멈춘다(무한 반복 방지)
_REEXEC_MARK = "CC_DEPS_UV_REEXEC"
EXIT_DEPS = 1


def missing_modules(modules: Iterable[str]) -> list[str]:
    out = []
    for m in modules:
        try:
            found = importlib.util.find_spec(m) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            out.append(m)
    return out


def uv_command(uv: str, requirements: Path, script: Path, argv: Sequence[str]) -> list[str]:
    """같은 인터프리터 기준 uv 격리 실행 명령. 환경 안의 ``python`` 이 그 인터프리터의 임시 venv 다."""
    return [uv, "run", "--quiet", "--no-project", "--python", sys.executable,
            "--with-requirements", str(requirements), "--", "python", str(script), *argv]


def pip_flags() -> str:
    """이 인터프리터에 맞는 pip 옵션(python-runtime 규칙 — 판정 축은 site-packages 쓰기 가능성).

    venv 안이면 없음 · PEP 668 관리형이면 ``--user --break-system-packages``(둘은 늘 함께) · 쓰기 불가면 ``--user`` · 쓸 수 있으면 없음.
    """
    if sys.prefix != sys.base_prefix:
        return ""
    if (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").exists():
        return "--user --break-system-packages"
    purelib = sysconfig.get_path("purelib")
    if not (purelib and os.access(purelib, os.W_OK)):
        return "--user"
    return ""


def python_command() -> str:
    """사용자에게 보여 줄 Python 명령 — Windows 는 ``py -3``, 없으면 ``python`` (``python3`` 는 대개 Store 별칭). 그 밖은 ``python3``."""
    if sys.platform == "win32":
        return "py -3" if shutil.which("py") else "python"
    return "python3"


def install_hints(requirements: Path) -> list[str]:
    py = python_command()
    flags = pip_flags()
    return [
        f'{py} -m pip install {flags + " " if flags else ""}-r "{requirements}"',
        "uv 설치(권장): https://docs.astral.sh/uv/getting-started/installation/ — 설치 뒤에는 의존성을 스크립트가 알아서 받는다",
    ]


def _fail(payload: dict, message: str) -> None:
    print(message, file=sys.stderr)
    print(json.dumps({"status": "error", **payload}, ensure_ascii=False))
    raise SystemExit(EXIT_DEPS)


def ensure(modules: Sequence[str], requirements: Path, *, script: Path | None = None,
           argv: Sequence[str] | None = None) -> None:
    """``modules`` 가 import 가능하게 한다. 이미 되면 반환, 아니면 uv 로 다시 실행하거나 안내를 내고 끝난다."""
    missing = missing_modules(modules)
    if not missing:
        return
    for stream in (sys.stdout, sys.stderr):  # 한국어 안내가 cp949 콘솔에서 죽지 않게
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass
    requirements = Path(requirements).resolve()
    if os.environ.get(_REEXEC_MARK) == "1":
        _fail({"error": "deps_missing", "missing": missing, "via": "uv", "install": install_hints(requirements)},
              f"오류: uv 로 받은 환경에서도 {', '.join(missing)} 를 찾지 못했습니다 — {requirements} 를 확인하세요")
    uv = shutil.which("uv")
    if not uv:
        _fail({"error": "deps_missing", "missing": missing, "via": "none", "install": install_hints(requirements)},
              f"오류: 필요한 패키지({', '.join(missing)})가 없고 uv 도 없습니다 — 아래 명령 중 하나로 설치한 뒤 다시 실행하세요:\n"
              + "\n".join(f"  {h}" for h in install_hints(requirements)))
    script = Path(script or sys.modules["__main__"].__file__).resolve()
    argv = list(sys.argv[1:] if argv is None else argv)
    env = dict(os.environ, **{_REEXEC_MARK: "1"})
    print(f"(필요한 패키지 {', '.join(missing)} 를 uv 격리 환경으로 받아 실행합니다)", file=sys.stderr)
    try:
        rc = subprocess.run(uv_command(uv, requirements, script, argv), env=env).returncode
    except OSError as exc:
        _fail({"error": "deps_missing", "missing": missing, "via": "uv", "install": install_hints(requirements)},
              f"오류: uv 를 실행하지 못했습니다({exc})")
    raise SystemExit(rc)
