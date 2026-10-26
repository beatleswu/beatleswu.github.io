# G027 permanent protected-source policy — security review and bounded exception
2026-10-26. Governance PR engineering ONLY. No Ruleset update, governance merge, G114 merge, Oracle deploy or student-data edits authorized.

## Reusable CI source integrity
Master pull_request_target workflow checks out protected workflow_sha into trusted/ and PR head into candidate/. Only the protected master verifier is executed. PR files are static Git blobs, never executed. GitHub token permissions contents:read, checkout persist-credentials:false.

Separate Owner source authorization is the GitHub administrator-controlled repository Actions variable G027_OWNER_APPROVED_RELEASE_V1_B64, never a PR file. It contains strict base64 JSON keys: schema, repository, pr_number, base_sha, base_tree, product_sha, product_tree, head_sha, head_tree, approver, decision_id, issued_at, expires_at, mode. Schema G027_REUSABLE_OWNER_SOURCE_APPROVAL_V1; repository beatleswu/beatleswu.github.io; approver beatleswu; decision_id prefix G027-; mode exact_two_parent_merge; expiry max 14 days. GitHub admin setting controls authorization; a self-declared approver string alone is NOT proof. Owner GO_MERGE/GO_DEPLOY remain separate.

Verifier compares protected workflow/base SHA, repo/base/head repo, PR number, exact source SHAs and trees, exact Product-then-protected-base parent commits, independently recomputed Git merge-tree, and all protected .github files, G027/G112 verifiers, Owner historic anchor and CODEOWNERS from protected base. Even if approval packet is spoofed by PR files, PR changes to control plane or injected Product blob fail closed. Missing/expired admin variable fails; future release needs only administrator update of this variable, not protected workflow edits.

Repository collaborator audit: only beatleswu with admin access currently confirmed. Do not impose an impossible second-person CODEOWNER review. Independent Claude + Reviewer engineering assessments and actual Owner administrator decision are retained separately.

## Local evidence
tests/test_g027_reusable_trusted_source_gate.py: 11 PASS, 0 FAIL native disposable Git tests, real verifier functions, no production network/CI settings mutation. Positive exact tree; negatives absent/malformed/expired approval, PR/SHA forgery, Product tree substitution, untrusted workflow, injected Product blob, PR-modified protected workflow, fork, wrong owner, reversed commit ancestry. The test approval is synthetic and must NEVER be installed as actual repository Actions variable.

## Ruleset 25328621 — precise OWNER-AUTHORIZED exception ONLY after dual review
Current actual GET: active on refs/heads/master; rules deletion, non_fast_forward, pull_request restrictions with 0 approvers and required review thread resolution, plus required_status_checks with ONLY g027-vnext-trusted-source (integration_id 15368); bypass_actors empty. Original governance PR will fail legacy hosted G027 because the PROTECTED current workflow pins PR #445/G111. This is expected and not bypassable by PR-provided changes.

After Claude and independent Reviewer formally ACCEPT source and Owner separately approves EXACT governance PR merge and minimal Ruleset exception:
1. Administrator performs fresh Ruleset GET via gh api repos/beatleswu/beatleswu.github.io/rulesets/25328621; saves complete baseline JSON SHA/time/operator. Stop on scope or policy drift.
2. Construct minimal PUT request to /repos/beatleswu/beatleswu.github.io/rulesets/25328621 using original name, target, enforcement, conditions, rules and bypass_actors; OMIT only the single required_status_checks rule. Preserve deletion, non_fast_forward and pull_request parameter values unchanged. Never disable whole Ruleset, add bypass or force push.
3. Re-query actual Ruleset immediately; inspect structured diff showing ONLY this one rule removed and all other controls remain active. Log admin operator, before/after config hashes, time and audit IDs. Stop if any unexpected change/API denial.
4. Merge ONLY approved Governance PR via ordinary review/merge (no direct master write) within exception window, record real master and governance SHAs. Do NOT merge G114 or any other PR under exception.
5. Immediately restore the required_status_checks rule with exact original context g027-vnext-trusted-source and integration_id 15368 using Ruleset PUT; re-query to verify original full four-rule policy and original scope/approval/restrictions, archive JSON and hashes. Stop and escalate if restoration fails.
6. Reintegrate new governance master into G114 draft PR #448 by normal merge, no force, keeping accepted Product 3067b6ad07059241e524d0e5737327abd6b8c5fb and deployment Product blobs identical. New head SHA/tree will change; Owner separately approves exact new PR+source identifiers via administrator-only Actions variable. The new protected workflow must run hosted G027 PASS on real PR #448 before requesting distinct Owner GO_MERGE G114.
7. Only after separate GO_MERGE and fresh near-cutover backup+restore Gate may Owner grant separate GO_DEPLOY for Oracle app+scheduler+static+Service Worker. Existing student data may not be overwritten by an older snapshot.

No Ruleset PUT or Merge is authorized by the engineering instruction that created this plan.

## G009
Historical g009-source-snapshot still pins earlier source; not currently the Ruleset required context. Leave unchanged in this governance PR, separately investigate any true security bugs.

## Reviewer security checklist
Validate actual master-sourced workflow/ref SHA, admin variable permission and audit, PR cannot self-approve, no candidate execution/secret exposure, immutable Product/tree/merge identity, bad SHA/blob/control-plane rejection and no new single-user CODEOWNER deadlock. Distinguish local 11 PASS from governance hosted old-check FAIL; no claim of new hosted PASS until governance policy legitimately merged/restored and Owner approval set.


## C1/C2 extension review 2026-10-27

The initial direct exact_two_parent_merge Owner approval contract remains valid for new PRs, but does NOT support G114 #448 after normal no-force integration of future protected governance master. The subsequently added reviewed_product_merge_chain mode explicitly requires a deterministic source-only chain of up to twelve first-parent merge commits, each with an approved historical protected-master second parent, and rejects any intervening ordinary unreviewed commit. Latest second parent must equal the current Owner-approved master. All source SHA/tree invariants, protected control-plane comparisons and expiry/Owner variable requirements remain mandatory.

A separate GitHub REST premerge provenance audit is required because native Ruleset required-check context is a name+Actions App ID and is not bound to the workflow ID. This audit is a procedural compensating Owner control, not a claim of an unspoofable native GitHub rule; real PR #450 proved same-name green checks can be emitted from unrelated push and pull_request workflow IDs while the official workflow failed. PR #450 was closed and remote branch removed.
Documentation and raw proof: docs/governance/G027_C1_C2_HOSTED_CHECK_OWNER_AUTH_POLICY_20261027.md and D:\g079-artifacts\G027_C1_PR450_SAME_NAME_HOSTED_PROVENANCE_20261027.json. Owner Actions variable was not created; strict=true is a separate future optional change, never part of restoration of the original ruleset.
