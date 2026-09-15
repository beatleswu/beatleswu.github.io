# Zone4 004 Owner UAT checklist

PREVIEW=python -m http.server 8765 --bind 0.0.0.0
DEFAULT_LOCALE=zh-TW
OWNER_UAT=NOT_RUN

## Main story
- [ ] Play S1-01 through S2-08 in exact order.
- [ ] At S2-08, Next enters Lord Trial at LORD-01 and does not jump to S3.
- [ ] Auto-play stops at Lord entry; no LORD-01→06 flattening.

## Lord fail
- [ ] Advance LORD-01 → LORD-02 → LORD-06.
- [ ] Press SIMULATE FAIL; verify LORD-03 and LORD-FAIL dialogue.
- [ ] Press Next; verify return to S2-08 practice/retry flow.

## Lord pass
- [ ] Re-enter Lord Trial and reach LORD-06.
- [ ] Press SIMULATE PASS; verify LORD-04 then LORD-05.
- [ ] Press Next; verify S3-01, then play S3-01 through S3-06.

## Locale and integrity
- [ ] Switch zh-TW/en-GB while in practice, Lord, and S3; text and voice remain paired.
- [ ] Verify Shui remains nonverbal.
- [ ] Verify no cross-locale fallback, overlap, or stale audio.

OWNER_RESULT=PASS / CORRECTIVE / HOLD
