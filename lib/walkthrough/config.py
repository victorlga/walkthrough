from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

SKILL_DIR = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def npm_global_root() -> str:
    npm = shutil.which("npm")
    if not npm:
        return ""
    result = subprocess.run([npm, "root", "-g"], capture_output=True, text=True)
    return result.stdout.strip()


@lru_cache(maxsize=None)
def output_contains(command: tuple, expect: str) -> bool:
    try:
        result = subprocess.run(list(command), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return expect in result.stdout + result.stderr


def expand_placeholders(value):
    if isinstance(value, dict):
        return {key: expand_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_placeholders(item) for item in value]
    if isinstance(value, str) and "${npmGlobalRoot}" in value:
        return value.replace("${npmGlobalRoot}", npm_global_root())
    return value


@dataclass(frozen=True)
class Language:
    name: str
    extensions: tuple
    root_markers: tuple
    command: tuple
    install: str
    language_ids: dict
    identifier_pattern: str
    implementation_pattern: Optional[str]
    initialization_options: Optional[dict]
    check_command: Optional[tuple] = None
    check_expect: Optional[str] = None
    open_mentions: bool = False

    def installed(self) -> bool:
        if shutil.which(self.command[0]) is None:
            return False
        if not self.check_command:
            return True
        return output_contains(self.check_command, self.check_expect or "")

    def resolved_initialization_options(self) -> Optional[dict]:
        if self.initialization_options is None:
            return None
        return expand_placeholders(self.initialization_options)


@dataclass(frozen=True)
class Config:
    languages: dict
    test_patterns: tuple
    generated_patterns: tuple

    def language_for(self, path: str) -> Optional[Language]:
        suffix = Path(path).suffix
        for language in self.languages.values():
            if suffix in language.extensions:
                return language
        return None

    def language_id(self, path: str) -> str:
        language = self.language_for(path)
        if language is None:
            return "plaintext"
        return language.language_ids.get(Path(path).suffix, language.name)

    def is_test(self, path: str) -> bool:
        return any(pattern.search(path) for pattern in self.test_patterns)

    def is_generated(self, path: str) -> bool:
        return any(pattern.search(path) for pattern in self.generated_patterns)


def load_config(path: Optional[Path] = None) -> Config:
    raw = json.loads((path or SKILL_DIR / "languages.json").read_text())
    languages = {}
    for name, entry in raw["languages"].items():
        languages[name] = Language(
            name=name,
            extensions=tuple(entry["extensions"]),
            root_markers=tuple(entry["rootMarkers"]),
            command=tuple(entry["command"]),
            install=entry["install"],
            language_ids=dict(entry.get("languageIds", {})),
            identifier_pattern=entry["identifierPattern"],
            implementation_pattern=entry.get("implementationPattern"),
            initialization_options=entry.get("initializationOptions"),
            check_command=tuple(entry["check"]["command"]) if "check" in entry else None,
            check_expect=entry["check"]["expect"] if "check" in entry else None,
            open_mentions=bool(entry.get("openMentions", False)),
        )
    return Config(
        languages=languages,
        test_patterns=tuple(re.compile(p) for p in raw["testPathPatterns"]),
        generated_patterns=tuple(re.compile(p) for p in raw["generatedPathPatterns"]),
    )
