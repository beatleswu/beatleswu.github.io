FROM python:3.12-slim

ARG APP_GIT_SHA=unknown
ARG APP_BUILD_DATE=unknown
ARG SGF_ENGINE_SOURCE_COMMIT=unknown

LABEL org.opencontainers.image.revision="${APP_GIT_SHA}" \
      org.opencontainers.image.created="${APP_BUILD_DATE}" \
      org.opencontainers.image.source="https://github.com/beatleswu/beatleswu.github.io" \
      com.godokoro.sgf-engine.source-commit="${SGF_ENGINE_SOURCE_COMMIT}"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV APP_GIT_SHA=${APP_GIT_SHA}
ENV APP_BUILD_DATE=${APP_BUILD_DATE}
ENV SGF_ENGINE_SOURCE_COMMIT=${SGF_ENGINE_SOURCE_COMMIT}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gnugo libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Explicit root .py COPY list -- deliberately not a `COPY *.py ./` wildcard.
# Per-file provenance for recovered and explicitly governed supplemental
# runtime sources is recorded in deploy/runtime-source-provenance.json. Current
# application modules otherwise retain their ordinary Git lineage. Every COPY
# here must also stay in sync with deploy/build-manifest.json's tracked inputs.
COPY app.py ./
COPY startup_diagnostics.py ./
COPY db.py ./
COPY shadow_judging.py ./
COPY shadow_dashboard.py ./
COPY shadow_event_storage.py ./
COPY scheduler.py ./
COPY community_leaderboard_rewards_scheduler.py ./
COPY katago_explain.py ./
COPY explain_overrides.py ./
COPY xp_settlement.py ./
# B043: close the complete module-scope application dependency graph with
# explicit per-file copies.  These modules are reachable from app.py (or a
# module-scope dependency of app.py); keep the curated image boundary and do
# not replace this list with a Python wildcard or broad root copy.
COPY canonical_acquisition_result.py ./
COPY coin_purchase_authority.py ./
COPY companion_operations.py ./
COPY daily_challenge_authority.py ./
COPY daily_challenge_d5b.py ./
COPY equipment_loadout_service.py ./
COPY equipment_ownership_service.py ./
COPY event_outbox.py ./
COPY item_use_operations.py ./
COPY login_journey_authority.py ./
COPY monster_combat_profiles.py ./
COPY monster_drop_profiles.py ./
COPY monster_encounter_selector.py ./
COPY monster_encounter_selector_runtime.py ./
COPY monster_identity.py ./
COPY monster_profiles.py ./
COPY monster_reward_profiles.py ./
COPY monster_settlement.py ./
COPY battlefield_monster_catalog_authority.py ./
COPY monster_catalog_foundation.py ./
COPY battlefield_monster_catalog_shadow_runtime.py ./
COPY battlefield_monster_catalog_shadow_caller.py ./
COPY monster_catalog_shadow_adapter.py ./
COPY player_presentation_api_contract.py ./
COPY player_presentation_read_service.py ./
COPY player_state_read_model.py ./
COPY premium_claim_operations.py ./
COPY premium_reward_bundle_runtime.py ./
COPY premium_reward_catalog_adapter.py ./
COPY premium_reward_claim_runtime.py ./
COPY premium_v1_revenue.py ./
COPY quest_catalog.py ./
COPY quest_claim_authority.py ./
COPY quest_identity.py ./
COPY quest_period_authority.py ./
COPY quest_progress_authority.py ./
COPY quest_progress_evaluator.py ./
COPY quest_reward_adapters.py ./
COPY quest_runtime.py ./
COPY quest_runtime_api.py ./
COPY quest_runtime_config.py ./
COPY question_capacity_authority.py ./
COPY question_idempotency.py ./
COPY shop_acquisition_result_bridge.py ./
COPY shop_offer_authority.py ./
COPY shop_offer_identity_projection.py ./
COPY spirit_combat_policy.py ./
COPY spirit_combat_runtime.py ./
COPY spirit_lineage.py ./
COPY spirit_runtime.py ./
# B056: these ten modules are production-reachable from app.py (directly or
# through its module-scope dependencies). Keep the runtime dependency closure
# explicit; do not replace this list with a wildcard or broad root copy.
COPY srs_review_authority.py ./
COPY battlefield_boss_reward_service.py ./
COPY mapping_a_wardrobe_runtime.py ./
COPY equipment_shop_offer_authority.py ./
COPY equipment_shop_starter_catalog.py ./
COPY equipment_commerce_service.py ./
COPY adventure_boss_finish_response.py ./
COPY adventure_spirit_unlock_transport.py ./
COPY spirit_adventure_milestone.py ./
COPY lord_trial_answer_service.py ./
# Backend Architecture V1 Wave2 (V1A2 ReviewService / V1A3 transaction and
# MapBattle-handoff boundaries): app.py now imports review_service.py and
# review_contracts.py at startup; review_service.py itself imports
# review_compatibility.py and legacy_review_serializer.py. All four are
# pure, storage/Flask-free modules -- keep them explicit so an image build
# cannot omit one and break app.py's own top-level import.
COPY review_contracts.py ./
COPY review_compatibility.py ./
COPY legacy_review_serializer.py ./
COPY review_service.py ./
COPY grimoire_api.py ./
COPY question_taxonomy.py ./
COPY monster_taxonomy.py ./
COPY chapter_i18n.py ./
COPY backend_i18n.py ./
COPY community_leaderboard_rewards.py ./
COPY rpg_item_registry.py ./
COPY rpg_wave1_lane_b.py ./
COPY rpg_world_npc_registry.py ./
COPY docs/planning/rpg_wave2_lane_a_character_identity_registry_v1.json ./docs/planning/rpg_wave2_lane_a_character_identity_registry_v1.json
# Map Battle V1 is application runtime, not external static content. Keep the
# shared runtime modules explicit so app.py can import the authoritative
# settlement service from the built image.
COPY map_battle_runtime.py ./
COPY map_battle_persistence.py ./
# SGF Owner Review Queue is authenticated, server-persisted repair staging.
# Its detector-derived source is read-only evidence, never canonical content.
COPY sgf_answer_review_queue.py ./
COPY sgf_answer_review_routes.py ./
# SGF Admin Workbench is imported by app.py during process startup. Keep the
# server-side module explicit so image builds cannot omit this runtime import.
COPY sgf_admin_workbench.py ./
COPY sgf_workbench_v2a.py ./
COPY sgf_workbench_v2a_routes.py ./
# The Workbench's PostgreSQL schema path lazily imports these two governed
# migration helpers. Keep the package boundary explicit; do not copy the
# migrations directory wholesale.
COPY migrations/__init__.py ./migrations/__init__.py
COPY migrations/sgf_admin_workbench_v1.py ./migrations/sgf_admin_workbench_v1.py
COPY migrations/sgf_human_review_v2a.py ./migrations/sgf_human_review_v2a.py
# B043: runtime-imported migration helpers are application dependencies, not
# migration execution.  Keep each file explicit; do not copy migrations/.
COPY migrations/coin_purchase_operations_v1.py ./migrations/coin_purchase_operations_v1.py
COPY migrations/companion_operations_v1.py ./migrations/companion_operations_v1.py
COPY migrations/domain_event_outbox_v1.py ./migrations/domain_event_outbox_v1.py
COPY migrations/equipment_canonical_slot_v1.py ./migrations/equipment_canonical_slot_v1.py
COPY migrations/item_use_operations_v1.py ./migrations/item_use_operations_v1.py
COPY migrations/login_journey_v1.py ./migrations/login_journey_v1.py
COPY migrations/monster_encounter_selector_state_v1.py ./migrations/monster_encounter_selector_state_v1.py
COPY migrations/premium_claim_lineage_v1.py ./migrations/premium_claim_lineage_v1.py
COPY migrations/premium_reward_bundle_v1.py ./migrations/premium_reward_bundle_v1.py
COPY migrations/quest_claim_v1.py ./migrations/quest_claim_v1.py
COPY migrations/quest_progress_v2.py ./migrations/quest_progress_v2.py
COPY migrations/question_capacity_lineage_v1.py ./migrations/question_capacity_lineage_v1.py
COPY migrations/review_log_submission_idempotency_v1.py ./migrations/review_log_submission_idempotency_v1.py
# B071A: app.py installs this additive server-only historical leaderboard
# evidence schema during startup; keep the migration explicitly packaged.
COPY migrations/historical_leaderboard_evidence_v1.py ./migrations/historical_leaderboard_evidence_v1.py
COPY migrations/spirit_evolution_events_v1.py ./migrations/spirit_evolution_events_v1.py
# PAY-PLANS-500 hotfix: lazily imported inside _newebpay()/_paypal() (only on
# first payment-route access, not at app startup) -- restored after being
# absent from this explicit COPY list despite app.py already depending on
# them, which made every /api/pay/* route raise an unhandled
# ModuleNotFoundError/500. See deploy/runtime-source-provenance.json.
COPY newebpay.py ./
COPY paypal_api.py ./
# Community Leaderboard Rewards operator tools (dry-run/read-only CLIs) --
# narrow copy, not the whole tools/ directory, since other scripts under
# tools/ carry unrelated dependencies/production risk not needed here.
# Depend on community_leaderboard_rewards.py, copied above.
COPY tools/community_leaderboard_rewards_manual.py /app/tools/community_leaderboard_rewards_manual.py
COPY tools/community_leaderboard_rewards_export_entries.py /app/tools/community_leaderboard_rewards_export_entries.py
COPY tools/community_leaderboard_rewards_real_grant_preview.py /app/tools/community_leaderboard_rewards_real_grant_preview.py
COPY tools/community_leaderboard_rewards_real_grant_commit.py /app/tools/community_leaderboard_rewards_real_grant_commit.py
# B071A: controlled historical restoration tooling; never exposed as a
# public client endpoint.
COPY tools/historical_leaderboard_restoration.py /app/tools/historical_leaderboard_restoration.py
COPY tools/community_leaderboard_rewards_exact_period.py /app/tools/community_leaderboard_rewards_exact_period.py
COPY sgf_engine ./sgf_engine

# ── Curated root static pages/scripts (explicit list, not a wildcard).
# Sourced from the exact commits recorded in
# deploy/runtime-source-provenance.json -- not copied from Production.
# Deliberately excludes debug pages, repair reports, backups, and other
# root-level residue never referenced by app.py's routes.
COPY login.html landing.html index.html terms.html manage.html admin.html \
     shadow_dashboard.html sgf_answer_review.html \
     bot.html daily_challenge.html community.html messages.html \
     share_view.html mistakes.html curriculum.html hero.html \
     rating_test.html shop.html profile.html premium_weekly.html \
     stats.html upgrade.html play.html inventory.html badges.html \
     item_journal.html games.html ./
COPY i18n.js sw.js srs.js monster_trash.js sound.js mobile-nav.js \
     site-nav.js community_reward_notifications.js \
     community_reward_rules.js pwa.js sgf_answer_review.js \
     sgf_admin_workbench_ux_v2.js sgf_workbench_v2a.js ./
COPY review_data/sgf_answer_review_queue_v1.json \
     ./review_data/sgf_answer_review_queue_v1.json
# Legacy Map Battle V1 is an explicitly routed subpath asset. Keep the
# repository-relative path so /js/map_battle_v1_adapter.js resolves in the
# built image exactly as it does from the source tree.
COPY js/map_battle_v1_adapter.js ./js/map_battle_v1_adapter.js
COPY js/rpg_wave2_wearable_renderer.js ./js/rpg_wave2_wearable_renderer.js
# Lord Trial review authority is an explicitly referenced browser module.
# Keep the repository-relative path so the built image retains the same
# /js/game/lord_trial_controller.js identity as the source checkout.
COPY js/game/lord_trial_controller.js ./js/game/lord_trial_controller.js
# Observer-only committed-review presentation dispatch is an explicitly
# referenced browser module and must remain a narrow static copy.
COPY js/game/presentation_dispatcher.js ./js/game/presentation_dispatcher.js
# B2 response-presentation effects are an explicitly referenced browser module
# and must remain a narrow static copy.
COPY js/game/presentation_effects_b2.js ./js/game/presentation_effects_b2.js
# B3 ReviewTransport is an explicitly referenced browser module and must
# remain a narrow static copy.
COPY js/game/review_transport.js ./js/game/review_transport.js
# B4 GameSession identity is an explicitly referenced browser module and must
# remain a narrow static copy.
COPY js/game/game_session.js ./js/game/game_session.js
# B5 QuestionLoader and BoardRenderer are explicit browser runtime modules;
# keep the copies narrow so the image cannot silently absorb unrelated JS.
COPY js/game/question_loader.js ./js/game/question_loader.js
COPY js/game/board_renderer.js ./js/game/board_renderer.js
# B6 ModeContext and B7 GameBootstrap are narrow browser runtime modules;
# keep both explicit so the image cannot absorb unrelated game JavaScript.
COPY js/game/mode_context.js ./js/game/mode_context.js
COPY js/game/game_bootstrap.js ./js/game/game_bootstrap.js
# Zone 1-10 generic cinematic replay is a narrow browser runtime module; keep
# the copy explicit for the same reason as the modules above.
COPY js/game/cinematic_replay.js ./js/game/cinematic_replay.js
# A041 Hero legacy-cache guard is a narrow browser runtime module referenced by
# the server-owned Hero shell; keep the release copy explicit.
COPY js/hero_legacy_cache_guard.js ./js/hero_legacy_cache_guard.js
COPY manifest.json robots.txt sitemap.xml og-image.jpg icon-192.png icon-512.png ./
COPY wgo ./wgo
COPY blog ./blog
# E9 Adventure Shell runtime assets (feature-flagged, default OFF -- see
# js/e9/feature_flags.js). These are tracked application code served by
# app.py's narrow /js/e9/, /css/e9/, /components/adventure/ static routes
# (_serve_live_static_or_baked_subpath), same category as the curated HTML/JS
# above -- NOT external/versioned content like assets/ or questions.json
# (see the "Content and asset boundary" note below). E9.1A2-FIX1: this was
# omitted from the original E9.1A2 COPY list, which meant these routes
# 404'd in every built image despite passing locally (tests read the host
# working tree, not the built image) -- see
# tests/deployment/test_e9_runtime_asset_packaging.py for the regression
# coverage that would have caught this.
COPY js/e9 ./js/e9
COPY css/e9 ./css/e9
COPY components/adventure ./components/adventure
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# ── Content and asset boundary ──────────────────────────────────────
# The following are deliberately NOT copied into this image. They are
# served at runtime from external, read-only or persistent mounts (see
# docker-compose.prod.yml and docs/deployment/canonical_image_build.md,
# "App Image / Content Boundary"). The application already has
# graceful-degradation handling for their absence:
#
#   assets/       -- VERSIONED STATIC ARTIFACT, mounted read-only at
#                     GO_ODYSSEY_LIVE_STATIC_ROOT/assets. app.py's
#                     /assets/<path:subpath> route already falls back to
#                     this mount before any baked copy (see
#                     _serve_live_static_or_baked_subpath); with no baked
#                     copy and no mount, individual files 404, the app
#                     process stays up.
#   shorts/       -- optional marketing media, same mount pattern via
#                     GO_ODYSSEY_LIVE_STATIC_ROOT/shorts. Absence is a
#                     404 per file, not a startup failure.
#   questions.json -- VERSIONED CONTENT BASELINE + persistent runtime
#                     storage. Path is configurable via QUESTIONS_JSON_PATH
#                     (see app.py); _load_questions()/_load_questions_fresh()
#                     already guard with os.path.exists() and return an
#                     empty list rather than crash when absent.
#   srs.db          -- EXCLUDED. Table inventory shows live user data
#                     (users, friendships, game_results, teacher_student,
#                     ...). Never referenced by any sqlite3.connect() call
#                     in current app.py/scheduler.py -- PostgreSQL is the
#                     authoritative runtime database. Must never be baked
#                     into a Git-tracked image.
#   go_learning.db  -- EXCLUDED. Its two tables (zones, grimoires) are
#                     already created directly in PostgreSQL by app.py
#                     (CREATE TABLE IF NOT EXISTS zones/grimoires) --
#                     confirmed obsolete relative to current runtime code.
#   docs/testing/   -- EXCLUDED. Internal QA/audit evidence, zero
#                     references anywhere in app.py/scheduler.py/
#                     shadow_judging.py. Never belonged in a production
#                     image.

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "app.py"]
