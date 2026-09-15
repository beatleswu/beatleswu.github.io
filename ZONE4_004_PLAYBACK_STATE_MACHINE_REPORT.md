# Zone4 004 playback state-machine report

MAIN: S1 → S2 → S2-08 LORD GATE → Lord state machine → S3.

Lord transitions:
- challenge_entry: LORD-01 → challenge_domain: LORD-02
- challenge_domain → challenge_active: LORD-06; LORD-PRE lines live on LORD-02
- challenge_active + Simulate Fail → failure_retraining: LORD-03; LORD-FAIL lines
- failure_retraining + Next → S2-08 practice gate
- challenge_active + Simulate Pass → success_background: LORD-04
- success_background + Next → success_portrait: LORD-05
- success_portrait + Next → S3-01

Auto-play is permitted only on the linear main track. At S2-08 it enters LORD-01 and stops; it never flattens Lord states.
S3 requires `lordPass=true`; direct scene jump is fail-closed before the simulated pass.
Previous, Next, Replay, Pause, and locale switching preserve the current valid state context.
