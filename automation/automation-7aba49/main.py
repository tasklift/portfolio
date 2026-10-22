# -*- coding: utf-8 -*-
"""폴더 정리 기록기 - 규칙에 따라 파일을 분류하고 이동 기록을 남긴다."""
import argparse
import fnmatch
import json
import math
import os
import pathlib
import re
import sys
import threading
import time
from datetime import datetime, timezone

EXT_RE = re.compile(r"\.[a-z0-9]+")
TARGET_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", re.ASCII)
CYCLES_RE = re.compile(r"[0-9]+")
FLOAT_RE = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


class CliError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError("명령줄 인자가 올바르지 않습니다(%s). 해결: 사용법은 "
                       "main.py preview|run|watch 이며 필요한 옵션을 모두 정확히 지정하세요."
                       % _ko_message(message))


def _ko_message(message):
    m = re.match(r"the following arguments are required: (.*)", message)
    if m:
        return "필수 옵션이 빠졌습니다: " + m.group(1)
    m = re.match(r"unrecognized arguments: (.*)", message)
    if m:
        return "알 수 없는 인자: " + m.group(1)
    m = re.match(r"argument (.*): expected one argument", message)
    if m:
        return "%s 옵션에 값이 없습니다" % m.group(1)
    m = re.match(r"argument command: invalid choice: ('[^']*')", message)
    if m:
        return "알 수 없는 명령 %s. preview, run, watch 중 하나만 쓸 수 있습니다" % m.group(1)
    m = re.match(r"argument (.*): invalid choice: ('[^']*')", message)
    if m:
        return "알 수 없는 명령 %s" % m.group(2)
    return "인자 형식이 맞지 않습니다"


HELP_TEXT = """폴더 정리 기록기 - 규칙에 따라 파일을 분류하고 이동 기록을 남긴다.

사용법:
  main.py preview --folder 폴더 --rules 규칙파일
  main.py run     --folder 폴더 --rules 규칙파일 --log 로그파일
  main.py watch   --folder 폴더 --rules 규칙파일 --log 로그파일 --cycles 횟수 --interval 초

명령:
  preview  이동 계획만 보여 준다(파일은 그대로 둔다)
  run      규칙대로 파일을 옮기고 로그에 기록한다
  watch    정해진 횟수만큼 폴더를 살피며 같은 상태가 이어진 파일만 옮긴다

옵션(모두 필수, --log 는 run·watch, --cycles·--interval 은 watch 에만 쓴다):
  --folder    정리할 폴더(이미 있는 디렉터리)
  --rules     규칙 파일(rules.json, 폴더 바깥)
  --log       이동 기록 파일(.jsonl, 폴더 바깥)
  --cycles    관찰 횟수(1 이상의 정수)
  --interval  관찰 간격(0보다 큰 초)
  --help, -h  이 도움말을 보여 준다
"""


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _no_dups(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("중복 키 " + k)
        d[k] = v
    return d


def _bad_const(name):
    raise ValueError("허용하지 않는 값 " + name)


def loads(text):
    return json.loads(text, object_pairs_hook=_no_dups, parse_constant=_bad_const)


def build_parser():
    p = _Parser(prog="main.py", add_help=False, allow_abbrev=False)
    sub = p.add_subparsers(dest="command", parser_class=_Parser)
    for name in ("preview", "run", "watch"):
        s = sub.add_parser(name, add_help=False, allow_abbrev=False)
        s.add_argument("--folder", required=True)
        s.add_argument("--rules", required=True)
        if name != "preview":
            s.add_argument("--log", required=True)
        if name == "watch":
            s.add_argument("--cycles", required=True)
            s.add_argument("--interval", required=True)
    return p


def inside(path, base):
    try:
        return os.path.commonpath([os.path.normcase(path), os.path.normcase(base)]) == os.path.normcase(base)
    except ValueError:
        return False


def validate_paths(args):
    folder = os.path.abspath(args.folder)
    if os.path.islink(folder) or not os.path.isdir(folder):
        kind = "감시 폴더" if args.command == "watch" else "정리할 폴더"
        raise CliError("%s가 존재하는 실제 디렉터리가 아닙니다: %s. 해결: --folder 에 이미 있는 "
                       "디렉터리(심볼릭 링크 제외)를 지정하세요." % (kind, args.folder))
    rules = os.path.abspath(args.rules)
    if not os.path.isfile(rules):
        raise CliError("규칙 파일이 없거나 일반 파일이 아닙니다: %s. 해결: --rules 에 이미 있는 "
                       "rules.json 파일 경로를 지정하세요." % args.rules)
    try:
        empty = os.path.getsize(rules) == 0
    except OSError as e:
        raise CliError("규칙 파일을 읽을 수 없습니다(%s). 해결: 파일 권한을 확인하세요." % e.strerror)
    if empty:
        raise CliError("규칙 파일이 비어 있습니다. 해결: rules 배열이 있는 JSON 내용을 작성하세요.")
    real_folder = os.path.realpath(folder)
    log = None
    paths = [("--rules", rules)]
    if getattr(args, "log", None) is not None:
        log = os.path.abspath(args.log)
        paths.append(("--log", log))
    for opt, p in paths:
        if inside(p, folder) or inside(os.path.realpath(p), real_folder):
            raise CliError("%s 경로가 감시 폴더 안에 있습니다. 해결: %s 를 --folder 바깥 경로로 지정하세요." % (opt, opt))
    if log is not None:
        parent = os.path.dirname(log)
        if not os.path.isdir(parent):
            raise CliError("로그 파일의 부모 디렉터리가 없습니다: %s. 해결: 부모 디렉터리를 먼저 만드세요." % parent)
        if os.path.lexists(log) and not os.path.isfile(log):
            raise CliError("로그 경로가 일반 파일이 아닙니다. 해결: --log 에 파일 경로를 지정하세요.")
    return folder, rules, log


_JSON_KO = [
    ("Expecting property name enclosed in double quotes", "키는 큰따옴표로 감싼 문자열이어야 합니다(마지막 쉼표가 남았는지도 확인)"),
    ("Expecting ',' delimiter", "항목 사이에 쉼표가 빠졌습니다"),
    ("Expecting ':' delimiter", "키 뒤에 콜론이 빠졌습니다"),
    ("Expecting value", "값이 와야 할 자리가 비었거나 형식이 틀렸습니다"),
    ("Unterminated string", "문자열의 닫는 큰따옴표가 없습니다"),
    ("Extra data", "JSON이 끝난 뒤에 불필요한 내용이 더 있습니다"),
    ("Invalid control character", "문자열 안에 허용되지 않는 제어 문자가 있습니다"),
    ("Invalid \\escape", "잘못된 이스케이프 문자가 있습니다"),
    ("Invalid \\uXXXX escape", "잘못된 유니코드 이스케이프가 있습니다"),
]


def _ko_json(msg):
    for en, ko in _JSON_KO:
        if msg.startswith(en):
            return ko
    return "JSON 문법 오류"


def load_rules(path):
    fix = (" 해결: README.md 의 '실행 방법'에 있는 규칙 파일 예시(rules.json)처럼 고치세요. 예: "
           '{"rules":[{"extension":".pdf","target":"documents"}]}')
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            data = loads(f.read())
    except UnicodeDecodeError:
        raise CliError("규칙 파일이 UTF-8 글자 부호가 아닙니다." + fix)
    except json.JSONDecodeError as e:
        raise CliError("규칙 파일이 올바른 JSON이 아닙니다(%d줄 %d번째 글자 근처: %s)."
                       % (e.lineno, e.colno, _ko_json(e.msg)) + fix)
    except ValueError as e:
        raise CliError("규칙 파일이 올바른 JSON이 아닙니다(%s)." % e + fix)
    except RecursionError:
        raise CliError("규칙 파일의 JSON이 너무 깊게 중첩되어 있습니다." + fix)
    except OSError as e:
        raise CliError("규칙 파일을 읽을 수 없습니다(%s). 해결: 파일 권한을 확인하세요." % e.strerror)
    if not isinstance(data, dict) or set(data) != {"rules"}:
        raise CliError("규칙 파일의 최상위는 rules 키 하나만 있는 객체여야 합니다." + fix)
    rules = data["rules"]
    if not isinstance(rules, list) or not rules:
        raise CliError("rules 는 하나 이상의 규칙을 담은 배열이어야 합니다." + fix)
    out = []
    for i, r in enumerate(rules, 1):
        if not isinstance(r, dict) or "target" not in r or not set(r) <= {"target", "extension", "name"} \
                or not (set(r) & {"extension", "name"}):
            raise CliError("%d번 규칙의 키가 올바르지 않습니다(target 필수, extension/name 중 하나 이상)." % i + fix)
        for k, v in r.items():
            if not isinstance(v, str) or not v:
                raise CliError("%d번 규칙의 %s 값이 비어 있지 않은 문자열이 아닙니다." % (i, k) + fix)
        if "extension" in r and not EXT_RE.fullmatch(r["extension"]):
            raise CliError("%d번 규칙의 extension 형식이 잘못되었습니다(예: .pdf, 소문자)." % i + fix)
        if not TARGET_RE.fullmatch(r["target"]):
            raise CliError("%d번 규칙의 target 형식이 잘못되었습니다(영문자로 시작, 영숫자·_-)." % i + fix)
        out.append(r)
    return out


def check_targets(folder, rules):
    for t in sorted({r["target"] for r in rules}):
        p = os.path.join(folder, t)
        if os.path.islink(p) or (os.path.lexists(p) and not os.path.isdir(p)):
            raise CliError("대상 경로 %s 가 이미 파일 또는 심볼릭 링크입니다. 해결: 해당 항목을 옮기거나 "
                           "규칙의 target 이름을 바꾸세요." % t)


def validate_log(log):
    """기존 로그를 검증한다. 이어 쓸 때 줄바꿈 보충이 필요한지 반환."""
    if log is None or not os.path.lexists(log):
        return False
    fix = " 해결: 로그 파일을 고치거나 다른 --log 경로를 지정하세요."
    try:
        with open(log, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise CliError("기존 로그를 읽을 수 없습니다(%s)." % e.strerror + fix)
    if not raw:
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise CliError("기존 로그가 UTF-8이 아닙니다." + fix)
    needs_nl = not text.endswith("\n")
    lines = text.split("\n")
    if not needs_nl:
        lines.pop()
    for n, line in enumerate(lines, 1):
        try:
            if not line.strip():
                raise ValueError("빈 줄")
            o = loads(line)
            if not isinstance(o, dict) or set(o) != {"timestamp", "source", "destination", "rule"}:
                raise ValueError("키 불일치")
            ts, src, dst, rule = o["timestamp"], o["source"], o["destination"], o["rule"]
            if not (isinstance(ts, str) and TS_RE.fullmatch(ts)):
                raise ValueError("timestamp")
            datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            if not (isinstance(src, str) and src and "/" not in src and "\\" not in src):
                raise ValueError("source")
            if not isinstance(dst, str):
                raise ValueError("destination")
            parts = dst.split("/")
            if len(parts) != 2 or not TARGET_RE.fullmatch(parts[0]) or not parts[1] or "\\" in parts[1]:
                raise ValueError("destination")
            if not (isinstance(rule, int) and not isinstance(rule, bool) and rule >= 1):
                raise ValueError("rule")
        except ValueError as e:
            why = "JSON 문법 오류" if isinstance(e, json.JSONDecodeError) else str(e)
            if "time data" in why or "does not match" in why:
                why = "timestamp"
            raise CliError("기존 로그 %d번째 줄이 형식에 맞지 않습니다(문제 항목: %s)." % (n, why) + fix)
    return needs_nl


def match_rule(name, rules):
    suffix = pathlib.Path(name).suffix.lower()
    for i, r in enumerate(rules, 1):
        if "extension" in r and suffix != r["extension"]:
            continue
        if "name" in r and not fnmatch.fnmatchcase(name, r["name"]):
            continue
        return i, r["target"]
    return None


def scan(folder):
    """바로 아래 일반 파일 (이름, (크기, mtime_ns)) 목록, 이름 오름차순."""
    res = []
    with os.scandir(folder) as it:
        for e in it:
            try:
                if e.is_symlink() or not e.is_file(follow_symlinks=False):
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            res.append((e.name, (st.st_size, st.st_mtime_ns)))
    res.sort(key=lambda x: x[0])
    return res


def pick_dest(folder, target, name, planned):
    p = pathlib.Path(name)
    cand, n = name, 0
    while True:
        full = os.path.join(folder, target, cand)
        key = os.path.normcase(full)
        if not os.path.lexists(full) and key not in planned:
            planned.add(key)
            return cand
        n += 1
        cand = "%s__%d%s" % (p.stem, n, p.suffix)


class Logger:
    def __init__(self, path, needs_nl):
        try:
            self.f = open(path, "a", encoding="utf-8", newline="\n")
            if needs_nl:
                self.f.write("\n")
                self.f.flush()
        except OSError as e:
            raise CliError("로그 파일을 쓸 수 없습니다(%s). 해결: 쓰기 권한과 경로를 확인하세요." % e.strerror)

    def add(self, source, dest, rule):
        rec = {"timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": source, "destination": dest, "rule": rule}
        self.f.write(dumps(rec) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def move_one(folder, name, target, rule, logger, items):
    tdir = os.path.join(folder, target)
    try:
        os.makedirs(tdir, exist_ok=True)
        dest_name = pick_dest(folder, target, name, set())
        os.rename(os.path.join(folder, name), os.path.join(tdir, dest_name))
    except OSError as e:
        raise CliError("파일 이동 중 입출력 오류가 났습니다(%s: %s). 해결: 권한과 디스크 상태를 확인한 뒤 "
                       "다시 실행하세요." % (name, e.strerror))
    item = {"source": name, "destination": target + "/" + dest_name, "rule": rule}
    try:
        logger.add(name, item["destination"], rule)
    except OSError as e:
        raise CliError("로그 기록에 실패했습니다(%s). 해결: 로그 경로의 쓰기 권한과 공간을 확인하세요." % e.strerror)
    items.append(item)


def do_preview(folder, rules):
    items, skipped, planned = [], 0, set()
    for name, _ in scan(folder):
        m = match_rule(name, rules)
        if m is None:
            skipped += 1
            continue
        d = pick_dest(folder, m[1], name, planned)
        items.append({"source": name, "destination": m[1] + "/" + d, "rule": m[0]})
    return items, skipped


def do_run(folder, rules, logger):
    items, skipped = [], 0
    for name, _ in scan(folder):
        m = match_rule(name, rules)
        if m is None:
            skipped += 1
            continue
        move_one(folder, name, m[1], m[0], logger, items)
    return items, skipped


def do_watch(folder, rules, logger, cycles, interval):
    items, prev, skipped = [], {}, 0
    print("감시를 시작했습니다.", flush=True)
    for c in range(cycles):
        if c:
            time.sleep(interval)
        skipped, cur = 0, {}
        for name, sig in scan(folder):
            m = match_rule(name, rules)
            if m is None:
                skipped += 1
            elif prev.get(name) == sig:
                move_one(folder, name, m[1], m[0], logger, items)
            else:
                cur[name] = sig
        prev = cur
    return items, skipped


def execute(argv):
    if any(a in ("--help", "-h") for a in argv):
        print(HELP_TEXT, end="")
        return
    args = build_parser().parse_args(argv)
    if args.command is None:
        raise CliError("명령이 없습니다. 해결: preview, run, watch 중 하나를 지정하세요.")
    cycles, interval = 1, 0
    if args.command == "watch":
        if not CYCLES_RE.fullmatch(args.cycles) or int(args.cycles) < 1:
            raise CliError("--cycles 는 1 이상의 정수여야 합니다. 해결: 예) --cycles 3")
        cycles = int(args.cycles)
        if not FLOAT_RE.fullmatch(args.interval):
            raise CliError("--interval 은 0보다 큰 숫자여야 합니다. 해결: 예) --interval 0.5")
        interval = float(args.interval)
        if not math.isfinite(interval) or interval <= 0 or interval > threading.TIMEOUT_MAX:
            raise CliError("--interval 은 0보다 큰 유한 실수(초)여야 합니다. 해결: 예) --interval 0.5")
    folder, rules_path, log = validate_paths(args)
    rules = load_rules(rules_path)
    check_targets(folder, rules)
    needs_nl = validate_log(log)

    if args.command == "preview":
        items, skipped = do_preview(folder, rules)
        matched, moved, log_out = len(items), 0, None
        summary = "일치 %d개, 이동 계획 %d개, 미일치 %d개입니다." % (matched, matched, skipped)
    else:
        logger = Logger(log, needs_nl)
        try:
            if args.command == "run":
                items, skipped = do_run(folder, rules, logger)
            else:
                items, skipped = do_watch(folder, rules, logger, cycles, interval)
        finally:
            logger.close()
        matched = moved = len(items)
        log_out = log
        summary = "일치 %d개, 이동 %d개, 미일치 %d개입니다." % (matched, moved, skipped)
    print(summary)
    for it in items:
        print("  %s -> %s (규칙 %d)" % (it["source"], it["destination"], it["rule"]))
    print(dumps({"ok": True, "command": args.command, "matched": matched, "moved": moved,
                 "skipped": skipped, "items": items, "log": log_out, "cycles": cycles}), flush=True)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        execute(sys.argv[1:] if argv is None else argv)
        return 0
    except CliError as e:
        msg = str(e)
    except OSError as e:
        msg = "입출력 오류가 났습니다(%s). 해결: 경로와 권한을 확인한 뒤 다시 실행하세요." % (e.strerror or e)
    print(msg)
    print(dumps({"ok": False, "error": msg}), flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
