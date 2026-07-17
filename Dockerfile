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
COPY db.py ./
COPY shadow_judging.py ./
COPY shadow_dashboard.py ./
COPY shadow_event_storage.py ./
COPY scheduler.py ./
COPY community_leaderboard_rewards_scheduler.py ./
COPY katago_explain.py ./
COPY explain_overrides.py ./
COPY grimoire_api.py ./
COPY question_taxonomy.py ./
COPY monster_taxonomy.py ./
COPY chapter_i18n.py ./
COPY backend_i18n.py ./
COPY community_leaderboard_rewards.py ./
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
COPY tools/community_leaderboard_rewards_exact_period.py /app/tools/community_leaderboard_rewards_exact_period.py
COPY sgf_engine ./sgf_engine

# ── Curated root static pages/scripts (explicit list, not a wildcard).
# Sourced from the exact commits recorded in
# deploy/runtime-source-provenance.json -- not copied from Production.
# Deliberately excludes debug pages, repair reports, backups, and other
# root-level residue never referenced by app.py's routes.
COPY login.html landing.html index.html terms.html manage.html admin.html \
     shadow_dashboard.html \
     bot.html daily_challenge.html community.html messages.html \
     share_view.html mistakes.html curriculum.html hero.html \
     rating_test.html shop.html profile.html premium_weekly.html \
     stats.html upgrade.html play.html inventory.html badges.html \
     games.html ./
COPY i18n.js sw.js srs.js monster_trash.js sound.js mobile-nav.js \
     site-nav.js community_reward_notifications.js \
     community_reward_rules.js pwa.js ./
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
