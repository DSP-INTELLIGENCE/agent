# Repository Instructions

## Read the repo documents
* Examine the files in `docs/`, `roadmap/`, and the source tree to get a feel for the current architecture.

## Normalize
1. **Check repo cleanliness** – if `git status` shows changes or conflicts, create a **normalization** branch first and commit a clean snapshot.
2. The normalization branch is the base for all subsequent milestone work.

## Directory layout (where things belong)
```
docs/        => copy all documentation here
data/patch   => unzip patches here, delete when done
data/zips    => copy all zip files from ~/Downloads here
roadmap/     => put all roadmap plans here
roadmap/milestones/ => put each milestone plan here
```

## Milestone template
1. **Outline** – what the milestone does and what it will accomplish.
2. **Audit/Inspect** – run any scripts, `rgrep`, `git` checks needed for the patch.
3. **Status** – verify the repo is clean and ready for a new branch.

## Patch instruction workflow
* **Create** milestone markdown files and place them in `roadmap/milestones/`.
* **Update** `roadmap/README.md` (or `roadmap/outline.md`) when milestones are finished and tick the checkboxes.

## General patch format
- Package patches as **ZIP** files.
- Unzipped content lives in `data/patch/`.
- Original zip files are copied from `~/Downloads` to `data/zips/` for archival.
- Docs are always copied directly into the repo; no diffs are generated for them.

## Patch workflow stages
1. **Install** – unzip patches to `data/patch` and copy zip files to `data/zips`.
2. **Prepare branch** – create a clean branch for the patch.
3. **Apply** – copy files from `data/patch` into the repository.
4. **Verification** – ensure the patch applied cleanly (`git status`).
5. **Audit/Inspect** – if verification fails, run additional audit scripts.
6. **Tests** – run smoke tests before committing.
7. **Commit** – commit, push, open a PR, and merge.
8. **Cleanup** – remove temporary files and place any generated docs in `roadmap/milestones/`.
9. **Hard Reset** – if something goes wrong, run `git reset --hard origin/main`.
10. **Revert** – as a last resort, revert the repo to a known good state.

---

### How to use the repository
1. **Inspect the architecture** – read the sections above to understand lanes, adapters, endpoints, and semantic controllers.
2. **Add a new lane** – edit the lane configuration in `core/` (or via the CLI) and point it at the desired adapters/endpoints.
3. **Create or enable an adapter** – drop a plugin into `data_agent/plugins/` or implement a new filter in `scripts/`.
4. **Select an LLM endpoint** – run `ollama list` to see available models, then invoke it with the `/model` syntax.
5. **Apply patches** – use `codec-patch.py` or `codec.py patch …` to stage, test, and merge changes in a controlled workflow.

All permanent state changes (new lanes, adapters, or endpoint configs) should be committed and tracked via the roadmap milestones in `roadmap/`.
