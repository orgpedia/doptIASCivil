"""Download IAS Civil List PDFs that are missing from LFS/doptIASCivil/pdfs.

Years come from the dropdown on /Home/Archive (ArchivedPdf/<year>.pdf) plus the
current calendar year (Current_Year_PDF/<year>.pdf). Existing files are never
re-downloaded; for the current year a warning is printed if the remote changed.
"""

import datetime
import re
import sys
import time

import requests

from common import (
    ARCHIVE_PAGE_URL,
    ARCHIVED_PDF_URL,
    CURRENT_PDF_URL,
    PDFS_DIR,
    USER_AGENT,
    link_pdf,
    pdf_path,
    read_records,
    sha1_file,
    utc_now,
    write_records,
)

RETRIES = 5
HEADERS = {"User-Agent": USER_AGENT}


def get_year_urls():
    r = requests.get(ARCHIVE_PAGE_URL, headers=HEADERS, timeout=60)
    r.raise_for_status()
    years = sorted(set(re.findall(r'option value="(\d{4})"', r.text)))
    if not years:
        raise SystemExit(f"Could not read the year list from {ARCHIVE_PAGE_URL}")

    year_urls = {y: (ARCHIVED_PDF_URL.format(year=y), "archived") for y in years}
    current = str(datetime.date.today().year)
    if current not in year_urls:
        year_urls[current] = (CURRENT_PDF_URL.format(year=current), "current")
    return year_urls, current


def total_size(r):
    if r.status_code == 206:
        m = re.search(r"/(\d+)$", r.headers.get("Content-Range", ""))
        return int(m.group(1)) if m else None
    length = r.headers.get("Content-Length")
    return int(length) if length else None


def fetch(url, dest):
    """Download url to dest via dest.part, resuming on retries. Returns (info, error)."""
    part = dest.with_name(dest.name + ".part")
    error = ""
    for attempt in range(1, RETRIES + 1):
        offset = part.stat().st_size if part.exists() else 0
        headers = dict(HEADERS, Range=f"bytes={offset}-") if offset else HEADERS
        try:
            with requests.get(url, headers=headers, stream=True, timeout=120) as r:
                if r.status_code == 404:
                    return None, "not_found"
                if r.status_code == 416:  # stale .part, start over
                    part.unlink()
                    continue
                r.raise_for_status()
                if r.status_code == 200:
                    offset = 0  # server ignored Range
                total = total_size(r)
                last_modified = r.headers.get("Last-Modified")
                with part.open("ab" if offset else "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)

            size = part.stat().st_size
            if total and size != total:
                raise OSError(f"size mismatch {size} vs {total}")
            part.replace(dest)
            return {"size": size, "last_modified": last_modified}, ""
        except (requests.RequestException, OSError) as e:
            error = str(e)
            print(f"\tattempt {attempt}/{RETRIES} failed: {error}")
            time.sleep(5 * attempt)
    return None, error


def check_current(year, url, record):
    """Warn if the in-place updated current-year PDF differs from what we have."""
    try:
        r = requests.head(url, headers=HEADERS, timeout=60, allow_redirects=True)
    except requests.RequestException as e:
        print(f"{year}: could not check remote ({e})")
        return False
    if r.status_code != 200:
        print(f"{year}: could not check remote (HTTP {r.status_code})")
        return False

    remote_size = int(r.headers.get("Content-Length") or 0) or None
    remote_lm = r.headers.get("Last-Modified")
    changed = False
    if remote_size and record.get("size") and remote_size != record["size"]:
        changed = True
    if remote_lm and record.get("last_modified") and remote_lm != record["last_modified"]:
        changed = True

    if changed:
        print(
            f"{year}: WARNING remote PDF has changed "
            f"(remote size={remote_size} last-modified={remote_lm}; "
            f"local size={record.get('size')} last-modified={record.get('last_modified')}). Not re-downloading."
        )
    elif remote_lm and not record.get("last_modified") and remote_size == record.get("size"):
        record["last_modified"] = remote_lm  # fill in for seeded records
        return True
    return False


def main():
    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    downloads = read_records("downloads")
    year_urls, current = get_year_urls()
    print(f"*** {len(year_urls)} years on site (current year {current})")

    downloaded, skipped, failed = [], [], []
    for year, (url, kind) in sorted(year_urls.items()):
        dest = pdf_path(year)
        if dest.exists():
            skipped.append(year)
            link_pdf(year)
            if kind == "current" and year in downloads:
                if check_current(year, url, downloads[year]):
                    write_records("downloads", downloads)
            continue

        print(f"{year}: downloading {url}")
        info, error = fetch(url, dest)
        if error == "not_found" and kind == "current":
            print(f"{year}: current year PDF not published yet")
            continue
        if not info:
            print(f"{year}: FAILED {error}")
            failed.append(year)
            downloads.setdefault(year, {"year": year, "url": url, "kind": kind})
            downloads[year]["status"] = f"failed:{error}"
            write_records("downloads", downloads)
            continue

        downloads[year] = {
            "year": year,
            "url": url,
            "kind": kind,
            "size": info["size"],
            "last_modified": info["last_modified"],
            "sha1": sha1_file(dest),
            "download_time_utc": utc_now(),
            "status": "downloaded",
        }
        write_records("downloads", downloads)
        link_pdf(year)
        downloaded.append(year)
        print(f"{year}: ok ({info['size']} bytes)")
        time.sleep(2)

    print(f"*** Downloaded: {len(downloaded)} {downloaded}")
    print(f"*** Skipped (already present): {len(skipped)}")
    print(f"*** Failed: {len(failed)} {failed}")
    if downloaded:
        print("*** Next: make link_wayback upload_archive sync_hf_push, then commit input/documents/")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
