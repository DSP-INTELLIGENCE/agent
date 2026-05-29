# Install these docs

Copy the files in this ZIP into the root of the `DSP-INTELLIGENCE/agent` checkout, preserving paths.

```bash
cd /path/to/agent
unzip /path/to/agent-docs-files.zip -d /tmp/agent-docs-files
cp /tmp/agent-docs-files/README.md README.md
cp /tmp/agent-docs-files/AGENTS.md AGENTS.md
mkdir -p docs
cp /tmp/agent-docs-files/docs/*.md docs/

git status --short
git diff --stat
git diff
```

Suggested commit:

```bash
git add README.md AGENTS.md docs/*.md
git commit -m "docs: establish agent handoff and patch workflow"
```
