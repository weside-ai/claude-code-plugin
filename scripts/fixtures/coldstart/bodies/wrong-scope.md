<!-- coldstart-receipt -->
```json
{
 "status": "green",
 "reasons": [],
 "digest": "@DIGEST@",
 "affected": ["worker/b"],
 "scenarios": [
  {"id": "master/a", "runs": 10, "hits": 10, "gated": true, "status": "rate"},
  {"id": "worker/b", "runs": 3, "hits": 3, "gated": true, "status": "run"}
 ]
}
```
