"""Generate project-local service credentials; never print or commit secrets."""
from pathlib import Path
import secrets
ROOT=Path(__file__).resolve().parents[1]
state=ROOT/'.cache/platform'; state.mkdir(parents=True,exist_ok=True)
path=state/'compose.env'
if not path.exists():
    values={key:secrets.token_hex(24) for key in ('AI07_DB_PASSWORD','AI07_LS_PASSWORD','AI07_LS_TOKEN','AI07_GRAFANA_PASSWORD')}
    path.write_text(''.join(f'{key}={value}\n' for key,value in values.items()),encoding='utf-8')
if not (state/'worker.key').exists(): (state/'worker.key').write_text(secrets.token_urlsafe(40),encoding='utf-8')
print('Project-local service environment ready: .cache/platform/compose.env (secrets hidden)')
