## Standup · PROJ-9001 Board answers · 2026-11-14 → 2026-11-21

**Vorhaben:** Board answers lands for every crew.
dient questions per day · line PROJ-9002, PROJ-9003, PROJ-9004, PROJ-9006 · line_goal 2026-11-30
- Questions per day below 5
- Every answer lands in one pass

**Ampel:** rot · **Line:** 1/4 (in_review 1, in_progress 1, selected 1) · **Risiko:** acme/app#13: PROJ-9003: money path · required red

### Erreicht

- acme/app#11 PROJ-9002: board answers api · 2026-11-20
- acme/app#12 PROJ-9006 \| answer log · 2026-11-18
- PROJ-9006 → done · 2026-11-18
- PROJ-9002 → in_review · 2026-11-21

### Was kommt

| Story | Stand | Plan |
|---|---|---|
| PROJ-9002 | in_review | yes |
| PROJ-9003 | in_progress | yes |
| PROJ-9004 | selected | no |
| PROJ-9005 (außerhalb der Line) | in_progress | yes |

### Wartet

- m-9001 → human Q901 · PROJ-9003 · 9.0 h

**Intensität (Trend):** 23.0 h ↑ · Worker 12.0 h · 2 PRs ↑ · done 1 ↑ · CI-Runden je Code-PR 2

### Deine Entscheidungen

| # | Frage | Empfehlung | Löst |
|---|---|---|---|
| Q902 | Schneiden wir PROJ-9011 in zwei? | Ja, zwei Stories. | PROJ-9011 |
| Q901 | Darf #13 gemergt werden? \| one-way | Ja, mergen. | PROJ-9003 |

### Auslastung

| Ressource | belegt | Grenze | frei |
|---|---|---|---|
| Worker | 3 | 4 | 1 |
| Bau-Master | 2 | n/a | n/a |
| Companions | 0 | - | - |
| Test-Slot | w-PROJ-9003 | 1 | Wartende n/a |
| Gate-Lock | - | 1 | - |
| Konten mit Luft | 1 | 2 | - |

- Master idle ohne Worker: m-9010
- Selected ohne Master: PROJ-9004
- Wartestunden: lock 4.5 h
- Flow-Effizienz: 0.04 · CI-Runden je Code-PR: 1

**Signale**

| id | Beleg | Quelle | Schwelle | wer |
|---|---|---|---|---|
| selected_without_master | keys=PROJ-9004 | standup.utilization.idle.selected_without_master | selected keys without master >= 1 | coordinator |
| free_slots_plan_waiting | free_slots=1; keys=PROJ-9004 | standup.utilization.workers.free · plans · board waiting_on | free worker slots >= 1 and a line key without plan or waiting on product | product |
| test_slot_bottleneck | holder=w-PROJ-9003; lock_h=4.5; touch_h=29.0 | standup.utilization.test_slot · utilization.waiting_h.lock | waiters >= 1 or waiting:lock hours > 10% of touch hours | machinery |
| master_idle_without_worker | master=m-9010; epic=PROJ-9010; open_line_keys=PROJ-9011 | standup.utilization.idle.masters | master idle, no live worker, open line keys >= 1 | m-9010 |

### Lücken

- build masters: no limit (no crew key)
- test-slot waiters: no source (we-worker status has no waits field)
- prs: 1 without a key in title or branch
