"""Build the governed E10 V2 clean-map WebP from the Owner PNG."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image


OWNER_SOURCE_SHA256 = "f735798ad1e072fad57ca5d9286facea0656dee5d409ad9ddabf39e96b961b4d"
EXPECTED_SIZE = (2048, 1152)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    if sha256(args.source) != OWNER_SOURCE_SHA256:
        raise SystemExit("Owner clean-map source SHA-256 mismatch")

    with Image.open(args.source) as source:
        if source.size != EXPECTED_SIZE or source.format != "PNG":
            raise SystemExit(f"Owner clean-map identity mismatch: {source.format} {source.size}")
        image = source.convert("RGB")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output, "WEBP", quality=90, method=6, exact=True)

    with Image.open(args.output) as derivative:
        if derivative.size != EXPECTED_SIZE or derivative.format != "WEBP":
            raise SystemExit("Generated V2 derivative identity mismatch")


if __name__ == "__main__":
    main()
