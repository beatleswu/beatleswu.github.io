# Coverage of Discovery

Discovery source: `git -c core.quotepath=false ls-files` on 2026-06-27.

## Repository-wide enumeration

| Category | Enumerated | Treatment |
|---|---:|---|
| All tracked paths | 102,737 / 102,737 | Enumerated. |
| Active first-party paths (excluding tracked backups and `venv311`) | 75,830 / 75,830 | Enumerated by path/type. |
| SGF files | 72,931 / 72,931 | Enumerated; not claimed as manually content-verified. |
| Archived backup paths | 26,907 | Enumerated and excluded from active architecture. |
| Active first-party Python | 128 / 128 | Automated lexical scan; runtime modules deep-read. |
| Archived Python | 69 / 69 | Enumerated; not treated as active behavior. |
| Vendored `venv311` Python | 13,087 / 13,087 | Enumerated; third-party source excluded from application semantics. |
| Active JavaScript | 11 / 11 | Scanned for globals, functions, events and dependencies. |
| Active HTML | 35 / 35 | Scanned for scripts, globals, fetches, handlers and UI systems. |

“Scanned” means every listed file was included in automated repository searches. Deep semantic inspection focused on the active runtime and critical user flows; it does not mean 72,931 SGFs or third-party packages were manually reviewed.

## Python files scanned: 128 / 128

- [x] `_check_17_18.py`
- [x] `_check_nearby_rank.py`
- [x] `_execute_mix.py`
- [x] `_mix_plan.py`
- [x] `_rename_topics.py`
- [x] `app.py`
- [x] `apply_chapter_classification.py`
- [x] `assets/weapons_v6_package/weapon_positioning.py`
- [x] `audit_i18n.py`
- [x] `backend_i18n.py`
- [x] `backfill_newbie_onboarding.py`
- [x] `build_blog.py`
- [x] `build_godokoro_manim_preview.py`
- [x] `build_godokoro_manim_shorts.py`
- [x] `build_godokoro_marketing_shorts.py`
- [x] `build_questions.py`
- [x] `build_rating_anchor_bank.py`
- [x] `build_rating_calibration.py`
- [x] `build_rating_verified.py`
- [x] `build_short1.py`
- [x] `build_shorts_2_8.py`
- [x] `chapter_i18n.py`
- [x] `chattts_worker.py`
- [x] `check_cache.py`
- [x] `check_candidates.py`
- [x] `check_sgf.py`
- [x] `check_visits.py`
- [x] `classify_questions.py`
- [x] `compare_visits.py`
- [x] `compose_daily.py`
- [x] `convert_mgt_to_sgf.py`
- [x] `copy_espeak.py`
- [x] `daily_problem.py`
- [x] `db.py`
- [x] `dl_chattts.py`
- [x] `explain_overrides.py`
- [x] `export_acceptable_lv1_sgfs_for_review.py`
- [x] `export_katago_risky_sgfs_for_review.py`
- [x] `gen_bgm.py`
- [x] `grimoire_api.py`
- [x] `import_reviewed_sgfs.py`
- [x] `katago_apply_full_report.py`
- [x] `katago_batch_classify.py`
- [x] `katago_debug.py`
- [x] `katago_explain.py`
- [x] `katago_final_test.py`
- [x] `katago_monitor.py`
- [x] `katago_persistent_test.py`
- [x] `katago_test.py`
- [x] `katago_verify_answers.py`
- [x] `katago_verify_applied_batch.py`
- [x] `local_classify_test.py`
- [x] `make_chapter_review_xlsx.py`
- [x] `make_guild_ui_assets.py`
- [x] `make_icon.py`
- [x] `make_manim_s1.py`
- [x] `make_manim_s2.py`
- [x] `make_manim_s3.py`
- [x] `make_manim_s4.py`
- [x] `make_manim_s5.py`
- [x] `make_manim_s6.py`
- [x] `make_manim_s7.py`
- [x] `make_manim_s8.py`
- [x] `make_short.py`
- [x] `make_short_cover.py`
- [x] `make_shorts_3_8.py`
- [x] `manim_s1.py`
- [x] `manim_s1_timed.py`
- [x] `manim_s2_timed.py`
- [x] `manim_s3_timed.py`
- [x] `manim_s4_timed.py`
- [x] `manim_s5_timed.py`
- [x] `manim_s6_timed.py`
- [x] `manim_s7_timed.py`
- [x] `manim_s8_timed.py`
- [x] `merge_final_into_questions.py`
- [x] `migrate_sqlite_to_pg.py`
- [x] `monster_taxonomy.py`
- [x] `newebpay.py`
- [x] `normalize_hero_armor_overlays.py`
- [x] `normalize_hero_characters.py`
- [x] `optimize_images.py`
- [x] `paypal_api.py`
- [x] `play_server_addon.py`
- [x] `posts_data.py`
- [x] `precompute.py`
- [x] `premium_weekly.py`
- [x] `premium_weekly_job.py`
- [x] `premium_weekly_service.py`
- [x] `publish_shorts.py`
- [x] `question_taxonomy.py`
- [x] `rating_calibration.py`
- [x] `redraw_hero_assets.py`
- [x] `refine_database.py`
- [x] `reset_v5.py`
- [x] `restore_missing_sgf_from_questions.py`
- [x] `restore_single_katago_answer.py`
- [x] `rollback_katago_acceptable_lv1_answers.py`
- [x] `rollback_katago_remaining_acceptable_answers.py`
- [x] `rollback_katago_risky_answers.py`
- [x] `scheduler.py`
- [x] `setup.py`
- [x] `simulate_rating_anchor_mix.py`
- [x] `solve_problems.py`
- [x] `sync_katago_answers_to_sgf.py`
- [x] `tag_difficulty.py`
- [x] `test_dm.py`
- [x] `test_explain_override.py`
- [x] `test_frame.py`
- [x] `test_gnugo_profile.py`
- [x] `test_grimoire_api.py`
- [x] `test_home_report_panel.py`
- [x] `test_kokoro.py`
- [x] `test_kokoro_all.py`
- [x] `test_newbie_quest.py`
- [x] `test_premium_weekly.py`
- [x] `test_q6_visits.py`
- [x] `test_quest_progress.py`
- [x] `test_rating_anchor_bank.py`
- [x] `test_rating_calibration.py`
- [x] `test_rating_test.py`
- [x] `test_security_regressions.py`
- [x] `test_slime_subjugation.py`
- [x] `test_trial_codes.py`
- [x] `tools/generate_daily_problem_social.py`
- [x] `tools/publish_shorts.py`
- [x] `wsgi.py`
- [x] `youtube_auth.py`

## JavaScript files scanned: 11 / 11

- [x] `i18n.js`
- [x] `mobile-nav.js`
- [x] `monster_trash.js`
- [x] `pwa.js`
- [x] `site-nav.js`
- [x] `sound.js`
- [x] `srs.js`
- [x] `sw.js`
- [x] `wgo/stone_skin.js`
- [x] `wgo/wgo.min.js`
- [x] `wgo/wgo.player.min.js`

## HTML files scanned: 35 / 35

- [x] `admin.html`
- [x] `assets/hero/chibi_rpg_fullbody_pixel_avatar.html`
- [x] `badges.html`
- [x] `blog/go-ai-improve.html`
- [x] `blog/go-rules-for-beginners.html`
- [x] `blog/go-scoring-counting.html`
- [x] `blog/go-vs-chess.html`
- [x] `blog/how-to-improve-at-go.html`
- [x] `blog/how-to-play-go.html`
- [x] `blog/index.html`
- [x] `blog/kids-learn-go-age.html`
- [x] `blog/what-is-life-and-death.html`
- [x] `blog/what-is-tsumego.html`
- [x] `bot.html`
- [x] `community.html`
- [x] `curriculum.html`
- [x] `daily_challenge.html`
- [x] `games.html`
- [x] `hero.html`
- [x] `index.html`
- [x] `inventory.html`
- [x] `landing.html`
- [x] `login.html`
- [x] `manage.html`
- [x] `messages.html`
- [x] `mistakes.html`
- [x] `play.html`
- [x] `premium_weekly.html`
- [x] `profile.html`
- [x] `rating_test.html`
- [x] `share_view.html`
- [x] `shop.html`
- [x] `stats.html`
- [x] `terms.html`
- [x] `upgrade.html`

## Runtime/config files inspected

- [x] `requirements.txt`
- [x] `Dockerfile`
- [x] `docker-compose.prod.yml`
- [x] `entrypoint.sh`
- [x] `nginx/default.conf`
- [x] `deploy.ps1` / `deploy_quick.ps1` classification rules (not executed)
- [x] `AGENTS.md`
- [x] `工作守則.md`

## Discovery limitations

- Production services were not contacted.
- Archived backups and third-party packages were enumerated but not treated as current behavior.
- SGF files were enumerated as a dataset; only representative files were opened during parser/fixture discovery.
- User-authorized untracked files were ignored entirely.
