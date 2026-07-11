"""Read-only SGF inventory and known quality issue detection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

from sgf_engine.core.coord_utils import sgf_to_xy
from sgf_engine.core.tree import SGFNode
from sgf_engine.parser.sgf_parser import parse_sgf


BOARD_SIZE = 19
BOARD_LETTERS = "ABCDEFGHJKLMNOPQRST"
PASS_COORDS = {"", "tt"}
LOCAL_PADDING = 2
FAR_DISTANCE = 8
LOCAL_PROBLEM_PATH_HINTS = (
    "死活",
    "做活",
    "殺棋",
    "杀棋",
    "手筋",
    "對殺",
    "对杀",
    "眼形",
    "活棋",
    "life-and-death",
    "life_and_death",
    "tesuji",
)


@dataclass(frozen=True, slots=True)
class SGFInventoryItem:
    source_path: str
    filename: str
    sha256: str
    parse_status: str
    root_children_count: int = 0
    root_child_moves: tuple[str, ...] = ()
    root_child_moves_go_coords: tuple[str, ...] = ()
    first_player_color_candidates: tuple[str, ...] = ()
    has_variations: bool = False
    quality_flags: tuple[str, ...] = ()
    quality_reasons: tuple[str, ...] = ()
    total_nodes: int = 0
    max_depth: int = 0
    terminal_count: int = 0
    has_comments: bool = False
    has_pass_moves: bool = False
    setup_stone_count: int = 0
    setup_bounding_box: dict[str, object] | None = None
    answer_distance_from_setup: int | None = None
    auto_reply_pattern_candidates: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def sgf_coord_to_go_coord(coord: str) -> str:
    """Convert a 19x19 SGF coordinate to normal board notation."""
    x, y = sgf_to_xy(coord)
    return f"{BOARD_LETTERS[x]}{BOARD_SIZE - y}"


def scan_sgf_file(path: str | Path) -> SGFInventoryItem:
    """Read one SGF file and return an owner-reviewable inventory item."""
    sgf_path = Path(path)
    raw = sgf_path.read_bytes()
    digest = sha256(raw).hexdigest().upper()
    source_path = sgf_path.as_posix()

    try:
        text = _decode_sgf(raw)
        root = parse_sgf(text)
        item = _build_item_from_root(root, source_path, sgf_path.name, digest)
        return detect_sgf_quality_flags(item)
    except Exception as error:  # noqa: BLE001 - inventory records parse failures.
        return SGFInventoryItem(
            source_path=source_path,
            filename=sgf_path.name,
            sha256=digest,
            parse_status=f"PARSE_ERROR: {error}",
            quality_flags=("PARSE_ERROR",),
            quality_reasons=(str(error),),
        )


def scan_sgf_tree(root_dir: str | Path) -> tuple[SGFInventoryItem, ...]:
    """Scan all ``*.sgf`` files below ``root_dir`` without modifying them."""
    root = Path(root_dir)
    return tuple(scan_sgf_file(path) for path in sorted(root.rglob("*.sgf")))


def build_sgf_inventory(root_dir: str | Path) -> dict[str, object]:
    items = scan_sgf_tree(root_dir)
    return {
        "schema_version": 1,
        "scope": Path(root_dir).as_posix(),
        "items": [item.to_dict() for item in items],
        "summary": _summary(items),
    }


def detect_sgf_quality_flags(inventory_item: SGFInventoryItem) -> SGFInventoryItem:
    """Attach read-only known quality issue flags to one inventory item."""
    flags = list(inventory_item.quality_flags)
    reasons = list(inventory_item.quality_reasons)

    def add(flag: str, reason: str) -> None:
        if flag not in flags:
            flags.append(flag)
            reasons.append(reason)

    if inventory_item.parse_status != "ok":
        add("PARSE_ERROR", inventory_item.parse_status)
        return _replace_flags(inventory_item, flags, reasons)

    if inventory_item.total_nodes == 0:
        add("EMPTY_GAME_TREE", "SGF parsed with no move or metadata nodes.")
    if inventory_item.root_children_count == 0:
        add("NO_ROOT_CHILDREN", "SGF root has no child node.")
    if not inventory_item.root_child_moves:
        add("NO_ANSWER_BRANCH", "SGF root has no B[] or W[] answer branch.")
    if inventory_item.setup_stone_count and not inventory_item.root_child_moves:
        add("SETUP_ONLY_NO_SOLUTION", "SGF has AB/AW setup stones but no answer branch.")
    if inventory_item.root_children_count > 1:
        add("MULTIPLE_ROOT_CHILDREN", "SGF root has multiple direct child nodes.")
    if inventory_item.has_variations:
        add("HAS_VARIATIONS", "SGF contains at least one branching node.")
    if inventory_item.max_depth <= 1 and inventory_item.root_child_moves:
        add("TERMINAL_TOO_SHALLOW", "SGF answer line ends at or near the first move.")
    if inventory_item.auto_reply_pattern_candidates:
        add(
            "POSSIBLE_AUTO_REPLY_PATTERN",
            "A root answer has a single opponent child that may be an auto-reply.",
        )

    first_move = _first_root_move(inventory_item)
    if first_move is not None:
        move_text, coord = first_move
        if _is_edge_line(coord):
            add(
                "ANSWER_ON_EDGE_LINE",
                f"root answer {move_text} / {sgf_coord_to_go_coord(coord)} is on board edge.",
            )
        if inventory_item.answer_distance_from_setup is not None:
            distance = inventory_item.answer_distance_from_setup
            if distance >= FAR_DISTANCE:
                add(
                    "ANSWER_FAR_FROM_SETUP_STONES",
                    f"root answer {move_text} / {sgf_coord_to_go_coord(coord)} is {distance} lines from setup stones.",
                )
        if (
            inventory_item.setup_bounding_box
            and not _coord_inside_padded_box(coord, inventory_item.setup_bounding_box)
        ):
            add(
                "ANSWER_OUTSIDE_LOCAL_REGION",
                f"root answer {move_text} / {sgf_coord_to_go_coord(coord)} is outside the padded setup region.",
            )
        if any(
            flag in flags
            for flag in (
                "ANSWER_ON_EDGE_LINE",
                "ANSWER_FAR_FROM_SETUP_STONES",
                "ANSWER_OUTSIDE_LOCAL_REGION",
            )
        ):
            add(
                "POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH",
                f"root answer {move_text} / {sgf_coord_to_go_coord(coord)} is a board crop review candidate.",
            )
        if _path_suggests_local_problem(inventory_item.source_path) and any(
            flag in flags
            for flag in ("ANSWER_FAR_FROM_SETUP_STONES", "ANSWER_OUTSIDE_LOCAL_REGION")
        ):
            add(
                "LIFE_AND_DEATH_CATEGORY_WITH_DISTANT_ANSWER",
                "path suggests life-and-death or tesuji content, but answer is distant from setup.",
            )
            add(
                "ANSWER_FAR_FROM_LOCAL_CLUSTER",
                f"root answer {move_text} / {sgf_coord_to_go_coord(coord)} is far from the local setup cluster.",
            )
            add(
                "ANSWER_OUTSIDE_PROBLEM_REGION",
                "root answer is outside the inferred local problem region.",
            )
            add(
                "POSSIBLE_GLOBAL_AI_TENUKI_ANSWER",
                "distant answer in local-problem path is a possible global AI tenuki candidate.",
            )

    return _replace_flags(inventory_item, flags, reasons)


def write_inventory_artifacts(
    root_dir: str | Path,
    markdown_path: str | Path,
    json_path: str | Path,
) -> dict[str, object]:
    inventory = build_sgf_inventory(root_dir)
    Path(json_path).write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    Path(markdown_path).write_text(_render_markdown_report(inventory), encoding="utf-8")
    return inventory


def _decode_sgf(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _build_item_from_root(
    root: SGFNode, source_path: str, filename: str, digest: str
) -> SGFInventoryItem:
    stats = _collect_stats(root)
    root_moves = tuple(_format_move(child) for child in root.children if child.move)
    root_go = tuple(
        f"{_format_move(child)} / {sgf_coord_to_go_coord(child.move.coord)}"
        for child in root.children
        if child.move
    )
    setup_coords = _setup_coords(root)
    first_move = next((child.move for child in root.children if child.move), None)
    bbox = _bounding_box(setup_coords)
    auto_replies = tuple(_auto_reply_candidates(root))
    distance = None
    if first_move is not None and setup_coords:
        distance = min(_manhattan(first_move.coord, coord) for coord in setup_coords)

    return SGFInventoryItem(
        source_path=source_path,
        filename=filename,
        sha256=digest,
        parse_status="ok",
        root_children_count=len(root.children),
        root_child_moves=root_moves,
        root_child_moves_go_coords=root_go,
        first_player_color_candidates=tuple(
            child.move.color for child in root.children if child.move
        ),
        has_variations=stats["has_variations"],
        total_nodes=stats["total_nodes"],
        max_depth=stats["max_depth"],
        terminal_count=stats["terminal_count"],
        has_comments=stats["has_comments"],
        has_pass_moves=stats["has_pass_moves"],
        setup_stone_count=len(setup_coords),
        setup_bounding_box=bbox,
        answer_distance_from_setup=distance,
        auto_reply_pattern_candidates=auto_replies,
    )


def _collect_stats(root: SGFNode) -> dict[str, object]:
    stats = {
        "total_nodes": 0,
        "max_depth": 0,
        "terminal_count": 0,
        "has_comments": False,
        "has_pass_moves": False,
        "has_variations": False,
    }

    def visit(node: SGFNode, depth: int) -> None:
        if node.move is not None or _has_meaningful_metadata(node):
            stats["total_nodes"] += 1
            stats["max_depth"] = max(stats["max_depth"], depth)
        if len(node.children) > 1:
            stats["has_variations"] = True
        if not node.children:
            stats["terminal_count"] += 1
        if node.metadata.get("comment") or "C" in node.metadata.get("properties", {}):
            stats["has_comments"] = True
        if node.metadata.get("pass"):
            stats["has_pass_moves"] = True
        for child in node.children:
            visit(child, depth + 1)

    visit(root, 0)
    return stats


def _has_meaningful_metadata(node: SGFNode) -> bool:
    properties = node.metadata.get("properties", {})
    return any(key != "properties" for key in node.metadata) or any(
        bool(values) for values in properties.values()
    )


def _setup_coords(root: SGFNode) -> tuple[str, ...]:
    properties = root.metadata.get("properties", {})
    coords: list[str] = []
    for prop in ("AB", "AW", "AE"):
        for coord in properties.get(prop, []):
            if coord not in PASS_COORDS:
                sgf_to_xy(coord)
                coords.append(coord)
    return tuple(coords)


def _format_move(node: SGFNode) -> str:
    if node.move is None:
        return ""
    return f"{node.move.color}[{node.move.coord}]"


def _first_root_move(item: SGFInventoryItem) -> tuple[str, str] | None:
    if not item.root_child_moves:
        return None
    text = item.root_child_moves[0]
    return text, text[2:4]


def _is_edge_line(coord: str) -> bool:
    x, y = sgf_to_xy(coord)
    return x in (0, 18) or y in (0, 18)


def _coord_inside_padded_box(coord: str, box: dict[str, object]) -> bool:
    x, y = sgf_to_xy(coord)
    return (
        int(box["min_x"]) - LOCAL_PADDING
        <= x
        <= int(box["max_x"]) + LOCAL_PADDING
        and int(box["min_y"]) - LOCAL_PADDING
        <= y
        <= int(box["max_y"]) + LOCAL_PADDING
    )


def _bounding_box(coords: tuple[str, ...]) -> dict[str, object] | None:
    if not coords:
        return None
    points = [sgf_to_xy(coord) for coord in coords]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
        "min_go": sgf_coord_to_go_coord(chr(ord("a") + min(xs)) + chr(ord("a") + min(ys))),
        "max_go": sgf_coord_to_go_coord(chr(ord("a") + max(xs)) + chr(ord("a") + max(ys))),
        "stone_count": len(coords),
    }


def _manhattan(left: str, right: str) -> int:
    lx, ly = sgf_to_xy(left)
    rx, ry = sgf_to_xy(right)
    return abs(lx - rx) + abs(ly - ry)


def _auto_reply_candidates(root: SGFNode) -> list[str]:
    candidates: list[str] = []
    for child in root.children:
        if child.move is None or len(child.children) != 1:
            continue
        reply = child.children[0]
        if reply.move is not None and reply.move.color != child.move.color:
            candidates.append(f"{_format_move(child)} -> {_format_move(reply)}")
    return candidates


def _path_suggests_local_problem(path: str) -> bool:
    lowered = path.lower()
    return any(hint in lowered for hint in LOCAL_PROBLEM_PATH_HINTS)


def _replace_flags(
    item: SGFInventoryItem, flags: list[str], reasons: list[str]
) -> SGFInventoryItem:
    data = item.to_dict()
    data["quality_flags"] = tuple(flags)
    data["quality_reasons"] = tuple(reasons)
    return SGFInventoryItem(**data)


def _summary(items: tuple[SGFInventoryItem, ...]) -> dict[str, int]:
    return {
        "total_sgf_files": len(items),
        "parse_success": sum(item.parse_status == "ok" for item in items),
        "parse_error": sum(item.parse_status != "ok" for item in items),
        "missing_answers": sum("NO_ANSWER_BRANCH" in item.quality_flags for item in items),
        "possible_board_crop_coordinate_mismatch": sum(
            "POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH" in item.quality_flags
            for item in items
        ),
        "possible_global_ai_tenuki": sum(
            "POSSIBLE_GLOBAL_AI_TENUKI_ANSWER" in item.quality_flags for item in items
        ),
        "multiple_root_children": sum(
            "MULTIPLE_ROOT_CHILDREN" in item.quality_flags for item in items
        ),
        "has_variations": sum("HAS_VARIATIONS" in item.quality_flags for item in items),
    }


def _render_markdown_report(inventory: dict[str, object]) -> str:
    items = [SGFInventoryItem(**item) for item in inventory["items"]]
    summary = inventory["summary"]

    def section(title: str, flags: tuple[str, ...]) -> list[str]:
        lines = [f"## {title}", ""]
        matches = [
            item for item in items if any(flag in item.quality_flags for flag in flags)
        ]
        if not matches:
            return lines + ["None detected.", ""]
        for item in matches:
            lines.extend(
                [
                    f"- `{item.source_path}`",
                    f"  - sha256: `{item.sha256}`",
                    f"  - parse_status: `{item.parse_status}`",
                    f"  - root_child_moves: {', '.join(item.root_child_moves) or 'none'}",
                    f"  - root_child_moves_go_coords: {', '.join(item.root_child_moves_go_coords) or 'none'}",
                    f"  - setup_bounding_box: `{item.setup_bounding_box}`",
                    f"  - quality_flags: {', '.join(item.quality_flags)}",
                    f"  - reason: {'; '.join(item.quality_reasons)}",
                ]
            )
        lines.append("")
        return lines

    lines = [
        "# SGF Inventory / Known Quality Issues Report",
        "",
        "## Scope",
        "",
        f"- Root scanned: `{inventory['scope']}`",
        "- This report is read-only and records owner-review candidates only.",
        "",
        "## Summary",
        "",
        f"- total SGF files: {summary['total_sgf_files']}",
        f"- parse success count: {summary['parse_success']}",
        f"- parse error count: {summary['parse_error']}",
        f"- missing answers count: {summary['missing_answers']}",
        "- possible board crop / coordinate mismatch count: "
        f"{summary['possible_board_crop_coordinate_mismatch']}",
        f"- possible global AI tenuki count: {summary['possible_global_ai_tenuki']}",
        f"- multiple root children count: {summary['multiple_root_children']}",
        f"- has variations count: {summary['has_variations']}",
        "",
    ]
    lines.extend(
        section(
            "Missing answers",
            ("NO_ANSWER_BRANCH", "SETUP_ONLY_NO_SOLUTION", "NO_ROOT_CHILDREN"),
        )
    )
    lines.extend(
        section(
            "Possible board crop / coordinate mismatch",
            (
                "ANSWER_ON_EDGE_LINE",
                "ANSWER_FAR_FROM_SETUP_STONES",
                "ANSWER_OUTSIDE_LOCAL_REGION",
                "POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH",
            ),
        )
    )
    lines.extend(
        section(
            "Possible global AI tenuki answers",
            (
                "POSSIBLE_GLOBAL_AI_TENUKI_ANSWER",
                "LIFE_AND_DEATH_CATEGORY_WITH_DISTANT_ANSWER",
                "ANSWER_FAR_FROM_LOCAL_CLUSTER",
            ),
        )
    )
    lines.extend(
        section(
            "Other quality flags",
            (
                "PARSE_ERROR",
                "HAS_VARIATIONS",
                "MULTIPLE_ROOT_CHILDREN",
                "POSSIBLE_AUTO_REPLY_PATTERN",
                "TERMINAL_TOO_SHALLOW",
            ),
        )
    )
    lines.extend(
        [
            "## Read-only safety statement",
            "",
            "- SGF bytes changed: no",
            "- SGF deleted: no",
            "- SGF moved: no",
            "- GF-003 production override enabled: no",
            "- GF-003 active runtime payload enabled: no",
            "- candidate override active behavior enabled: no",
            "- READY_IDS changed: no",
            "- puzzle_variation_overrides.json active config changed: no",
            "- DB/API/backend/fake app.py added: no",
            "- SGF engine judging semantics changed: no",
            "- C:\\go-website touched: no",
            "",
        ]
    )
    return "\n".join(lines)
