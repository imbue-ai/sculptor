#!/usr/bin/env bash
# Sourceable helpers for driving the QA-harness browser control API.
#
#   source marketing/shots/control.sh
#   loc_testid SIDEBAR_HOME_LINK   # -> "x y" or ""
#   click_testid SIDEBAR_HOME_LINK
#   click_text "Changes"
#   shot                            # -> prints screenshot path
#
# The control port is written by marketing/seed/harness.py to
# <demo dir>/screenshots/control_port.txt (demo dir defaults to
# /tmp/sculptor-demo; override with SCULPTOR_DEMO_DIR, matching seed/config.py).

SS_DIR="${SCULPTOR_DEMO_DIR:-/tmp/sculptor-demo}/screenshots"
CTRL="$(cat "$SS_DIR/control_port.txt" 2>/dev/null)"
BASE="http://127.0.0.1:$CTRL"

ex() { curl -s -X POST "$BASE/execute" -d "$1"; }

# Locate by data-testid; prints "x y" of the first match (empty if none).
loc_testid() {
  ex "{\"action\":\"locate\",\"selector\":\"[data-testid=$1]\"}" \
    | python3 -c "import json,sys; e=json.load(sys.stdin).get('elements',[]); print(f\"{e[0]['x']} {e[0]['y']}\" if e else '')"
}

# Locate by visible text; prints "x y" of the first match (empty if none).
loc_text() {
  ex "{\"action\":\"locate\",\"text\":\"$1\"}" \
    | python3 -c "import json,sys; e=json.load(sys.stdin).get('elements',[]); print(f\"{e[0]['x']} {e[0]['y']}\" if e else '')"
}

click_xy() { ex "{\"action\":\"click\",\"x\":$1,\"y\":$2}" >/dev/null; }

click_testid() { local c; c="$(loc_testid "$1")"; [ -n "$c" ] && click_xy ${c% *} ${c#* }; }
click_text()   { local c; c="$(loc_text "$1")";   [ -n "$c" ] && click_xy ${c% *} ${c#* }; }

# Type into whatever has focus (e.g. a terminal PTY).
type_text() { ex "{\"action\":\"type\",\"text\":$(python3 -c "import json,sys;print(json.dumps(sys.argv[1]))" "$1")}" >/dev/null; }
press_key() { ex "{\"action\":\"press\",\"key\":\"$1\"}" >/dev/null; }
# Fill a named field (replaces contents); good for the ProseMirror chat input.
fill_id()   { ex "{\"action\":\"fill\",\"id\":\"$1\",\"text\":$(python3 -c "import json,sys;print(json.dumps(sys.argv[1]))" "$2")}" >/dev/null; }
# Run a shell line in the focused terminal: type it then Enter.
term_run()  { type_text "$1"; press_key "Enter"; }

# Take a screenshot; prints its absolute path.
shot() {
  curl -s "$BASE/screenshot" | python3 -c "import json,sys; print(json.load(sys.stdin)['screenshot'])"
}

status() { curl -s "$BASE/status"; }
