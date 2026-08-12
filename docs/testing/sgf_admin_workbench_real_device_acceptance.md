# SGF Admin Workbench local/LAN acceptance

This is a deliberately isolated, non-Production acceptance target for the
merged SGF Admin Workbench. It uses a dedicated Docker Compose project,
PostgreSQL volume, read-only tracked fixture corpus, and a dedicated HTTP
port. It does not use the Production database, `go-data` volume, content
publisher, rollback runner, or application deployment path.

The launcher verifies the current worktree `HEAD` before starting and the
running app exposes `/api/acceptance/identity`. HTML pages carry a visible
`NON-PRODUCTION ACCEPTANCE` badge with the source SHA. The acceptance image is
tagged with that SHA, so a feature branch or merged SHA cannot drift silently.

## Owner procedure

From `D:\go-website-nonprod-lan-real-device-acceptance-001` (or the checked-out
acceptance branch):

1. Start the isolated target:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/acceptance/run-lan-acceptance.ps1 -Action Start
   ```

   The command prints the LAN URL and a path to a local credentials file. The
   credentials file is outside Git and its passwords are never printed by the
   application.

2. Connect the iPad and Desktop to the same trusted Wi-Fi/LAN. Open the
   printed URL in Safari/Desktop. The default port is `5080`; do not substitute
   the Production URL.

3. Log in with the `owner.acceptance.admin` credentials from the generated
   credentials file. Normal server-side Admin authorization and CSRF checks
   remain active.

4. Exercise `/index.html` and `/admin/sgf-answer-review`:

   - play a fixture question and use **Repair This Question** or **Flag for
     Review**;
   - open the seeded player report and inspect move, verdict, aggregation, and
     provenance;
   - create a staged repair, retest the same question, and confirm the page
     distinguishes **STAGED VERDICT** from **PRODUCTION VERDICT**;
   - stage more than one item and create a batch handoff. Stop at handoff;
     this profile has no Production publisher.

5. Stop the target when finished:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/acceptance/run-lan-acceptance.ps1 -Action Stop
   ```

6. Reset only the acceptance database and seeded review evidence when needed:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/acceptance/run-lan-acceptance.ps1 -Action Reset
   ```

   `Reset` is scoped to the fixed `go-odyssey-acceptance` Compose project and
   removes only its named volumes before reseeding. It cannot target the
   Production Compose project.

## Boundaries

- `tests/fixtures/acceptance/questions.json` is the only corpus mounted; it is
  read-only and contains no Production questions.
- The only host-exposed service is the app HTTP port. PostgreSQL is internal to
  the acceptance network and has no host port.
- `GO_ODYSSEY_ACCEPTANCE_PUBLISH_DISABLED=1` and the absence of publisher
  services/credentials make Production content publication unavailable.
- The stack is a reusable local/LAN target for future merged feature SHAs; it
  is not a cloud staging platform or a Production deployment framework.
- Codex can verify local HTTP routes and backend identity, but cannot claim an
  iPad Safari pass without the Owner completing the real-device exercise.
