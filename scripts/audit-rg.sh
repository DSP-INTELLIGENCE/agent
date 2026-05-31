mkdir -p audit-pack

rg -n "/question|/web|/scrape|/switch|/tool|AgentSpec|AgentScript|semantic router|plugin|plugins|roadmap|deprecated|legacy|obsolete|TODO|FIXME" \
  . --glob '!/.git/**' > audit-pack/stale-refs.txt

rg -n "argparse|click|typer|fire|def main|if __name__ == .__main__.|/prompt|/ground|/summon" \
  . --glob '!/.git/**' > audit-pack/cli-routes.txt

find . -maxdepth 4 -type f | sort > audit-pack/file-inventory.txt
git status --short > audit-pack/git-status.txt
git diff --stat > audit-pack/git-diff-stat.txt
git diff > audit-pack/git-diff.patch

zip -r audit-pack.zip audit-pack