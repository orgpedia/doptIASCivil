"""One-time: copy already downloaded PDFs into LFS and build downloads.json.

Usage: seed.py <src_pdfs_dir> <pdf_urls.csv>
"""

import csv
import datetime
import shutil
import sys
from pathlib import Path

import requests

from common import PDFS_DIR, USER_AGENT, link_pdf, pdf_path, read_records, sha1_file, write_records


def head_last_modified(url):
    try:
        r = requests.head(url, headers={"User-Agent": USER_AGENT}, timeout=30, allow_redirects=True)
        return r.headers.get("Last-Modified") if r.status_code == 200 else None
    except requests.RequestException:
        return None


def main(src_dir, urls_csv):
    with urls_csv.open() as f:
        year_urls = {row["year"]: row["url"] for row in csv.DictReader(f)}

    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    downloads = read_records("downloads")

    src_pdfs = sorted(p for p in src_dir.glob("*.pdf") if p.is_file() and not p.is_symlink())
    print(f"*** Seeding {len(src_pdfs)} PDFs from {src_dir}")
    for src in src_pdfs:
        year = src.stem
        dest = pdf_path(year)
        if dest.exists() and dest.stat().st_size == src.stat().st_size:
            print(f"{year}: already in LFS")
        else:
            print(f"{year}: copying ({src.stat().st_size} bytes)")
            shutil.copy2(src, dest)
        link_pdf(year)

        if downloads.get(year, {}).get("status") == "downloaded":
            continue

        url = year_urls.get(year)
        if not url:
            print(f"{year}: WARNING no url in {urls_csv.name}, skipping record")
            continue

        mtime = datetime.datetime.fromtimestamp(src.stat().st_mtime, tz=datetime.timezone.utc)
        downloads[year] = {
            "year": year,
            "url": url,
            "kind": "current" if "Current_Year_PDF" in url else "archived",
            "size": dest.stat().st_size,
            "last_modified": head_last_modified(url),
            "sha1": sha1_file(dest),
            "download_time_utc": mtime.strftime("%Y-%m-%d %H:%M:%S %Z%z"),
            "status": "seeded",
        }
        write_records("downloads", downloads)

    print(f"*** Done: {len(downloads)} records in downloads.json")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"Usage: {sys.argv[0]} <src_pdfs_dir> <pdf_urls.csv>")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
