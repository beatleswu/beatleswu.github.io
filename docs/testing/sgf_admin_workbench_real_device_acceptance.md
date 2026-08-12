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

## Temporary remote iPad acceptance

The LAN target can be exposed temporarily through a Cloudflare Quick Tunnel
without exposing port `5080` or PostgreSQL to the Internet. This is not a
staging platform and it has no Production publisher. The URL is HTTPS-only,
unguessable, and revoked when the recorded `cloudflared` process is stopped.

One-time local CLI installation (outside this repository, if needed):

```powershell
winget install --id Cloudflare.cloudflared --exact --scope user
```

The launcher fails closed if the CLI is absent; it never downloads or commits
a third-party binary. With the local acceptance app already running:

1. Start the temporary remote access:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/acceptance/run-lan-acceptance.ps1 -Action StartRemote
   ```

   Copy the printed `REMOTE_ACCEPTANCE_URL=https://...trycloudflare.com` to
   the Owner. The command verifies source SHA, environment identity, login,
   CSRF fail-closed behavior, Admin Workbench API access, and the required
   routes through the actual HTTPS tunnel.

2. From the iPad on any external network, open the printed HTTPS URL and use
   the existing generated acceptance Admin credentials. Test `/index.html`
   and `/admin/sgf-answer-review`; staged repairs and batch handoff remain
   non-Production.

3. Revoke the URL immediately after testing:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/acceptance/run-lan-acceptance.ps1 -Action StopRemote
   ```

   `StopRemote` only stops the PID recorded by this acceptance launcher and
   refuses to stop an unrelated process. `Stop` also revokes any recorded
   tunnel before stopping the local stack.

The current app paths use ordinary HTTPS HTTP/fetch requests; no separate
WebSocket/SSE transport is required for the acceptance flows. Cloudflare
Quick Tunnel still forwards the app's existing transport if an optional
Socket.IO path is encountered.

## Boundaries

- `tests/fixtures/acceptance/questions.json` is the only corpus mounted; it is
  read-only and contains no Production questions.
- The only host-exposed service is the app HTTP port. PostgreSQL is internal to
  the acceptance network and has no host port.
- `GO_ODYSSEY_ACCEPTANCE_PUBLISH_DISABLED=1` and the absence of publisher
  services/credentials make Production content publication unavailable.
- The stack is a reusable local/LAN target for future merged feature SHAs; it
  is not a cloud staging platform or a Production deployment framework.
- Remote access is an ephemeral `cloudflared tunnel --url
  http://127.0.0.1:<acceptance-port>` process. No tunnel token, provider
  credential, or remote URL is stored in Git.
- Codex can verify local HTTP routes and backend identity, but cannot claim an
  iPad Safari pass without the Owner completing the real-device exercise.
