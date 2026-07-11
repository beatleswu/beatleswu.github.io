# First Image Deployment Checklist

This checklist is for the future Production deployment that follows the tooling merge.

Important:

- PR/tooling merge does not deploy Production.

## Checklist

- [ ] build from merged `master`
- [ ] package and checksum image
- [ ] run read-only preflight
- [ ] record rollback image
- [ ] verify external content mounts
- [ ] confirm `GO_DEPLOY`
- [ ] switch app
- [ ] verify app
- [ ] switch scheduler
- [ ] verify scheduler
- [ ] verify E2.4A
- [ ] verify premium-weekly default safety
- [ ] record release result
- [ ] confirm rollback procedure is ready

## Operator Inputs

- final Production content-path values
- release artifact path
- owner `GO_DEPLOY` authorization

## Stop Conditions

- any checksum mismatch
- any OCI revision mismatch
- any health failure
- any unexpected container image
- any shadow or premium-weekly traceback
- any attempt to mutate PostgreSQL or nginx unnecessarily
