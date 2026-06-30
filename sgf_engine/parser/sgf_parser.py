"""Strict structural SGF parser with complete variation preservation."""

from __future__ import annotations

from dataclasses import dataclass

from sgf_engine.core.tree import Move, SGFNode


def parse_sgf(sgf_string: str) -> SGFNode:
    """Parse exactly one SGF game tree into an ``SGFNode`` root."""
    if not isinstance(sgf_string, str) or not sgf_string.strip():
        raise ValueError("SGF must be a non-empty string.")
    return _SGFParser(sgf_string).parse()


@dataclass
class _ParsedNode:
    properties: dict[str, list[str]]


class _SGFParser:
    def __init__(self, source: str):
        self.source = source
        self.index = 0

    def parse(self) -> SGFNode:
        self._skip_whitespace()
        root = SGFNode()
        self._parse_game_tree(root, use_container_for_first=True)
        self._skip_whitespace()
        if self.index != len(self.source):
            raise ValueError(f"Unexpected trailing SGF content at offset {self.index}.")
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
        while self._peek() == ";":
            parsed = self._parse_node()
            node = self._build_node(parsed)
            if first and use_container_for_first and node.move is None:
                parent.metadata.update(node.metadata)
                current = parent
            else:
                node.parent = current
                current.children.append(node)
                current = node
            first = False
            self._skip_whitespace()

        while self._peek() == "(":
            self._parse_game_tree(current, use_container_for_first=False)
            self._skip_whitespace()

        self._consume(")")

    def _parse_node(self) -> _ParsedNode:
        self._consume(";")
        properties: dict[str, list[str]] = {}
        self._skip_whitespace()

        while True:
            char = self._peek()
            if not char or char in ";()":
                break
            if not ("A" <= char <= "Z"):
                raise ValueError(
                    f"Invalid SGF property identifier at offset {self.index}."
                )

            identifier = self._parse_identifier()
            self._skip_whitespace()
            if self._peek() != "[":
                raise ValueError(
                    f"SGF property {identifier} has no value at offset {self.index}."
                )

            values: list[str] = []
            while self._peek() == "[":
                values.append(self._parse_property_value())
                self._skip_whitespace()
            properties.setdefault(identifier, []).extend(values)

        return _ParsedNode(properties)

    def _parse_identifier(self) -> str:
        start = self.index
        while "A" <= self._peek() <= "Z":
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
            if coord == "":
                metadata["pass"] = True
            else:
                try:
                    move = Move(color=color, coord=coord)
                except ValueError as error:
                    raise ValueError(
                        f"Invalid SGF move {color}[{coord}]."
                    ) from error

        return SGFNode(move=move, metadata=metadata)

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

