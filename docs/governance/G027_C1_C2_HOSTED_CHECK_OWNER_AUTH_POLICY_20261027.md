# G027 C1/C2 — Hosted Check origin and Owner approval freshness
2026-10-27 | PR #449 governance additive review | NO Ruleset change / no production PR merge

## C1 proven: same-name workflow PASS is possible, native bypass NOT established

The trusted workflow currently has ID **396547662**, path .github/workflows/g027-vnext-trusted-source.yml, event pull_request_target; its check job is g027-vnext-trusted-source and Actions App ID 15368.
The protected master workflow inventory has four workflows total and only the trusted G027 currently has that check name.

Owner-authorized isolation used temporary DRAFT PR #450, with a new untrusted ordinary workflow ID **397286037** at .github/workflows/g027-check-collision-probe-20261027.yml. Its only command printed nonproduction marker text, permissions contents:read, no checkout or data write.

Real GitHub REST and Check Run IDs:
- Trusted protected G027 run 40359105262 / Check Job 121699416630, event pull_request_target, FAILURE.
- Untrusted ordinary pull_request run 40359105141 / Check Job 121699410160, SUCCESS with the SAME check name and App ID 15368.
- Untrusted ordinary push run 40359040666 / Check Job 121699177714, SUCCESS with the SAME check name and App ID 15368.
- PR #450 mergeState remained BLOCKED despite those two green checks. This proves NAME+APP source ambiguity, NOT a demonstrated Ruleset bypass.
- PR #450 was immediately CLOSED and its remote experimental branch DELETED after evidence capture. No master/G114/Oracle edits.

C1 raw receipts at D:\g079-artifacts:
G027_C1_PROTECTED_MASTER_WORKFLOW_INVENTORY_20261027.json (SHA256 6688668d758f6c94559eb022bbeb3075ffd0aafa16041087d70cec24773c160c).
G027_C1_PR450_SAME_NAME_HOSTED_PROVENANCE_20261027.json (SHA256 cfb6021c59fbed00c746709b0e05e94367d6d3b48e5078d969d1cd0d45cd311e).
G027_C1_PR450_LIVE_HOSTED_SOURCE_PREFLIGHT_20261027.json (SHA256 6851642d8cb2ebddb529bcb22b4af975d68c52877f34d20993440c881ce4330f): HOLD (three same-name source runs, missing Owner variable, draft, no independently validated source trees).

## Exact independent pre-GO_MERGE procedural compensating control

scripts/release/g027_hosted_check_origin_preflight.py is a READ-ONLY GitHub API tool, separate from Required Check itself.
It maps EVERY same-named Check Run to actual Workflow Run ID, expected Workflow ID 396547662, path, event pull_request_target, Run ID, Job/Check Run ID, GitHub Actions App ID 15368, job conclusion, actual head SHA and PR/base/master relation.
It fails closed if same-named checks from other workflows exist; if more than one is present, regardless of green status; if status or identity differs; if Owner variable is absent/expired/updated after the CI run; if master advanced, PR head changed, or GitHub Git Commit trees and two-parent integration do not match the Owner admin packet.
The tool explicitly labels its outcome as a PROCEDURAL owner-premerge source audit. GitHub Ruleset only matches check name+App, so it is NOT a native cryptographically bound "Require workflows" guarantee. It must be executed IMMEDIATELY BEFORE actual G114 GO_MERGE and its receipts checked by Owner. Any conflict HOLD.

Actual fixed-suite C1/C2 tests: original 11 reusable-gate tests plus 8 hosted provenance/freshness tests: 19 PASS, 0 FAIL. This is local simulation / API negative validation, not hosted release authorization.

## C2 repository permission and freshness findings

GitHub API: repository owner is personal **User**, not Organization; no native organization-level Required Workflow policy was verified available, so DO NOT claim Require Workflows as a real configured protection.
Repository collaborator inventory: only beatleswu (admin) currently visible.
G027_OWNER_APPROVED_RELEASE_V1_B64 repository Actions variable currently DOES NOT EXIST. Do not create one until Owner explicitly approves a PR/source packet. GH App and fine-grained token permissions are NOT fully enumerable via collaborator/Actions-variable REST endpoints. Admin audit must separately review installed apps, PAT scopes / repository rules, changing collaborator grants, and recent variable modifications; never claim complete write-permission census.
Strictly required current source packet: PR id, Product SHA/tree, base SHA/tree, HEAD SHA/tree, Owner decision, issued_at, expires_at; no cached PASS is sufficient after variable update, expiry or a new master.

strict_required_status_checks_policy currently false. RECOMMEND true for a later separately authorized policy change, but note it forces PR up-to-date with master. Do NOT add strict=true secretly to the ONE-TIME restore of original Ruleset.
Exact single-field strict=true draft and exact original restore are saved at:
D:\g079-artifacts\g027-c2-owner-validity-preflight-20261027
Strict=true proposal SHA256 9dc19b92fae4e1ce9cc2afa264718e4fd3a6c836c985fabc2a90f896b4610f76.
Audit receipt SHA256 f8bd194296b533ac66722bd0c50a641d2a2181eed994a2316099e1593bcdc174.
NO Ruleset PUT sent.

## One-time controlled Governance merger: unchanged

Once independent Claude and Reviewer accept the UPDATED Governance PR #449 C1/C2 source and Owner explicitly authorizes the precise temporary exception:
1. Recheck Ruleset 25328621, live master, exact reviewed PR #449 head, and immutable approved diff. Archive pre-change JSON+SHA/time/operator.
2. Temporarily remove ONLY current required_status_checks rule for g027-vnext-trusted-source. Preserve active, pull_request, deletion, non_fast_forward and bypass_actors=[].
3. GET and verify only one expected difference, then merge ONLY Governance #449 through ordinary PR flow while tightly controlling window. Never merge G114/other PR in this window.
4. Immediately restore EXACT original required check context and integration 15368 and strict=false (the original value); GET compare entire rule config; halt on unexpected drift.
5. Separately propose strict=true if Owner later approves a distinct policy change, never inside "restore original".
6. Integrate master into G114 #448 by ordinary no-force merge, keep accepted G114 Product SHA 3067b6ad and all deployable Product blobs unchanged.
7. Owner admin then creates exact up-to-date Actions approval variable; re-run real protected G027 hosted check; execute independent API provenance tool on actual HEAD and require no spoof success results.
8. Only then request separate G114 GO_MERGE; after new encrypted NAS backup + offline restore and rollback planning, separately request GO_DEPLOY. No student data edits under governance authorization.

## Failure handling and future governance

Any workflow/control-plane PR remains fail-closed under G027 and must go through separately Owner-authorized Governance exception; it is not a product bug. If incident occurs while required check is temporarily absent, first restore original Ruleset, then STOP with audit evidence. Owner's existing backup deadline 2026-10-28 15:03:43 Taipei remains.


## Multi-master no-force G114 integration contract (C1 follow-up)

The original reusable G027 verifier permitted only an exact two-parent merge of Product SHA and current protected master. However G114 PR #448 already contains a reviewed historical integration merge. After the Governance PR updates master, normal non-force Git merging creates a NEW HEAD with parents (old reviewed PR head, new protected master), which is not a direct two-parent Product merge.

The updated reusable approval mode **reviewed_product_merge_chain** supports up to 12 first-parent merge layers. Every layer:
- has EXACTLY TWO parents, rejecting any intervening ordinary/unreviewed code commit;
- binds second parent to actual ancestor of current protected master, with top-level second parent EXACT current approved base;
- must match git merge-tree --write-tree of the two actual parents (no hand-inserted code or conflict-resolution source injection);
- maintains all control-plane files identical to the respective trusted master commit at that stage;
- first-parent chain MUST terminate at the exact immutable Owner-approved Product SHA/tree.

The final head/tree, base/tree and Product/tree must still match current administrator Actions approval. The original exact_two_parent_merge mode remains supported for direct new product PRs. New chain mode allows G114 #448 to adopt the governance master via ordinary non-force merge without re-Build or changing Product content.

Local native-Git positive 2-stage clean merge and negative unreviewed intermediate commit tests have been added. Before owner authorizes new G114 PR head after Governance merge, record approved mode reviewed_product_merge_chain and exact new Git SHAs/trees; no old approval packet may be reused.
