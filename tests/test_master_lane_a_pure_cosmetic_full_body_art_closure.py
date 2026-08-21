"""Deterministic validation for the Lane A pure-cosmetic art pack."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import unittest

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "docs" / "planning" / "rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003"
MANIFEST = PACK / "rpg_wave2_master_lane_a_pure_cosmetic_full_body_art_closure_003_manifest.json"
BASE = "ac182ed173620a11e66bebeb6003c121b9ceee95"

NEW_IDS = [
    "robe_plain", "robe_student", "robe_bamboo", "robe_crane", "robe_fox", "robe_snow", "robe_dragon",
    "back_pack", "back_flag", "back_lantern", "back_wings", "back_scroll", "back_foxtail", "back_cloak", "back_dragon_wings",
    "acc_bracelet", "acc_fan", "acc_goboard_bag", "acc_jade_ring", "acc_goban_seal", "acc_dragon_pendant",
]
EXISTING_IDS = [
    "hat_cloth", "hat_bamboo", "hat_student", "hat_feather", "hat_scholar", "hat_foxmask", "hat_onihorns",
    "hat_dragon_horn", "hat_celestial_crown", "hat_premium", "title_beginner", "title_scholar", "title_wanderer",
    "title_streak", "title_foxwit", "title_master", "title_dragonslayer", "title_godshand", "title_celestial",
    "title_eternity", "title_newbie_voyage", "title_claire_recruit", "title_premium",
]
MATRIX_NAMES = [
    "PURE_COSMETIC_21_DESKTOP_MATRIX.png",
    "PURE_COSMETIC_21_MOBILE_MATRIX.png",
    "PURE_COSMETIC_44_FULL_LINEUP.png",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PureCosmeticClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.records = {row["cosmetic_id"]: row for row in cls.manifest["new_candidates"]}

    def test_exact_registry_and_counts(self) -> None:
        self.assertEqual(list(self.records), NEW_IDS)
        self.assertEqual(len(set(self.records)), 21)
        self.assertEqual([row["cosmetic_id"] for row in self.manifest["existing_approved_23"]], EXISTING_IDS)
        self.assertEqual(self.manifest["counts"]["new_pure_cosmetic_art_candidates"], 21)
        self.assertEqual(self.manifest["counts"]["pure_cosmetic_full_body_art"], 44)
        self.assertEqual(self.manifest["counts"]["remaining_art_gap"], 0)

    def test_presentation_authority_invariants(self) -> None:
        for row in self.records.values():
            self.assertTrue(row["pure_presentation"])
            self.assertEqual(row["functional_effect_count"], 0)
            self.assertEqual(row["combat_authority"], "NO")
            self.assertEqual(row["progression_authority"], "NO")
            self.assertEqual(row["ownership_authority"], "NO")
            self.assertTrue(all(value in {"PASS", "NOT_APPLICABLE"} for value in row["compatibility_screen"].values()))
        self.assertEqual(self.manifest["authority"]["functional_equipment_authority"], "player_inventory + server EQUIPMENT_DEFS")
        self.assertEqual(self.manifest["authority"]["functional_equipment_authority_changed"], "NO")
        self.assertEqual(self.manifest["authority"]["character_combat_authority"], "NO")
        self.assertEqual(self.manifest["authority"]["client_combat_authority"], "NO")

    def test_master_and_derivative_closure(self) -> None:
        for cosmetic_id in NEW_IDS:
            row = self.records[cosmetic_id]
            source = ROOT / row["raw_source"]
            master = ROOT / row["master_png"]
            webp = ROOT / row["runtime_derivative_webp"]
            self.assertTrue(source.is_file(), cosmetic_id)
            self.assertTrue(master.is_file(), cosmetic_id)
            self.assertTrue(webp.is_file(), cosmetic_id)
            self.assertEqual(sha256(source), row["source_sha256"], cosmetic_id)
            self.assertEqual(sha256(master), row["master_sha256"], cosmetic_id)
            self.assertEqual(sha256(webp), row["webp_sha256"], cosmetic_id)
            with Image.open(master) as image:
                self.assertEqual(image.size, (1056, 1408), cosmetic_id)
                self.assertEqual(image.mode, "RGBA", cosmetic_id)
                pixels = np.array(image, dtype=np.uint8)
                alpha = image.getchannel("A")
                self.assertGreater(alpha.getbbox()[2] - alpha.getbbox()[0], 0, cosmetic_id)
                self.assertEqual(alpha.getpixel((0, 0)), 0, cosmetic_id)
                self.assertEqual(alpha.getpixel((1055, 1407)), 0, cosmetic_id)
                transparent = pixels[:, :, 3] == 0
                self.assertTrue(np.all(pixels[:, :, :3][transparent] == 0), cosmetic_id)
            with Image.open(webp) as image:
                self.assertEqual(image.size, (1056, 1408), cosmetic_id)
                self.assertEqual(image.mode, "RGBA", cosmetic_id)

    def test_review_artifacts_exist(self) -> None:
        for name in MATRIX_NAMES:
            path = PACK / "matrices" / name
            self.assertTrue(path.is_file(), name)
            with Image.open(path) as image:
                self.assertEqual(image.mode, "RGB", name)
                self.assertGreater(image.width, 1000, name)
                self.assertGreater(image.height, 500, name)

    def test_existing_23_are_unchanged_from_base(self) -> None:
        for cosmetic_id in EXISTING_IDS:
            relative = f"assets/hero/items/{cosmetic_id}.svg"
            expected = subprocess.run(
                ["git", "show", f"{BASE}:{relative}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
            self.assertEqual((ROOT / relative).read_bytes(), expected, relative)


if __name__ == "__main__":
    unittest.main()
