## Standup · Portfolio · 2026-11-14 → 2026-11-21

| Epic | Ampel | Line | Intensität (Trend) | Nächster Schritt | Risiko |
|---|---|---|---|---|---|
| PROJ-9001 Board answers | rot | 1/4 (in_review 1, in_progress 1, selected 1) | 23.0 h ↑ · 2 PRs ↑ | PROJ-9002 in_review | acme/app#13: PROJ-9003: money path · required red |
| PROJ-9010 Release train | gelb | 0/1 (in_progress 1) | 0.0 h → · 0 PRs → | PROJ-9011 in_progress | PROJ-9011: no work in 48 h |
| PROJ-9020 Flow pane | grün | 0/1 (in_progress 1) | 6.0 h ↑ · 1 PRs ↑ | PROJ-9021 in_progress | - |

### Erreicht

- acme/app#11 PROJ-9002: board answers api · 2026-11-20
- acme/app#14 flow pane lanes · 2026-11-19
- acme/app#12 PROJ-9006 \| answer log · 2026-11-18
- PROJ-9006 → done · 2026-11-18
- PROJ-9002 → in_review · 2026-11-21

### Was kommt

- PROJ-9001: PROJ-9002 in_review
- PROJ-9010: PROJ-9011 in_progress
- PROJ-9020: PROJ-9021 in_progress

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
