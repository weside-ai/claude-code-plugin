## Summary

Tightens the master card's start steps.

<!-- coldstart-receipt -->
```json
{
 "status": "green",
 "reasons": [],
 "digest": "@DIGEST@",
 "affected": ["master/a"],
 "runs": 3,
 "tokens": 21000,
 "scenarios": [
  {"id": "master/a", "runs": 3, "hits": 3, "gated": true, "status": "run"},
  {"id": "worker/b", "runs": 10, "hits": 10, "gated": true, "status": "rate"}
 ]
}
```
