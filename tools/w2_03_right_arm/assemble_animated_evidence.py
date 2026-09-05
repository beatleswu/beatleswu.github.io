"""Assemble browser-captured runtime frames into Owner-review GIFs."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def save_gif(frame_dir: Path, output_path: Path, duration_ms: int) -> int:
    frames = []
    for path in sorted(frame_dir.glob("*.png")):
        with Image.open(path) as image:
            frames.append(image.convert("RGB"))
    if len(frames) < 2:
        raise ValueError(f"animated evidence requires at least two frames: {frame_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    first, *rest = frames
    first.save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=rest,
        duration=duration_ms,
        loop=0,
        optimize=False,
        disposal=2,
    )
    return len(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    results: dict[str, int] = {}
    for viewport_dir in sorted(args.input_root.iterdir()):
        if not viewport_dir.is_dir():
            continue
        for state_dir in sorted(viewport_dir.iterdir()):
            if not state_dir.is_dir():
                continue
            if viewport_dir.name == "desktop-debug-slow-motion":
                output_name = "right-arm-slow-motion-debug.gif"
                duration = 240
            else:
                state_name = "open-hand-idle" if state_dir.name == "open" else "grip-idle"
                output_name = f"{viewport_dir.name}-{state_name}.gif"
                duration = 120
            results[output_name] = save_gif(
                state_dir,
                args.output_dir / output_name,
                duration,
            )
    if len(results) < 7:
        raise ValueError(f"expected desktop/iPad/mobile open+grip plus debug GIFs, got {sorted(results)}")
    for name, frame_count in sorted(results.items()):
        print(f"{name}: {frame_count} frames")


if __name__ == "__main__":
    main()
