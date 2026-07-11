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

# Explicit root .py COPY list -- deliberately not a `COPY *.py ./` wildcard.
# Every file here has recorded Git provenance in
# deploy/runtime-source-provenance.json (app.py/shadow_judging.py/
# shadow_dashboard.py are tracked directly on origin/master; the rest were
# recovered from verified local Graph A commits in DEPLOY-GOV-2B-FIX). This
# list must stay in sync with that provenance file and with
# deploy/build-manifest.json's build_inputs.tracked_in_canonical_branch_this_sprint.
COPY app.py ./
COPY shadow_judging.py ./
COPY shadow_dashboard.py ./
COPY scheduler.py ./
COPY katago_explain.py ./
COPY explain_overrides.py ./
COPY grimoire_api.py ./
COPY question_taxonomy.py ./
COPY monster_taxonomy.py ./
COPY chapter_i18n.py ./
COPY backend_i18n.py ./
COPY community_leaderboard_rewards.py ./
# Community Leaderboard Rewards operator tools (dry-run/read-only CLIs) --
# narrow copy, not the whole tools/ directory, since other scripts under
# tools/ carry unrelated dependencies/production risk not needed here.
# Depend on community_leaderboard_rewards.py, copied above.
COPY tools/community_leaderboard_rewards_manual.py /app/tools/community_leaderboard_rewards_manual.py
COPY tools/community_leaderboard_rewards_export_entries.py /app/tools/community_leaderboard_rewards_export_entries.py
COPY tools/community_leaderboard_rewards_real_grant_preview.py /app/tools/community_leaderboard_rewards_real_grant_preview.py
COPY tools/community_leaderboard_rewards_real_grant_commit.py /app/tools/community_leaderboard_rewards_real_grant_commit.py
COPY sgf_engine ./sgf_engine
COPY questions.json srs.db go_learning.db ./
COPY *.html *.js *.json *.png ./
COPY robots.txt sitemap.xml og-image.jpg ./
COPY wgo ./wgo
COPY blog ./blog
COPY docs/testing ./docs/testing

COPY assets/*.png ./assets/
COPY assets/*.webp ./assets/
COPY assets/boards ./assets/boards
COPY assets/community ./assets/community
COPY assets/go_rpg_assets ./assets/go_rpg_assets
COPY assets/go_rpg_assets_v3 ./assets/go_rpg_assets_v3
COPY assets/guild_bounty_assets ./assets/guild_bounty_assets
COPY assets/guild_ui ./assets/guild_ui
COPY assets/hero/accessories ./assets/hero/accessories
COPY assets/hero/accessory_icons ./assets/hero/accessory_icons
COPY assets/hero/characters ./assets/hero/characters
COPY assets/hero/gear_v2 ./assets/hero/gear_v2
COPY assets/hero/gear_v2_icons ./assets/hero/gear_v2_icons
COPY assets/hero/items ./assets/hero/items
COPY assets/hero/*.webp ./assets/hero/
COPY assets/landing_page_assets ./assets/landing_page_assets
COPY assets/monsters ./assets/monsters
COPY assets/shop ./assets/shop
COPY assets/pets/*.webp ./assets/pets/
COPY assets/pets/dragon_anim_v2/*.webp ./assets/pets/dragon_anim_v2/
COPY assets/pets/dragon_anim_lv2/*.webp ./assets/pets/dragon_anim_lv2/
COPY assets/pets/dragon_anim_lv3/*.webp ./assets/pets/dragon_anim_lv3/
COPY assets/pets/horse_anim_v2/*.webp ./assets/pets/horse_anim_v2/
COPY assets/pets/horse_anim_lv2/*.webp ./assets/pets/horse_anim_lv2/
COPY assets/pets/horse_anim_lv3/*.webp ./assets/pets/horse_anim_lv3/
COPY assets/pets/cat_anim_v2/*.webp ./assets/pets/cat_anim_v2/
COPY assets/pets/cat_anim_lv2/*.webp ./assets/pets/cat_anim_lv2/
COPY assets/pets/cat_anim_lv3/*.webp ./assets/pets/cat_anim_lv3/
COPY assets/play_page_assets ./assets/play_page_assets
COPY assets/rating_test ./assets/rating_test
COPY assets/stats ./assets/stats
COPY assets/stones ./assets/stones
COPY assets/storyboards ./assets/storyboards
COPY assets/tiers ./assets/tiers
COPY assets/upgrade_page_assets ./assets/upgrade_page_assets

COPY shorts ./shorts
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["python", "app.py"]
