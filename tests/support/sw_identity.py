"""Derived assertions for the checked-in static runtime identity family."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from tests.support.repo_root import find_repo_root


DEFAULT_CACHE_TAG_PATHS = (
    "i18n.js",
    "css/e9/immersive_rpg.css",
    "js/e9/feature_flags.js",
    "js/e9/right_cards.js",
    "js/e9/world_stage.js",
)

_SW_VERSION_RE = re.compile(
    r"(?m)^[ \t]*const VERSION\s*=\s*'([^']+)';[ \t]*$"
)
_SW_ASSET_IDENTITY_RE = re.compile(
    r"(?m)^[ \t]*const ASSET_IDENTITY\s*=\s*'([^']+)';[ \t]*$"
)
_ASSET_VERSION_RE = re.compile(
    r"(?m)^[ \t]*var ASSET_VERSION\s*=\s*'([^']+)';[ \t]*$"
)
_SW_VERSION_VALUE_RE = re.compile(r"v\d+-[a-z0-9]+(?:-[a-z0-9]+)*$")
_ASSET_IDENTITY_VALUE_RE = re.compile(r"source-[a-z0-9]+(?:-[a-z0-9]+)*$")
_ASSET_VERSION_VALUE_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*$")
_CACHE_TAG_VALUE_RE = re.compile(r"\d{8}[a-z0-9]+$")


@dataclass(frozen=True)
class StaticRuntimeIdentity:
    """All checked-in static identity values derived from one checkout."""

    sw_version: str
    sw_asset_identity: str
    asset_version: str
    cache_tags: dict[str, str]


def _checkout_root(root: Path | str | None = None) -> Path:
    return find_repo_root(root or __file__)


def _read_unique(path: Path, pattern: re.Pattern[str], label: str) -> str:
    source = path.read_text(encoding="utf-8")
    matches = pattern.findall(source)
    if len(matches) != 1:
        raise AssertionError(
            f"expected exactly one active {label} declaration in {path}, found {len(matches)}"
        )
    return matches[0]


def read_active_sw_identity(
    root: Path | str | None = None,
) -> tuple[str, str]:
    """Return the executable sw.js VERSION and ASSET_IDENTITY declarations."""

    checkout = _checkout_root(root)
    sw_path = checkout / "sw.js"
    return (
        _read_unique(sw_path, _SW_VERSION_RE, "SW VERSION"),
        _read_unique(sw_path, _SW_ASSET_IDENTITY_RE, "SW ASSET_IDENTITY"),
    )


def read_asset_version(root: Path | str | None = None) -> str:
    """Return the executable feature_flags.js ASSET_VERSION declaration."""

    checkout = _checkout_root(root)
    return _read_unique(
        checkout / "js" / "e9" / "feature_flags.js",
        _ASSET_VERSION_RE,
        "ASSET_VERSION",
    )


def read_cache_tag_group(
    root: Path | str | None = None,
    paths: Iterable[str] = DEFAULT_CACHE_TAG_PATHS,
) -> dict[str, str]:
    """Return one cache-buster token for each named static runtime resource."""

    checkout = _checkout_root(root)
    index = (checkout / "index.html").read_text(encoding="utf-8")
    tags: dict[str, str] = {}
    for path in paths:
        escaped_path = re.escape(path)
        matches = re.findall(
            rf"(?:src|href)=\"/{escaped_path}\?v=([^\"']+)\"",
            index,
        )
        if len(matches) != 1:
            raise AssertionError(
                f"expected exactly one cache-busted reference for /{path}, found {len(matches)}"
            )
        tags[path] = matches[0]
    return tags


def read_cache_tag(root: Path | str | None, path: str) -> str:
    """Return the derived cache-buster token for one static resource."""

    return read_cache_tag_group(root, paths=(path,))[path]


def read_static_runtime_identity(
    root: Path | str | None = None,
) -> StaticRuntimeIdentity:
    """Derive the complete static runtime identity family from one checkout."""

    sw_version, sw_asset_identity = read_active_sw_identity(root)
    return StaticRuntimeIdentity(
        sw_version=sw_version,
        sw_asset_identity=sw_asset_identity,
        asset_version=read_asset_version(root),
        cache_tags=read_cache_tag_group(root),
    )


def assert_static_runtime_identity_well_formed(
    identity: StaticRuntimeIdentity | None = None,
    root: Path | str | None = None,
) -> StaticRuntimeIdentity:
    """Validate shape while leaving forward values owned by the checkout."""

    identity = identity or read_static_runtime_identity(root)
    checkout = _checkout_root(root)
    sw_source = (checkout / "sw.js").read_text(encoding="utf-8")
    assert _SW_VERSION_VALUE_RE.fullmatch(identity.sw_version), identity.sw_version
    assert _ASSET_IDENTITY_VALUE_RE.fullmatch(
        identity.sw_asset_identity
    ), identity.sw_asset_identity
    assert _ASSET_VERSION_VALUE_RE.fullmatch(identity.asset_version), identity.asset_version
    assert re.search(
        r"(?m)^const SHELL_CACHE\s*=\s*`cg-shell-\$\{VERSION\}-\$\{ASSET_IDENTITY\}`;[ \t]*$",
        sw_source,
    )
    assert re.search(
        r"(?m)^const IMG_CACHE\s*=\s*`cg-img-\$\{VERSION\}-\$\{ASSET_IDENTITY\}`;[ \t]*$",
        sw_source,
    )
    assert_static_cache_tag_group_well_formed(identity.cache_tags)
    return identity


def assert_static_cache_tag_group_well_formed(
    tags: dict[str, str],
) -> dict[str, str]:
    """Validate a derived group without freezing it to a historical token."""

    assert tags, tags
    for path, tag in tags.items():
        assert _CACHE_TAG_VALUE_RE.fullmatch(tag), (path, tag)
    return tags
