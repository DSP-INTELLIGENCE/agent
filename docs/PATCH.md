# Patch Workflow

Agent uses staged patch ZIPs. A patch ZIP is both the code/docs patch package
and the staged terminal workflow package.

## Package layout

```text
patch-name.zip
├── README.md
├── change.patch
├── changed-files.txt
├── checksums.txt
├── package-manifest.json
├── patch.json
├── apply_patch.sh
├── tests/
│   ├── smoke.sh
│   └── verify.py
└── stages/
    ├── 00_inspect.sh
    ├── 01_preflight.sh
    ├── 02_apply.sh
    ├── 03_test.sh
    ├── 04_report.sh
    ├── 05_commit.sh
    └── 06_push.sh
```

## Stage rule

```text
One command = one stage = stop.
```

No stage should automatically call the next stage. Inspect must not apply.
Apply must not test. Test must not commit. Commit must not push.

## Manual workflow

```bash
cd ~/Downloads/agent
source .venv/bin/activate

mkdir -p /tmp/PATCH_NAME
rm -rf /tmp/PATCH_NAME/*
unzip -q ~/Downloads/PATCH_NAME.zip -d /tmp/PATCH_NAME

bash /tmp/PATCH_NAME/stages/00_inspect.sh
bash /tmp/PATCH_NAME/stages/01_preflight.sh
bash /tmp/PATCH_NAME/stages/02_apply.sh
bash /tmp/PATCH_NAME/stages/03_test.sh
bash /tmp/PATCH_NAME/stages/04_report.sh
bash /tmp/PATCH_NAME/stages/05_commit.sh "commit message"
bash /tmp/PATCH_NAME/stages/06_push.sh
```

## Live LLM/Ollama policy

Patch tests must avoid live LLM/Ollama calls unless `patch.json` sets
`requires_live_llm` to `true` and the user explicitly approves live checks.

Allowed default checks include static verification, `git apply --check`,
`python -m py_compile`, and focused deterministic pytest groups.

Forbidden by default:

```text
python agent-cli.py prompt "Hello"
python agent-cli.py run --text "/prompt Hello"
anything that invokes live model synthesis
```

## Codex role

Codex is a patch-stage runner. It should run one requested stage, paste exact
output, and stop. It should not design architecture, manually edit files, create
patches, commit, or push unless the requested stage explicitly does that.

<!-- agent-three-llm-lanes:start -->
## Patch direction: three LLM lanes

Patch work should preserve this contract:

- `/prompt` is direct-to-LLM.
- `/ground` is grounded/RAG/evidence-backed and sends the evidence packet to the LLM.
- `/summon` is persona/session control; `/summon prompt <message>` is the explicit persona-routed prompt path.
- Legacy answer-like prompt-template command names are unwired and must not be aliases.

Grounding repair patches should target `/ground`, not legacy command surfaces.
<!-- agent-three-llm-lanes:end -->

<!-- agent-grounded-resolver-memory:start -->
## Patch memory: grounded resolver direction

Checked:

- [x] `/prompt` is direct and must not implicitly ground or summon-route.
- [x] `/ground` is the primary grounded/RAG repair target.
- [x] old answer-like command names are unwired, not aliases.
- [x] `/summon prompt` is the explicit persona-routed prompt path.
- [x] first resolver repair is deterministic and dependency-free.

Next patch direction:

- move grounding toward `GroundingQuery -> EvidencePacket -> render/synthesize`
- keep provider packages optional and behind adapters
- do not add new grounded lane names
<!-- agent-grounded-resolver-memory:end -->

<!-- agent-legacy-semantic-stack:start -->
## Patch policy: semantic stack legacy

Do not patch semantic router, AgentSpec, AgentScript, or encoder layers back into runtime execution. They are legacy/unwired and must not become aliases or hidden front doors.

Patch future grounding work at `/ground` and the EvidencePacket/provider-adapter layer.
<!-- agent-legacy-semantic-stack:end -->

<!-- agent-codec-docs-tighten-v2-patch:start -->
## Active codec-patch workflow

Prefer `codec-patch.py` as the patch operator.

```text
review:
  branch -> inspect -> preflight -> apply -> test -> report

publish:
  commit -> push

merge-cleanup:
  merge -> push -> cleanup
```

The lower-level stage scripts remain implementation details, but the active
operator flow is:

```text
review -> inspect report -> publish -> merge-cleanup
```

Do not publish when any of these are true:

- report hides untracked or newly added files
- `changed-files.txt` and `git status` disagree
- the package is missing `change.patch`, `changed-files.txt`, `patch.json`, or
  `package-manifest.json`
- the package ZIP is nested incorrectly and the runner did not intentionally
  descend into that package root
- whitespace warnings or package validation warnings have not been inspected

Temporary package extraction and work directories under `/tmp` must be cleaned
on every exit path: success, failure, and interruption.
<!-- agent-codec-docs-tighten-v2-patch:end -->
