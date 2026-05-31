mkdir -p audit-pack
cp AUDIT-*.txt audit-pack/
git ls-files > audit-pack/git-files.txt
git diff --stat > audit-pack/git-diff-stat.txt
git diff > audit-pack/git-diff.patch
zip -r audit-pack.zip audit-pack