import argparse, csv, json, os, re, sys


def read_rows(path, enc):
    if enc == "auto":
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                return list(csv.reader(f))
        except UnicodeDecodeError:
            with open(path, encoding="cp949", newline="") as f:
                return list(csv.reader(f))
    with open(path, encoding=enc, newline="") as f:
        return list(csv.reader(f))


def norm_period(s):
    nums = re.findall(r"\d+", s or "")
    if not nums:
        return None
    if len(nums) == 1:
        n = nums[0]
        if len(n) == 4:
            y, m = n, None
        elif len(n) == 6:
            y, m = n[:4], n[4:]
        else:
            return None
    else:
        y, m = nums[0], nums[1]
        if len(y) != 4 or len(m) > 2:
            return None
    if m is None:
        return y
    if not 1 <= int(m) <= 12:
        return None
    return "%s-%02d" % (y, int(m))


def norm_value(s):
    t = (s or "").replace(",", "").replace(" ", "").replace("\u00a0", "").strip()
    if not t or t == "-":
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    try:
        if re.fullmatch(r"[+-]?\d+", t):
            return int(t)
    except ValueError:
        pass
    return int(v) if v == int(v) else v


class KoParser(argparse.ArgumentParser):
    def error(self, message):
        names = {"the following arguments are required": "꼭 필요한 인자가 빠졌습니다"}
        msg = message
        for k, v in names.items():
            if message.startswith(k):
                msg = v + ":" + message.split(":", 1)[1]
        sys.stderr.write("인자 오류: %s\n" % msg)
        sys.stderr.write("고치는 방법: --input, --region-col, --period-col, --value-col 네 가지는 반드시 적어야 합니다.\n")
        sys.stderr.write('예: python build.py --input 내파일.csv --region-col 지역 --period-col 기준월 --value-col 값\n')
        sys.stderr.write("자세한 사용법은 README.md를 보거나 --help를 붙여 실행하세요.\n")
        sys.exit(2)


def main():
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:
            pass
    p = KoParser()
    p.add_argument("--input", required=True)
    p.add_argument("--region-col", required=True)
    p.add_argument("--period-col", required=True)
    p.add_argument("--value-col", required=True)
    p.add_argument("--outdir", default="data")
    p.add_argument("--title")
    p.add_argument("--unit", default="")
    p.add_argument("--source", default="공공데이터포털")
    p.add_argument("--encoding", default="auto")
    a = p.parse_args()

    if not os.path.isfile(a.input):
        sys.stderr.write("입력 파일을 찾을 수 없습니다: %s\n고치는 방법: 파일 이름과 경로를 확인하세요. 폴더가 다르면 전체 경로를 적고, 공백이 있으면 큰따옴표로 감싸세요.\n" % a.input)
        return 1
    try:
        rows = read_rows(a.input, a.encoding)
    except (UnicodeDecodeError, LookupError) as e:
        sys.stderr.write("파일을 읽을 수 없습니다(인코딩 오류): %s\n고치는 방법: --encoding cp949 또는 --encoding utf-8 처럼 파일에 맞는 인코딩을 직접 지정하세요.\n" % e)
        return 1
    if not rows:
        sys.stderr.write("입력 파일이 비어 있습니다.\n고치는 방법: 첫 줄에 머리글이 있는 CSV 파일인지 확인하세요.\n")
        return 1
    head = [h.strip() for h in rows[0]]
    idx = []
    for c in (a.region_col, a.period_col, a.value_col):
        if c not in head:
            first = (head[0] if head else "")
            if first.startswith("<") or "\x00" in first or "\ufffd" in first or first.startswith("PK") or first.startswith("%PDF"):
                sys.stderr.write("CSV 파일이 아닌 것 같습니다: %s (첫 줄이 웹 문서·압축·바이너리 형태입니다)\n고치는 방법: 공공데이터포털에서 받은 CSV 파일(.csv)을 --input에 적으세요. 엑셀 파일(.xlsx)이면 엑셀에서 'CSV로 저장'한 뒤 쓰세요.\n" % a.input)
                return 1
            sys.stderr.write("열 이름을 찾을 수 없습니다: %s (머리글: %s)\n고치는 방법: 위 머리글 목록의 이름과 똑같이 열 이름 인자에 적으세요.\n" % (c, ", ".join(head)))
            return 1
        idx.append(head.index(c))
    ri, pi, vi = idx

    dropped = 0
    agg = {}
    has_day = 0
    for row in rows[1:]:
        if not row or all(not c.strip() for c in row):
            continue
        get = lambda i: row[i] if i < len(row) else ""
        region = get(ri).strip()
        raw_period = get(pi)
        period = norm_period(raw_period)
        if period is not None and len(re.findall(r"\d+", raw_period)) >= 3:
            has_day += 1
        value = norm_value(get(vi))
        if not region or period is None or value is None:
            dropped += 1
            continue
        k = (period, region)
        agg[k] = agg.get(k, 0) + value
    records = []
    for (period, region) in sorted(agg):
        v = agg[(period, region)]
        if isinstance(v, float):
            v = round(v, 10)
            if v == int(v):
                v = int(v)
        records.append({"region": region, "period": period, "value": v})
    data = {
        "title": a.title if a.title is not None else os.path.splitext(os.path.basename(a.input))[0],
        "source": a.source,
        "unit": a.unit,
        "regions": sorted({r["region"] for r in records}),
        "periods": sorted({r["period"] for r in records}),
        "records": records,
        "dropped_rows": dropped,
    }
    kinds = {len(r["period"]) for r in records}
    if len(kinds) > 1:
        sys.stderr.write("경고: 기간 표기가 연도('2023')와 월('2023-01')로 섞여 있습니다. 한 파일에서는 한 가지로 통일해야 그래프가 맞습니다.\n")
    if has_day:
        sys.stderr.write("경고: 기간에 일(day)이 들어 있는 행이 %d개 있습니다. 일은 무시하고 월 단위로 합칩니다.\n" % has_day)
    text = json.dumps(data, ensure_ascii=False)
    os.makedirs(a.outdir, exist_ok=True)
    with open(os.path.join(a.outdir, "data.json"), "w", encoding="utf-8", newline="") as f:
        f.write(text)
    with open(os.path.join(a.outdir, "data.js"), "w", encoding="utf-8", newline="") as f:
        f.write("window.DASHBOARD_DATA = " + text + ";\n")
    print("완료: %d건을 정리했고 %d행을 버렸습니다. 지역 %d곳, 기간 %d개. 저장 위치: %s" % (
        len(records), dropped, len(data["regions"]), len(data["periods"]), os.path.abspath(a.outdir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
