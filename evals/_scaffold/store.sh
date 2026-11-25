#!/usr/bin/env bash
# The generic crew plus an optimization store: a charter whose `last_broadcast:` lies $1 days back
# (default 30), a ledger with one unproven row past `review_by` and one of a mandatory class, an
# inbox with one role-file add seen once and twelve adds.
set -eu
bash "$(dirname "$0")/crew.sh"
back="${1:-30}"
day() { python3 -c "import datetime,sys; print(datetime.date.today() - datetime.timedelta(days=int(sys.argv[1])))" "$1"; }
s=.weside/optimization
mkdir -p "$s/inbox" .claude/rules .weside/roles
cat > "$s/CHARTER.md" <<C
---
last_optimize: $(day 9)
last_broadcast: $(day "$back")
---

# Charter

Goal: fewer instruction lines that nobody needs.
C
cat > "$s/LEDGER.md" <<L
# Ledger

| date | key | target | decision | evidence | metric | before → after | review_by | change |
|---|---|---|---|---|---|---|---|---|
| $(day 60) | gap--claude-rules-review-md | .claude/rules/review.md | applied | 1 retro line | recurrence | 1 → 0 | $(day 30) | #12 |
| $(day 60) | gap--claude-rules-payments-md | .claude/rules/payments.md | applied | 1 retro line | recurrence | 1 → 0 | $(day 30) | #13 |
L
printf -- '- Before you ask a reviewer, re-read the diff once.\n' > .claude/rules/review.md
printf -- '- A refund over the daily cap waits for the human.\n' > .claude/rules/payments.md
printf '# Ada\n\n- Keep plans short.\n' > .weside/roles/ada.md
entry() { # key target body evidence-line
  cat > "$s/inbox/$(day 2)-$1.md" <<E
---
key: $1
pattern: gap
target: $2
target_repo: this
action: add
confidence: Medium
source: retro
---

$3

## Evidence

- $(day 2) retro session s-$1: $4
E
}
entry gap--weside-roles-ada-md .weside/roles/ada.md \
  'Add to my notes: "I post the plan link in the ticket before I start." Lived practice.' \
  'seen once, worked well'
for n in 1 2 3 4 5 6 7 8 9 10 11 12; do
  entry "gap--docs-topic-$n-md" "docs/topic-$n.md" "Add a line about topic $n." "a session missed topic $n"
done
git add -A && git commit -qm store
