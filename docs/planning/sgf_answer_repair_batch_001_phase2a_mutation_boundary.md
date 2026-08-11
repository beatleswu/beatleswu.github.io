# SGF-ANSWER-REPAIR-BATCH-001 — Phase 2A Mutation Boundary Reconciliation

Status: READY_FOR_OWNER_MUTATION_BOUNDARY_REVIEW

This phase is analysis and immutable candidate-artifact generation only. The revoked 54-group / 65-record umbrella batch is preserved as historical evidence and has not been mutated or applied.

## Locked source

- `SOURCE_SAFE_BATCH_SHA256=388bba6fb0a2c8c9f7c087f1516816b34262b3c98c43737bb9ac85a55037c696`
- `SOURCE_SAFE_BATCH_FILE_SHA256=24fc6f0c8459146d3894ff92e0e7169977f86afdd72d3cd966477b197b6afe97`
- `SOURCE_MANIFEST_SHA256=b3f7daf67b458805ccdbbb51569af49be40d79903e7d830a73bd9929f47bed20`
- `SOURCE_REPAIR_PLAN_SHA256=81e8b958193a34271fa29e3478f92c0237601bf6482b76922af38c2ecf8ac5d6`

## Corrected mutation-boundary model

- Historical umbrella: `FULLY_APPLYABLE_END_TO_END` = THE_COMPLETE_HYPOTHETICAL_REPAIR_PLAN_REACHED_THE_OWNER_DESIRED_VERDICT
- Corrected lanes: `SAFE_NATIVE_SGF_BATCH_001` and `FALLBACK_REMEDIATION_CANDIDATE_BATCH_001`
- `PHASE1B_CLASSIFICATION_ROOT_CAUSE=A_AND_B: Phase 1B intentionally simulated hypothetical fallback removal, then classified plan-level end-to-end reachability without separating it from the later authorization-specific mutation boundary`
- Phase 1B intentionally removed the stored fallback in its in-memory simulated record. It therefore proved plan-level reachability, not that an SGF-only authorization could execute every plan.
- The old Phase 1B artifacts are not silently rewritten. These Phase 2A artifacts supersede only their mutation-boundary terminology.

### Decomposition method

- The exact committed 54-group / 65-record safe artifact was partitioned only by its machine-recorded `planned_operations` value.
- Exact `REWRITE_NATIVE_ROOT_ANSWER_SET` records entered Lane A; exact `CLEAR_PRECOMPUTED_KATAGO_FALLBACK` records entered Lane B. Mixed or unknown operation signatures would fail closed.
- Every compact record was joined back to the committed Phase 1B manifest by review-group key, legacy question ID, current record index, and source path before evidence was copied.
- The partition is exhaustive and disjoint: `4 + 61 = 65` records and `4 + 50 = 54` groups.

## Lane A — SAFE_NATIVE_SGF_BATCH_001

- `GROUPS=4`
- `RECORDS=4`
- `IDS=7998,8057,8092,8100`
- `CANONICAL_SGF_REWRITE_REQUIRED=YES`
- `FALLBACK_MUTATION_REQUIRED=NO`
- `ALL_FINAL_EFFECTIVE_MATCH=YES`
- `SAFE_NATIVE_SGF_BATCH_SHA256=6fd56597f599ce1be117ac2558aaa6a2e19ffb2531d802278cedc3d97f1d1b0a`
- `SAFE_NATIVE_SGF_BATCH_FILE_SHA256=47d08829116ffb60bd5e29062c228c394cc81ee6a0758dc9e4a1394cd5c3a69a`

| Question | Current effective by surface | Owner desired | Post-SGF rewrite by surface | Fallback unchanged | Match |
| ---: | --- | --- | --- | --- | --- |
| 8057 | daily=E2; friend=E2; main=E2; map=E2; rating=E2,Q16 | E2, Q16 | daily=E2,Q16; friend=E2,Q16; main=E2,Q16; map=E2,Q16; rating=E2,Q16 | YES (`Q16`) | YES |
| 8092 | daily=E1; friend=E1; main=E1; map=E1; rating=E1,Q17 | E1, Q17 | daily=E1,Q17; friend=E1,Q17; main=E1,Q17; map=E1,Q17; rating=E1,Q17 | YES (`Q17`) | YES |
| 8100 | daily=P18; friend=P18; main=P18; map=P18; rating=P18,Q4 | P18, Q4 | daily=P18,Q4; friend=P18,Q4; main=P18,Q4; map=P18,Q4; rating=P18,Q4 | YES (`Q4`) | YES |
| 7998 | daily=C2; friend=C2; main=C2; map=C2; rating=C16,C2 | C16, C2 | daily=C16,C2; friend=C16,C2; main=C16,C2; map=C16,C2; rating=C16,C2 | YES (`C16`) | YES |

## Lane B — FALLBACK_REMEDIATION_CANDIDATE_BATCH_001

- `GROUPS=50`
- `RECORDS=61`
- `SGF_REWRITE_REQUIRED=NO`
- `FALLBACK_REMEDIATION_REQUIRED=YES`
- `PER_RECORD_FALLBACK_CLEAR_SAFE=61`
- `FALLBACK_CLEAR_REQUIRES_FURTHER_REVIEW=0`
- `NOT_SAFE_TO_CLEAR=0`
- `SAME_CONTENT_DUPLICATE_GROUPS=6`
- `DUPLICATE_RECORDS=17`
- Of the six duplicate groups, three have the same fallback value across their records and three have different per-record fallback values. No fallback field is shared by content hash.
- `FALLBACK_REMEDIATION_CANDIDATE_BATCH_SHA256=8f86e709306d5f6c0e46d6cad9b5094bebb9eaf618bf0c0d16ab12c237e2d422`
- `FALLBACK_REMEDIATION_CANDIDATE_BATCH_FILE_SHA256=8db0585194e7b8f33f012a5e8f091e0090d3cfbaae1b0c5116fbfeead866a0f8`

Every candidate below retains per-question provenance. Same-content duplicate records remain separate `questions.json` fields; content grouping does not merge their identity or fallback value.

| Question | Review group | Native | Owner desired | Current fallback | Current effective | Proposed action | Simulated final | Match | Safety |
| ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8413 | `c983d3aea650b7f819199830675f96b2e4e2bc7bbc6c3db4682d104b9289a0e9` | O19 | O19 | Q4 | O19, Q4 | clear `katago_best_move` | O19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8189 | `8ffa35807b44b1b40595418eac4b95631d8a54e384a49b4c439824f82c5c5fe8` | Q17 | Q17 | Q4 | Q17, Q4 | clear `katago_best_move` | Q17 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41862 | `8ffa35807b44b1b40595418eac4b95631d8a54e384a49b4c439824f82c5c5fe8` | Q17 | Q17 | D17 | D17, Q17 | clear `katago_best_move` | Q17 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41960 | `8ffa35807b44b1b40595418eac4b95631d8a54e384a49b4c439824f82c5c5fe8` | Q17 | Q17 | D17 | D17, Q17 | clear `katago_best_move` | Q17 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 7958 | `83d1dfeff494c84a51cb12260a39f97f9e7f56b18f8a829348069097d7456df9` | S18 | S18 | R4 | R4, S18 | clear `katago_best_move` | S18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 7993 | `0cac695d17a603c59e2f376e47b212744ebcaeb9d6d8ae15a11bac1b1e0f5d01` | S17 | S17 | D17 | D17, S17 | clear `katago_best_move` | S17 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 7956 | `eedb38205c2db498d55eaa67e24b0a908840d2a7ea308eb6b98e7f527adcb032` | F3 | F3 | D17 | D17, F3 | clear `katago_best_move` | F3 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8117 | `7ca77b0e640922c0d53914e499f4a21eecd8ea40e08e24f90431c9c6606826b0` | O19 | O19 | Q4 | O19, Q4 | clear `katago_best_move` | O19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 7989 | `2ce569fa8896fe309aa74ba68a70ec04206cb28f43d3edfac9554e61ac0653db` | E2 | E2 | D16 | D16, E2 | clear `katago_best_move` | E2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 73069 | `45818fe2438c997dba9ebdbeae66762e0a8c03d1577701f8dc7d73a126bd3484` | E1 | E1 | D16 | D16, E1 | clear `katago_best_move` | E1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 73632 | `f744bd055978e1ccbde06a5b0b71150a851438b312b404dcd3bd9e986bbfd0b6` | D2 | D2 | Q16 | D2, Q16 | clear `katago_best_move` | D2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 37624 | `12fd3d8277edbf2c9b3535ffaadffa4bacbb7cf16db110e108783b7ad1364a83` | N18, S18 | N18, S18 | D4 | D4, N18, S18 | clear `katago_best_move` | N18, S18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 65063 | `94917d59b2f909a02a4232d66b16c6db47fe23f8e29e2eb8c917812f7950919b` | A4 | A4 | C16 | A4, C16 | clear `katago_best_move` | A4 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 73096 | `8fbe5abd819510ffded984592395713466b855fe6d06b2f95f8cc984674a34f8` | A2 | A2 | D16 | A2, D16 | clear `katago_best_move` | A2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 73121 | `2e79cef46199c7c60a865b656b17e94aeb92db64a37e675f860c361b11b33643` | C1 | C1 | Q4 | C1, Q4 | clear `katago_best_move` | C1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 73212 | `25d37303899c7eefad666d825d1b55612c754b0c390cc587c1d7cfc4b7a4ed17` | E2 | E2 | Q16 | E2, Q16 | clear `katago_best_move` | E2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8069 | `f9719c534575e18cd2cebfb595b9103d8ff95b3dac9b90cd3c18499697ddc383` | S19 | S19 | R4 | R4, S19 | clear `katago_best_move` | S19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8122 | `7574678786d7014d2d728e1bc9fb85808a08ce2069651b814cf5ae28207a843d` | P17 | P17 | R4 | P17, R4 | clear `katago_best_move` | P17 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8134 | `c013687c466263306d47b9be9808c5b8612514294d6a56721bb6aa0118784db1` | E3 | E3 | Q16 | E3, Q16 | clear `katago_best_move` | E3 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8137 | `0ba943b4f7fcc0260050293ffb4425b98b5d8f950e45da1d32ca1414cb875379` | Q19 | Q19 | D17 | D17, Q19 | clear `katago_best_move` | Q19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 7961 | `c954ce7426624c5a5859faa08575b7eef504d370f51b514fe0b4ff0e73aac09c` | B2 | B2 | C16 | B2, C16 | clear `katago_best_move` | B2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 7980 | `8b640a44f3b686fd31510282b4ebf266904ff85e0e4221c7c242d3ebd20194a7` | S18 | S18 | D17 | D17, S18 | clear `katago_best_move` | S18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 7999 | `2ec2a48f005fd3a05e0ca505e5d8d303aad6cbb979133584469bef58882d07eb` | S17 | S17 | R4 | R4, S17 | clear `katago_best_move` | S17 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8005 | `5568aa1157fd0ab5fd00159758f88b63c07dd0a948f5f07b4c7b24ab61d31cb3` | E4 | E4 | C16 | C16, E4 | clear `katago_best_move` | E4 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8009 | `1ade70efcbd36ca7835ee4d4309ec012c79e9f6a2eabe67631967ffbfc7f87bf` | C1 | C1 | Q16 | C1, Q16 | clear `katago_best_move` | C1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8020 | `8bc6109e4bd5edff6540db7974e4fe034c32b306cbc000d848975bcb651f61a0` | B2 | B2 | Q4 | B2, Q4 | clear `katago_best_move` | B2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8033 | `93dc7260e6722228480aeada9a1f481e3dc9cd37aeacd30693b7ed9515ee5b35` | E4 | E4 | C16 | C16, E4 | clear `katago_best_move` | E4 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8188 | `a25ae0fae2d455096081e8e3379dd5613abbe5bb418a95206fd2e65e6324f564` | E3 | E3 | C16 | C16, E3 | clear `katago_best_move` | E3 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41959 | `a25ae0fae2d455096081e8e3379dd5613abbe5bb418a95206fd2e65e6324f564` | E3 | E3 | C16 | C16, E3 | clear `katago_best_move` | E3 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41931 | `1a3a228af0a412d30597327bc313c21d037445dd59393425c933b311d5174934` | J19 | J19 | R5 | J19, R5 | clear `katago_best_move` | J19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8163 | `1a3a228af0a412d30597327bc313c21d037445dd59393425c933b311d5174934` | J19 | J19 | Q4 | J19, Q4 | clear `katago_best_move` | J19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41833 | `1a3a228af0a412d30597327bc313c21d037445dd59393425c933b311d5174934` | J19 | J19 | Q4 | J19, Q4 | clear `katago_best_move` | J19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41951 | `1af01d54c3392f56884d3131ea6b5568c63ae1bbaa09eb59ff0506d7d72faa9e` | C2 | C2 | D16 | C2, D16 | clear `katago_best_move` | C2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8181 | `1af01d54c3392f56884d3131ea6b5568c63ae1bbaa09eb59ff0506d7d72faa9e` | C2 | C2 | Q3 | C2, Q3 | clear `katago_best_move` | C2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41853 | `1af01d54c3392f56884d3131ea6b5568c63ae1bbaa09eb59ff0506d7d72faa9e` | C2 | C2 | Q4 | C2, Q4 | clear `katago_best_move` | C2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 64952 | `962b89557947f8a139a3b81fda2dc6e64f7af6b69a7094ded19e628559bdad29` | S19 | S19 | Q4 | Q4, S19 | clear `katago_best_move` | S19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 65106 | `bc01b2c688439401f029557636fdb1a6dd74e2f1ba21391560bb4d02bcdbbeb2` | B1, B4 | B1, B4 | Q3 | B4, B1, Q3 | clear `katago_best_move` | B4, B1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 72868 | `22099cc7cf2a91fef776744f941612964b295fec41c0dcd85c8c43cdc2ef12f7` | B1 | B1 | Q4 | B1, Q4 | clear `katago_best_move` | B1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 73581 | `521041fa11d33ee519e23fed219895510c114935863581b462fb298080b2dd5d` | B1 | B1 | Q4 | B1, Q4 | clear `katago_best_move` | B1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8095 | `3da37d57150feb6d834fcb2257ed02cfdfa9079cfcd116cd2dd5d766df101077` | S19 | S19 | D17 | D17, S19 | clear `katago_best_move` | S19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8128 | `143853e8392b272c874a8b1a5fb75f633f5a7b53f99385c6d54dffcfb5d4bb6b` | B6 | B6 | D16 | B6, D16 | clear `katago_best_move` | B6 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8001 | `87a0441ca0bcfaa7e4b96a3e7054c785c78cd2de45d6560ccb0221a67c85fa66` | S19 | S19 | Q4 | Q4, S19 | clear `katago_best_move` | S19 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8012 | `06e81c6fe91d1c0d057b9dd00b7bdbc8a5dfa3ce5b3c619bcd386e353657c141` | A2 | A2 | Q3 | A2, Q3 | clear `katago_best_move` | A2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8056 | `2db22c0ff0795188e2bdde5e26911afcae55e7fd2c4dde4bc9a93973197321c0` | T17 | T17 | R4 | R4, T17 | clear `katago_best_move` | T17 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8088 | `4b5185b547d42291ff71554146199013a5ef7953ad2e949e6fadc9bca3f773c0` | C2 | C2 | Q3 | C2, Q3 | clear `katago_best_move` | C2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8091 | `13f6fdf7b27facb743e7d3a89423b1c6c3f1bf930cf89b894e8de5095adb4c0d` | T18 | T18 | R4 | R4, T18 | clear `katago_best_move` | T18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8097 | `faa45d63c166cc943792c679ea6d719019d5ebc0c210a466defa0fb28da2a18c` | F1 | F1 | C16 | C16, F1 | clear `katago_best_move` | F1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8112 | `dd47e47939b175064be790c88b00aae62c675083372387173ab5ac982f7a825d` | C2 | C2 | Q3 | C2, Q3 | clear `katago_best_move` | C2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8124 | `bf0cd3a52787983f4c1e4fc22e8a5aea87d95cb340d9f3db7c72f6ae55808b72` | S18 | S18 | D16 | D16, S18 | clear `katago_best_move` | S18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8129 | `f9760f16a1ace695dadaf23a50a1508114c0f0c6981e569e3cfc462ac8c456ce` | R18 | R18 | D16 | D16, R18 | clear `katago_best_move` | R18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8132 | `dae7a09f5d0d19c0f955de84793e21abd61cafe67f1bad31a748d218a1849635` | A2 | A2 | Q4 | A2, Q4 | clear `katago_best_move` | A2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 7960 | `49a15db251c94f572482835bcbc55f024484f9b96e941414263cc4482e7076fc` | P18 | P18 | Q4 | P18, Q4 | clear `katago_best_move` | P18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 7969 | `336b8e0aa333ac0d4e5922c8e9159ce7b310b1c6b2ead06eb71e01b5b8f2aa21` | Q18 | Q18 | D17 | D17, Q18 | clear `katago_best_move` | Q18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8036 | `89537a4e8d90eb6aba96cb3d0319b8ca9f11afda680799e96dee6b218b190713` | C2 | C2 | Q3 | C2, Q3 | clear `katago_best_move` | C2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8040 | `91bc4a298ece7e454bf614c02c9076f6827b91e55aa6aa133cc16399ff7f3d20` | C2 | C2 | Q3 | C2, Q3 | clear `katago_best_move` | C2 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8162 | `5c26de779011a37f63631251257ad05e456a5e89ba15188ef7cc12d73fd742fd` | D1 | D1 | Q3 | D1, Q3 | clear `katago_best_move` | D1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41832 | `5c26de779011a37f63631251257ad05e456a5e89ba15188ef7cc12d73fd742fd` | D1 | D1 | Q3 | D1, Q3 | clear `katago_best_move` | D1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41930 | `5c26de779011a37f63631251257ad05e456a5e89ba15188ef7cc12d73fd742fd` | D1 | D1 | Q3 | D1, Q3 | clear `katago_best_move` | D1 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 8209 | `0b33d853e0fa2f64e31a74b42c69aa6d4fc2391dfd96fc206183130a91715cbd` | P18 | P18 | Q4 | P18, Q4 | clear `katago_best_move` | P18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41884 | `0b33d853e0fa2f64e31a74b42c69aa6d4fc2391dfd96fc206183130a91715cbd` | P18 | P18 | Q4 | P18, Q4 | clear `katago_best_move` | P18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |
| 41982 | `0b33d853e0fa2f64e31a74b42c69aa6d4fc2391dfd96fc206183130a91715cbd` | P18 | P18 | Q4 | P18, Q4 | clear `katago_best_move` | P18 | YES | `PER_RECORD_FALLBACK_CLEAR_SAFE` |

## Exact fallback implementation trace

- `FALLBACK_SOURCE_FIELD=katago_best_move`
- `FALLBACK_STORAGE_LOCATION=QUESTIONS_JSON_PATH per-question record; Production config resolves it to /app/data/questions.json in persistent go-data`
- `FALLBACK_STORAGE_TYPE=PERSISTENT_QUESTIONS_JSON_CONTENT_NOT_DATABASE_NOT_SGF`
- `FALLBACK_RUNTIME_LOAD_PATH=app._load_questions -> app._build_rt_pool -> pool_q.katago_best_move -> app._rt_server_verify`
- `FALLBACK_PROVENANCE=HISTORICAL_OWNER_SIDE_OFFLINE_KATAGO_PREPROCESSING; PER_RECORD_LINEAGE_UNRESOLVED; KATAGO_RUNTIME_IN_PRODUCTION=NO`
- `FALLBACK_GENERATION_HISTORY=Owner-confirmed offline preprocessing before upload. Historical local comparison-log evidence records visits=300, local=True, write=False; that log does not prove how the current per-record values were persisted, so exact per-record lineage remains unresolved.`
- `FALLBACK_ACCEPTANCE_CONDITION=Rating Test only: exactly one submitted move equals the session-transformed stored fallback after accepted/native legacy replay has not returned true`
- `RATING_TEST_CONSUMER_PATH=POST /api/rating_test/answer -> _rt_server_verify`
- `GAMEPLAY_CONSUMER_PATH=NO_NON_RATING_GAMEPLAY_VERDICT_CONSUMER_FOUND; main practice, daily challenge, friend challenge, and Map Battle use native SGF and/or accepted_moves`
- `PROPOSED_CLEAR_REPRESENTATION=SET_PER_RECORD_KATAGO_BEST_MOVE_TO_EMPTY_STRING`
- `VERIFIED_OVERRIDE=rating_verified_questions.json would take precedence, but the file is absent from the canonical tree and not packaged`
- Other consumers: Rating Test answer response informational best_move field; question/curriculum metadata APIs; Shadow candidate evidence (observational only)

The current planner's `CLEAR_PRECOMPUTED_KATAGO_FALLBACK` means setting the individual record's `katago_best_move` to an empty string. In Production that would be a mutation of persistent `/app/data/questions.json`; it is not an SGF edit, DB mutation, or image/build-artifact edit. This phase performs none of those mutations.

## Safety conclusion for the 61 fallback-only records

- Native SGF already exactly represents the Owner-desired accepted set for all 61 records.
- The historical fallback adds one unwanted Rating Test acceptance for all 61 records.
- No candidate uses fallback as its only answer source; every candidate retains at least one native answer.
- No candidate has `accepted_moves` metadata, and clearing fallback removes no Owner-desired move.
- Clearing changes Rating Test verdict and removes informational/observational fallback evidence (`best_move` response and Shadow candidate evidence); it does not change non-Rating gameplay verdicts.
- These findings establish candidate safety only. Mutation remains separately Owner-gated.

## Explicit exclusions and invariants

- `QUESTION_15436_INCLUDED=NO`
- `QUESTION_15388_INCLUDED=NO`
- `QUESTION_65095_INCLUDED=NO`
- Manual reconstruction, stale 74535/35389, and all 47 unresolved older-snapshot groups remain excluded.
- `CANONICAL_SGF_MUTATED=NO`
- `FALLBACK_DATA_MUTATED=NO`
- `QUESTIONS_JSON_MUTATED=NO`
- `ACCEPTED_MOVES_MUTATED=NO`
- `PRODUCTION_DB_MUTATED=NO`
- `KATAGO_RUN=NONE`
- `IDENTITY_IMPLEMENTED=NO`
- `MERGE=NO`
- `DEPLOY=NO`
