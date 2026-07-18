# Quant_agent

## 커밋 메세지 양식

```
[TYPE] 간결한 제목
ex. [DOCS] README 커밋 컨벤션 추가
```
GitHub Issues는 CI 실패 자동화에 사용하므로 커밋 메시지에는 이슈 번호를 강제하지 않습니다.

| TYPE         |                               | 
| ------------ | ------------------------------------ | 
| **FEAT**     | 새로운 기능 추가                            | 
| **FIX**      | 버그 수정                                |
| **DOCS**     | 문서 수정(README, 가이드, 주석 등)             |  
| **STYLE**    | 코드 포맷/세미콜론/공백 등, 로직 변경 없음        |
| **REFACTOR** | 리팩터링(동작 동일, 구조 개선/성능 향상)             | 
| **TEST**     | 테스트 코드 추가/수정                         | 
| **CHORE**    | 빌드/배포/의존성/스크립트 등 개발환경(패키지 매니저 포함) 변경 |

---
## CI 실패 자동 이슈 봇

`.github/workflows/ci-issue-bot.yml`은 `Code checks`, 배포, 서버 헬스체크 워크플로가 실패하거나 시간 초과하면 GitHub Issue를 자동 생성한다.

- 실패 작업과 실패 단계, 브랜치, 커밋, 실행 로그 링크를 이슈에 기록한다.
- 같은 워크플로 작업의 미해결 이슈가 있으면 새 이슈 대신 최신 실패를 댓글로 남긴다.
- `automated` 라벨이 없을 경우 자동 생성한다.
- 봇이 동작하려면 저장소의 Actions가 기본 `GITHUB_TOKEN`에 Issues 쓰기 권한을 허용해야 한다.

CI 실패 자체가 아닌 취소(`cancelled`) 실행은 이슈로 만들지 않는다.

---

## 목적(현재 이 README scope)
`README`는 **Rocky Linux 8.10 Native Bash MVP spine** 실행 재현성과 안전 계약을 최상위 단에서 정리한다.
AI/FE 상세 절차는 각각 `ai/README_AI.md`, `fe/README.md`에 두고, 여기는 핵심 순서와 검증 명령만 둔다.

## 정확한 선행 조건
- Rocky Linux 8.10 x86_64
- Bash(권장 4.4+), Python 3.11.13, Node 24.15.0, npm 11.12.1
  (`/etc/rocky-release` 및 `--version`으로 고정값 확인)
- Docker/Compose 미사용
- 외부 DB/Redis/OAuth/LLM credential 사용 금지
- 저장소 바깥 작업공간 사용(안전성 상의 이유)

## MVP Spine
`fe`(직접 Vite) → loopback `/ai-api` 프록시 → `ai/ai_graph/api.py` → `backtest_module` → 공개 `AnalysisJob/APIEnvelope` → 동일 브라우저 세션 FE 표시

## 실행 전제: parent/child topology
- AI와 FE는 같은 쉘에서 섞어 실행하지 않는다.
- 실행은 parent Bash가 수행하고 child가 AI/FE 런타임을 독점으로 띄운다.
- child는 canonical `FE_ROOT`와 `env -i`, bounded curl, 시간축/identity 검증을 통과해야 한다.
- loopback 포트 점검/종료 후 listener 정리는 `ss`와 bounded `curl`만으로 수행한다.

## 저장소 외부 venv + fixture env
- venv는 반드시 저장소 경로 밖 생성
- AI/FE는 아래 fixture로만 시작
  - `AUTH_ENABLED=0`
  - `AI_LLM_PROVIDER=mock`
  - `AI_JOB_STORE=memory`
  - `AI_AUDIT_SINK=noop`
  - data-source 계열 env는 제거 (`AI_DATABASE_DSN`, `QUANT_DB_DSN`, `DATABASE_URL`, `AI_DEFAULT_TICKER`, `AI_BACKTEST_LOOKBACK_DAYS`, `AI_L4_EVIDENCE_LIMIT`, `AI_DB_CONNECT_TIMEOUT_SECONDS`, `AI_DB_STATEMENT_TIMEOUT_MS`, `AI_SCREENING_LIMIT`, `AI_SCREENING_BACKTEST_SELECTION_LIMIT`, `AI_PORTFOLIO_BACKTEST_TICKER_LIMIT`, `AI_SECTOR_CACHE_TTL_SECONDS`, `BE_JOB_STORE_MODE`, `REDIS_URL`, `AUTH_SESSION_COOKIE_NAME`, `AI_CORS_ALLOW_ORIGINS`)

## Verification

### 1. Parent setup → child smoke → owned cleanup → residue → literal four-file delta

```bash
set -Eeuo pipefail
required=(bash uname grep awk paste cat sleep curl python3 node npm git ss ps setsid mktemp kill readlink dirname mkdir rm sed sort tr env)
for name in "${required[@]}"; do command -v "$name" >/dev/null || { echo "missing: $name" >&2; exit 1; }; done
((BASH_VERSINFO[0]>4||(BASH_VERSINFO[0]==4&&BASH_VERSINFO[1]>=4)))
[[ $(uname -m) == x86_64 ]]
grep -q '^Rocky Linux release 8\.10 ' /etc/rocky-release
[[ $(python3 --version 2>&1) == 'Python 3.11.13' ]]
[[ $(node --version) == 'v24.15.0' ]]
[[ $(npm --version) == '11.12.1' ]]

WORKTREE_ROOT=$(readlink -f "$(git rev-parse --show-toplevel)")
cd "$WORKTREE_ROOT"

repo_snapshot(){
  python3 - "$1" <<'PY'
import hashlib,json,os,stat,subprocess,sys
raw=subprocess.check_output(["git","ls-files","-z","--cached","--others","--exclude-standard","--",".",":(exclude).gjc",":(exclude).gjc/**"])
out={}
for raw_path in raw.split(b"\0"):
    if not raw_path: continue
    path=os.fsdecode(raw_path)
    if path==".gjc" or path.startswith(".gjc/"): continue
    try: st=os.lstat(path)
    except FileNotFoundError:
        out[path] = {"kind":"missing"}
        continue
    if stat.S_ISLNK(st.st_mode):
        data=os.readlink(path).encode("utf-8","surrogateescape")
        kind="symlink"
    elif stat.S_ISREG(st.st_mode):
        data=open(path,"rb").read()
        kind="file"
    else:
        data=b""
        kind="other"
    out[path]={"kind":kind,"mode":stat.S_IMODE(st.st_mode),"sha256":hashlib.sha256(data).hexdigest()}
json.dump(out,open(sys.argv[1],"w",encoding="utf-8"),ensure_ascii=False,sort_keys=True,indent=2)
PY
}

SAFETY_DIR=$(readlink -f "$(mktemp -d -t quantagent-safety.XXXXXX)")
[[ $SAFETY_DIR != "$WORKTREE_ROOT" && $SAFETY_DIR != "$WORKTREE_ROOT/"* ]]
repo_snapshot "$SAFETY_DIR/baseline.json"

auto_venv=0
if [[ -n ${MVP_VENV:-} ]]; then
  MVP_VENV=$(readlink -m "$MVP_VENV"); parent=$(dirname "$MVP_VENV"); [[ -d $parent && -w $parent ]]
else
  parent=$(mktemp -d -t quantagent-venv.XXXXXX)
  MVP_VENV="$parent/venv"
  auto_venv=1
fi
[[ $MVP_VENV != "$WORKTREE_ROOT" && $MVP_VENV != "$WORKTREE_ROOT/"* && ! -e $MVP_VENV ]]
python3 -m venv "$MVP_VENV"
MVP_VENV=$(readlink -f "$MVP_VENV")
export WORKTREE_ROOT SAFETY_DIR MVP_VENV
"$MVP_VENV/bin/python" -m pip install --upgrade pip
"$MVP_VENV/bin/python" -m pip install -e ./backtest_module -e ./ai
"$MVP_VENV/bin/python" -m pip install 'pytest>=8,<9'
npm --prefix fe ci

export AUTH_ENABLED=0 AI_LLM_PROVIDER=mock AI_JOB_STORE=memory AI_AUDIT_SINK=noop
DATA_SOURCE_ENV_KEYS=(AI_DATABASE_DSN QUANT_DB_DSN DATABASE_URL AI_DEFAULT_TICKER AI_BACKTEST_LOOKBACK_DAYS AI_L4_EVIDENCE_LIMIT AI_DB_CONNECT_TIMEOUT_SECONDS AI_DB_STATEMENT_TIMEOUT_MS AI_SCREENING_LIMIT AI_SCREENING_BACKTEST_SELECTION_LIMIT AI_PORTFOLIO_BACKTEST_TICKER_LIMIT AI_SECTOR_CACHE_TTL_SECONDS)
unset "${DATA_SOURCE_ENV_KEYS[@]}" BE_JOB_STORE_MODE REDIS_URL AUTH_SESSION_COOKIE_NAME AI_CORS_ALLOW_ORIGINS

"$MVP_VENV/bin/python" -m pytest backtest_module/tests -q
"$MVP_VENV/bin/python" -m pytest ai/tests/test_ai_graph_backtest_module_integration.py ai/tests/test_graph_e2e.py ai/tests/test_api.py ai/tests/contracts -q
npm --prefix fe run test

SMOKE_SCRIPT="$SAFETY_DIR/smoke-child.sh"
export SMOKE_ROOT_FILE="$SAFETY_DIR/smoke-root.path"

cat >"$SMOKE_SCRIPT" <<'SMOKE'
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$WORKTREE_ROOT"
NODE_BIN=$(readlink -f "$(command -v node)")
VITE_ENTRY=$(readlink -f "$WORKTREE_ROOT/fe/node_modules/.bin/vite")
FE_ROOT=$(readlink -f "$WORKTREE_ROOT/fe")
[[ -x $NODE_BIN && -f $VITE_ENTRY && $VITE_ENTRY == "$WORKTREE_ROOT/fe/node_modules/"* ]]
[[ $FE_ROOT == "$WORKTREE_ROOT/fe" && $FE_ROOT == "$WORKTREE_ROOT/"* ]]
[[ -f "$FE_ROOT/index.html" && -f "$FE_ROOT/vite.config.ts" ]]

fail(){ echo "ERROR: $*" >&2; return 1; }
proc_field(){ python3 - "$1" "$2" <<'PY'
import os,sys
pid=int(sys.argv[1]); field=sys.argv[2]
stat=open(f"/proc/{pid}/stat",encoding="ascii").read(); tail=stat[stat.rfind(")")+2:].split()
values={"ppid":tail[1],"start":tail[19]}
if field=="exe":
    print(os.path.realpath(f"/proc/{pid}/exe"))
elif field=="argvhash":
    import hashlib
    print(hashlib.sha256(open(f"/proc/{pid}/cmdline","rb").read()).hexdigest())
else:
    print(values[field])
PY
}
pgid_of(){ ps -o pgid= -p "$1"|tr -d ' '; }
sid_of(){ ps -o sid= -p "$1"|tr -d ' '; }
array_has(){ local n=$1 x; shift; for x in "$@"; do [[ $x == "$n" ]]&&return 0; done; return 1; }
add_unique(){ local -n a=$1; local v=$2; array_has "$v" "${a[@]:-}"||a+=("$v"); }
remove_value(){ local -n a=$1; local v=$2 out=() x; for x in "${a[@]:-}"; do [[ $x == "$v" ]]||out+=("$x"); done; a=("${out[@]:-}"); }
raw_rows(){ ss -H -ltn "sport = :$1"; }
owned_rows(){ ss -H -ltnp "sport = :$1"; }
listener_pids(){ sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p'|sort -u; }

active_pids=(); active_pgids=(); all_owned_pids=(); all_owned_pgids=(); cleanup_running=0

declare -A own_start=() own_pgid=() own_sid=() own_exe=() own_argv=() own_role=()
record_identity(){
 local p=$1 g=$2 s=$3 role=$4
 kill -0 "$p" 2>/dev/null
 own_start[$p]=$(proc_field "$p" start); own_pgid[$p]=$g; own_sid[$p]=$s
 own_exe[$p]=$(proc_field "$p" exe); own_argv[$p]=$(proc_field "$p" argvhash); own_role[$p]=$role
 [[ $(pgid_of "$p") == "$g" && $(sid_of "$p") == "$s" ]]
 add_unique active_pids "$p"; add_unique all_owned_pids "$p"
}

validate_identity(){
 local p=$1
 [[ -n ${own_start[$p]:-} ]]||return 1
 kill -0 "$p" 2>/dev/null||return 2
 [[ $(proc_field "$p" start) == "${own_start[$p]}" && $(pgid_of "$p") == "${own_pgid[$p]}" &&
    $(sid_of "$p") == "${own_sid[$p]}" && $(proc_field "$p" exe) == "${own_exe[$p]}" &&
    $(proc_field "$p" argvhash) == "${own_argv[$p]}" ]]
}
assert_identity(){ validate_identity "$1"||fail "identity changed PID=$1 role=${own_role[$1]:-unknown}"; }

verify_group(){
 local g=$1 p rc live=0
 array_has "$g" "${active_pgids[@]:-}"||return 1
 for p in "${active_pids[@]:-}"; do
  [[ ${own_pgid[$p]:-} == "$g" ]]||continue
  set +e; validate_identity "$p"; rc=$?; set -e
  ((rc==0))&&((live+=1)); ((rc==1))&&return 1
 done
 ((live>0))||{ fail "all registered identities vanished PGID=$g"; return 1; }
}
wait_group(){ local g=$1 i; for ((i=0;i<20;i++)); do kill -0 -- "-$g" 2>/dev/null||return 0; sleep .25; done; return 1; }
stop_group(){
 local g=$1
 verify_group "$g"||return 1
 kill -TERM -- "-$g"||return 1
 wait_group "$g"&&return 0
 verify_group "$g"||return 1
 kill -KILL -- "-$g"||return 1
 wait_group "$g"
}
deactivate(){ local g=$1 p kept=(); for p in "${active_pids[@]:-}"; do if [[ ${own_pgid[$p]:-} == "$g" ]]; then unset 'own_start[$p]' 'own_pgid[$p]' 'own_sid[$p]' 'own_exe[$p]' 'own_argv[$p]' 'own_role[$p]'; else kept+=("$p"); fi; done; active_pids=("${kept[@]:-}"); remove_value active_pgids "$g"; }

SMOKE_ROOT=$(mktemp -d -t quantagent-mvp.XXXXXX)
echo "$SMOKE_ROOT">"$SMOKE_ROOT_FILE"
LAUNCHER="$SMOKE_ROOT/launcher.py"
cat >"$LAUNCHER" <<'PY'
import json,os,signal,sys,time
specfile,pidfile,ackfile,separator,*command=sys.argv[1:]
assert separator=="--" and command
spec=json.load(open(specfile,encoding="utf-8"))
blocked={signal.SIGINT,signal.SIGTERM}; signal.pthread_sigmask(signal.SIG_BLOCK,blocked)
child=None; cleaning=False

def alive(pid):
    try: os.kill(pid,0); return True
    except ProcessLookupError: return False

def group_alive(pid):
    try: os.killpg(pid,0); return True
    except ProcessLookupError: return False

def terminate(code):
    global cleaning
    if cleaning: os._exit(code)
    cleaning=True; signal.pthread_sigmask(signal.SIG_BLOCK,blocked)
    if child is None: raise SystemExit(code)
    try:
        is_group=os.getpgid(child)==child and os.getsid(child)==child
    except ProcessLookupError:
        is_group=False
    try:
        os.killpg(child,signal.SIGTERM) if is_group else os.kill(child,signal.SIGTERM)
    except (ProcessLookupError,PermissionError):
        pass
    end=time.monotonic()+2
    while time.monotonic()<end and (group_alive(child) if is_group else alive(child)):
        time.sleep(.05)
    if group_alive(child) if is_group else alive(child):
        try:
            os.killpg(child,signal.SIGKILL) if is_group else os.kill(child,signal.SIGKILL)
        except (ProcessLookupError,PermissionError):
            pass
    try: os.waitpid(child,0)
    except ChildProcessError:
        pass
    raise SystemExit(code)

def handler(signum,_): terminate(128+signum)

def identity():
    exe=os.path.realpath(f"/proc/{child}/exe")
    argv=[os.fsdecode(x) for x in open(f"/proc/{child}/cmdline","rb").read().split(b"\0") if x]
    return exe,argv,os.getpgid(child),os.getsid(child)

try:
    child=os.fork()
    if child==0:
        try:
            os.setsid(); signal.pthread_sigmask(signal.SIG_UNBLOCK,blocked); os.execvpe(command[0],command,os.environ)
        except BaseException:
            os._exit(127)
    signal.signal(signal.SIGINT,handler); signal.signal(signal.SIGTERM,handler)
    signal.pthread_sigmask(signal.SIG_UNBLOCK,blocked)
    stable=0; previous=None; deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        current=identity()
        valid=(current[0]==spec["exe"] and current[1]==spec["argv"] and current[2]==child and current[3]==child)
        stable=stable+1 if valid and current==previous else (1 if valid else 0)
        previous=current
        if stable>=5:
            break
        time.sleep(.1)
    if stable<5:
        raise RuntimeError("post-exec identity never stabilized")
    tmp=f"{pidfile}.{os.getpid()}.tmp"
    with open(tmp,"w",encoding="ascii") as f: f.write(str(child)); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,pidfile)
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        if os.path.exists(ackfile): raise SystemExit(0)
        if not group_alive(child): raise RuntimeError("group exited before ACK")
        time.sleep(.05)
    raise TimeoutError("ACK timeout")
except SystemExit as exc:
    if exc.code==0: raise
    terminate(int(exc.code or 1))
except BaseException:
    terminate(1)
PY

write_spec(){
 local file=$1 exe=$2; shift 2
 python3 - "$file" "$exe" "$@" <<'PY'
import json,os,sys
path,exe,*argv=sys.argv[1:]
json.dump({"exe":os.path.realpath(exe),"argv":argv},open(path,"w",encoding="utf-8"),ensure_ascii=False)
PY
}
spec_matches(){
 python3 - "$1" "$2" <<'PY'
import json,os,sys
spec=json.load(open(sys.argv[1],encoding="utf-8")); pid=int(sys.argv[2])
exe=os.path.realpath(f"/proc/{pid}/exe")
argv=[os.fsdecode(x) for x in open(f"/proc/{pid}/cmdline","rb").read().split(b"\0") if x]
raise SystemExit(0 if exe==spec["exe"] and argv==spec["argv"] else 1)
PY
}

sup_pid= sup_start= sup_pgid= sup_sid= sup_exe= sup_argv= sup_ppid=
prov_pid= prov_start= prov_pgid= prov_sid= prov_exe= prov_argv= prov_verified=0
capture_supervisor(){
  sup_pid=$1; kill -0 "$sup_pid" 2>/dev/null
  sup_start=$(proc_field "$sup_pid" start); sup_pgid=$(pgid_of "$sup_pid"); sup_sid=$(sid_of "$sup_pid")
  sup_exe=$(proc_field "$sup_pid" exe); sup_argv=$(proc_field "$sup_pid" argvhash); sup_ppid=$(proc_field "$sup_pid" ppid)
  [[ $sup_ppid == $$ ]]
}
validate_supervisor(){
  kill -0 "$sup_pid" 2>/dev/null||return 2
  [[ $(proc_field "$sup_pid" start) == "$sup_start" && $(pgid_of "$sup_pid") == "$sup_pgid" &&
     $(sid_of "$sup_pid") == "$sup_sid" && $(proc_field "$sup_pid" exe) == "$sup_exe" &&
     $(proc_field "$sup_pid" argvhash) == "$sup_argv" && $(proc_field "$sup_pid" ppid) == "$sup_ppid" ]]
}
validate_provisional_group(){
  kill -0 "$prov_pid" 2>/dev/null||return 2
  [[ $(proc_field "$prov_pid" start) == "$prov_start" && $(pgid_of "$prov_pid") == "$prov_pgid" &&
     $(sid_of "$prov_pid") == "$prov_sid" && $(proc_field "$prov_pid" exe) == "$prov_exe" &&
     $(proc_field "$prov_pid" argvhash) == "$prov_argv" ]]
}
wait_pid(){ local p=$1 i; for ((i=0;i<20;i++)); do kill -0 "$p" 2>/dev/null||return 0; sleep .25; done; return 1; }
stop_provisional(){
  local rc=0
  if [[ $sup_pid =~ ^[1-9][0-9]*$ ]]; then
    if ! kill -0 "$sup_pid" 2>/dev/null; then
      fail "recorded supervisor vanished; refusing further signals"; rc=1
    else
      validate_supervisor||{ fail "unknown supervisor; refusing TERM"; rc=1; }
      if ((rc==0)); then kill -TERM "$sup_pid"||rc=1; fi
      if ((rc==0))&&!wait_pid "$sup_pid"; then
        validate_supervisor||{ fail "unknown supervisor; refusing KILL"; rc=1; }
        if ((rc==0)); then kill -KILL "$sup_pid"||rc=1; wait_pid "$sup_pid"||rc=1; fi
      fi
      wait "$sup_pid" 2>/dev/null||true
    fi
  fi
  if [[ $prov_verified == 1 ]]; then
    if ! kill -0 "$prov_pid" 2>/dev/null; then
      fail "recorded provisional group vanished; refusing further signals"; rc=1
    else
      validate_provisional_group||{ fail "unknown provisional group; refusing TERM"; rc=1; }
      if ((rc==0)); then kill -TERM -- "-$prov_pgid"||rc=1; fi
      if ((rc==0))&&!wait_group "$prov_pgid"; then
        validate_provisional_group||{ fail "unknown provisional group; refusing KILL"; rc=1; }
        if ((rc==0)); then kill -KILL -- "-$prov_pgid"||rc=1; wait_group "$prov_pgid"||rc=1; fi
      fi
    fi
  fi
  sup_pid= sup_start= sup_pgid= sup_sid= sup_exe= sup_argv= sup_ppid=
  prov_pid= prov_start= prov_pgid= prov_sid= prov_exe= prov_argv= prov_verified=0
  return "$rc"
}

cleanup(){
  local rc=${1:-$?} g port rows pids unknown=()
  ((cleanup_running==0))||exit "$rc"; cleanup_running=1; trap - EXIT INT TERM
  stop_provisional||rc=1
  for g in "${active_pgids[@]:-}"; do if stop_group "$g"; then deactivate "$g"; else rc=1; fi; done
  sleep .5
  for port in 18000 18001; do
    if ! rows=$(raw_rows "$port"); then
      unknown+=("port=$port,probe=failed")
      rc=1
      continue
    fi
    if [[ -n $rows ]]; then
      if ! owned=$(owned_rows "$port"); then
        unknown+=("port=$port,owner-probe=failed,rows=$rows")
        rc=1
        continue
      fi
      pids=$(listener_pids<<<"$owned"|paste -sd, -)
      [[ -n $pids ]]||pids=unavailable
      unknown+=("port=$port,pid=$pids,rows=$rows")
    fi
  done
  if ((${#unknown[@]})); then echo "unknown listeners; no further kill: ${unknown[*]}; logs=$SMOKE_ROOT" >&2; rc=1; fi
  exit "$rc"
}
trap 'cleanup $?' EXIT; trap 'cleanup 130' INT; trap 'cleanup 143' TERM

launch_service(){
  local out_pid=$1 out_group=$2 label=$3 spec=$4 stdout=$5 stderr=$6; shift 6
  local pidfile="$SMOKE_ROOT/$label.pid" ack="$SMOKE_ROOT/$label.ack" p g s i
  python3 "$LAUNCHER" "$spec" "$pidfile" "$ack" -- "$@" >"$stdout" 2>"$stderr" &
  capture_supervisor "$!"
  for ((i=0;i<240;i++)); do [[ -s $pidfile ]]&&break; kill -0 "$sup_pid" 2>/dev/null||{ fail "$label supervisor exited"; return 1; }; sleep .05; done
  [[ -s $pidfile ]]; p=$(cat "$pidfile"); [[ $p =~ ^[1-9][0-9]*$ ]]; spec_matches "$spec" "$p"
  g=$(pgid_of "$p"); s=$(sid_of "$p"); [[ $p == "$g" && $p == "$s" ]]
  prov_pid=$p; prov_start=$(proc_field "$p" start); prov_pgid=$g; prov_sid=$s
  prov_exe=$(proc_field "$p" exe); prov_argv=$(proc_field "$p" argvhash); prov_verified=1
  record_identity "$p" "$g" "$s" "$label-leader"; add_unique active_pgids "$g"; add_unique all_owned_pgids "$g"
  assert_identity "$p"; spec_matches "$spec" "$p"
  printf -v "$out_pid" '%s' "$p"; printf -v "$out_group" '%s' "$g"
  echo registered>"$ack"; wait "$sup_pid"
  sup_pid= sup_start= sup_pgid= sup_sid= sup_exe= sup_argv= sup_ppid=
  prov_pid= prov_start= prov_pgid= prov_sid= prov_exe= prov_argv= prov_verified=0
}

http_rc=0; http_code=000
http(){
  local method=$1 url=$2 input=$3 output=$4 max=$5
  set +e
  if [[ $method == POST ]]; then
    http_code=$(curl -q --noproxy '*' -sS --connect-timeout 2 --max-time "$max" -o "$output" -w '%{http_code}' -H 'Content-Type: application/json; charset=utf-8' --data-binary "@$input" "$url")
  else
    http_code=$(curl -q --noproxy '*' -sS --connect-timeout 2 --max-time "$max" -o "$output" -w '%{http_code}' "$url")
  fi
  http_rc=$?
  set -e
  [[ $http_code =~ ^[0-9]{3}$ ]]||http_code=000
}
expect(){ [[ $http_rc -eq 0 && $http_code == "$1" ]]||fail "$2 rc=$http_rc http=$http_code logs=$SMOKE_ROOT"; }
json_assert(){
  python3 - "$@" <<'PY'
import json,sys
mode,*a=sys.argv[1:]
def load(p): return json.load(open(p,encoding="utf-8"))
def keys(x):
  if isinstance(x,dict):
    for k,v in x.items(): yield k; yield from keys(v)
  elif isinstance(x,list):
    for v in x: yield from keys(v)

def status(x):
  assert x["service"]=="QuantAgent AI API" and x["schema_version"]
  assert x["data_source"]["configured"] is False
  assert x["job_store"]["requested_mode"]==x["job_store"]["active_mode"]=="memory" and x["job_store"]["fallback"] is False
  return x["schema_version"]

def job(x,q,s,want):
  r=x["result"]
  assert x["query"]==q and x["job_id"] and x["trace_id"]==r["trace_id"]
  assert r["status"]==want and r["schema_version"]==s and r["debug_ref"]==f"debug:{x['trace_id']}"
  assert len(x["stages"])==5 and all(v["status"]=="succeeded" for v in x["stages"])
  assert {"internal_payload","node_outputs","llm_prompts"}.isdisjoint(set(keys(x)))
  return r

if mode=="status": left,right=map(load,a); assert status(left)==status(right)
elif mode in ("ready","clarification"):
  x,st,q=load(a[0]),load(a[1]),a[2]
  r=job(x,q,status(st),"ready" if mode=="ready" else "need_clarification")
  p=r["user_payload"]
  if mode=="ready":
    assert r["strategy_spec"]["name"] and p["performance"]["selected_candidate_id"] and p["performance"]["metrics"]
    for n in ("web_projection","email_projection"): assert p["report"][n]["title"] and p["report"][n]["summary"] and p["report"][n]["sections"]
  else:
    assert p["question"].strip() and len(p["candidate_cards"])==len(p["options"])==3 and p["report"] is None and p["performance"] is None
elif mode=="poll":
  x,y=map(load,a)
  for f in ("job_id","trace_id","query","result","stages"): assert x[f]==y[f]
PY
}

for port in 18000 18001; do
  rows=$(raw_rows "$port") || { echo "listener probe failed for $port; refusing to continue" >&2; exit 1; }
  [[ -z $rows ]]||{ echo "occupied $port; refusing kill" >&2; exit 1; }
done
AI_PY="$MVP_VENV/bin/python"
AI_SPEC="$SMOKE_ROOT/ai-spec.json"; FE_SPEC="$SMOKE_ROOT/fe-spec.json"
write_spec "$AI_SPEC" "$AI_PY" "$AI_PY" -m uvicorn ai_graph.api:app --app-dir ai --host 127.0.0.1 --port 18001
write_spec "$FE_SPEC" "$NODE_BIN" "$NODE_BIN" "$VITE_ENTRY" "$FE_ROOT" --host 127.0.0.1

# env -i prevents every unspecified host data-source/provider/auth variable from reaching AI.
ai_root= ai_group=
launch_service ai_root ai_group ai "$AI_SPEC" "$SMOKE_ROOT/ai.out" "$SMOKE_ROOT/ai.err" \
  env -i PATH="$PATH" HOME="${HOME:-/tmp}" LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUTF8=1 \
  AUTH_ENABLED=0 AI_LLM_PROVIDER=mock AI_JOB_STORE=memory AI_AUDIT_SINK=noop \
  "$AI_PY" -m uvicorn ai_graph.api:app --app-dir ai --host 127.0.0.1 --port 18001
fe_root= fe_group=
launch_service fe_root fe_group fe "$FE_SPEC" "$SMOKE_ROOT/fe.out" "$SMOKE_ROOT/fe.err" \
  "$NODE_BIN" "$VITE_ENTRY" "$FE_ROOT" --host 127.0.0.1

ready=0
for ((i=0;i<90;i++)); do
  http GET http://127.0.0.1:18001/api-status '' "$SMOKE_ROOT/direct-status.json" 3
  d=0; [[ $http_rc -eq 0 && $http_code == 200 ]]&&d=1
  http GET http://127.0.0.1:18000/ai-api/api-status '' "$SMOKE_ROOT/proxy-status.json" 3
  p=0; [[ $http_rc -eq 0 && $http_code == 200 ]]&&p=1
  [[ $d == 1 && $p == 1 ]]&&{ ready=1; break; }
  sleep .5

done
[[ $ready == 1 ]]
assert_identity "$ai_root"; spec_matches "$AI_SPEC" "$ai_root"
assert_identity "$fe_root"; spec_matches "$FE_SPEC" "$fe_root"

ai_listeners=(); fe_listeners=()
for item in "18001:$ai_group:ai_listeners" "18000:$fe_group:fe_listeners"; do
  IFS=: read -r port group target <<<"$item"
  rows=$(owned_rows "$port") || fail "listener ownership probe failed for $port"
  [[ -n $rows ]]
  while IFS= read -r row; do [[ $(awk '{print $4}'<<<"$row") == "127.0.0.1:$port" ]]; done<<<"$rows"
  mapfile -t pids < <(listener_pids<<<"$rows")
  ((${#pids[@]}>0))
  for lp in "${pids[@]}"; do
    [[ $(pgid_of "$lp") == "$group" ]]
    record_identity "$lp" "$group" "$(sid_of "$lp")" "port-$port-listener"
    add_unique "$target" "$lp"
    assert_identity "$lp"
  done
done

http GET http://127.0.0.1:18001/api-status '' "$SMOKE_ROOT/direct-status.json" 5; expect 200 'direct status'
http GET http://127.0.0.1:18000/ai-api/api-status '' "$SMOKE_ROOT/proxy-status.json" 5; expect 200 'proxy status'
json_assert status "$SMOKE_ROOT/direct-status.json" "$SMOKE_ROOT/proxy-status.json"

python3 - "$SMOKE_ROOT/ready.json" "$SMOKE_ROOT/clarify.json" "$SMOKE_ROOT/down.json" <<'PY'
import json,sys
for p,q in zip(sys.argv[1:],["RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어","저평가주 사줘","AI down 확인"]):
    json.dump({"query":q},open(p,"w",encoding="utf-8"),ensure_ascii=False)
PY
flow(){
  local base=$1 label=$2 st=$3 req=$4 query=$5 mode=$6
  local create="$SMOKE_ROOT/$label-create.json" get="$SMOKE_ROOT/$label-get.json" id
  http POST "$base/analysis-jobs" "$req" "$create" 45; expect 201 "$label create"
  json_assert "$mode" "$create" "$st" "$query"
  id=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8"))["job_id"])' "$create")
  http GET "$base/analysis-jobs/$id" '' "$get" 5; expect 200 "$label get"; json_assert poll "$create" "$get"
}
ready_q='RSI가 30 이하로 떨어진 KOSPI200 종목을 사고, 70 이상이면 팔고 싶어'; clarify_q='저평가주 사줘'
flow http://127.0.0.1:18001 direct-ready "$SMOKE_ROOT/direct-status.json" "$SMOKE_ROOT/ready.json" "$ready_q" ready
flow http://127.0.0.1:18000/ai-api proxy-ready "$SMOKE_ROOT/proxy-status.json" "$SMOKE_ROOT/ready.json" "$ready_q" ready
flow http://127.0.0.1:18001 direct-clarification "$SMOKE_ROOT/direct-status.json" "$SMOKE_ROOT/clarify.json" "$clarify_q" clarification
flow http://127.0.0.1:18000/ai-api proxy-clarification "$SMOKE_ROOT/proxy-status.json" "$SMOKE_ROOT/clarify.json" "$clarify_q" clarification

[[ -t 0 && -t 1 ]]||fail 'interactive TTY required; incomplete'
echo 'QA: loopback fixture; ready /ai-api 201+debug marker; compare only name, selected id/metrics, web title/conclusion/section titles; clarification status+3 cards.'
read -r -p 'Type READY_CLARIFICATION_QA_COMPLETE: ' evidence
[[ $evidence == READY_CLARIFICATION_QA_COMPLETE ]]
stop_group "$ai_group"; deactivate "$ai_group"
http GET http://127.0.0.1:18000/ '' "$SMOKE_ROOT/fe-after-down" 5; expect 200 'FE after AI-down'
http POST http://127.0.0.1:18000/ai-api/analysis-jobs "$SMOKE_ROOT/down.json" "$SMOKE_ROOT/down-response" 45
[[ $http_rc -ne 0 || ! $http_code =~ ^2[0-9][0-9]$ ]]
read -r -p 'Enter exact origin http://127.0.0.1:18000: ' origin; [[ $origin == http://127.0.0.1:18000 ]]
read -r -p 'Type AI_DOWN_ERROR_OBSERVED: ' down; [[ $down == AI_DOWN_ERROR_OBSERVED ]]
read -r -p 'After cleanup console block enter null,null,null: ' nulls; [[ $nulls == null,null,null ]]
cleanup 0
SMOKE

set +e
bash "$SMOKE_SCRIPT"
smoke_rc=$?
set -e
if ((smoke_rc != 0)); then
  echo "blocking smoke failure rc=$smoke_rc logs=$(cat "$SMOKE_ROOT_FILE" 2>/dev/null||true)" >&2
  exit "$smoke_rc"
fi

set +e
git grep -nEi 'p[o]wer(shell)?|p[w]sh|p[y] -3\.11|S[c]ripts[/\\]|[A-Za-z]:\\' -- README.md ai/README_AI.md fe/README.md
residue_rc=$?
set -e
if ((residue_rc==0)); then
  echo 'non-Native residue found' >&2
  exit 1
fi
if ((residue_rc!=1)); then
  echo 'residue scan failed' >&2
  exit "$residue_rc"
fi

repo_snapshot "$SAFETY_DIR/post.json"
python3 - "$SAFETY_DIR/baseline.json" "$SAFETY_DIR/post.json" <<'PY'
import json,sys
before=json.load(open(sys.argv[1],encoding="utf-8")); after=json.load(open(sys.argv[2],encoding="utf-8"))
changed=sorted(p for p in before.keys()|after.keys() if before.get(p)!=after.get(p))
allowed={"README.md","ai/README_AI.md","fe/README.md","ai/tests/test_api.py"}
unexpected=sorted(set(changed)-allowed)
print("executor_delta=",changed)
if unexpected:
    raise SystemExit(f"non-allowlisted delta: {unexpected}")
blocked_prefixes=("fe/src/","ai/ai_graph/","backtest_module/","quantagent_strategy/","backend/","DE/","service_db/")
blocked_names={"fe/package.json","fe/package-lock.json","ai/pyproject.toml","backtest_module/pyproject.toml"}
blocked=[p for p in changed if p in blocked_names or p.startswith(blocked_prefixes)]
if blocked:
    raise SystemExit(f"blocked delta: {blocked}")
PY
printf 'FINAL GATE PASSED: four-file executor delta is allowlisted\n'
```

- 마지막 `printf` 출력 이후에는 추가 명령이 없어야 한다.

## Loopback/SSH 게이트
- 외부 노출 금지. AI/FE는 loopback 전용.
- 원격 접속이 필요한 경우 SSH tunnel은 오직 `18000` 포트로만 사용.
  - `ssh -L 18000:127.0.0.1:18000 user@remote-host`

## 비목표
- 제품 코드/manifest/lockfile/migration 변경
- OAuth/Google 로그인 성공 보장(로그인 통과 fixture만 허용)
- PostgreSQL/Redis/AOAI live, Docker, 외부 DB 연동
- reload/restart 지속성, FE hydration 영속 보강
- 미확인 주체 프로세스 임의 종료

## 참고
- AI 상세 실행/테스트 가드: `ai/README_AI.md`
- FE 실행/설정 상세: `fe/README.md`