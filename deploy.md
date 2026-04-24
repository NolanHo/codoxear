# codoxear deploy (current production: 18743)

This is the exact deployment used now.

## 0) Required order

Always run in this order:

1. commit
2. push
3. build
4. restart tmux service
5. health check

## 1) Commit and push

```bash
cd /vePFS-Mindverse/user/nolanho/code/codoxear
git add -A
git commit -m "<message>"
git push origin main
```

Verify branch sync:

```bash
cd /vePFS-Mindverse/user/nolanho/code/codoxear
git rev-parse --short HEAD
git rev-parse --short origin/main
git status --short --branch
```

## 2) Build frontend into backend static dir

```bash
cd /vePFS-Mindverse/user/nolanho/code/codoxear/web
npm run build
```

Build command already copies `web/dist` into:

`/vePFS-Mindverse/user/nolanho/code/codoxear/codoxear/static/dist`

## 3) Restart production tmux service

```bash
set -e
REPO=/vePFS-Mindverse/user/nolanho/code/codoxear
LOG=/root/.local/share/codoxear/logs/server-18743-tmux.log
SESSION=codoxear-18743

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
fi

: > "$LOG"

tmux new-session -d -s "$SESSION" "cd $REPO && export PATH=/root/.pi/agent/bin:/vePFS-Mindverse/user/nolanho/code/pi/fork/current/runtime/bin:/vePFS-Mindverse/user/nolanho/code/pi/.cache/bun/bin:/vePFS-Mindverse/user/nolanho/cache/go/bin:/root/.local/bin:/root/.local/share/pnpm:/root/.nvm/versions/node/v25.6.0/bin:/root/bin:/root/.local/bin:/usr/local/cuda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/go/bin:/root/.volc/bin && export HOME=/root SHELL=/usr/bin/zsh USER=root TERM=screen PI_CODING_AGENT_DIR=/root/.pi/agent PI_FORK_PI_BIN=/vePFS-Mindverse/user/nolanho/code/pi/fork/current/runtime/lib/node_modules/@mariozechner/pi-coding-agent/dist/pi PI_FORK_RUNTIME=/vePFS-Mindverse/user/nolanho/code/pi/fork/current/runtime/lib/node_modules PI_FORK_STACK_ROOT=/vePFS-Mindverse/user/nolanho/code/pi/fork/current PI_HOME=/root/.pi PI_NODE_BIN=/root/.nvm/versions/node/v25.6.0/bin/node PI_ROOT=/vePFS-Mindverse/user/nolanho/code/pi PI_SECRETS_ENV=/root/.config/pi/secrets.env PI_SHARED_GH_CONFIG=/vePFS-Mindverse/user/nolanho/code/pi/home/shared/.config/gh PI_SKIP_PACKAGE_UPDATE_CHECK=1 PI_SKIP_VERSION_CHECK=1 PI_STATE_DIR=/vePFS-Mindverse/user/nolanho/code/pi/state PI_SYSTEM_HOME=/root PI_UPSTREAM_BIN=/root/.nvm/versions/node/v25.6.0/bin/pi-upstream-nvm PI_UPSTREAM_HOME=/vePFS-Mindverse/user/nolanho/code/pi/home/upstream PI_UPSTREAM_NODE_MODULES=/vePFS-Mindverse/user/intern/nolanho/cache/root_migrated/dot_nvm/versions/node/v25.6.0/lib/node_modules PI_UPSTREAM_PREFIX=/vePFS-Mindverse/user/intern/nolanho/cache/root_migrated/dot_nvm/versions/node/v25.6.0 CODEX_WEB_PASSWORD=kujyoai_299 CODOXEAR_APP_DIR=/root/.local/share/codoxear CODEX_WEB_PORT=18743 && exec .venv/bin/python -m codoxear.server >> $LOG 2>&1"
```

## 4) Health check and bundle check

```bash
python - <<'PY'
import subprocess, tempfile, time, re, sys
base='http://127.0.0.1:18743'
cookie = tempfile.NamedTemporaryFile(delete=False).name
last_err = None
for _ in range(30):
    try:
        login = subprocess.check_output(['curl','-sS','-c',cookie,'-H','Content-Type: application/json','-d','{"password":"kujyoai_299"}',base+'/api/login'], text=True, stderr=subprocess.STDOUT).strip()
        me = subprocess.check_output(['curl','-sS','-b',cookie,base+'/api/me'], text=True, stderr=subprocess.STDOUT).strip()
        root = subprocess.check_output(['curl','-sS',base+'/'], text=True, stderr=subprocess.STDOUT)
        bundle = re.search(r'/assets/index-[^"\']+\.js', root)
        print(login)
        print(me)
        print(bundle.group(0) if bundle else 'bundle-not-found')
        sys.exit(0)
    except subprocess.CalledProcessError as exc:
        last_err = exc.output.strip()
    except Exception as exc:
        last_err = str(exc)
    time.sleep(1)
print(last_err or 'unknown failure')
sys.exit(1)
PY
```

Expected:

- `/api/login` returns `{"ok":true}`
- `/api/me` returns `{"ok":true}`
- root HTML references `/assets/index-*.js`

## 5) Reboot behavior (important)

No automatic Pi session respawn happens while this service is down.

- If the machine drops offline, broker and pi child processes stop.
- After reboot, starting `codoxear.server` only discovers currently running sidecar sockets.
- Historical Pi sessions can be resumed on demand when you send/enqueue to that historical session.

Operationally: after reboot, you must run section 3 to bring service back first.
