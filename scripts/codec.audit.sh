mkdir -p audit-pack/codec 

python -m py_compile codec.py codec-patch.py

rg -n "argparse|def main|subparser|add_parser|patch|zip|apply|status|commit|branch|git|data/patch|data/zip|data/zips|roadmap|milestone" \
  codec.py codec-patch.py tests docs README.md INSTRUCTIONS.md \
  > audit-pack/codec/codec-patch-surface.txt

rg -n "codec|codec-patch|patch workflow|apply_patch|data/patch|data/zip|data/zips" \
  . --glob '!/.git/**' \
  > audit-pack/codec/codec-references.txt

python codec.py --help > audit-pack/codec/codec-help.txt 2>&1
python codec.py status > audit-pack/codec/codec-status.txt 2>&1 || true
python codec.py status --json > audit-pack/codec/codec-status-json.txt 2>&1 || true

python codec-patch.py --help > audit-pack/codec/codec-patch-help.txt 2>&1 || true

git status --short > audit-pack/codec/git-status.txt
git diff --stat > audit-pack/codec/git-diff-stat.txt
