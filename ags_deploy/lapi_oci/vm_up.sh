#!/usr/bin/env bash
# Runs ON the Lapi VM. Generates Lapi-only secrets, creates the LAPI_OWNER
# schema in the Lapi Autonomous Database, builds the images and starts Lapi.
# Re-running is safe: existing secrets and the schema are reused.
set -euo pipefail
APP=/opt/lapi/app
S=/opt/lapi/secrets
IP="${PUBLIC_IP:?set PUBLIC_IP}"
COMPOSE=(docker compose -f "$APP/ags_deploy/lapi_oci/compose.yaml")
say(){ printf 'LAPI-VM> %s\n' "$*"; }

cd "$APP"
mkdir -p "$S/tns"; chmod 700 "$S"
test -s "$S/adb_admin_password" || { say "missing $S/adb_admin_password"; exit 1; }
test -s "$S/tns/tnsnames.ora" || { say "missing $S/tns/tnsnames.ora"; exit 1; }

umask 077
if [ ! -s "$S/app_db_password" ]; then
  printf 'Ap%s7' "$(openssl rand -base64 48 | tr -dc A-Za-z0-9 | head -c 24)" > "$S/app_db_password"
fi
if [ ! -s "$S/lapi.env" ]; then
  MK=$(python3 -c 'import base64,secrets;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')
  BT=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')
  printf '%s\n' "$BT" > "$S/bootstrap_token"
  {
    echo "DATABASE_URL=oracle+oracledb://LAPI_OWNER:$(cat "$S/app_db_password")@lapidb_low"
    echo "AEGIS_MASTER_KEY=$MK"
    echo "AEGIS_BOOTSTRAP_TOKEN=$BT"
    echo "ALLOWED_ORIGINS=http://$IP"
  } > "$S/lapi.env"
fi
# Containers run as uid 10001; the 700 secrets folder still guards the host.
chmod 644 "$S/lapi.env" "$S/tns/tnsnames.ora" "$S/adb_admin_password" "$S/app_db_password"
chmod 755 "$S/tns"

say "building images (first build takes 10-20 minutes)"
"${COMPOSE[@]}" build --pull

say "creating LAPI_OWNER schema in lapidb"
"${COMPOSE[@]}" run --rm --no-deps -T \
  -v "$S/adb_admin_password:/run/lapi/admin_pw:ro" \
  -v "$S/app_db_password:/run/lapi/app_pw:ro" \
  --entrypoint python api - <<'PY'
import oracledb
admin = open('/run/lapi/admin_pw').read().strip()
app = open('/run/lapi/app_pw').read().strip()
con = oracledb.connect(user='ADMIN', password=admin, dsn='lapidb_low', config_dir='/run/lapi/tns')
cur = con.cursor()
cur.execute("select count(*) from dba_users where username = 'LAPI_OWNER'")
if cur.fetchone()[0] == 0:
    cur.execute(f'create user LAPI_OWNER identified by "{app}" quota unlimited on data')
    print('LAPI-VM> created LAPI_OWNER')
else:
    cur.execute(f'alter user LAPI_OWNER identified by "{app}"')
    print('LAPI-VM> LAPI_OWNER already exists; password refreshed')
cur.execute('grant create session, create table, create sequence, create view, create procedure to LAPI_OWNER')
try:
    cur.execute('grant db_developer_role to LAPI_OWNER')
except oracledb.DatabaseError:
    pass
print('LAPI-VM> database version', con.version)
PY

say "starting ollama and pulling free local models"
"${COMPOSE[@]}" up -d ollama qdrant
for _ in $(seq 30); do "${COMPOSE[@]}" exec -T ollama ollama list >/dev/null 2>&1 && break; sleep 5; done
"${COMPOSE[@]}" exec -T ollama ollama pull "${LAPI_MODEL:-qwen3:4b}"
"${COMPOSE[@]}" exec -T ollama ollama pull nomic-embed-text

say "starting web, api and worker"
"${COMPOSE[@]}" up -d
for _ in $(seq 60); do
  if curl -fsS http://127.0.0.1/api/auth/status >/dev/null 2>&1; then
    say "Lapi is up at http://$IP"
    "${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
    exit 0
  fi
  sleep 10
done
say "Lapi did not become ready; recent logs:"
"${COMPOSE[@]}" ps
"${COMPOSE[@]}" logs --tail 40 api web
exit 1
