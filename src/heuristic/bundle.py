"""Canonical candidate source bundles and path-security checks."""

from __future__ import annotations
import hashlib
import json
import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

_ALLOWED = ("main.cpp", "include/", "src/")
_HEADER_SUFFIXES = {".h", ".hh", ".hpp", ".hxx"}
_SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx"}


def _clean_path(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("candidate paths must be non-empty POSIX paths")
    original = name
    name = posixpath.normpath(name)
    if (
        name == "."
        or name.startswith("../")
        or name.startswith("/")
        or "/../" in f"/{name}"
    ):
        raise ValueError(f"unsafe candidate path: {name!r}")
    if name != original:
        raise ValueError(f"candidate path is not normalized: {original!r}")
    if any(part in {"", "."} for part in name.split("/")):
        raise ValueError(f"non-canonical candidate path: {name!r}")
    if name != "main.cpp" and not any(
        name.startswith(prefix) for prefix in _ALLOWED[1:]
    ):
        raise ValueError(f"undeclared candidate path: {name!r}")
    suffix = Path(name).suffix.lower()
    if name.startswith("include/") and suffix not in _HEADER_SUFFIXES:
        raise ValueError(f"candidate include is not a C++ header: {name!r}")
    if name.startswith("src/") and suffix not in _SOURCE_SUFFIXES:
        raise ValueError(f"candidate source is not a C/C++ source file: {name!r}")
    return name


@dataclass(frozen=True)
class CandidateBundleV1:
    files: Mapping[str, str]

    def __post_init__(self) -> None:
        normalized: dict[str, str] = {}
        for raw_name, raw_contents in self.files.items():
            name = _clean_path(raw_name)
            if not isinstance(raw_contents, str):
                raise ValueError("candidate files must be UTF-8 text")
            if "\x00" in raw_contents:
                raise ValueError(f"candidate file contains NUL bytes: {name}")
            normalized[name] = raw_contents.replace("\r\n", "\n").replace("\r", "\n")
        if "main.cpp" not in normalized:
            raise ValueError("candidate bundle must contain main.cpp")
        object.__setattr__(self, "files", dict(sorted(normalized.items())))

    def canonical_json(self) -> str:
        return json.dumps(
            {"version": 1, "files": self.files},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_json(cls, payload: str) -> "CandidateBundleV1":
        raw = json.loads(payload)
        if raw.get("version") != 1 or not isinstance(raw.get("files"), dict):
            raise ValueError("not a CandidateBundleV1 JSON payload")
        return cls(raw["files"])

    @classmethod
    def from_directory(cls, root: str | Path) -> "CandidateBundleV1":
        root = Path(root).resolve()
        files: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"candidate bundle may not contain symlinks: {path}")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            try:
                files[relative] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"candidate file is not UTF-8 text: {relative}"
                ) from exc
        return cls(files)

    def write(self, root) -> None:
        root = Path(root)
        for name, contents in self.files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents, encoding="utf-8", newline="\n")
