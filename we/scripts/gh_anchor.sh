# Sourced by the PR watchers (watch-pr-checks.sh, watch-pr-conflicts.sh): where their `gh` calls run.
#
# gh_anchor: changes to the repo's main checkout, the parent of `git rev-parse --git-common-dir`,
# and sets ORIGIN_REPO to <owner>/<repo> of a github.com `origin` remote (empty otherwise). The
# main checkout survives removing the worktree the watcher started in, and it keeps the caller's
# directory context: a `gh` that picks its account by the working directory (a shim per
# workplace) answers for the same account as in the caller's repo. Outside a git repo the working
# directory stays. Never `cd /`: from there such a `gh` speaks with the wrong account and answers
# "Could not resolve to a Repository".
# The watchers resolve the repo with `-R`, else `gh repo view` (it follows `gh repo set-default`
# and a fork's upstream), and only when that fails with ORIGIN_REPO.
gh_anchor() {
  local common url slug
  ORIGIN_REPO=""
  common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || return 0
  if url=$(git remote get-url origin 2>/dev/null); then
    slug=$(sed -nE 's#^(git@github\.com:|ssh://git@github\.com/|https://github\.com/)##p' <<<"$url")
    slug=${slug%/}; slug=${slug%.git}
    case "$slug" in
      */*/*|.*|"") ;;
      */*) ORIGIN_REPO=$slug ;;
    esac
  fi
  cd "$(dirname "$common")" || return 0
}
