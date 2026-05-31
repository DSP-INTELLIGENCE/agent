git clone https://github.com/DSP-INTELLIGENCE/agent
cd agent

git status --short
find . -maxdepth 3 -type f | sort > AUDIT-files.txt

# docs/code references to old lanes or stale architecture
rg -n "/question|/web|/scrape|/switch|/tool|AgentSpec|AgentScript|semantic router|plugin|plugins|roadmap|runtime-boundaries|llm-control-plane|session-cache|cli-usage" . \
  --glob '!/.git/**' > AUDIT-stale-refs.txt

# docs index points to missing docs
while read -r f; do test -f "$f" || echo "MISSING $f"; done <<'EOF' > AUDIT-missing-docs.txt
docs/cli-usage.md
docs/runtime-boundaries.md
docs/llm-control-plane.md
docs/session-cache.md
EOF

# inventory docs and Python entrypoints
find . -maxdepth 4 \( -name '*.md' -o -name '*.py' -o -name '*.sh' \) | sort > AUDIT-source-inventory.txt

# TODO/FIXME/deprecated language
rg -n "TODO|FIXME|deprecated|legacy|archive|compat|remove|obsolete|stale" . \
  --glob '!/.git/**' > AUDIT-flags.txt

# CLI route/command definitions
rg -n "argparse|click|typer|fire|def main|if __name__ == .__main__.|/prompt|/ground|/summon" . \
  --glob '!/.git/**' > AUDIT-cli-routes.txt