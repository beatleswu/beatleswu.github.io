"""Bounded checks for the W2-03 apprentice_p1 skeletal foundation.

These tests prove the engineering contract without claiming that the current
flat art is production-riggable. Owner-art-dependent visual checks stay
explicitly blocked in the manifest/report.
"""

from __future__ import annotations

import json
import hashlib
import struct
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs" / "planning" / "w2_03_hero_true_2d_skeletal_rig_vertical_slice_005r2"
MANIFEST_PATH = PACKAGE / "apprentice_p1_skeletal_manifest.json"
RUNTIME_PATH = ROOT / "js" / "e9" / "hero_skeletal_rig.js"
PROBE_PATH = (
    ROOT
    / "docs"
    / "evidence"
    / "w2_03_hero_true_2d_skeletal_rig_vertical_slice_005r2"
    / "foundation_probe.html"
)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_is_one_hero_presentation_foundation_with_exact_bone_graph():
    manifest = load_manifest()
    assert manifest["hero_id"] == "apprentice_p1"
    assert manifest["presentation_only"] is True
    assert manifest["source_art_mutated"] is False
    assert manifest["new_art_created"] is False
    assert manifest["foundation_status"] == {
        "bone_hierarchy": "IMPLEMENTED",
        "slot_contract": "IMPLEMENTED",
        "attachment_metadata": "IMPLEMENTED",
        "animation_timeline": "IMPLEMENTED",
        "responsive_runtime": "IMPLEMENTED",
        "lifecycle_cleanup": "IMPLEMENTED",
        "production_visual_rig": "BLOCKED_WAIT_OWNER_APPROVED_RIG_ART",
    }
    assert manifest["design_space"] == {
        "width": 1056,
        "height": 1408,
        "coordinate_system": "x-right_y-down",
        "responsive_rule": "fit_design_space_inside_canvas_without_changing_skeleton_coordinates",
    }
    bone_ids = [bone["id"] for bone in manifest["bones"]]
    assert len(bone_ids) == 15
    assert len(bone_ids) == len(set(bone_ids))
    assert {
        "ROOT",
        "PELVIS",
        "LOWER_BODY",
        "TORSO",
        "CHEST",
        "NECK",
        "HEAD",
        "SHOULDER_L",
        "UPPER_ARM_L",
        "FOREARM_L",
        "HAND_L",
        "SHOULDER_R",
        "UPPER_ARM_R",
        "FOREARM_R",
        "HAND_R",
    } == set(bone_ids)
    parent_by_id = {bone["id"]: bone["parent"] for bone in manifest["bones"]}
    assert parent_by_id["ROOT"] is None
    assert parent_by_id["PELVIS"] == "ROOT"
    assert parent_by_id["TORSO"] == "PELVIS"
    assert parent_by_id["CHEST"] == "TORSO"
    assert parent_by_id["HEAD"] == "NECK"
    assert parent_by_id["FOREARM_R"] == "UPPER_ARM_R"
    assert parent_by_id["HAND_R"] == "FOREARM_R"


def test_manifest_has_reusable_slot_and_attachment_contract():
    manifest = load_manifest()
    slot_ids = [slot["id"] for slot in manifest["slots"]]
    assert len(slot_ids) == len(set(slot_ids))
    assert {
        "BACK",
        "TORSO",
        "SHOULDER",
        "CHEST_ACCESSORY",
        "HAND_R",
        "HAND_L",
        "HEAD",
        "FRONT",
    } <= set(slot_ids)
    assert len(manifest["attachments"]) == 18
    attachment_ids = [attachment["id"] for attachment in manifest["attachments"]]
    assert len(attachment_ids) == len(set(attachment_ids))
    for attachment in manifest["attachments"]:
        assert {"id", "item_id", "slot", "asset", "attachment_type", "source_rect", "pivot", "local_transform"} <= set(attachment)
        assert attachment["attachment_type"] == "region"
        assert len(attachment["source_rect"]) == 4
        assert len(attachment["pivot"]) == 2
        assert {"x", "y", "rotation_deg", "scale"} <= set(attachment["local_transform"])
    for item_id in ("wooden_sword", "cloth_robe", "fox_pelt", "lucky_stone"):
        item = manifest["items"][item_id]
        assert {"item_id", "slot", "bone_or_socket", "attachments", "presentation_only"} <= set(item)
        assert item["presentation_only"] is True
        assert item["attachments"]
    assert manifest["items"]["wooden_sword"]["bone_or_socket"] == "HAND_R"
    assert manifest["items"]["lucky_stone"]["bone_or_socket"] == "CHEST"


def test_manifest_proves_source_provenance_and_keeps_art_gate_explicit():
    manifest = load_manifest()
    for asset in manifest["assets"].values():
        assert asset["dimensions"] == [1056, 1408]
        assert len(asset["sha256"]) == 64
        assert asset["derived"] is False
        path = ROOT / asset["path"].lstrip("/")
        payload = path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == asset["sha256"]
        assert payload[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack(">II", payload[16:24]) == (1056, 1408)
    limitations = manifest["source_art_limitations"]
    assert limitations["hero_hidden_pixel_blocker"] is True
    assert manifest["items"]["cloth_robe"]["new_art_required_for_professional_deformation"] is True
    assert manifest["items"]["fox_pelt"]["new_art_required"] is True
    assert manifest["items"]["wooden_sword"]["visual_grip_requires_new_art"] is True
    assert "right_hand_closed_grip" in limitations["wooden_sword_grip_requirement"]
    assert "shoulder underside" in limitations["fox_pelt_requirement"]
    dependencies = manifest["art_dependencies"]
    assert len(dependencies) == 5
    assert [dependency["status"] for dependency in dependencies] == [
        "WAIT_OWNER_APPROVED_ART",
        "WAIT_OWNER_APPROVED_ART",
        "WAIT_OWNER_APPROVED_ART",
        "WAIT_OWNER_APPROVED_ART",
        "WAIT_OWNER_APPROVED_ART",
    ]
    assert {dependency["id"] for dependency in dependencies} == {
        "apprentice_head_hair_rig_patch",
        "apprentice_torso_pelvis_rig_patches",
        "apprentice_arm_hand_rig_patches",
        "cloth_robe_skeletal_segments",
        "fox_pelt_skeletal_mantle_segments",
    }


def test_runtime_uses_real_bones_slots_local_transforms_and_no_flat_overlay_authority():
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    assert "class Bone" in source
    assert "class Slot" in source
    assert "class Attachment" in source
    assert "updateWorldTransforms" in source
    assert "multiply(bone.world, attachment.localMatrix())" in source
    assert "context.transform(" in source
    assert "style.transform" not in source
    assert "position:absolute" not in source
    assert "rpg_wave2_wearable_renderer" not in source
    assert "presentation_only" not in source or "inventory" not in source.lower()


def test_probe_is_explicitly_foundation_only_and_not_a_product_route():
    probe = PROBE_PATH.read_text(encoding="utf-8")
    assert "Final visual rig proof: blocked pending Owner-approved rig art." in probe
    assert "/js/e9/hero_skeletal_rig.js" in probe
    assert "full_loadout" in probe
    assert "inventory or loadout authority" in probe
    assert "hero.html" not in probe


def _run_node_contract() -> dict:
    script = r'''
const fs = require('fs');
const manifest = JSON.parse(fs.readFileSync('docs/planning/w2_03_hero_true_2d_skeletal_rig_vertical_slice_005r2/apprentice_p1_skeletal_manifest.json', 'utf8'));
const api = require('./js/e9/hero_skeletal_rig.js');
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
rig.setEquipment(['wooden_sword', 'cloth_robe', 'fox_pelt', 'lucky_stone']);
rig.setTime(0);
const atStart = rig.getAttachmentWorldTransform('wooden_sword_hand_r');
const handAtStart = rig.bones.get('HAND_R').world;
rig.setTime(600);
const atMotion = rig.getAttachmentWorldTransform('wooden_sword_hand_r');
const handAtMotion = rig.bones.get('HAND_R').world;
if (Math.abs(atStart.tx - handAtStart.tx) > 1e-8 || Math.abs(atStart.ty - handAtStart.ty) > 1e-8) throw new Error('sword is not attached to HAND_R');
if (Math.abs(atMotion.tx - handAtMotion.tx) > 1e-8 || Math.abs(atMotion.ty - handAtMotion.ty) > 1e-8) throw new Error('sword did not follow HAND_R');
if (atStart.tx === atMotion.tx && atStart.ty === atMotion.ty) throw new Error('idle timeline did not move HAND_R');
if (rig.getDrawList().length !== 18) throw new Error('full proof preset did not select 18 attachments');
const desktop = rig.layoutFor(1440, 900);
const ipad = rig.layoutFor(1024, 1366);
const mobile = rig.layoutFor(390, 844);
if (desktop.design_width !== 1056 || ipad.design_height !== 1408 || mobile.scale <= 0) throw new Error('responsive layout contract failed');
for (let index = 0; index < 50; index += 1) {
  const cycle = new api.SkeletalRig(manifest);
  cycle.mount(canvas, assets);
  cycle.setEquipment(['lucky_stone']);
  cycle.play();
  cycle.pause();
  cycle.destroy();
  const lifecycle = cycle.lifecycleSnapshot();
  if (lifecycle.active_raf || lifecycle.active_timers || lifecycle.active_listeners || lifecycle.active_animation_instances) throw new Error('lifecycle leak');
}
console.log(JSON.stringify({
  bones: rig.bones.size,
  slots: rig.slots.size,
  attachments: rig.attachments.size,
  selected: rig.getEquipment().length,
  sword_follows_hand: true,
  idle_moved_hand: true,
  responsive: [desktop.scale, ipad.scale, mobile.scale],
  mount_destroy_50x: true,
}));
'''
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_node_runtime_proves_bone_following_idle_and_50x_cleanup():
    result = _run_node_contract()
    assert result == {
        "bones": 15,
        "slots": 18,
        "attachments": 18,
        "selected": 4,
        "sword_follows_hand": True,
        "idle_moved_hand": True,
        "responsive": result["responsive"],
        "mount_destroy_50x": True,
    }
    assert all(scale > 0 for scale in result["responsive"])
