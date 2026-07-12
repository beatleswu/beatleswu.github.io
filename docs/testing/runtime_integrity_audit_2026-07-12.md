# Runtime Integrity Audit 2026-07-12

- Production deployed commit: `1581d13ebca47f93ea92a597729f431de7e6ed1e`
- Production app image: `go-odyssey-app:1581d13e`
- Current master ref: `master`
- Production commit ref: `origin/master`
- Runtime files audited: `1301`
- Direct served fetches: `50`
- Container-inferred served hashes: `0`
- Clean: `1242`
- Confirmed regressed: `43`
- Static override: `3`
- Cache mismatch: `0`
- Missing: `0`
- Unknown: `0`

## Key Findings

- Provenance coverage is absent in current runtime: `0` governed files out of `1301`
- Referenced-by-source count: `379`
- Authenticated route sampling used the built-in `admin / admin1234` account.
- `sw.js` version in current tree: `v173-mobile-stage-intro-entry`

## Confirmed Affected Files

| path | current master sha256 | production served sha256 | matched historical commit | classification |
| --- | --- | --- | --- | --- |
| `admin.html` | `4f598651073885ef987a4174212a1e9b68f09fac3d5a9139bd9bdc7815ac00c5` | `89cd84dbbfd7c313732933bc58d255336c7ad4440213e79ccb2f9497e9cba158` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `badges.html` | `be8c174498335f70eb5dee647b2e67adcb02ca3d074163400fc09a6f2130f281` | `55a121e4b95bc1d18edcda9b137551df771ee7056a491c8316407e772f34fd70` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/go-ai-improve.html` | `67a5b57987a336c552e4dd754540f5d61457e5b436226c91c8a359e2a12781d8` | `2e35afcf5ba083a3df29cf4ece1114a66ae790ec45985329b334238869b99d36` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/go-rules-for-beginners.html` | `09e416cce412fd489cdf3347e2267de67e23e8efb43ab900cdbae1434cefc266` | `3be3050d680f25fb5bd058750f9884ada7096e6d5e06cd3c9784592bdc6695b6` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/go-scoring-counting.html` | `9873d21b2dbb5aaba861aaedd0d6790589bc340307c39c6110cfd582d93112e5` | `3ff02b32693b7da8206205f7b57604e1ed0723211a074888a5154fb4c2d45cfe` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/go-vs-chess.html` | `caeea1f9f94abdbcc2e0d2b8d72b79898923c33d3a98730ca0ac85270071957d` | `45cd0fa41256fb7ffe646e9512887897b073d347847f0412a67513da93ff62e3` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/how-to-improve-at-go.html` | `60763bbbee8bfaddf79d3aeddafc1cda1ef0d173beafe4172520305500c645b0` | `a8d47c56ee39aa3880f92c3072cadaf019476ce3523ef69a22230dd553c89faf` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/how-to-play-go.html` | `b2cad69170e12d221563192731aca97aaae352e5e17a2ee58ab600b5dd665027` | `143ec9780f529041e6c889aef5e6232225b73e5691b15d4618780ec1623b7541` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/index.html` | `b404d9e73f624828c55f17b1dbac58eb946dec6d98b2fb69b0f788ce487fe980` | `b5b4d559da60a82840d13feda8b6b1c1cd00a855d19697aeb4c69c37daf325d2` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/kids-learn-go-age.html` | `970b9b71e2059535f1e7450e871dd464f0727e2ffdce831444936817ca2512be` | `631aa47c262e315701cff0abbac5c841e72740526ec5a027f7505d01669fc875` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/what-is-life-and-death.html` | `51d02b725e0d12bb211d731972d593dad03ace1319726843f7b2e7f358f3921f` | `3ba7660a79c9276a8a73a0e4481ba936e71748a6b074c3a0ba6f07d967c806e3` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `blog/what-is-tsumego.html` | `81c644e1cc11ea928817ccec76e0f4d7068e6079776e297a826df6ea9c53ce38` | `a7f94f97b8ace463e3b5c94796c7e90526da6cce7c3dff1c66e7a593ae668216` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `bot.html` | `2283b7c52f32fcae00034d186615b5495e3924eeb2e0c18f8daca2e2c2c55897` | `c6cebe240a26f796b380eff80fe7d9c4f338176cc34f14614e2131730b8e6fde` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `community.html` | `b0f5acb60198559d1bd16e2d3015b6ad88eb872297dbc39da7eb65abbf5ab624` | `1b2947d0d76d42d8620a750306c445bf9393a8c1082d7a050b403162ff7dadbe` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `curriculum.html` | `12aca5c48cbef9039b8c6268917650fb6673ae9e5ce38919e9d05101de07352e` | `5ff784277d52d2db3e710e2764e6c386b2fc49f9fee7dba7f2c56628d3a8f784` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `daily_challenge.html` | `94034d465d1a4020cb8db9c76daf3084fd51d4c0712d2e5fb5f003bfbdda0116` | `32e016ae4aa80c24cdb7406559bb9cc9e382d71dde48e382e503ad166ec88212` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `games.html` | `db92970625df75c5f6b80368e3673d809fa46029c81de671d3a38fc719e7c189` | `f1b1d15a719ca8ef2cc2762aa924f5149e187cec3237c9db1502da26a59165a9` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `hero.html` | `87b9530a3df1ca4257e4dbffe1d093649094eaf3dcdf2749e3efd928876a9173` | `b8e3b35d7c4015819d847f57ebd04af125703f86d290a49ab5091c0f1eaa6a98` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `index.html` | `f0ed0a2f804656c32f1a254d69109e06d32b848132398a146c21c1e07a8d2d16` | `bb082baf83e5140a33f0d901fb42a21e1996629bed1e966880fcb63d86752db0` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `inventory.html` | `b4109e664d2f98382918131cf5850eba8f4e174bb874eb4bfa34198f9993e300` | `93e42d3d16a049ff0e00a5c382b55d759f98f3102a13cde06c287452a8aed100` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `landing.html` | `3466c2b94bffafdf72a544ce8149c3de7b95fd129a1d7e2bc5ab8c20b4121192` | `3137dc54b107cd5b154ea63a386973d00ea9cb0cd4ff4b4e8a04958940dc8283` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `manage.html` | `e9d7fb87e260007fc583a0340b9c1d6a60f85fbb8e5512121558d8253df820cb` | `9c8ad231f49ae6ed18fe24763174877116e4f67e3716c77d4e8306b924f6fc93` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `manifest.json` | `b060d0005cf0530be43a7eaa10ab3bd81d6626c13f13dcea78c8c049ac8be18c` | `80b51db4b2dd303d594c33a60c60eaa577da03b7617eac98a754b616da50f6c7` | `3d71012a3147638d9333bdbcaaf8c4da855bdefd` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `mistakes.html` | `dbfa7a93520a9da62a327a6c9648c9487be4b42344cf460897e45d0caeef7d58` | `2ab45cf82d2c9378fa5e330d13c32f9e34d73392dd997e4cccb63c68154beb4f` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `mobile-nav.js` | `3eecb6b45f90d21679476985278627461cfba0990a27d6df289c90220c7d75ce` | `5c428b33101502aa59e173214c4c346e8aa9a9256985caabeaaac5c684e671df` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `monster_trash.js` | `54ac5af7f6a820e35865b874a3d6c7ab36436cb6fdf25fcfb551801410312d17` | `f59ec84dbf7b52234f41ff2f829f5b49906d45fc4eea2aa6b6c66aecb80d7bd8` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `play.html` | `b4c23e20f221ee2d496aca9a68e2eaf380ed48a6a32f462ef5e73c1f3f357e7c` | `b40467d8a080a9a6ebdf56c13d88d6319eb0fca28d28051e19444f77df558b7b` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `profile.html` | `10d16490fd4c7161b03e8c1c8fea10fc47716c9e3ae7f8f829a9c25ab21492cf` | `218447b10af64eb5747470d7f47b341854356285a0e59074b612ba2b12c5b0ee` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `pwa.js` | `866751b1bb64b49f49afc5093f0edf401010f6b44600ec4711b7c9478b11d57b` | `8ef74af6b5a6109c94040cef9487795b1294cced1c68f0c39059c6100367dda5` | `3d71012a3147638d9333bdbcaaf8c4da855bdefd` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `rating_test.html` | `a69ab385eaef03fd4372605e011d29e5fe3a6f8a0663e29da90db2992f26556a` | `8356b00bb19a7e35d9f9056283ff1b4e570c02e899179c07ce1f310ae60286d8` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `robots.txt` | `7e9afffb9b5b7e09f41064bf06fbb4c300f0e31145a86e37d6e139b7f08d0833` | `17db2fcd5f3f440a873aad098adc9d7a86aed166a021ab5ac5ffe6b0e22024dc` | `3d71012a3147638d9333bdbcaaf8c4da855bdefd` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `share_view.html` | `578b912394edf2b64b44a398e4f80f743ecb6b4d8967b4c350333b9f67502008` | `084c90853296119acfacc12ad56f59d1de174ec04b39254b93b3efa55ffde995` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `shop.html` | `ab1dedc7c961fc652db75c2b87f5bb0f63af985b0f1b206201df9621dcff469d` | `36e1d6d011539fe4a956ede6eaccd85a17e544687a6183a08f06901eec0111b5` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `site-nav.js` | `4d9c6ae766ce35f3c91d0327be3bdc2a91e17a2d88002a02e73c470884424eb4` | `2ffad76bd6d9c75e98e55d787a9596a4581a1beee2fd48e882ad5314ac570ac4` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `sitemap.xml` | `5a43a1e407e6c3d14a4d53563d8f00cf97306c4040919b7a2eeb101a5f7f91bd` | `e4be13de68b9a14b82521e3b8eb99b46578b1ad6fc9b9648776b82f40516560e` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `srs.js` | `cd30eb0fdbdf2ba8c428fb8ba445b7bb7ab89e995431925b44cffe8b67d95c61` | `bac408cf15db682453cf6761d66f7e84b7c6610605e9b29758153eaf10ab31fe` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `stats.html` | `7183226ba45d22c396fb4fef6fdfbcb92bac875994234389181274435ffd42c5` | `c4522866e5ca138b01cd1993b9cd5c11114c7b5b8295495b4ebc46e034f2add0` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `terms.html` | `ea83f4079fc1e4462fa6b18f292c6de21a43c3a89c054099dc1932538a37def1` | `9c057fdf967c8444ea65fd3285e49d0676df951df5949ac1488f47ba708f33c6` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `upgrade.html` | `97793aa781e57705cc05edad280cf070496d508d9dfb461242e6bb16e6caff44` | `7adca767202ca8a1379b9ce2e23ac0c12effa8a6d896e99f9037cf677466d14f` | `` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `wgo/stone_skin.js` | `7e950b0045139f2e0f31b64af959341917889d9192cedfcd380984cb3e57ae8e` | `b94287d6140a824f0748e7ff1bcf51d34ed9cc5811a34b572dd3467dccb364b0` | `a15d4a1faad7a98d23eabf82df10d5d71474d20c` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `wgo/wgo.min.js` | `3549d446278aace66bc135ccf5294aaf53955b47afd3cdb0c03633e0bc379e6f` | `24f2c3e3c1c5b1e7af63dc5a5a01efecaf51fbb9f0025c0ed1cea4a50eade8d6` | `b4ebf529cf24ed3a39170591dcd022d473a33ef4` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `wgo/wgo.player.css` | `bf6804cdbc079a120510924435bf593a125a7f0ad241137b4274d5661ef45cdc` | `d8828c3d9217bdd7df319e1c0954a76fbb0e14504c263addeedd33dbacea8d66` | `b4ebf529cf24ed3a39170591dcd022d473a33ef4` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `wgo/wgo.player.min.js` | `ee0b5bee222bffb7759f362280900939ed3ae1118f268d99c5e0585bbb373907` | `7b267ac0ca2f4537fcf0e0bc28a54780bae7dd859ecc5c25a8b3437b0461b2bb` | `b4ebf529cf24ed3a39170591dcd022d473a33ef4` | `REGRESSED_TO_OLD_GIT_VERSION` |
| `chapter_overrides.json` | `2d74a176b4a7d6ad3c3e17ab0375a8dd3c2c33b20d42da8a9c456ddf7177a117` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `daily_final.png` | `b3af4e4aa6eac0ea60d9c53b91913f269d36a6d3c7cf31bc0ac0050c616f157f` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `daily_q.png` | `8a795878b39497d02bfafc3adefc689716181f377249540c3534dbf6ed461dcf` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `daily_q_data.json` | `eee0776e9c6ee0e13de17ab6a81f4a648da048f9da465ad838249e918b91d2a3` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `fb_cover.jpg` | `3910d927eb198149465ccbd8519c1cd5ce0892852bcfa78deddf2b450bfcfde9` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `fb_post_open_pets.jpg` | `cfba08c306c062c78baf87a08fae608a7bf14b7e5e5512ce2737affb076d1f7c` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `go_odyssey_storyboard_4.png` | `9cc4de6c00e2baf7b0d44365df5a121dc28b4a9473be02976d8ae80f9a6a3d1a` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `katago_answer_overrides.json` | `c9ffeeb78ea8e01b3581cec382b0d76995c208bdfdfb9ea41acb73865f5d2e0f` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `katago_checkpoint.json` | `9ce872a0875a98cac3ff5cd9fdfcf76f6c3a02ad9ebc81d2f8795b7f409550ad` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `login.html` | `3fc24fe3d63d855face31ee4c88e38a7abe21c2445b607708d7a0d607e04b4a0` | `515b2c628a6e5889b24e56bb0ced90cdba1563966f269ff8ad83f30ed05b0010` | `` | `SERVED_HASH_MISMATCH` |
| `questions.json` | `55ea08f94be08ac2d11e86dc6d5b2b4e83d73288631e5aa5b4d94876da7dfac7` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `uni_stats.png` | `466b4b46c88eabb1061af1c91186ff70bca60fd2d396e2a2190bd8c2915c8c15` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `youtube_banner_final.jpg` | `c0f49b4611e3879a4c916935273596fd21a5fb70c85aac7acb60b2cdde49ee05` | `788f63fcf2333248f9db9f56ee74faffb91b94fcab0fdb0023cd269e6362b87f` | `` | `SERVED_HASH_MISMATCH` |
| `assets/hero/chibi_rpg_fullbody_pixel_avatar.html` | `24cbc359d134553d1760a4064279169c6fdb4514156607ba14a0e06f59db27e3` | `5787934785db5fe37f2f706b49cda19cfff339ccdaa04f7ff24d2d357d72c5db` | `b4ebf529cf24ed3a39170591dcd022d473a33ef4` | `STATIC_OVERRIDE` |
| `i18n.js` | `44b35176f9470f2ff5190cd870f46cc37750146ce20950abc171734174a9a5be` | `bf84cca277addbdc408e83c55e93559cdb94e710b0a68fe8e43a9ea64c6e672a` | `` | `STATIC_OVERRIDE` |
| `sw.js` | `1e9ae6744d1ffdcb8b125ff4b8db96beda7fdaa8ce7f63befdb973f2e20fcc01` | `150e0ecbef379637c48d53a6e43c20a6610dc384e1adf782a674e8775f9b4aed` | `` | `STATIC_OVERRIDE` |

## Route Audit

| URL | final URL | status | bytes | sha256 |
| --- | --- | --- | --- | --- |
| `/` | `https://godokoro.com/` | `200` | `729281` | `bb082baf83e5140a33f0d901fb42a21e1996629bed1e966880fcb63d86752db0` |
| `/login` | `https://godokoro.com/login` | `200` | `34707` | `515b2c628a6e5889b24e56bb0ced90cdba1563966f269ff8ad83f30ed05b0010` |
| `/admin` | `https://godokoro.com/admin` | `200` | `171189` | `89cd84dbbfd7c313732933bc58d255336c7ad4440213e79ccb2f9497e9cba158` |
| `/upgrade` | `https://godokoro.com/upgrade` | `200` | `42719` | `7adca767202ca8a1379b9ce2e23ac0c12effa8a6d896e99f9037cf677466d14f` |
| `/stats` | `https://godokoro.com/stats` | `200` | `89084` | `c4522866e5ca138b01cd1993b9cd5c11114c7b5b8295495b4ebc46e034f2add0` |
| `/community` | `https://godokoro.com/community` | `200` | `67505` | `1b2947d0d76d42d8620a750306c445bf9393a8c1082d7a050b403162ff7dadbe` |
| `/hero` | `https://godokoro.com/hero` | `200` | `220400` | `b8e3b35d7c4015819d847f57ebd04af125703f86d290a49ab5091c0f1eaa6a98` |
| `/shop` | `https://godokoro.com/shop` | `200` | `64875` | `36e1d6d011539fe4a956ede6eaccd85a17e544687a6183a08f06901eec0111b5` |

## Counts

- CLEAN: `1242`
- REGRESSED_TO_OLD_GIT_VERSION: `43`
- MASTER_ALREADY_REGRESSED: `0`
- RELEASE_PACKAGED_WRONG_SOURCE: `0`
- CONTAINER_MISMATCH: `0`
- STATIC_OVERRIDE: `3`
- SERVED_HASH_MISMATCH: `13`
- SERVICE_WORKER_STALE: `0`
- MISSING: `0`
- UNTRACKED_ASSET: `0`
- UNKNOWN: `0`

## Notes

- The Flask app serves runtime files via `send_from_directory` from the container filesystem; the nginx layer proxies through to the app rather than serving `/opt/go-odyssey-static/current` directly.
- `assets/` files resolve from the static-current mirror in production; for these files, served content matches the static mirror, not the app container.
- For direct HTML/JS routes, the served hash was captured over authenticated HTTP; for asset families, the served hash follows the static-current mirror path validated with live requests.
