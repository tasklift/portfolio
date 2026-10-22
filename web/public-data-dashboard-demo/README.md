# Static Dashboard from a Public-Data CSV

> A Python script cleans one Korean public-data CSV, and a static page with filters, KPI cards, SVG charts and a sortable table opens straight from index.html with no server.

![demo 1](docs/01_real_dashboard.png)
![demo 2](docs/02_sample_build.png)
![demo 3](docs/03_real_filters.png)
![demo 4](docs/demo.gif)

## The problem it solves

Anyone who downloads a CSV from a Korean public-data portal runs into inconsistent column names, mixed date formats, numbers written with commas, blanks or dashes, and a mix of UTF-8 and CP949 encodings. The file can't be charted as it is, and cleaning it by hand each time is tedious.

## What it does

- build.py picks the region, period and value columns, then writes the cleaned result as JSON and JS files.
- Periods such as 2023, 202301, 2023.02 or 2023년 3월 are normalized to YYYY or YYYY-MM; commas and spaces are stripped from values; unparseable rows are dropped and counted; duplicate region-and-period rows are summed.
- Reads UTF-8 first and falls back to CP949; prints a one-line summary on success and a warning when period formats are mixed or contain days.
- The static page offers region and start/end period filters with a reset button, plus three KPI cards (period total, latest value, top region).
- Draws a trend line chart and a ranking bar chart in plain SVG, with hover tooltips and a unit label.
- A sortable table (mouse, Enter or Space) and export of the current filtered view as a UTF-8 CSV with a BOM.

## How to run

1. Install Python 3. Only the standard library is used, so there is nothing else to install. On Windows, use py if python doesn't work.
2. To just view the page, open index.html in a browser. The bundled data/data.js is already built.
3. To rebuild with your own CSV (this overwrites data/data.json and data/data.js): python build.py --input 내파일.csv --region-col 지역열이름 --period-col 기간열이름 --value-col 값열이름 --title "내 제목" --unit 단위 --source "내 자료 이름"
4. To try the synthetic sample: python build.py --input 예제/지역별_월별_예시.csv --region-col 지역 --period-col 기준월 --value-col "이용 건수" --outdir 예제/결과 --title "예시 지역별 이용 건수" --unit 건 --source "직접 만든 가상 자료"
5. Open 예제/결과/index.html to see the result.

Sample files: `data/data.json`, `data/source.csv`, `예제/README.txt`, `예제/지역별_월별_예시.csv`, `예제/결과/data.json`

## Notes and limits

It handles one CSV with three columns (region, period, value) at a time and isn't meant for very large files. The charts have no legend, the 17 bars are hard to read on narrow screens, and tooltips may not appear on touch screens. The real sample's license terms and source URL weren't recorded, so the original CSV is left out; check the terms before redistributing. The rounding rules for commas, dashes and month formats were tested only on a synthetic sample, the CSV export wasn't tried in Excel, and I haven't seen the page in other people's browsers.

Tech: Python 3, HTML, CSS, JavaScript, SVG

## 한국어 안내 — 공공데이터 CSV 지역 통계 대시보드

> 공공데이터 CSV 한 개를 파이썬으로 정제하고, 필터·지표 카드·SVG 차트·정렬 표가 있는 정적 페이지를 서버 없이 index.html만 열어 볼 수 있게 만든 시연물입니다.

### 해결한 문제

공공데이터포털에서 CSV를 내려받으면 열 이름, 날짜 표기, 숫자 표기(쉼표·빈 칸·'-')가 제각각이고 인코딩도 UTF-8과 CP949가 섞여 있습니다. 그대로는 차트를 그릴 수 없고, 매번 손으로 정리하기도 번거롭습니다.

### 하는 일

- build.py가 지역·기간·값 열을 골라 정제한 뒤 JSON과 JS 파일로 저장합니다.
- 2023, 202301, 2023.02, 2023년 3월 같은 기간 표기를 YYYY 또는 YYYY-MM으로 맞추고, 값의 쉼표·공백을 지웁니다. 해석할 수 없는 행은 버리고 그 수를 기록하며, 같은 지역·기간은 값을 더합니다.
- UTF-8을 먼저 시도하고 실패하면 CP949로 읽습니다. 성공하면 한 줄로 결과를 알리고, 기간 표기가 섞였거나 일(day)이 있으면 경고합니다.
- 정적 페이지에서 지역·시작 기간·끝 기간 필터와 초기화 버튼, 핵심 지표 카드 3개(기간 합계, 최근 값, 최고 지역)를 쓸 수 있습니다.
- 순수 SVG로 기간별 추이 선그래프와 지역별 순위 막대그래프를 그리며, 마우스를 올리면 값과 단위가 뜹니다.
- 열 머리글을 눌러(Enter·Space 포함) 정렬하는 상세 표와, 현재 필터 결과를 UTF-8(BOM 포함) CSV로 내려받는 기능이 있습니다.

### 실행 방법

1. Python 3를 준비합니다. 표준 라이브러리만 쓰므로 추가로 설치할 것은 없습니다. 윈도에서 python이 안 되면 py로 바꿔 입력하세요.
2. 화면만 보려면 index.html을 브라우저로 엽니다. 만들어진 data/data.js가 이미 들어 있습니다.
3. 내 CSV로 바꾸려면 다음을 실행합니다(data/data.json, data/data.js를 덮어씁니다): python build.py --input 내파일.csv --region-col 지역열이름 --period-col 기간열이름 --value-col 값열이름 --title "내 제목" --unit 단위 --source "내 자료 이름"
4. 가상 예제로 연습하려면 다음을 실행합니다: python build.py --input 예제/지역별_월별_예시.csv --region-col 지역 --period-col 기준월 --value-col "이용 건수" --outdir 예제/결과 --title "예시 지역별 이용 건수" --unit 건 --source "직접 만든 가상 자료"
5. 예제/결과/index.html을 열어 결과를 확인합니다.

### 한계

한 번에 CSV 한 개의 세 열(지역·기간·값)만 다루며, 매우 큰 파일에는 맞지 않습니다. 차트에 범례가 없고, 17개 막대는 좁은 화면에서 글자가 작으며, 터치 화면에서는 값 표시가 안 뜰 수 있습니다. 실제 예시 데이터의 이용 조건과 원본 주소를 기록하지 못해 원본 CSV는 뺐으니, 재배포 전에 조건을 확인해야 합니다. 쉼표·'-'·월 표기 규칙은 가상 예제로만 확인했고, CSV 내려받기를 엑셀에서 열어 보지 않았으며, 다른 사람의 브라우저 화면도 확인하지 못했습니다.

---
Category: 웹사이트 · Built and tested with Claude Code. Every number above comes from a real run on this machine.
