# Runtime Governance Contract

Before any formal production deploy, the runtime surface must be inventoried and compared across these layers:

1. Git runtime source
2. Release archive
3. Container filesystem
4. Served HTTP content

If any layer disagrees with the canonical runtime source, deployment is blocked until the mismatch is classified and resolved.

Required artifacts:

- `docs/testing/runtime_integrity_inventory_<date>.csv`
- `docs/testing/runtime_restore_matrix_<date>.csv`
- `docs/testing/runtime_restore_matrix_<date>.md`

Required behavior:

- Generate the inventory automatically before deploy.
- Compare hashes, not filenames.
- Treat static overrides as a separate source-of-truth class.
- Treat generated runtime files as generated, not as hand-restored HTML.
- Fail closed on any mismatch until the source path is known.

Reference implementation:

- `tools/build_runtime_restore_matrix.py`
