# Web list scraper with Excel export

> A Windows tool that collects repeating list pages into Excel or CSV and records what changed since the previous run.

![demo 1](docs/01_suggest.png)
![demo 2](docs/02_extract.png)
![demo 3](docs/03_crawl.png)
![demo 4](docs/04_diff.png)

## The problem it solves

Sellers who check competitor prices and stock every day, and staff who copy job or board listings into a spreadsheet by hand, spend time on the same repetitive work. A one-off scraped file doesn't help much once the page changes, because they can't run it again themselves.

## What it does

- Walks through multiple pages automatically, with an adjustable delay between pages
- Saves results as xlsx or CSV, and reads older EUC-KR sites without garbled Korean text
- Compares against the previous result and records only price changes, removed items and new items
- If the site structure changes and nothing can be collected, writes to an alert file and keeps the previous result
- Ships as an executable with a user guide, so the same job settings can be rerun without installing Python
- Includes a sample bat file for daily runs

## Demo walkthrough

This folder shows the result only: screenshots, sample input and what comes out. The tool itself is a paid product, so its source code is not published here.

1. Send the target URL and the fields you need (for example product name, price, link) in a message; feasibility is checked before purchase.
2. The job settings for that site are built, and an xlsx or CSV result is returned. Example: a 30-page, 600-row run on a public practice site finished with 0 failed pages.
3. With the Standard or Premium plan you also get the executable and a user guide, so you can rerun the same job and get a change log (price changes, removed items, new items) against the previous result.

Sample files: `sample/-_-.csv`, `sample/-_-.csv`, `sample/-_-_-.csv`, `sample/-.json`, `sample/-.json`, `sample/-_-.json`, `sample/-_-.json`

## Notes and limits

It can't handle pages that need login or CAPTCHA, sites that forbid scraping, or personal data. Pages drawn later by JavaScript work only from saved HTML files, and locating items uses simple tag/class selectors, so complex shop layouts may not work. Multi-site runs weren't tested, and real-site checks went up to 30 pages and 600 rows. Registering the daily run in Windows Task Scheduler has not been verified; only the bat example was run twice on a practice site.

Tech: Python, Windows executable, xlsx, CSV, HTML parsing, CLI

## 한국어 안내 — 웹 목록 수집 및 엑셀 저장 도구

> 반복되는 웹 목록을 엑셀·CSV로 모으고, 지난 결과와 달라진 점을 기록해 주는 윈도우용 수집 도구입니다.

### 해결한 문제

경쟁 쇼핑몰의 가격·재고를 매일 확인하는 판매자나 공고·게시판 목록을 일일이 복사해 엑셀에 붙이는 실무자는 같은 작업을 계속 반복합니다. 한 번 받고 끝나는 수집 파일은 페이지가 바뀌면 직접 다시 돌릴 수 없어서 도움이 오래가지 않습니다.

### 하는 일

- 여러 쪽을 자동으로 돌며 수집하고, 쪽 사이 간격을 조절할 수 있습니다
- 결과를 xlsx·CSV로 저장하며, 옛 EUC-KR 사이트도 한글이 깨지지 않습니다
- 이전 결과와 비교해 가격 변경·사라진 항목·새 항목만 골라 기록합니다
- 사이트 구조가 바뀌어 수집이 안 되면 알림 파일에 남기고 이전 결과는 보존합니다
- 실행 파일과 사용설명서를 함께 제공해, 파이썬 설치 없이 같은 작업 설정으로 다시 돌릴 수 있습니다
- 매일 실행용 bat 예시 파일이 들어 있습니다

### 데모 보는 법

이 폴더는 화면과 표본 입력, 결과 설명만 보여 줍니다. 실제 도구는 유료 상품이라 소스 코드는 올리지 않습니다.

1. 수집할 주소와 필요한 항목(예: 상품명·가격·링크)을 메시지로 보내면, 구매 전에 수집 가능 여부를 먼저 확인합니다.
2. 해당 사이트에 맞는 작업 설정을 만들어 xlsx 또는 CSV 결과를 보내 드립니다. 예: 연습용 공개 사이트 30쪽 600건 수집에서 실패한 쪽은 0개였습니다.
3. 표준·프리미엄은 실행 파일과 사용설명서도 함께 드려서, 같은 설정으로 다시 돌리고 이전 결과 대비 변경내역(가격 변경·사라진 항목·새 항목)을 받아 볼 수 있습니다.

### 한계

로그인·캡차가 필요한 페이지, 수집을 막은 사이트, 개인정보 수집은 작업하지 않습니다. 자바스크립트로 나중에 그려지는 화면은 저장한 HTML 파일로만 가능하고, 위치 지정이 태그·클래스만 쓰는 단순한 방식이라 구조가 복잡한 쇼핑몰은 안 될 수 있습니다. 여러 사이트를 한 번에 도는 구성은 시험하지 않았고 실제 사이트 확인은 30쪽 600건까지입니다. 윈도우 작업 스케줄러 등록은 확인하지 못했고, 연습용 사이트로 bat 예시를 두 번 실행해 본 것까지입니다.

---
Category: 크롤링 · Built and tested with Claude Code. Every number above comes from a real run on this machine.
