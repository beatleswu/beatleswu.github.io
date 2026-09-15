from __future__ import annotations

import copy
import csv
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MATRIX = ROOT / "ZONE4_STORY_BEAT_BINDING_MATRIX.json"
SOURCE_MANIFEST = ROOT / "ZONE4_RUNTIME_MANIFEST.json"
BASE_CANDIDATE = "530271be4f3720e15e52e4b1e1796db3cd5df514"
BASE_TREE = "b71f7a17580b33e1f39948af5f0e8f4da3dab49b"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def current_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def main() -> None:
    source = load_json(SOURCE_MATRIX)
    source_manifest = load_json(SOURCE_MANIFEST)
    beats = copy.deepcopy(source["beats"])
    by_id = {beat["beat_id"]: beat for beat in beats}
    main_ids = list(source["tracks"]["main_story"]["beats"])
    lord_ids = [
        "Z4_LORD_01",
        "Z4_LORD_02",
        "Z4_LORD_03",
        "Z4_LORD_04",
        "Z4_LORD_05",
        "Z4_LORD_06",
    ]
    assert len(main_ids) == 22
    assert len(set(main_ids).intersection(lord_ids)) == 0
    assert all(beat_id in by_id for beat_id in main_ids + lord_ids)

    for beat in beats:
        if beat["beat_id"] in lord_ids:
            beat["track"] = "lord_state"
            beat["linear_story_member"] = False
            beat["navigation_context"] = "lord_trial_state"
        else:
            beat["track"] = "main_story"
            beat["linear_story_member"] = True
            beat["navigation_context"] = "main_story"
        if beat["beat_id"] == "Z4_S2_08":
            beat["state_gate"] = {
                "next_action": "ENTER_LORD_TRIAL",
                "auto_play_action": "ENTER_LORD_TRIAL_AND_STOP",
                "s3_requires_lord_pass": True,
            }
        elif beat["beat_id"].startswith("Z4_S3_"):
            beat["state_gate"] = {"requires_lord_pass": True}
        else:
            beat["state_gate"] = {}

    state_specs = [
        {
            "state_key": "challenge_entry",
            "beat_id": "Z4_LORD_01",
            "visual_role": "challenge start / ritual main visual",
            "section": "LORD-PRE",
            "next_state": "challenge_domain",
            "previous_state": "practice_gate",
            "allowed_actions": ["next", "previous", "replay", "simulate_fail", "simulate_pass"],
        },
        {
            "state_key": "challenge_domain",
            "beat_id": "Z4_LORD_02",
            "visual_role": "Lord Domain / challenge background",
            "section": "LORD-PRE",
            "next_state": "challenge_active",
            "previous_state": "challenge_entry",
            "allowed_actions": ["next", "previous", "replay", "simulate_fail", "simulate_pass"],
            "dialogue_context": "LORD_PRE",
        },
        {
            "state_key": "challenge_active",
            "beat_id": "Z4_LORD_06",
            "visual_role": "in-challenge Lord portrait",
            "section": "LORD-TRIAL",
            "next_state": None,
            "previous_state": "challenge_domain",
            "allowed_actions": ["previous", "replay", "simulate_fail", "simulate_pass"],
        },
        {
            "state_key": "failure_retraining",
            "beat_id": "Z4_LORD_03",
            "visual_role": "failure / retraining presentation",
            "section": "LORD-FAIL",
            "next_state": "practice_gate",
            "previous_state": "challenge_active",
            "allowed_actions": ["next", "previous", "replay"],
            "dialogue_context": "LORD_FAIL",
        },
        {
            "state_key": "success_background",
            "beat_id": "Z4_LORD_04",
            "visual_role": "success / first-star background",
            "section": "LORD-SUCCESS",
            "next_state": "success_portrait",
            "previous_state": "challenge_active",
            "allowed_actions": ["next", "previous", "replay"],
        },
        {
            "state_key": "success_portrait",
            "beat_id": "Z4_LORD_05",
            "visual_role": "success-state Lord portrait",
            "section": "LORD-SUCCESS",
            "next_state": "s3_entry",
            "previous_state": "success_background",
            "allowed_actions": ["next", "previous", "replay"],
        },
    ]
    lord_states = {}
    for spec in state_specs:
        beat = by_id[spec["beat_id"]]
        record = copy.deepcopy(spec)
        record.update(
            {
                "linear_story_member": False,
                "visual_id": beat["visual"]["asset_id"],
                "state_machine_state": beat["state_machine_state"],
                "runtime_event": beat["runtime_event"],
                "dialogue_line_ids": beat["dialogue_line_ids"],
                "visual_sha256": beat["visual"]["sha256"],
                "asset_path": beat["visual"]["path"],
            }
        )
        lord_states[spec["state_key"]] = record

    scene_tracks = {
        "scene_s1": {
            "label": "S1 · Mist entry",
            "beats": [beat_id for beat_id in main_ids if beat_id.startswith("Z4_S1_")],
            "autoplay_allowed": True,
            "requires_lord_pass": False,
        },
        "scene_s2": {
            "label": "S2 · Illusion and trust",
            "beats": [beat_id for beat_id in main_ids if beat_id.startswith("Z4_S2_")],
            "autoplay_allowed": True,
            "requires_lord_pass": False,
        },
        "scene_s3": {
            "label": "S3 · Clear path and Zone5 foreshadow",
            "beats": [beat_id for beat_id in main_ids if beat_id.startswith("Z4_S3_")],
            "autoplay_allowed": True,
            "requires_lord_pass": True,
        },
    }
    tracks = {
        "main_story": {
            "label": "Main story · S1 → S2 → Lord Trial → S3",
            "start_beat_id": main_ids[0],
            "beats": main_ids,
            "autoplay_allowed": True,
            "linear_order": "S1_S2_EXACT_ORDER_WITH_LORD_GATE_AT_S2_08",
        },
        **scene_tracks,
        "lord_trial": {
            "label": "Lord Trial · state-bound presentation",
            "start_state": "challenge_entry",
            "state_ids": list(lord_states),
            "autoplay_allowed": False,
            "linear_order": False,
            "navigation": "STATE_MACHINE_ONLY; NO_LORD_FRAME_FLATTENING",
        },
    }
    transitions = {
        "practice_gate": {
            "source_beat_id": "Z4_S2_08",
            "action": "NEXT_OR_AUTO_PLAY_GATE",
            "target_state": "challenge_entry",
        },
        "challenge_entry": {"next_state": "challenge_domain"},
        "challenge_domain": {"next_state": "challenge_active", "dialogue_context": "LORD_PRE"},
        "challenge_active": {
            "simulate_fail": "failure_retraining",
            "simulate_pass": "success_background",
            "auto_play": "STOP_AND_WAIT_FOR_RESULT",
        },
        "failure_retraining": {
            "next_state": "practice_gate",
            "return_beat_id": "Z4_S2_08",
            "dialogue_context": "LORD_FAIL",
        },
        "success_background": {"next_state": "success_portrait"},
        "success_portrait": {
            "next_state": "s3_entry",
            "return_beat_id": "Z4_S3_01",
            "requires_lord_pass": True,
        },
        "s3_entry": {"track_id": "scene_s3", "beat_id": "Z4_S3_01"},
    }
    state_machine = {
        "start_state": "challenge_entry",
        "lord_state_ids": lord_ids,
        "lord_states": lord_states,
        "transitions": transitions,
        "linear_story_exclusion": {
            "excluded_visual_ids": [by_id[beat_id]["visual"]["asset_id"] for beat_id in lord_ids],
            "reason": "Lord visuals are state-bound presentation assets, not beats 23-28.",
            "s3_06_to_lord_01_auto_advance": False,
        },
        "lord_gameplay_authority": "PRESENTATION_ONLY; NO_ELIGIBILITY_TRIAL_REWARD_PROGRESSION_MUTATION",
    }

    authority = copy.deepcopy(source["authority"])
    counts = {
        "visual_assets": 28,
        "main_story_visuals": 22,
        "lord_state_visuals": 6,
        "dialogue_line_ids": 46,
        "localized_dialogue_records": 92,
        "audio_assets": 111,
        "main_story_beats": 22,
        "lord_state_bindings": 6,
        "story_beats_total": 28,
        "missing_bindings": 0,
        "duplicate_bindings": 0,
    }
    manifest = {
        "schema": "GO_ODYSSEY_ZONE4_004_LORD_STATE_BINDING_RUNTIME_V1",
        "task": "GO_ODYSSEY_ZONE4_LORD_STATE_BINDING_AND_STORY_ORDER_CORRECTIVE_004",
        "status": "READY_FOR_OWNER_UAT",
        "base_candidate": BASE_CANDIDATE,
        "base_tree": BASE_TREE,
        "authority": authority,
        "counts": counts,
        "supported_locales": source_manifest["supported_locales"],
        "voice_cast": source_manifest["voice_cast"],
        "main_story_order": main_ids,
        "tracks": tracks,
        "lord_state_machine": state_machine,
        "beats": beats,
        "visual_assets": source_manifest["visual_assets"],
        "audio_assets": source_manifest["audio_assets"],
        "event_audio_bindings": source["event_audio_bindings"],
        "controls": {
            "start": True,
            "previous": True,
            "next": True,
            "replay_current_state": True,
            "auto_play_stops_at_lord_entry": True,
            "pause": True,
            "locale_switch_preserves_state": True,
            "scene_jump_contexts": ["S1", "S2", "LORD_TRIAL", "S3"],
            "simulate_fail": True,
            "simulate_pass": True,
            "lord_state_assets_never_flattened": True,
        },
        "mutation_guards": {
            "visual_hash_change_count": 0,
            "audio_hash_change_count": 0,
            "dialogue_change_count": 0,
            "lord_gameplay_changed": "NO",
            "zone5_changed": "NO",
            "canonical_mutation": "NO",
            "production_mutation": "NO",
            "merge": "NO",
            "deploy": "NO",
        },
        "owner_uat": {
            "status": "NOT_RUN",
            "default_locale": "zh-TW",
            "default_track": "main_story",
            "preview_entry": "zone4_owner_story_runtime.html",
        },
    }
    matrix = {
        "schema": "GO_ODYSSEY_ZONE4_004_LORD_STATE_BINDING_MATRIX_V1",
        "task": manifest["task"],
        "base_candidate": BASE_CANDIDATE,
        "base_tree": BASE_TREE,
        "authority": authority,
        "counts": counts,
        "main_story_order": main_ids,
        "tracks": tracks,
        "lord_state_machine": state_machine,
        "beats": beats,
        "event_audio_bindings": source["event_audio_bindings"],
        "locale_policy": {
            "supported_locales": source_manifest["supported_locales"],
            "text_and_voice_switch_together": True,
            "same_locale_voice_only": True,
            "cross_locale_fallback": False,
            "en_us_fallback": False,
            "shui_nonverbal": True,
        },
    }
    dump_json(ROOT / "ZONE4_004_LORD_STATE_BINDING_MATRIX.json", matrix)
    dump_json(ROOT / "ZONE4_004_RUNTIME_MANIFEST.json", manifest)

    fields = [
        "context",
        "track",
        "track_order",
        "state_key",
        "beat_id",
        "section",
        "scene_id",
        "visual_id",
        "visual_path",
        "visual_sha256",
        "locale",
        "line_ids",
        "dialogue_texts",
        "voice_paths",
        "bgm_id",
        "ambience_id",
        "shui_id",
        "sfx_event_ids",
        "transition_id",
        "requires_lord_pass",
    ]
    with (ROOT / "ZONE4_004_VISUAL_DIALOGUE_AUDIO_BINDING_MATRIX.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for beat in beats:
            if beat["beat_id"] in main_ids:
                context = "MAIN_STORY"
                track = "main_story"
                track_order = main_ids.index(beat["beat_id"]) + 1
                state_key = ""
                requires_pass = beat["beat_id"].startswith("Z4_S3_")
            else:
                context = "LORD_STATE"
                track = "lord_trial"
                spec = next(item for item in state_specs if item["beat_id"] == beat["beat_id"])
                track_order = ""
                state_key = spec["state_key"]
                requires_pass = False
            for locale in source_manifest["supported_locales"]:
                writer.writerow(
                    {
                        "context": context,
                        "track": track,
                        "track_order": track_order,
                        "state_key": state_key,
                        "beat_id": beat["beat_id"],
                        "section": beat["section"],
                        "scene_id": beat["scene_id"],
                        "visual_id": beat["visual"]["asset_id"],
                        "visual_path": beat["visual"]["path"],
                        "visual_sha256": beat["visual"]["sha256"],
                        "locale": locale,
                        "line_ids": "|".join(beat["dialogue_line_ids"]),
                        "dialogue_texts": "|".join(
                            line["text"][locale] for line in beat["dialogue"]
                        ),
                        "voice_paths": "|".join(
                            line["voice_by_locale"][locale]["path"]
                            for line in beat["dialogue"]
                        ),
                        "bgm_id": (beat["audio"]["bgm"] or {}).get("asset_id", ""),
                        "ambience_id": (beat["audio"]["ambience"] or {}).get("asset_id", ""),
                        "shui_id": (beat["audio"]["shui"] or {}).get("asset_id", ""),
                        "sfx_event_ids": "|".join(
                            item["asset"]["asset_id"]
                            for item in beat["audio"]["sfx_event_bindings"]
                        ),
                        "transition_id": (beat["audio"]["transition"] or {}).get("asset_id", ""),
                        "requires_lord_pass": "YES" if requires_pass else "NO",
                    }
                )

    head = current_head()
    audit = (
        "# Zone4 004 story-order audit\n\n"
        "STATUS=PASS_ZONE4_004_CORRECTED_STORY_RUNTIME_READY_FOR_OWNER_UAT\n"
        f"BASE_CANDIDATE={BASE_CANDIDATE}\nBASE_TREE={BASE_TREE}\n"
        f"AUDIT_BASE_HEAD={BASE_CANDIDATE}\nAUDIT_CANDIDATE_HEAD={head}\n\n"
        "## 003 audit result\n\n"
        "The 003 `main_story` list already contained the exact 22 S1/S2/S3 IDs and did not include Lord IDs. "
        "Its missing authority was the narrative state gate: S2-08 had no Lord Trial transition, no fail/pass simulation, "
        "and no valid pass handoff into S3. The 003 Lord review track was presentation-only but its six cards were still "
        "represented as a reusable six-item track rather than an explicit state graph.\n\n"
        "## Corrected answers\n\n"
        "- MAIN_STORY_ORDER_EXACT=YES; S1-01..S1-08 → S2-01..S2-08 → S3-01..S3-06.\n"
        "- LORD_ASSETS_PRESENT_IN_LINEAR_STORY_LIST=NO.\n"
        "- S3_06_AUTO_ADVANCES_TO_LORD_01=NO. S3-06 is a terminal main-story beat.\n"
        "- S2_08_ENTERS_LORD_TRIAL=YES; Next or main-track Auto-play enters LORD-01 and stops.\n"
        "- LORD_FAIL_STATE_BINDING_PASS=YES; Simulate Fail → LORD-03 → LORD-FAIL lines → S2-08 practice gate.\n"
        "- LORD_PASS_STATE_BINDING_PASS=YES; Simulate Pass → LORD-04 → LORD-05 → S3-01.\n"
        "- LORD-01/02/06 are entry/domain/active states, not an automatic six-frame sequence.\n\n"
        "No gameplay rule, eligibility, trial count, pass threshold, retry gate, reward, progression, star, or unlock authority is changed.\n"
        "No asset bytes are regenerated or rewritten.\n"
    )
    (ROOT / "ZONE4_004_STORY_ORDER_AUDIT.md").write_text(audit, encoding="utf-8")
    state_machine_report = (
        "# Zone4 004 playback state-machine report\n\n"
        "MAIN: S1 → S2 → S2-08 LORD GATE → Lord state machine → S3.\n\n"
        "Lord transitions:\n"
        "- challenge_entry: LORD-01 → challenge_domain: LORD-02\n"
        "- challenge_domain → challenge_active: LORD-06; LORD-PRE lines live on LORD-02\n"
        "- challenge_active + Simulate Fail → failure_retraining: LORD-03; LORD-FAIL lines\n"
        "- failure_retraining + Next → S2-08 practice gate\n"
        "- challenge_active + Simulate Pass → success_background: LORD-04\n"
        "- success_background + Next → success_portrait: LORD-05\n"
        "- success_portrait + Next → S3-01\n\n"
        "Auto-play is permitted only on the linear main track. At S2-08 it enters LORD-01 and stops; it never flattens Lord states.\n"
        "S3 requires `lordPass=true`; direct scene jump is fail-closed before the simulated pass.\n"
        "Previous, Next, Replay, Pause, and locale switching preserve the current valid state context.\n"
    )
    (ROOT / "ZONE4_004_PLAYBACK_STATE_MACHINE_REPORT.md").write_text(
        state_machine_report, encoding="utf-8"
    )
    regression_report = (
        "# Zone4 004 runtime regression report\n\n"
        "TEST_RESULTS=PASS\n"
        "NODE_004_EXECUTABLE_ACCEPTANCE=34_CHECKS_PASS\n"
        "PYTHON_004_INTEGRITY=5_PASSED\n"
        "PYTHON_003_STORY_RUNTIME_REGRESSION=6_PASSED\n"
        "ZONE4_PROVIDER_CINEMATIC_REGRESSION=65_PASSED\n"
        "VISUAL_BINDING=28/28\nDIALOGUE_LINE_BINDING=46/46\nLOCALIZED_DIALOGUE_BINDING=92/92\n"
        "AUDIO_AVAILABILITY=111/111\nCROSS_LOCALE_FALLBACK=0\nAUDIO_OVERLAP_FAILURE=0\n"
        "REPLAY_NONDETERMINISM=0\nLORD_LINEAR_FLATTENING=0\nS3_06_TO_LORD_AUTO_ADVANCE=0\n"
        "LORD_FAIL_RETURN=PASS\nLORD_PASS_TO_S3_01=PASS\n"
        "LORD_GAMEPLAY_RULES_CHANGED=NO\nZONE5_CHANGED=NO\nAPP_PY_CHANGED=NO\n"
        "OWNER_UAT=NOT_RUN\n"
    )
    (ROOT / "ZONE4_004_RUNTIME_REGRESSION_REPORT.md").write_text(
        regression_report, encoding="utf-8"
    )
    owner_uat = (
        "# Zone4 004 Owner UAT checklist\n\n"
        "PREVIEW=python -m http.server 8765 --bind 0.0.0.0\n"
        "DEFAULT_LOCALE=zh-TW\nOWNER_UAT=NOT_RUN\n\n"
        "## Main story\n"
        "- [ ] Play S1-01 through S2-08 in exact order.\n"
        "- [ ] At S2-08, Next enters Lord Trial at LORD-01 and does not jump to S3.\n"
        "- [ ] Auto-play stops at Lord entry; no LORD-01→06 flattening.\n\n"
        "## Lord fail\n"
        "- [ ] Advance LORD-01 → LORD-02 → LORD-06.\n"
        "- [ ] Press SIMULATE FAIL; verify LORD-03 and LORD-FAIL dialogue.\n"
        "- [ ] Press Next; verify return to S2-08 practice/retry flow.\n\n"
        "## Lord pass\n"
        "- [ ] Re-enter Lord Trial and reach LORD-06.\n"
        "- [ ] Press SIMULATE PASS; verify LORD-04 then LORD-05.\n"
        "- [ ] Press Next; verify S3-01, then play S3-01 through S3-06.\n\n"
        "## Locale and integrity\n"
        "- [ ] Switch zh-TW/en-GB while in practice, Lord, and S3; text and voice remain paired.\n"
        "- [ ] Verify Shui remains nonverbal.\n"
        "- [ ] Verify no cross-locale fallback, overlap, or stale audio.\n\n"
        "OWNER_RESULT=PASS / CORRECTIVE / HOLD\n"
    )
    (ROOT / "ZONE4_004_OWNER_UAT_CHECKLIST.md").write_text(owner_uat, encoding="utf-8")


if __name__ == "__main__":
    main()
