"""Strict structural SGF parser with complete variation preservation."""

from __future__ import annotations

from dataclasses import dataclass

from sgf_engine.core.tree import Move, SGFNode


UNKNOWN_PROPERTY = "UNKNOWN_PROPERTY"
LEGACY_PASS_TT = "LEGACY_PASS_TT"
EMPTY_PASS = "EMPTY_PASS"
INVALID_MOVE_COORD = "INVALID_MOVE_COORD"
UNSUPPORTED_BOARD_SIZE = "UNSUPPORTED_BOARD_SIZE"

_KNOWN_PROPERTIES = {
    "AB",
    "AE",
    "AN",
    "AP",
    "AR",
    "AS",
    "AW",
    "B",
    "BR",
    "BT",
    "CA",
    "C",
    "CP",
    "CR",
    "DD",
    "DM",
    "DO",
    "DT",
    "EV",
    "FF",
    "FG",
    "GB",
    "GC",
    "GM",
    "GN",
    "GW",
    "HA",
    "HO",
    "IT",
    "KM",
    "LB",
    "LN",
    "MA",
    "N",
    "OB",
    "ON",
    "OT",
    "OW",
    "PB",
    "PC",
    "PL",
    "PM",
    "RE",
    "RO",
    "RU",
    "SO",
    "SQ",
    "ST",
    "SZ",
    "TB",
    "TE",
    "TM",
    "TR",
    "TW",
    "US",
    "V",
    "VW",
    "W",
    "WR",
    "WT",
}
_LONG_FORM_ALIASES = {
    "addblack": "AB",
    "addempty": "AE",
    "addwhite": "AW",
    "application": "AP",
    "black": "B",
    "boardsize": "SZ",
    "comment": "C",
    "fileformat": "FF",
    "gameresult": "RE",
    "gametype": "GM",
    "playertoplay": "PL",
    "result": "RE",
    "white": "W",
}


def parse_sgf(sgf_string: str, strict: bool = True) -> SGFNode:
    """Parse exactly one SGF game tree into an ``SGFNode`` root."""
    if not isinstance(sgf_string, str) or not sgf_string.strip():
        raise ValueError("SGF must be a non-empty string.")
    return _SGFParser(sgf_string, strict=strict).parse()


@dataclass
class _ParsedNode:
    properties: dict[str, list[str]]
    raw_properties: list[tuple[str, str, list[str], int]]
    node_index: int
    offset: int


class _SGFParser:
    def __init__(self, source: str, *, strict: bool):
        self.source = source
        self.strict = strict
        self.index = 0
        self.node_index = 0
        self.diagnostics: list[dict[str, str]] = []

    def parse(self) -> SGFNode:
        self._skip_whitespace()
        root = SGFNode()
        self._parse_game_tree(root, use_container_for_first=True)
        self._skip_whitespace()
        if self.index != len(self.source):
            raise ValueError(f"Unexpected trailing SGF content at offset {self.index}.")
        if self.diagnostics:
            root.metadata["diagnostics"] = list(self.diagnostics)
        return root

    def _parse_game_tree(
        self,
        parent: SGFNode,
        *,
        use_container_for_first: bool,
    ) -> None:
        self._consume("(")
        self._skip_whitespace()
        if self._peek() != ";":
            raise ValueError(f"SGF game tree has no node at offset {self.index}.")

        current = parent
        first = True
        stop_analyzing = False
        while self._peek() == ";":
            parsed = self._parse_node()
            node = None if stop_analyzing else self._build_node(parsed)
            if node is not None:
                stop_this_tree = node.metadata.pop("_stop_tree", False)
                if first and use_container_for_first and node.move is None:
                    parent.metadata.update(node.metadata)
                    current = parent
                else:
                    node.parent = current
                    current.children.append(node)
                    current = node
                if stop_this_tree:
                    stop_analyzing = True
            first = False
            self._skip_whitespace()

        while self._peek() == "(":
            self._parse_game_tree(current, use_container_for_first=False)
            self._skip_whitespace()

        self._consume(")")

    def _parse_node(self) -> _ParsedNode:
        start = self.index
        self.node_index += 1
        self._consume(";")
        properties: dict[str, list[str]] = {}
        raw_properties: list[tuple[str, str, list[str], int]] = []
        self._skip_whitespace()

        while True:
            char = self._peek()
            if not char or char in ";()":
                break
            if not char.isalpha():
                raise ValueError(
                    f"Invalid SGF property identifier at offset {self.index}."
                )

            property_offset = self.index
            identifier = self._parse_identifier()
            canonical = _canonicalize_property_identifier(identifier)
            if canonical == "":
                raise ValueError(
                    f"Invalid SGF property identifier at offset {property_offset}."
                )
            self._skip_whitespace()
            if self._peek() != "[":
                raise ValueError(
                    f"SGF property {identifier} has no value at offset {self.index}."
                )

            values: list[str] = []
            while self._peek() == "[":
                values.append(self._parse_property_value())
                self._skip_whitespace()
            properties.setdefault(canonical, []).extend(values)
            raw_properties.append((identifier, canonical, list(values), property_offset))

        return _ParsedNode(properties, raw_properties, self.node_index, start)

    def _parse_identifier(self) -> str:
        start = self.index
        while self._peek().isalpha():
            self.index += 1
        return self.source[start : self.index]

    def _parse_property_value(self) -> str:
        self._consume("[")
        result: list[str] = []
        while self.index < len(self.source):
            char = self.source[self.index]
            self.index += 1
            if char == "]":
                return "".join(result)
            if char != "\\":
                result.append(char)
                continue

            if self.index >= len(self.source):
                raise ValueError("SGF property ends with an incomplete escape.")
            escaped = self.source[self.index]
            self.index += 1
            if escaped == "\r":
                if self.index < len(self.source) and self.source[self.index] == "\n":
                    self.index += 1
                continue
            if escaped == "\n":
                continue
            result.append(escaped)

        raise ValueError("Unterminated SGF property value.")

    def _build_node(self, parsed: _ParsedNode) -> SGFNode:
        properties = parsed.properties
        for identifier, canonical, values, offset in parsed.raw_properties:
            if canonical not in _KNOWN_PROPERTIES:
                self._add_diagnostic(
                    UNKNOWN_PROPERTY,
                    parsed,
                    offset=offset,
                    raw=f"{identifier}[{']['.join(values)}]",
                )
        move_keys = [color for color in ("B", "W") if color in properties]
        if len(move_keys) > 1:
            raise ValueError("An SGF node cannot contain both B and W moves.")

        metadata: dict = {
            "properties": {key: list(values) for key, values in properties.items()}
        }
        if "C" in properties:
            metadata["comment"] = properties["C"][0]
        if "RESULT" in properties:
            metadata["result"] = properties["RESULT"][0]
        if "RE" in properties:
            metadata["game_result"] = properties["RE"][0]
        if "SZ" in properties:
            try:
                metadata["size"] = int(properties["SZ"][0])
            except (TypeError, ValueError) as error:
                raise ValueError("SGF SZ must be an integer.") from error
            if metadata["size"] > 19:
                if self.strict:
                    raise ValueError("unsupported board size")
                self._add_diagnostic(
                    UNSUPPORTED_BOARD_SIZE,
                    parsed,
                    raw=f"SZ[{properties['SZ'][0]}]",
                )
                metadata["_stop_tree"] = True
        if "PL" in properties:
            player = properties["PL"][0]
            if player not in ("B", "W"):
                raise ValueError('SGF PL must be exactly "B" or "W".')
            metadata["player_to_move"] = player

        move = None
        if move_keys:
            color = move_keys[0]
            values = properties[color]
            if len(values) != 1:
                raise ValueError(f"SGF move property {color} must have one value.")
            metadata["color"] = color
            coord = values[0]
            metadata["raw_move"] = f"{color}[{coord}]"
            if coord == "":
                metadata["pass"] = True
                move = Move(color=color, coord=None, is_pass=True)
                self._add_diagnostic(
                    EMPTY_PASS,
                    parsed,
                    raw=metadata["raw_move"],
                )
            elif coord == "tt" and metadata.get("size", 19) <= 19:
                metadata["pass"] = True
                move = Move(color=color, coord=None, is_pass=True)
                self._add_diagnostic(
                    LEGACY_PASS_TT,
                    parsed,
                    raw=metadata["raw_move"],
                )
            else:
                try:
                    move = Move(color=color, coord=coord)
                except ValueError as error:
                    if not self.strict:
                        self._add_diagnostic(
                            INVALID_MOVE_COORD,
                            parsed,
                            raw=metadata["raw_move"],
                        )
                        return SGFNode(move=None, metadata=metadata)
                    raise ValueError(
                        f"Invalid SGF move {color}[{coord}]."
                    ) from error

        return SGFNode(move=move, metadata=metadata)

    def _add_diagnostic(
        self,
        code: str,
        parsed: _ParsedNode,
        *,
        raw: str,
        offset: int | None = None,
    ) -> None:
        self.diagnostics.append(
            {
                "code": code,
                "detail": (
                    f"node={parsed.node_index} offset={parsed.offset if offset is None else offset} "
                    f"raw={raw}"
                ),
            }
        )

    def _skip_whitespace(self) -> None:
        while self.index < len(self.source) and self.source[self.index].isspace():
            self.index += 1

    def _peek(self) -> str:
        if self.index >= len(self.source):
            return ""
        return self.source[self.index]

    def _consume(self, expected: str) -> None:
        if self._peek() != expected:
            raise ValueError(
                f"Expected {expected!r} at SGF offset {self.index}, "
                f"found {self._peek()!r}."
            )
        self.index += 1


def _canonicalize_property_identifier(identifier: str) -> str:
    alias = _LONG_FORM_ALIASES.get(identifier.lower())
    if alias is not None:
        return alias
    uppercase_letters = "".join(char for char in identifier if "A" <= char <= "Z")
    return uppercase_letters

