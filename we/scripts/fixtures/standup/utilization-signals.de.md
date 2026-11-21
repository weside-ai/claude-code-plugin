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
