# Portfolio: small runnable automation demos

Short, working examples of the kind of jobs I take: web scraping, Excel/VBA-style tools, macros and small websites. Each folder has a README with the problem, screenshots and how to run or view it. Where a folder is a demo of a paid product, only screenshots and sample input are published.

각 폴더에 해결한 문제, 화면, 실행 방법이 있습니다. 유료 상품은 화면과 표본 입력만 공개합니다.

## 크롤링

- [Book Listing Scraper Sample Kit](crawling/books-scrape-sample/) - A standard-library Python command-line tool that crawls all 50 pages of a public practice bookstore and produces an Excel workbook, price-change comparison, request log, and a sample folder for a product page. (code)
- [Web list scraping to Excel, rerunnable](crawling/custom-crawler-kit/) - A paid scraping service that delivers an Excel or CSV file of repeated web lists, plus a program and job settings so the buyer can rerun the collection later. (demo only)
- [Spreadsheet Reports for Collected List Changes](crawling/change-watch-sample-log/) - A Python command-line tool that compares two saved collection records and produces an Excel file and an HTML page showing added, removed, and changed rows. (code)
- [Web List Changes in Spreadsheet Reports](crawling/web-change-watcher/) - A privately distributed tool configured for a chosen web list that compares saved records and exports new, removed, and changed items to Excel and an HTML report. (demo only)

## 엑셀·VBA

- [Merge, split and dedupe Excel files](excel_vba/excel-merge-split/) - A Windows command-line tool that merges many Excel/CSV files into one, splits a file by column value, removes duplicate rows and totals by group, with no install and no Excel required. (demo only)
- [Spreadsheet Inventory Tracking and Stock Movement](excel_vba/gsheet-inventory/) - A demo of a paid spreadsheet inventory script that calculates stock balances and monthly movements, checks entries, and provides shortage alerts, with source code kept private. (demo only)

## 웹사이트

- [One-page website maker for small shops](web/biz-landing-template-kit/) - A browser tool that turns a business name, intro and phone number into a single-file one-page website and a share image, with no install or sign-up. (demo only)
- [Static Dashboard from a Public-Data CSV](web/public-data-dashboard-demo/) - A Python script cleans one Korean public-data CSV, and a static page with filters, KPI cards, SVG charts and a sortable table opens straight from index.html with no server. (code)

## 업무 자동화

- [File Sorting with Move Logs](automation/automation-7aba49/) - A Python command-line tool that sorts files by extension and filename rules, previews planned moves, and records completed moves in JSONL logs. (code)
- [Compare Product CSVs and Track Changes](automation/automation-ac3ab7/) - A Python command-line tool that compares two product CSVs by SKU and saves product statuses, changed fields, price and stock differences, counts, and execution logs. (code)

---
Built and tested with Claude Code. No client work is shown here; every demo uses sample or public practice data.
