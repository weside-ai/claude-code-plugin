# Sourced by the PR watchers (watch-pr-checks.sh, watch-pr-conflicts.sh): where their `gh` calls run.
#
# gh_anchor: with REPO empty, sets it to <owner>/<repo> of the caller's `origin` remote (left empty
# for a remote that is no GitHub URL, so the caller falls back to `gh repo view`); then changes to
# the repo's main checkout, the parent of `git rev-parse --git-common-dir`. The main checkout
# survives removing the worktree the watcher started in, and it keeps the caller's directory
# context: a `gh` that picks its account by the working directory (a shim per workplace) answers
# for the same account as in the caller's repo. Outside a git repo the working directory stays.
# Never `cd /`: from there such a `gh` speaks with the wrong account and answers
# "Could not resolve to a Repository".
gh_anchor() {
  local common url slug
  common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 0
  if [ -z "$REPO" ] && url=$(git remote get-url origin 2>/dev/null); then
    slug=$(sed -E 's#^(git@[^:]+:|ssh://[^/]+/|https?://[^/]+/)##; s#/+$##; s#\.git$##' <<<"$url")
    case "$slug" in
      */*/*|/*|.*|*:*|"") ;;
      */*) REPO=$slug ;;
    esac
  fi
  cd "$(dirname "$common")" || return 0
}
