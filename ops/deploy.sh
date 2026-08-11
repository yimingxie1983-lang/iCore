#!/usr/bin/env bash

set -euo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$OPS_DIR/.." && pwd)"
COMPOSE_FILE="$OPS_DIR/compose.yaml"
ENV_FILE="$OPS_DIR/.env"
DATA_DIR="$OPS_DIR/data"
BACKUP_DIR="$OPS_DIR/backups"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

require_commands() {
  command -v docker >/dev/null
  docker compose version >/dev/null
  command -v curl >/dev/null
  command -v tar >/dev/null
  command -v openssl >/dev/null
  command -v python3 >/dev/null
  command -v sha256sum >/dev/null
}

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

seed_directory() {
  local source="$1"
  local target="$2"
  mkdir -p "$target"
  if [ -d "$source" ] && [ -z "$(find "$target" -mindepth 1 -print -quit)" ]; then
    cp -a "$source/." "$target/"
  fi
}

initialize() {
  require_commands
  mkdir -p \
    "$DATA_DIR/state" \
    "$DATA_DIR/workspaces" \
    "$DATA_DIR/agent_instances" \
    "$DATA_DIR/persona_profiles" \
    "$DATA_DIR/playbooks" \
    "$DATA_DIR/skill_uploads" \
    "$BACKUP_DIR"
  seed_directory \
    "$ROOT_DIR/cancer_claw/resources/persona_profiles" \
    "$DATA_DIR/persona_profiles"
  seed_directory \
    "$ROOT_DIR/cancer_claw/resources/knowledge/playbooks" \
    "$DATA_DIR/playbooks"
  if [ ! -f "$ENV_FILE" ]; then
    cp "$OPS_DIR/env.example" "$ENV_FILE"
  fi
  if ! grep -q '^CANCER_CLAW_AUTH_SECRET=.\+' "$ENV_FILE"; then
    set_env_value CANCER_CLAW_AUTH_SECRET "$(openssl rand -hex 48)"
  fi
  set_env_value APP_UID "$(id -u)"
  set_env_value APP_GID "$(id -g)"
}

wait_for_health() {
  local port
  port="$(grep '^APP_PORT=' "$ENV_FILE" | tail -n 1 | cut -d= -f2)"
  port="${port:-8000}"
  for _ in $(seq 1 90); do
    if curl -fsS "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1; then
      compose ps
      return 0
    fi
    sleep 2
  done
  compose logs --tail 200 app
  return 1
}

start() {
  initialize
  compose up -d --build
  wait_for_health
}

stop() {
  compose down
}

backup() {
  initialize
  local stamp
  local target
  stamp="$(date +%Y%m%d_%H%M%S)"
  target="$BACKUP_DIR/$stamp"
  mkdir -p "$target"
  if [ -f "$DATA_DIR/state/cancer_claw.db" ]; then
    if compose ps --status running --services | grep -qx app; then
      compose exec -T app python -c "import sqlite3; s=sqlite3.connect('/app/cancer_claw/var/state/cancer_claw.db'); d=sqlite3.connect('/app/cancer_claw/var/state/cancer_claw.backup.db'); s.backup(d); d.close(); s.close()"
      mv "$DATA_DIR/state/cancer_claw.backup.db" "$target/cancer_claw.db"
    else
      python3 -c "import sqlite3; s=sqlite3.connect('$DATA_DIR/state/cancer_claw.db'); d=sqlite3.connect('$target/cancer_claw.db'); s.backup(d); d.close(); s.close()"
    fi
  fi
  tar \
    --exclude='state/cancer_claw.db' \
    --exclude='state/cancer_claw.db-wal' \
    --exclude='state/cancer_claw.db-shm' \
    -czf "$target/runtime-data.tar.gz" \
    -C "$DATA_DIR" .
  sha256sum "$target"/* > "$target/SHA256SUMS.txt"
  printf '%s\n' "$target"
}

update() {
  backup
  compose build --pull
  compose up -d
  wait_for_health
}

case "${1:-up}" in
  up)
    start
    ;;
  down)
    stop
    ;;
  restart)
    stop
    start
    ;;
  status)
    compose ps
    ;;
  logs)
    compose logs -f --tail 200 app
    ;;
  backup)
    backup
    ;;
  update)
    update
    ;;
  *)
    printf '%s\n' "usage: $0 {up|down|restart|status|logs|backup|update}"
    exit 2
    ;;
esac
