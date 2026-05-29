# Patch Runner Integrity

Patch packages may include `checksums.txt`.

When present, checksums are verified before patch metadata or patch contents are trusted.

<!-- agent-codec-docs-tighten-v2-integrity:start -->
## Codec patch runner integrity requirements

Patch review output must explicitly account for added and untracked files.
When `--full-diff` is requested, added text files should have bounded content
previews, and binary/unreadable files should be labeled rather than silently
omitted.

The patch runner must validate package root shape before preflight. A nested ZIP
must be rejected clearly or intentionally resolved to the single package root;
it must not proceed with empty metadata or a missing `change.patch`.

The runner must validate `changed-files.txt` against the applied repository
state before commit. Files listed there should be the files staged for commit;
missing or hidden added files are review failures.

Any temporary extraction/work directories created under `/tmp` by
`codec-patch.py`, the patch installer, or package stages must be cleaned before
exit on success, failure, and interruption.
<!-- agent-codec-docs-tighten-v2-integrity:end -->
