"""RELEASE-FIX-A3 Phase 5 -- hardened runtime asset-reference scanner.

The RELEASE-FIX-A2 scanner (tests/test_release_fix_a2_asset_closure.py's
scan_runtime_image_references) only matched string literals containing a
full "/assets/..." path. RELEASE-FIX-A3's live browser audit
(docs/incidents/2026-07-12-full-site-asset-outage.md, RELEASE-FIX-A3
addendum) found that a materially large share of real broken-image
requests come from patterns that scan invisibly to that literal-only regex:

  1. Query-string / fragment suffixes on an otherwise-static path
     (e.g. "/assets/shop/newbie_gift_pack.webp?v=1").
  2. A module-level "root" constant concatenated with a string literal
     (e.g. HERO_CHARACTER_ROOT + 'chibi_reference_normalized.webp', or the
     template-literal form `${HERO_ITEM_ROOT}unknown.svg`).
  3. A dict/object literal mapping bare keys to bare filenames, combined
     with a literal root at the point of use
     (e.g. CHARACTER_ART = {apprentice: 'chibi_apprentice_normalized.webp', ...}
     then '/assets/hero/characters/' + CHARACTER_ART[key]).

None of these are optional to resolve -- they are exactly the class of
reference that was invisible to the original scan and caused real 404s
in production. This module resolves what is statically resolvable and
explicitly reports what is not, rather than silently dropping it.

A fourth class is genuinely NOT resolvable by static analysis: a root
concatenated with a value that only exists at runtime (a database field,
an API response), e.g. messages.html's:
    root + value + '.webp'   where value = data[field]
This module reports these as unresolved_dynamic_references with their
source location, per the incident task's explicit requirement to warn
rather than ignore.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXTENSIONS = ("png", "jpe?g", "webp", "gif", "ico", "svg", "avif")
_EXT_ALTERNATION = "|".join(IMAGE_EXTENSIONS)

# A full static string literal containing an asset path, optionally with a
# query string and/or fragment (RELEASE-FIX-A2's original pattern lacked
# the trailing "(?:\?[^'\"#]*)?(?:#[^'\"]*)?").
LITERAL_PATH_PATTERN = re.compile(
    r"""["'(](/[a-zA-Z0-9_./-]+\.(?:%s))(?:\?[^'"#)]*)?(?:#[^'")]*)?["')]"""
    % _EXT_ALTERNATION
)

# const NAME_ROOT = '/assets/...'   (also `let`/`var`)
ROOT_CONST_PATTERN = re.compile(
    r"""(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*['"](/assets/[^'"]*/)['"]"""
)

# NAME_ROOT + 'literal.ext'  (string-literal concatenation)
ROOT_PLUS_LITERAL_PATTERN = re.compile(
    r"""([A-Za-z_][A-Za-z0-9_]*)\s*\+\s*['"]([a-zA-Z0-9_.-]+\.(?:%s))['"]""" % _EXT_ALTERNATION
)

# `${NAME_ROOT}literal.ext`  (template-literal form of the same thing)
TEMPLATE_ROOT_LITERAL_PATTERN = re.compile(
    r"""\$\{([A-Za-z_][A-Za-z0-9_]*)\}([a-zA-Z0-9_.-]+\.(?:%s))""" % _EXT_ALTERNATION
)

# `${NAME_ROOT}${<non-literal expr>}literal.ext` or trailing without a
# literal suffix -- template interpolation whose inner expression is not a
# string literal is NOT statically resolvable.
TEMPLATE_ROOT_DYNAMIC_PATTERN = re.compile(
    r"""\$\{([A-Za-z_][A-Za-z0-9_]*)\}\$\{([^}]+)\}"""
)

# 'literal/root/' + <bareIdentifierOrExpr>  where the identifier is not a
# string literal (handled separately above) -- e.g. `root + value + '.webp'`.
# We look for ROOT-like identifiers (already known from ROOT_CONST_PATTERN
# or ending in a literal '/assets/.../' string) immediately followed by
# `+ <identifier-or-property-access>` that is NOT a quoted string literal.
DYNAMIC_ROOT_CONCAT_PATTERN = re.compile(
    r"""([A-Za-z_][A-Za-z0-9_]*)\s*\+\s*([A-Za-z_][A-Za-z0-9_.\[\]'"]*)\s*\+\s*['"]\.([a-zA-Z0-9]+)['"]"""
)

# Simple single-level object literal: NAME = {key: 'bare-filename.ext', ...}
# Deliberately conservative -- only matches when every value looks like a
# bare filename literal (no '/', ends in a known image extension), so it
# does not misfire on unrelated dict literals.
DICT_LITERAL_PATTERN = re.compile(
    r"""(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{([^{}]*)\}"""
)
DICT_ENTRY_PATTERN = re.compile(
    r"""([A-Za-z_][A-Za-z0-9_]*)\s*:\s*['"]([a-zA-Z0-9_.-]+\.(?:%s))['"]""" % _EXT_ALTERNATION
)

# root literal immediately preceding a '+' used at the point of use, e.g.
# '/assets/hero/characters/' + CHARACTER_ART[key]
LITERAL_ROOT_PLUS_IDENT_PATTERN = re.compile(
    r"""['"](/assets/[^'"]*/)['"]\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)"""
)

SCAN_GLOBS = ("*.html", "blog/*.html", "*.js", "*.css")


@dataclass
class ScanResult:
    resolved_paths: set = field(default_factory=set)
    unresolved_dynamic_references: list = field(default_factory=list)


def strip_query_and_fragment(path: str) -> str:
    """Normalize a referenced path by dropping any query string / fragment."""
    return path.split("?", 1)[0].split("#", 1)[0]


def _find_root_constants(text: str) -> dict:
    return {name: root for name, root in ROOT_CONST_PATTERN.findall(text)}


def _find_dict_literals(text: str) -> dict:
    """Return {dict_name: {key: bare_filename}} for simple flat object
    literals whose values are all bare image-filename string literals."""
    dicts = {}
    for name, body in DICT_LITERAL_PATTERN.findall(text):
        entries = DICT_ENTRY_PATTERN.findall(body)
        if not entries:
            continue
        dicts[name] = {key: filename for key, filename in entries}
    return dicts


def scan_text(text: str, source_label: str = "<text>") -> ScanResult:
    """Scan one file's source text for image references, resolving root
    constants, template literals, and dict-literal concatenations, and
    reporting any concatenation that depends on a genuinely runtime value.
    """
    result = ScanResult()

    # Class 1: direct string-literal paths (with optional query/fragment).
    for match in LITERAL_PATH_PATTERN.finditer(text):
        result.resolved_paths.add(strip_query_and_fragment(match.group(1)))

    roots = _find_root_constants(text)
    dicts = _find_dict_literals(text)

    # Class 2: ROOT_NAME + 'literal.ext'  /  `${ROOT_NAME}literal.ext`
    for root_name, filename in ROOT_PLUS_LITERAL_PATTERN.findall(text):
        root = roots.get(root_name)
        if root:
            result.resolved_paths.add(root + filename)
    for root_name, filename in TEMPLATE_ROOT_LITERAL_PATTERN.findall(text):
        root = roots.get(root_name)
        if root:
            result.resolved_paths.add(root + filename)

    # Class 3: literal root + dict-lookup identifier, e.g.
    # '/assets/hero/characters/' + CHARACTER_ART[key]  (or .apprentice)
    for root, ident in LITERAL_ROOT_PLUS_IDENT_PATTERN.findall(text):
        dict_values = dicts.get(ident)
        if dict_values:
            for filename in dict_values.values():
                result.resolved_paths.add(root + filename)

    # Also resolve ROOT_NAME (constant) + dict-lookup identifier, symmetric
    # to the literal-root form above.
    root_plus_ident_pattern = re.compile(
        r"""([A-Za-z_][A-Za-z0-9_]*)\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)(?:\[|\.)"""
    )
    for root_name, ident in root_plus_ident_pattern.findall(text):
        root = roots.get(root_name)
        dict_values = dicts.get(ident)
        if root and dict_values:
            for filename in dict_values.values():
                result.resolved_paths.add(root + filename)

    # Class 4: template literal with a non-literal inner expression --
    # `${ROOT}${expr}` where expr is not a string literal is unresolved
    # UNLESS expr is itself a bare filename-producing dict/property that we
    # cannot prove resolves to a fixed set -- treat conservatively as
    # unresolved and report it.
    for root_name, inner_expr in TEMPLATE_ROOT_DYNAMIC_PATTERN.findall(text):
        if root_name in roots:
            result.unresolved_dynamic_references.append({
                "source": source_label,
                "pattern": f"${{{root_name}}}${{{inner_expr}}}",
                "reason": (
                    "template-literal interpolation depends on a non-literal "
                    "expression that cannot be resolved by static analysis"
                ),
            })

    # Class 5: root + <runtime-identifier> + '.ext'  (e.g. root+value+'.webp'
    # where value comes from runtime data, not a known dict literal).
    for root_name, ident_expr, ext in DYNAMIC_ROOT_CONCAT_PATTERN.findall(text):
        base_ident = re.split(r"[.\[]", ident_expr, 1)[0]
        if base_ident in dicts:
            # Already resolved via the dict-literal path above.
            continue
        if root_name in roots or root_name.endswith("root") or root_name.endswith("Root"):
            result.unresolved_dynamic_references.append({
                "source": source_label,
                "pattern": f"{root_name}+{ident_expr}+'.{ext}'",
                "reason": (
                    "concatenation depends on a runtime-only value (not a "
                    "string literal, not a known dict literal) -- cannot be "
                    "statically resolved to a fixed path"
                ),
            })

    # Class 6 (catch-all): any line that mentions a known root constant next
    # to a '+' concatenation operator, that wasn't already fully resolved
    # above, is flagged rather than silently dropped -- e.g. a root combined
    # with a property-access expression pulled from a data array
    # (`(item.root || HERO_GEAR_ROOT) + (variant || item.art)`), which is too
    # structurally varied for the concatenation patterns above to resolve.
    already_flagged_lines = {ref["pattern"] for ref in result.unresolved_dynamic_references}
    for line in text.splitlines():
        if "+" not in line:
            continue
        line_stripped = line.strip()
        for root_name in roots:
            if root_name not in line:
                continue
            already_resolved_here = (
                bool(ROOT_PLUS_LITERAL_PATTERN.search(line))
                or bool(TEMPLATE_ROOT_LITERAL_PATTERN.search(line))
                or bool(LITERAL_ROOT_PLUS_IDENT_PATTERN.search(line))
            )
            if already_resolved_here:
                continue
            if not re.search(r"\.(?:%s)\b" % _EXT_ALTERNATION, line) and root_name not in line:
                continue
            if line_stripped not in already_flagged_lines:
                result.unresolved_dynamic_references.append({
                    "source": source_label,
                    "pattern": line_stripped,
                    "reason": (
                        f"line references root constant '{root_name}' in a "
                        "concatenation/property-access shape too structurally "
                        "varied to statically resolve to a fixed set of paths"
                    ),
                })
                already_flagged_lines.add(line_stripped)

    return result


def scan_paths(paths) -> ScanResult:
    combined = ScanResult()
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        partial = scan_text(text, source_label=str(path))
        combined.resolved_paths |= partial.resolved_paths
        combined.unresolved_dynamic_references.extend(partial.unresolved_dynamic_references)
    return combined


def scan_repo(repo_root: Path) -> ScanResult:
    paths = []
    for pattern in SCAN_GLOBS:
        paths.extend(repo_root.glob(pattern))
        paths.extend(repo_root.glob("**/" + pattern))
    paths = sorted(set(p for p in paths if "node_modules" not in p.parts))
    return scan_paths(paths)
