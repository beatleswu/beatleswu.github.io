"""Focused regression tests for the one-asset acc_jade_ring revision."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BASE = "d79f0c869507796b502b4bb6e491df49d94ef467"
PACK = ROOT / "docs" / "planning" / "rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003"
REVISION = PACK / "revisions" / "acc_jade_ring_visual_readability_fix_004"
MANIFEST = PACK / "rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003_manifest.json"
MASTER = PACK / "masters" / "acc_jade_ring.png"
WEBP = PACK / "masters" / "acc_jade_ring.webp"
BEFORE = REVISION / "acc_jade_ring_before.png"

OTHER_20 = [
    "robe_plain", "robe_student", "robe_bamboo", "robe_crane", "robe_fox", "robe_snow", "robe_dragon",
    "back_pack", "back_flag", "back_lantern", "back_wings", "back_scroll", "back_foxtail", "back_cloak", "back_dragon_wings",
    "acc_bracelet", "acc_fan", "acc_goboard_bag", "acc_goban_seal", "acc_dragon_pendant",
]
EXISTING_23 = [
    "hat_cloth", "hat_bamboo", "hat_student", "hat_feather", "hat_scholar", "hat_foxmask", "hat_onihorns",
    "hat_dragon_horn", "hat_celestial_crown", "hat_premium", "title_beginner", "title_scholar", "title_wanderer",
    "title_streak", "title_foxwit", "title_master", "title_dragonslayer", "title_godshand", "title_celestial",
    "title_eternity", "title_newbie_voyage", "title_claire_recruit", "title_premium",
]


def base_bytes(relative: str) -> bytes:
    return subprocess.run(["git", "show", f"{BASE}:{relative}"], cwd=ROOT, check=True, capture_output=True).stdout


class AccJadeRingRevisionTests(unittest.TestCase):
    def test_authorized_identity_and_readability_revision(self) -> None:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        row = next(item for item in data["new_candidates"] if item["cosmetic_id"] == "acc_jade_ring")
        self.assertEqual(row["readability_revision"]["task"], "GO_ODYSSEY_MASTER_LANE_A_ACC_JADE_RING_VISUAL_READABILITY_FIX_004")
        self.assertEqual(row["readability_revision"]["functional_effect_count"], 0)
        self.assertEqual(row["readability_revision"]["other_cosmetic_ids_changed"], 0)
        self.assertEqual(row["combat_authority"], "NO")
        self.assertEqual(row["progression_authority"], "NO")
        self.assertEqual(row["ownership_authority"], "NO")

        before = np.array(Image.open(BEFORE).convert("RGBA"))
        after = np.array(Image.open(MASTER).convert("RGBA"))
        self.assertEqual(before.shape, after.shape)
        self.assertGreater(np.count_nonzero(np.any(before != after, axis=2)), 0)
        region_before = before[650:850, 650:820]
        region_after = after[650:850, 650:820]
        green_before = (region_before[:, :, 3] > 20) & (region_before[:, :, 1] > 70) & (region_before[:, :, 1] > region_before[:, :, 0] * 1.05) & (region_before[:, :, 1] > region_before[:, :, 2] * 1.02)
        green_after = (region_after[:, :, 3] > 20) & (region_after[:, :, 1] > 70) & (region_after[:, :, 1] > region_after[:, :, 0] * 1.05) & (region_after[:, :, 1] > region_after[:, :, 2] * 1.02)
        self.assertGreater(int(green_after.sum()), int(green_before.sum()), "jade setting did not become more perceptible")

    def test_master_dimensions_alpha_and_mobile_review_artifacts(self) -> None:
        with Image.open(MASTER) as image:
            self.assertEqual(image.size, (1056, 1408))
            self.assertEqual(image.mode, "RGBA")
            alpha = image.getchannel("A")
            self.assertIsNotNone(alpha.getbbox())
            self.assertEqual(alpha.getpixel((0, 0)), 0)
            self.assertEqual(alpha.getpixel((1055, 1407)), 0)
            pixels = np.array(image, dtype=np.uint8)
            transparent = pixels[:, :, 3] == 0
            self.assertTrue(np.all(pixels[:, :, :3][transparent] == 0))
        with Image.open(WEBP) as image:
            self.assertEqual(image.size, (1056, 1408))
            self.assertEqual(image.mode, "RGBA")
        for name in ("ACC_JADE_RING_DESKTOP_AFTER.png", "ACC_JADE_RING_MOBILE_AFTER.png", "ACC_JADE_RING_BEFORE_AFTER.png"):
            with Image.open(REVISION / name) as image:
                self.assertEqual(image.mode, "RGB", name)
                self.assertGreater(image.width, 300, name)
                self.assertGreater(image.height, 300, name)

    def test_other_cosmetics_and_existing_catalog_are_byte_identical(self) -> None:
        for cosmetic_id in OTHER_20:
            for extension in ("png", "webp"):
                relative = f"docs/planning/rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003/masters/{cosmetic_id}.{extension}"
                self.assertEqual((ROOT / relative).read_bytes(), base_bytes(relative), relative)
        for cosmetic_id in EXISTING_23:
            relative = f"assets/hero/items/{cosmetic_id}.svg"
            self.assertEqual((ROOT / relative).read_bytes(), base_bytes(relative), relative)

    def test_changed_paths_are_micro_revision_scoped(self) -> None:
        allowed = (
            "docs/planning/rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003/masters/acc_jade_ring.png",
            "docs/planning/rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003/masters/acc_jade_ring.webp",
            "docs/planning/rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003/rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003_manifest.json",
            "docs/planning/rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003/revisions/acc_jade_ring_visual_readability_fix_004/",
            "tests/test_acc_jade_ring_visual_readability_fix.py",
            "tools/build_acc_jade_ring_visual_readability_fix.py",
        )
        changed = subprocess.run(["git", "diff", "--name-only", BASE, "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
        unexpected = [path for path in changed if not any(path == prefix or path.startswith(prefix) for prefix in allowed)]
        self.assertEqual(unexpected, [])
        self.assertFalse(any("assets/hero/characters/" in path for path in changed))


if __name__ == "__main__":
    unittest.main()
