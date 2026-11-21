# ZeroDayCTF security test suite

Automated checks that were used for the pre-launch security test. They create throwaway
accounts (`zdsec_*`, `zdx*`, `zdpw_*`), temporarily move the event schedule to exercise each
phase, and restore the real schedule when finished (even on failure).

**Run only against your own local or staging copy, never against production while players are active.**

```bash
# copy the helper + a stage into the app container, then run it
docker compose cp scripts/security_test/h.py ctfd:/tmp/h.py
docker compose cp scripts/security_test/stage1_auth.py ctfd:/tmp/stage1.py
docker compose exec -T -e PYTHONPATH=/opt/CTFd -w /opt/CTFd ctfd python /tmp/stage1.py

# stage 2 also reviews admin pages; pass an admin password through the environment (never commit it)
docker compose cp scripts/security_test/stage2_injection_logic.py ctfd:/tmp/stage2.py
docker compose exec -T -e ADMPW='<admin password>' -e PYTHONPATH=/opt/CTFd -w /opt/CTFd ctfd python /tmp/stage2.py
```

Stage 1 registers the two test users that stage 2 and 3 log in as. Delete all `zd*` test users
and their uploaded files afterwards. The schedule values restored at the end are hard-coded
(29 Nov 2026, 11:00 / 16:00 / 18:00 IST): edit `cfg(...)` calls if your schedule changes.
