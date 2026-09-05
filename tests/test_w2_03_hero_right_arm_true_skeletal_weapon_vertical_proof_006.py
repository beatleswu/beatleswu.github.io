"""Bounded proof checks for the W2-03 right-arm skeletal weapon slice.

The tests exercise the existing 15-bone/18-slot foundation through a
right-arm manifest variant.  They verify technical attachment/state behavior;
human visual acceptance remains an Owner decision.
"""

from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs" / "planning" / "w2_03_hero_true_2d_skeletal_rig_vertical_slice_005r2"
BASE_MANIFEST_PATH = PACKAGE / "apprentice_p1_skeletal_manifest.json"
VARIANT_MANIFEST_PATH = PACKAGE / "apprentice_p1_right_arm_manifest.json"
RUNTIME_PATH = ROOT / "js" / "e9" / "hero_skeletal_rig.js"
PROOF_PATH = (
    ROOT
    / "docs"
    / "evidence"
    / "w2_03_hero_right_arm_true_skeletal_weapon_vertical_proof_006"
    / "proof.html"
)
EVIDENCE_DIR = PROOF_PATH.parent
ASSET_ROOT = ROOT / "assets" / "hero" / "rigs" / "apprentice_p1" / "right_arm"

EXPECTED_RUNTIME = {
    "upper_arm_R": ("35d2d30d7cf956353ae18e8d00379d1b9a7ccc9d086070794733a790b73f04f1", (860, 1119)),
    "forearm_R": ("0bec423268a8d04fab47fc05bfa3f57ae2561d849b70860fd175265e3da521bc", (788, 964)),
    "hand_R_open": ("287e86b063048072f5b749aaa0292a733d32a0518cf8e4648361a5a5056069b4", (644, 485)),
    "hand_R_grip_back": ("082223d9f0bccfcb88955a1515867ebab1064afb13732ffd83eb88d6405ebe15", (703, 736)),
    "hand_R_grip_front": ("047165d77a070e2db48103f6528c947fd504ea06e1614687132d9f371175c16a", (286, 299)),
}
EXPECTED_SOURCES = {
    "ART_01": ("1-照片-1.jpg", "ae0e37d7cb27f82baf4f929a578a4aedbdd92549f2c390766b13224c5b629eb6", (1254, 1254)),
    "ART_02": ("2-照片-2.jpg", "eed155532a97550b8007eb5791d77169f0283cc0668193c524508a0f8867d0d6", (1254, 1254)),
    "ART_03": ("3-照片-3.jpg", "db9419761e3b6cd6284072508bc0dd8c244223c352b74034d415e7b65a993d93", (1275, 1233)),
    "ART_04": ("4-照片-4.jpg", "002f2885e6997a09b3dbd84a0c9edb85e9a0373a1f6a5b045a3d53ef03f3d877", (1254, 1254)),
    "ART_05": ("5-照片-5.jpg", "7cfbbfdafde06218165c15019e9cacc4f684a418c5899391ba45c7c05241dee1", (1276, 1233)),
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def png_info(path: Path) -> tuple[tuple[int, int], int, tuple[int, int], int]:
    payload = path.read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    width, height, bit_depth, color_type = struct.unpack(">IIBB", payload[16:26])
    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    return (width, height), color_type, alpha.getextrema(), len(payload)


def test_owner_source_provenance_and_five_runtime_parts_are_exact_rgba_pngs():
    manifest = load_json(VARIANT_MANIFEST_PATH)
    assert manifest["hero_id"] == "apprentice_p1"
    assert manifest["presentation_only"] is True
    assert manifest["source_art_mutated"] is False
    assert manifest["new_art_generated"] is False
    assert set(manifest["assets"]) == {
        "right_arm_upper_arm_R",
        "right_arm_forearm_R",
        "right_arm_hand_R_open",
        "right_arm_hand_R_grip_back",
        "right_arm_hand_R_grip_front",
    }
    for asset_name, (expected_hash, expected_dimensions) in EXPECTED_RUNTIME.items():
        asset = manifest["assets"][f"right_arm_{asset_name}"]
        path = ROOT / asset["path"].lstrip("/")
        assert path == ASSET_ROOT / f"{asset_name}.png"
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
        dimensions, color_type, alpha_extrema, byte_count = png_info(path)
        assert dimensions == expected_dimensions
        assert color_type == 6  # RGBA PNG, not a screenshot or flattened plate.
        assert alpha_extrema[0] == 0
        assert alpha_extrema[1] == 255
        assert byte_count > 0
        assert asset["dimensions"] == list(expected_dimensions)
        assert asset["sha256"] == expected_hash
        assert asset["true_alpha"] is True
        assert asset["derived"] is True

    provenance = {entry["asset_id"]: entry for entry in manifest["art_source_provenance"]}
    assert set(provenance) == set(EXPECTED_SOURCES)
    for asset_id, (filename, source_hash, dimensions) in EXPECTED_SOURCES.items():
        entry = provenance[asset_id]
        assert entry["source_filename"] == filename
        assert entry["source_sha256"] == source_hash
        assert tuple(entry["source_dimensions"]) == dimensions
    art05_operation = provenance["ART_05"]["technical_operation"]
    assert "hand/finger/thumb" in art05_operation
    assert "wooden sword pixels excluded" in art05_operation


def test_variant_preserves_foundation_graph_and_explicit_right_arm_contract():
    base = load_json(BASE_MANIFEST_PATH)
    variant = load_json(VARIANT_MANIFEST_PATH)
    assert variant["base_manifest"] == "apprentice_p1_skeletal_manifest.json"
    assert len(base["bones"]) == 15
    assert len(base["slots"]) == 18
    parent_by_id = {bone["id"]: bone["parent"] for bone in base["bones"]}
    assert parent_by_id["SHOULDER_R"] == "CHEST"
    assert parent_by_id["UPPER_ARM_R"] == "SHOULDER_R"
    assert parent_by_id["FOREARM_R"] == "UPPER_ARM_R"
    assert parent_by_id["HAND_R"] == "FOREARM_R"
    slot_by_id = {slot["id"]: slot for slot in base["slots"]}
    assert slot_by_id["HAND_R"]["bone"] == "HAND_R"
    assert slot_by_id["FRONT"]["bone"] == "HAND_R"
    assert variant["replace_attachment_ids"] == [
        "body_upper_arm_r",
        "body_forearm_r",
        "body_hand_r",
    ]
    additions = variant["add_attachments"]
    assert len(additions) == 5
    assert len({attachment["id"] for attachment in additions}) == 5
    by_role = {attachment["semantic_role"]: attachment for attachment in additions}
    assert by_role["UPPER_ARM_R"]["slot"] == "SHOULDER_R"
    assert by_role["FOREARM_R"]["slot"] == "FOREARM_R"
    assert by_role["HAND_R_OPEN"]["slot"] == "HAND_R"
    assert by_role["HAND_R_GRIP_BACK"]["slot"] == "HAND_R"
    assert by_role["HAND_R_GRIP_FRONT"]["slot"] == "FRONT"
    assert by_role["HAND_R_GRIP_FRONT"]["right_hand_state"] == "GRIP"
    assert variant["right_arm"]["chain"] == [
        "SHOULDER_R",
        "UPPER_ARM_R",
        "FOREARM_R",
        "HAND_R",
    ]
    assert variant["right_arm"]["states"] == ["OPEN", "GRIP"]
    assert variant["right_arm"]["equipment_socket"] == "HAND_R"
    assert variant["proof_contract"]["grip_draw_order"] == [
        "HAND_R_GRIP_BACK",
        "WOODEN_SWORD",
        "HAND_R_GRIP_FRONT",
    ]
    assert variant["proof_contract"]["combat_authority"] == "none"


def _run_node_contract() -> dict:
    script = r"""
const fs = require('fs');
const base = JSON.parse(fs.readFileSync('docs/planning/w2_03_hero_true_2d_skeletal_rig_vertical_slice_005r2/apprentice_p1_skeletal_manifest.json', 'utf8'));
const variant = JSON.parse(fs.readFileSync('docs/planning/w2_03_hero_true_2d_skeletal_rig_vertical_slice_005r2/apprentice_p1_right_arm_manifest.json', 'utf8'));
const api = require('./js/e9/hero_skeletal_rig.js');
const manifest = api.composeManifest(base, variant);
const rig = new api.SkeletalRig(manifest);
const noop = () => {};
const context = {
  canvas: {width: 528, height: 704}, save: noop, restore: noop,
  clearRect: noop, translate: noop, scale: noop, transform: noop,
  beginPath: noop, moveTo: noop, lineTo: noop, closePath: noop,
  clip: noop, drawImage: noop,
};
const canvas = {clientWidth: 528, clientHeight: 704, width: 528, height: 704, getContext: () => context};
const assets = Object.fromEntries(Object.keys(manifest.assets).map(key => [key, {}]));
const expectedAssets = [
  'right_arm_upper_arm_R',
  'right_arm_forearm_R',
  'right_arm_hand_R_open',
  'right_arm_hand_R_grip_back',
  'right_arm_hand_R_grip_front',
];
const finite = value => Number.isFinite(value);
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const near = (left, right) => Math.abs(left - right) <= 1e-8;
assert(rig.bones.size === 15, 'foundation bone count changed');
assert(rig.slots.size === 18, 'foundation slot count changed');
assert(expectedAssets.every(key => manifest.assets[key]), 'missing right-arm asset key');

rig.setEquipment([]);
assert(rig.rightHandState === 'OPEN', 'empty equipment did not select OPEN');
const openIds = rig.getDrawList().map(entry => entry.attachment.id);
assert(openIds.includes('right_arm_hand_R_open'), 'OPEN hand missing');
assert(!openIds.includes('wooden_sword_hand_r'), 'OPEN state has ghost sword');
assert(!openIds.includes('right_arm_hand_R_grip_back'), 'OPEN state has grip back');
assert(!openIds.includes('right_arm_hand_R_grip_front'), 'OPEN state has grip front');
assert(rig.draw(context, assets).missing_assets.length === 0, 'OPEN draw reported missing assets');

rig.setEquipment(['wooden_sword']);
assert(rig.rightHandState === 'GRIP', 'sword equipment did not select GRIP');
const gripRelevant = rig.getDrawList()
  .filter(entry => ['HAND_R_GRIP_BACK', 'WOODEN_SWORD', 'HAND_R_GRIP_FRONT'].includes(entry.attachment.semantic_role))
  .map(entry => entry.attachment.semantic_role);
assert(JSON.stringify(gripRelevant) === JSON.stringify(['HAND_R_GRIP_BACK', 'WOODEN_SWORD', 'HAND_R_GRIP_FRONT']), 'grip draw order is not back/sword/front');
const attachmentByRole = Object.fromEntries([...rig.attachments.values()].filter(item => item.semantic_role).map(item => [item.semantic_role, item]));
assert(rig.slots.get(attachmentByRole.UPPER_ARM_R.slot).bone === 'UPPER_ARM_R', 'upper arm slot is not UPPER_ARM_R');
assert(rig.slots.get(attachmentByRole.FOREARM_R.slot).bone === 'FOREARM_R', 'forearm slot is not FOREARM_R');
assert(rig.slots.get(attachmentByRole.HAND_R_GRIP_BACK.slot).bone === 'HAND_R', 'grip back slot is not HAND_R');
assert(rig.slots.get(attachmentByRole.HAND_R_GRIP_FRONT.slot).bone === 'HAND_R', 'grip front slot is not HAND_R');
assert(rig.slots.get(attachmentByRole.WOODEN_SWORD.slot).bone === 'HAND_R', 'sword slot is not HAND_R');

let previousHand = null;
let previousSword = null;
let swordDetachCount = 0;
let swordFrameLagCount = 0;
const idleSampleTimes = [0, 120, 300, 600, 900, 1200, 1500, 1800, 2100, 2399];
for (let loop = 0; loop < 50; loop += 1) {
  for (const time of idleSampleTimes) {
    rig.setTime(loop * 2400 + time);
    const handWorld = rig.bones.get('HAND_R').world;
    const sword = rig.getAttachmentWorldTransform('wooden_sword_hand_r');
    const swordExpected = api.multiply(handWorld, rig.attachments.get('wooden_sword_hand_r').localMatrix());
    assert(near(sword.tx, swordExpected.tx) && near(sword.ty, swordExpected.ty), 'sword is not composed from HAND_R local transform');
    assert([sword.a, sword.b, sword.c, sword.d, sword.tx, sword.ty].every(finite), 'non-finite sword transform');
    for (const id of ['right_arm_hand_R_grip_back', 'right_arm_hand_R_grip_front']) {
      const attachment = rig.attachments.get(id);
      const actual = rig.getAttachmentWorldTransform(id);
      const expected = api.multiply(handWorld, attachment.localMatrix());
      assert(near(actual.tx, expected.tx) && near(actual.ty, expected.ty), `${id} is not composed from HAND_R`);
    }
    if (previousHand && previousSword) {
      const handMoved = !near(previousHand.tx, handWorld.tx) || !near(previousHand.ty, handWorld.ty);
      const swordMoved = !near(previousSword.tx, sword.tx) || !near(previousSword.ty, sword.ty);
      if (handMoved && !swordMoved) swordFrameLagCount += 1;
    }
    previousHand = handWorld;
    previousSword = sword;
  }
}
assert(swordDetachCount === 0, 'sword detached');
assert(swordFrameLagCount === 0, 'sword lagged behind HAND_R');

for (const [width, height] of [[1440, 900], [1180, 820], [820, 1180], [430, 932]]) {
  const layout = rig.layoutFor(width, height);
  assert(layout.scale > 0 && finite(layout.offset_x) && finite(layout.offset_y), 'responsive layout failed');
}
for (let index = 0; index < 50; index += 1) {
  const cycle = new api.SkeletalRig(manifest);
  cycle.mount(canvas, assets);
  cycle.setEquipment(['wooden_sword']);
  cycle.play();
  cycle.pause();
  cycle.destroy();
  const lifecycle = cycle.lifecycleSnapshot();
  assert(!lifecycle.active_raf && !lifecycle.active_timers && !lifecycle.active_listeners && !lifecycle.active_animation_instances, 'lifecycle leak');
}
console.log(JSON.stringify({
  bones: rig.bones.size,
  slots: rig.slots.size,
  open_state: true,
  grip_state: true,
  grip_draw_order: gripRelevant,
  sword_follows_hand: true,
  sword_detach_count: swordDetachCount,
  sword_frame_lag_count: swordFrameLagCount,
  idle_loops: 50,
  idle_samples_per_loop: idleSampleTimes.length,
  responsive_viewports: 4,
  mount_destroy_50x: true,
}));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_node_runtime_proves_right_arm_chain_states_draw_order_resize_and_cleanup():
    assert "setRightHandState" in RUNTIME_PATH.read_text(encoding="utf-8")
    result = _run_node_contract()
    assert result == {
        "bones": 15,
        "slots": 18,
        "open_state": True,
        "grip_state": True,
        "grip_draw_order": ["HAND_R_GRIP_BACK", "WOODEN_SWORD", "HAND_R_GRIP_FRONT"],
        "sword_follows_hand": True,
        "sword_detach_count": 0,
        "sword_frame_lag_count": 0,
        "idle_loops": 50,
        "idle_samples_per_loop": 10,
        "responsive_viewports": 4,
        "mount_destroy_50x": True,
    }


def test_owner_evidence_is_animated_review_surface_and_presentation_only():
    proof = PROOF_PATH.read_text(encoding="utf-8")
    assert "Owner visual acceptance remains pending." in proof
    assert "wooden_sword" in proof
    assert "right_arm_hand_R_grip_front" not in proof or "manifest" in proof
    assert "inventory" not in proof.lower()
    assert "loadout" not in proof.lower()


def test_owner_animated_evidence_has_all_required_viewports_and_multiple_frames():
    required = {
        "desktop-open-hand-idle.gif",
        "desktop-grip-idle.gif",
        "ipad-portrait-open-hand-idle.gif",
        "ipad-portrait-grip-idle.gif",
        "mobile-portrait-open-hand-idle.gif",
        "mobile-portrait-grip-idle.gif",
        "right-arm-slow-motion-debug.gif",
    }
    assert {path.name for path in EVIDENCE_DIR.glob("*.gif")} >= required
    for name in required:
        path = EVIDENCE_DIR / name
        with Image.open(path) as image:
            assert image.format == "GIF"
            assert image.size[0] > 0 and image.size[1] > 0
            assert getattr(image, "n_frames", 1) >= 2

    browser_results = load_json(EVIDENCE_DIR / "browser-results.json")
    assert browser_results["ok"] is True
    assert {result["label"] for result in browser_results["results"]} == {
        "desktop",
        "ipad-portrait",
        "mobile-portrait",
        "desktop-debug-slow-motion",
    }
    assert all(not result["errors"] for result in browser_results["results"])
    assert all(not result["proof"]["missing"] for result in browser_results["results"])
