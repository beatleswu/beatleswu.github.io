"""Contract tests for the isolated A055 feasibility design mockup.

These tests deliberately do not import a Live2D/Cubism runtime. The repository
does not contain an authorized runtime, so the test target is the labelled
design contract and the separation between identity art, hand rig, socket, and
weapon metadata.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "planning" / "a055_p0_live2d_feasibility"


class A055Live2DFeasibilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model_path = DEMO / "rig-model.json"
        cls.model = json.loads(cls.model_path.read_text(encoding="utf-8"))
        cls.html = (DEMO / "demo" / "index.html").read_text(encoding="utf-8")
        cls.js = (DEMO / "demo" / "feasibility.js").read_text(encoding="utf-8")
        cls.css = (DEMO / "demo" / "feasibility.css").read_text(encoding="utf-8")
        cls.readme = (DEMO / "README.md").read_text(encoding="utf-8")

    def test_expected_artifact_set_exists(self) -> None:
        expected = {
            "README.md",
            "rig-model.json",
            "decomposition.svg",
            "socket-diagram.svg",
            "demo/index.html",
            "demo/feasibility.css",
            "demo/feasibility.js",
        }
        actual = {path.relative_to(DEMO).as_posix() for path in DEMO.rglob("*") if path.is_file()}
        self.assertTrue(expected <= actual)

    def test_runtime_block_is_explicit_and_not_misrepresented(self) -> None:
        self.assertFalse(self.model["prototype"]["officialRuntimeAvailable"])
        self.assertEqual(self.model["prototype"]["status"], "DESIGN_MOCKUP_NOT_LIVE2D_RUNTIME")
        self.assertFalse(self.model["prototype"]["goOdysseyIntegration"])
        self.assertFalse(self.model["prototype"]["featureGatesChanged"])
        self.assertIn("LIVE2D_RUNTIME_EXECUTION=BLOCKED_BY_SDK_AVAILABILITY", self.readme)
        self.assertIn("ACTUAL RUNTIME OUTPUT: NOT AVAILABLE", self.html)
        self.assertIn("FEATURE GATES: OFF", self.html)
        self.assertIn("design-mockup", self.html.lower() + self.js.lower() + self.readme.lower())

    def test_apprentice_decomposition_contains_independent_hand_and_weapon_socket(self) -> None:
        rig = self.model["characterRig"]
        self.assertEqual(rig["id"], "apprentice_live2d_candidate_rig_v0")
        self.assertEqual(rig["handRigId"], "apprentice_right_hand_grip_rig_v0")
        self.assertEqual(rig["canvas"], [1056, 1408])
        for region in (
            "HEAD", "HAIR_FRONT", "HAIR_BACK", "FACE", "EYES", "MOUTH", "TORSO",
            "RIGHT_UPPER_ARM", "RIGHT_FOREARM", "RIGHT_HAND", "LEFT_UPPER_ARM",
            "LEFT_FOREARM", "LEFT_HAND", "LOWER_BODY",
        ):
            self.assertIn(region, rig["decomposition"])
        self.assertEqual(self.model["hierarchy"]["RIGHT_HAND"], ["RIGHT_HAND_WEAPON_SOCKET"])
        self.assertEqual(self.model["hierarchy"]["RIGHT_FOREARM"], ["RIGHT_HAND"])
        socket = self.model["attachments"]["RIGHT_HAND_WEAPON_SOCKET"]
        self.assertEqual(socket["parent"], "RIGHT_HAND")
        self.assertEqual(socket["id"], "RIGHT_HAND_WEAPON_SOCKET")
        self.assertEqual(socket["position"], [800, 800])
        self.assertIn("gripPoint", socket["transformRule"])
        self.assertIn("gripAxis", socket["transformRule"])
        self.assertIn("gripWidth", socket["transformRule"])

    def test_minimum_parameter_set_is_bounded(self) -> None:
        ids = [parameter["id"] for parameter in self.model["parameters"]]
        expected = {
            "PARAM_BODY_ANGLE_X",
            "PARAM_BODY_ANGLE_Y",
            "PARAM_RIGHT_ARM_ANGLE",
            "PARAM_RIGHT_FOREARM_ANGLE",
            "PARAM_RIGHT_WRIST_ANGLE",
            "PARAM_RIGHT_HAND_GRIP",
            "PARAM_BREATH",
            "PARAM_EYE_OPEN_L",
            "PARAM_EYE_OPEN_R",
        }
        self.assertEqual(set(ids), expected)
        self.assertEqual(len(ids), 9)

    def test_both_weapons_use_same_rig_and_semantic_grip_metadata(self) -> None:
        weapons = self.model["weapons"]
        self.assertEqual(set(weapons), {"wooden_sword", "iron_sword"})
        self.assertEqual(self.model["characterRig"]["handRigId"], "apprentice_right_hand_grip_rig_v0")
        for weapon_id, weapon in weapons.items():
            self.assertEqual(weapon["id"], weapon_id)
            self.assertEqual(weapon["gripPoint"], [128, 208])
            self.assertIn("x", weapon["gripAxis"])
            self.assertIn("y", weapon["gripAxis"])
            self.assertGreater(weapon["gripWidth"], 0)
            self.assertIn("asset", weapon)
        self.assertEqual(weapons["wooden_sword"]["swapClass"], "one_hand_sword")
        self.assertEqual(weapons["iron_sword"]["swapClass"], "one_hand_sword")
        self.assertIn("sameRigForWeaponSwap", self.model["characterRig"])
        self.assertTrue(self.model["characterRig"]["sameRigForWeaponSwap"])
        self.assertIn("applyWeaponTransform", self.js)
        self.assertIn("RIGHT_HAND_WEAPON_SOCKET", self.js)
        self.assertIn("gripPoint", self.js)
        self.assertIn("gripAxis", self.js)
        self.assertIn("gripWidth", self.js)

    def test_weapon_is_not_baked_into_character_layer(self) -> None:
        self.assertIn("id=\"character-layer\"", self.html)
        self.assertIn("id=\"weapon-layer\"", self.html)
        self.assertIn("id=\"grip-layer\"", self.html)
        self.assertIn("WEAPON ART IS NOT BAKED INTO CHARACTER", self.html)
        self.assertEqual(self.model["characterRig"]["sameRigForWeaponSwap"], True)

    def test_motion_and_measurement_are_explicitly_mock_only(self) -> None:
        self.assertIn("PARAM_BREATH", self.js)
        self.assertIn("requestAnimationFrame", self.js)
        self.assertIn("mock idle", self.html.lower())
        self.assertIn("NOT CUBISM METRICS", self.html)
        self.assertIn("performance.now", self.js)
        self.assertIn("MODEL_BYTES", self.readme.upper())

    def test_viewer_is_responsive_and_accessible(self) -> None:
        self.assertIn('name="viewport"', self.html)
        self.assertIn("aria-label", self.html)
        self.assertIn("@media (max-width: 760px)", self.css)
        self.assertIn("@media (max-width: 430px)", self.css)
        self.assertIn("overflow-x: hidden", self.css)
        self.assertIn("aspect-ratio: 1056 / 1408", self.css)

    def test_scope_firewall_is_written_down(self) -> None:
        for token in (
            "APP_PY_CHANGED=NO",
            "Owner visual",
            "NOT_GRANTED",
            "A054",
            "payment",
            "Production",
        ):
            self.assertIn(token, self.readme)


if __name__ == "__main__":
    unittest.main()
