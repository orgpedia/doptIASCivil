# doptIASCivil — Spec

Archive the IAS Civil List PDFs published by DoPT at
<https://iascivillist.dopt.gov.in/Home/Archive>. The pipeline does four things:

1. Download them.
2. Link them in the Wayback Machine.
3. Upload them to archive.org.
4. Keep the PDFs in a Hugging Face dataset.

## 1. Source website

| What | URL |
|---|---|
| Year list | `https://iascivillist.dopt.gov.in/Home/Archive`: `<option value="YYYY">` entries in the year dropdown |
| Archived year | `https://iascivillist.dopt.gov.in/ReportOutput/ArchivedPdf/<year>.pdf` |
| Current year | `https://iascivillist.dopt.gov.in/ReportOutput/Current_Year_PDF/<year>.pdf`, where `<year>` = this calendar year. This is what the page's "Current" button opens, through `ebook()` → `Ebook/Index.html` with `reportType=1`. |

- The current-year PDF is updated in place during the year (`Last-Modified` changes). It is **not** listed in the dropdown, and `ArchivedPdf/<current year>.pdf` returns 404.
- Some years are missing from the site (e.g. 1958, 1961, 1980).
- Requests use the `User-Agent: Mozilla/5.0` header.

## 2. Repository layout

```
doptIASCivil/
├── Makefile
├── SPEC.md
├── pyproject.toml            # uv project
├── env.example               # template for .env
├── .gitignore                # .env, .venv/, LFS/, input/logs/*.log
├── input/
│   ├── src/
│   │   ├── common.py         # paths, constants, json/symlink helpers
│   │   ├── seed.py           # one-time: copy existing PDFs + build downloads.json
│   │   ├── download.py
│   │   ├── link_wayback.py
│   │   ├── upload_archive.py # upload + --update-metadata
│   │   └── sync_hf.py        # pull | push
│   ├── documents/            # tracked in git
│   │   ├── downloads.json
│   │   ├── wayback.json
│   │   ├── archive.json
│   │   └── <year>.pdf  ->  ../../LFS/doptIASCivil/pdfs/<year>.pdf   (relative symlinks)
│   └── logs/                 # <target>.log, written via tee
└── LFS/doptIASCivil/         # NOT in git; local mirror of HF dataset Orgpedia/doptIASCivil
    └── pdfs/<year>.pdf
```

- PDFs are stored **only** in `LFS/doptIASCivil/pdfs/`.
- `input/documents/<year>.pdf` are relative symlinks to them. The symlinks are committed to git, so they dangle until `make import` has been run.
- The JSON state files live **only** in `input/documents/` (git) and are never pushed to HF.
- The HF dataset holds only `pdfs/<year>.pdf`.
- Code does not reuse or import anything from mahgetGR or mahgetNewGRs.

## 3. Environment (`.env`, loaded with python-dotenv)

| Variable | Used by | Notes |
|---|---|---|
| `HF_TOKEN` | import, sync_hf_push | Needs write access to `Orgpedia/doptIASCivil`. |
| `HF_REPO_ID` | import, sync_hf_push | Optional. Default: `Orgpedia/doptIASCivil`. |
| `IA_ACCESS_KEY` | link_wayback, upload_archive | archive.org S3 key. Also used for SPN2. |
| `IA_SECRET_KEY` | link_wayback, upload_archive | |

`env.example` lists all of these with empty values.

## 4. State files (`input/documents/*.json`)

- Each file is a JSON list with one record per year, sorted by year and written with `indent=2` so git diffs stay readable.
- Each file is rewritten after every year is processed, so an interrupted run can resume.

**downloads.json**
```json
{"year": "2026", "url": "https://…/Current_Year_PDF/2026.pdf", "kind": "current",
 "size": 67381848, "last_modified": "Mon, 22 Jun 2026 07:28:04 GMT",
 "sha1": "…", "download_time_utc": "2026-10-07 11:55:00 UTC+0000", "status": "downloaded"}
```
- `kind` is `current` or `archived`.
- `status` is `downloaded`, `seeded` or `failed:<reason>`.

**wayback.json**
```json
{"year": "2026", "url": "<source url>", "link_success": true, "job_id": "…",
 "timestamp": "20261007115500", "archive_url": "https://web.archive.org/web/<ts>/<url>",
 "content_url": "https://web.archive.org/web/<ts>id_/<url>", "message": "", "time_utc": "…"}
```

**archive.json**
```json
{"year": "2026", "identifier": "in.gov.dopt.iascivillist.2026",
 "archive_url": "https://archive.org/details/in.gov.dopt.iascivillist.2026",
 "upload_success": true, "message": "", "time_utc": "…"}
```

## 5. Make targets

Every target runs `uv run python -u input/src/<script>.py …` and pipes the output through `tee input/logs/<target>.log`.

### `make install`
Runs `uv venv && uv sync`. Dependencies: `requests`, `internetarchive`, `huggingface-hub`, `python-dotenv`.

### `make seed` (one-time)
1. Copies `iasCivilList/pdfs/*.pdf` to `LFS/doptIASCivil/pdfs/`. It skips non-PDF entries such as the `mahgetGR-src` symlink, and skips files already present with the same size.
2. Builds `downloads.json` from `iasCivilList/pdf_urls.csv` plus the local size and sha1, with `status: seeded`.
3. Creates the `input/documents/<year>.pdf` symlinks.

### `make import`
1. Calls `huggingface_hub.snapshot_download(repo_id, repo_type="dataset", local_dir="LFS/doptIASCivil", allow_patterns=["pdfs/*.pdf"])`, which fetches only missing or changed files.
2. Creates or repairs the symlinks for every year listed in `downloads.json`.

### `make download`
1. Fetches `/Home/Archive` and parses the dropdown years. Adds the current calendar year using the `Current_Year_PDF` URL.
2. For each year where `LFS/doptIASCivil/pdfs/<year>.pdf` is **missing**:
   - Download it with `requests`, streaming to `<year>.pdf.part` with retries, resuming with a `Range` header when possible.
   - Verify the size against `Content-Length`, then rename the file to `<year>.pdf`.
   - Create the symlink and add or update the `downloads.json` record.
3. If the file **exists**, skip it. For the current year only, also send a HEAD request and print a **warning** if the remote `Content-Length` or `Last-Modified` differs from `downloads.json`. The file is not re-downloaded.
4. If the current year returns 404 (e.g. in early January, before publication), log "not published yet" and do not treat it as an error.
5. Print a summary of downloaded, skipped and failed years. Exit with a non-zero code if any download failed.

To test: delete any `<year>.pdf` from `LFS/doptIASCivil/pdfs/`, then run `make download`.

### `make link_wayback` (SPN2)
Runs for every year in `downloads.json` without `link_success: true` in `wayback.json`. Years run one at a time.

1. `POST https://web.archive.org/save`
   - Headers: `Accept: application/json`, `Authorization: LOW <IA_ACCESS_KEY>:<IA_SECRET_KEY>`
   - Form: `url=<source url>`, `capture_all=1`, `skip_first_archive=1`, `if_not_archived_within=<WAYBACK_REUSE>`
   - `WAYBACK_REUSE` defaults to `30d` and can be overridden from make, e.g. `make link_wayback WAYBACK_REUSE=365d`. A recent existing capture is reused instead of capturing the PDF again.
2. Read the `job_id` from the response, then poll `GET https://web.archive.org/save/status/<job_id>` every 5 s until `status` is `success` or `error`. The poll times out after 600 s because the PDFs are up to ~70 MB.
3. On success, record the `timestamp`, `archive_url` and `content_url`. On error or timeout, record `link_success: false` and the message; the next run retries it.
4. Wait 10 s between years. On HTTP 429 or 5xx, back off for 60 s. After 3 consecutive service failures, stop the run.

### `make upload_archive`
Runs for every year in `downloads.json` without `upload_success: true` in `archive.json`. It uses `internetarchive.upload(identifier, files={"<year>.pdf": path}, metadata=…, access_key, secret_key, checksum=True, retries=5, retries_sleep=30)`. `checksum=True` makes re-runs skip files that are already uploaded.

- **identifier**: `in.gov.dopt.iascivillist.<year>`
- **collection**: set by the Makefile variable `IA_COLLECTION ?= opensource` (Community Texts), which is passed to the script as `--collection`. To change it, run `make upload_archive IA_COLLECTION=iascivil` or edit the one line in the Makefile.
- **metadata** (built in a single function in `upload_archive.py`). Example for 2026:

| Field | Value |
|---|---|
| `collection` | `opensource` (from `IA_COLLECTION`) |
| `mediatype` | `texts` |
| `title` | `IAS Civil List 2026` |
| `creator` | `Department of Personnel and Training, Government of India` |
| `publisher` | `Department of Personnel and Training, Government of India` |
| `date` | `2026` |
| `year` | `2026` |
| `language` | `eng` |
| `subject` | `IAS Civil List; Indian Administrative Service; IAS; Department of Personnel and Training; DoPT; Government of India; 2026` |
| `source` | `https://iascivillist.dopt.gov.in/ReportOutput/Current_Year_PDF/2026.pdf` |
| `source_page` | `https://iascivillist.dopt.gov.in/Home/Archive` |
| `wayback_url` | `https://web.archive.org/web/<ts>/<source url>` (only if linked) |
| `edition` | `current` or `archived`, as on the DoPT site at the time of download |
| `source_last_modified` | `Mon, 22 Jun 2026 07:28:04 GMT` (from the `Last-Modified` header, if known) |
| `sha1` | sha1 of the uploaded PDF |
| `licenseurl` | not set. Government of India publication; add one later if needed. |
| `description` | HTML: "IAS Civil List <year>, published by the Department of Personnel and Training, Government of India", plus a table of Title, Year, Department, Source URL, Wayback URL and download date |

- archive.org adds its own technical metadata on top of this: OCR text, page count, file size and md5.
- If a year has no Wayback link yet, upload it anyway and leave the `wayback_url` field out. The intended order is `link_wayback` first, then `upload_archive`.

### `make update_archive_metadata`
- For every year with `upload_success: true`, it rebuilds the metadata with the function above and applies it with `internetarchive.modify_metadata`. It does not re-upload the PDF.
- Use it after changing the metadata function, after a Wayback link is added later, or to move items with `make update_archive_metadata IA_COLLECTION=iascivil`. Moving items into `iascivil` only works once your account has write access to that collection; otherwise the archive.org admins move them when they create it.
- After every upload, print the identifier and URL. At the end, print the list of all `https://archive.org/details/<identifier>` URLs, for the collection request.

### `make sync_hf_push`
1. `HfApi.create_repo(repo_id, repo_type="dataset", exist_ok=True)`
2. `HfApi.upload_folder(folder_path="LFS/doptIASCivil", repo_type="dataset", allow_patterns=["pdfs/*.pdf"], commit_message="sync IAS civil list pdfs")`

Unchanged files are not uploaded again.

### `make help`
Lists the targets (default goal).

## 6. Typical flows

- **First time (this machine):** `make install && make seed && make sync_hf_push && make link_wayback && make upload_archive`
- **Fresh clone:** `make install && make import`
- **Periodic update:** `make download && make link_wayback && make upload_archive && make sync_hf_push`, then commit `input/documents/`.

## 7. Out of scope

- Re-downloading or versioning a changed current-year PDF. Only a warning is printed.
- Parsing or extracting data from the PDFs (`flow/`, `output/`).
