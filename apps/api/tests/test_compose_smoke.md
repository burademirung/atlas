# Compose smoke checklist (run after `docker compose up -d --build`)

- [ ] `curl -fsS localhost:8080/healthz` → `{"status":"ok"}`
- [ ] `curl -fsS -XPOST localhost:8080/v1/auth/register -H 'content-type: application/json' \
       -d '{"email":"smoke@example.com","password":"supersecret12"}'` → 201 with `{"id":...,"email":...}`
- [ ] `curl -fsS -XPOST localhost:8080/v1/auth/login -H 'content-type: application/json' \
       -d '{"email":"smoke@example.com","password":"supersecret12"}'` → 200 with access+refresh
- [ ] `docker compose logs migrate` shows Alembic ran `0001` exactly once
- [ ] `docker compose exec db psql -U atlas -d atlas -c '\dt'` lists all 7 tables
