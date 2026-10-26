"""Lossless SGF value-span editing for the existing eight square symmetries.

Only declared point properties are edited. Text and escape sequences are never
decoded/re-serialized. No application bootstrap, database or answer authority.
"""

_POINT_LISTS = frozenset(('AB', 'AW', 'AE', 'TR', 'SQ', 'CR', 'MA'))
_ALPHABET = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'


def _properties(source):
    """Yield (game, node, identifier, start, end) for raw value interiors.

    Brackets, semicolons and parentheses inside a value are data, including
    escaped closing brackets. Per-game node numbers distinguish root SZ from
    text or a nested variation. Invalid structure fails before any edits escape.
    """
    i, game, node, depth = 0, -1, -1, 0
    while i < len(source):
        char = source[i]
        if char.isspace():
            i += 1
        elif char == '(':
            if depth == 0:
                game += 1
                node = -1
            depth += 1
            i += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                raise ValueError('unbalanced_sgf_tree')
            i += 1
        elif char == ';' and depth:
            node += 1
            i += 1
        elif char.isascii() and char.isalpha() and depth and node >= 0:
            start = i
            while i < len(source) and source[i].isascii() and source[i].isalpha():
                i += 1
            prop = source[start:i]
            while i < len(source) and source[i].isspace():
                i += 1
            if i == len(source) or source[i] != '[':
                raise ValueError('sgf_property_without_value')
            while i < len(source) and source[i] == '[':
                i += 1
                start = i
                while i < len(source) and source[i] != ']':
                    if source[i] == '\\':
                        i += 1  # skip the escaped character, even ] or backslash
                    i += 1
                if i >= len(source):
                    raise ValueError('unterminated_sgf_value')
                yield game, node, prop, start, i
                i += 1
                while i < len(source) and source[i].isspace():
                    i += 1
        else:
            raise ValueError('invalid_sgf_token')
    if depth or game < 0:
        raise ValueError('unbalanced_sgf_tree')


def transform_sgf(content: str, t: int) -> str:
    if t == 0:
        return content
    if type(t) is not int or not 1 <= t <= 7:
        raise ValueError('invalid_sgf_transform')
    tokens = list(_properties(content))
    sizes = {}
    for game, node, prop, start, end in tokens:
        if prop == 'SZ' and node == 0:
            raw = content[start:end]
            if not raw.isascii() or not raw.isdigit() or not 1 <= int(raw) <= 52:
                raise ValueError('unsupported_sgf_board_size')
            if game in sizes:
                raise ValueError('duplicate_sgf_board_size')
            sizes[game] = int(raw)

    def point(raw, size, *, move=False):
        if move and (raw == '' or (raw == 'tt' and size <= 19)):
            return raw
        if len(raw) != 2 or any(c not in _ALPHABET[:size] for c in raw):
            return raw
        x, y = map(_ALPHABET.index, raw)
        n = size - 1
        x, y = ((x, y), (n-y, x), (n-x, n-y), (y, n-x),
                (n-x, y), (x, n-y), (y, x), (n-y, n-x))[t]
        return _ALPHABET[x] + _ALPHABET[y]

    edits = []
    for game, _, prop, start, end in tokens:
        raw, size = content[start:end], sizes.get(game, 19)
        changed = raw
        if prop in ('B', 'W'):
            changed = point(raw, size, move=True)
        elif prop == 'LB':
            # A valid composed point has its separator at offset 2. Everything
            # following it is opaque raw label text (including escaped ':').
            if len(raw) >= 3 and raw[2] == ':':
                changed = point(raw[:2], size) + raw[2:]
        elif prop in _POINT_LISTS:
            if len(raw) == 5 and raw[2] == ':' and all(
                    c in _ALPHABET[:size] for c in raw[:2] + raw[3:]):
                a, b = point(raw[:2], size), point(raw[3:], size)
                # Compressed rectangles require upper-left : lower-right,
                # rather than the possibly reversed transformed endpoints.
                xs = [_ALPHABET.index(a[0]), _ALPHABET.index(b[0])]
                ys = [_ALPHABET.index(a[1]), _ALPHABET.index(b[1])]
                changed = (_ALPHABET[min(xs)] + _ALPHABET[min(ys)] + ':' +
                           _ALPHABET[max(xs)] + _ALPHABET[max(ys)])
            else:
                changed = point(raw, size)
        if changed != raw:
            edits.append((start, end, changed))
    for start, end, changed in reversed(edits):
        content = content[:start] + changed + content[end:]
    return content
