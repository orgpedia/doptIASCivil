.DEFAULT_GOAL := help
SHELL := /bin/bash

SRC  := input/src
LOGS := input/logs
PY   := uv run python -u

# archive.org collection; change here or override: make upload_archive IA_COLLECTION=iascivil
IA_COLLECTION ?= ias-civil-list
# Wayback SPN2: reuse an existing capture newer than this instead of re-capturing
WAYBACK_REUSE ?= 30d

# Existing downloads used by `make seed`
SEED_PDFS ?= iasCivilList/pdfs
SEED_CSV  ?= iasCivilList/pdf_urls.csv

.PHONY: help install seed import download link_wayback upload_archive update_archive_metadata sync_hf_push

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  install                  set up the uv environment"
	@echo "  seed                     one-time: copy $(SEED_PDFS) into LFS and build downloads.json"
	@echo "  import                   download PDFs from the HF dataset into LFS/doptIASCivil"
	@echo "  download                 download missing PDFs (incl. current year) from iascivillist.dopt.gov.in"
	@echo "  link_wayback             capture PDF URLs in the Wayback Machine (SPN2)  [WAYBACK_REUSE=$(WAYBACK_REUSE)]"
	@echo "  upload_archive           upload PDFs to archive.org                      [IA_COLLECTION=$(IA_COLLECTION)]"
	@echo "  update_archive_metadata  re-apply metadata to uploaded archive.org items [IA_COLLECTION=$(IA_COLLECTION)]"
	@echo "  sync_hf_push             push LFS/doptIASCivil/pdfs to the HF dataset"
	@echo ""
	@echo "Credentials are read from .env (see env.example). See SPEC.md for details."

install: pyproject.toml
	uv venv
	uv sync

seed:
	set -o pipefail; $(PY) $(SRC)/seed.py $(SEED_PDFS) $(SEED_CSV) | tee $(LOGS)/seed.log

import:
	set -o pipefail; $(PY) $(SRC)/sync_hf.py pull | tee $(LOGS)/import.log

download:
	set -o pipefail; $(PY) $(SRC)/download.py | tee $(LOGS)/download.log

link_wayback:
	set -o pipefail; $(PY) $(SRC)/link_wayback.py --reuse $(WAYBACK_REUSE) | tee $(LOGS)/link_wayback.log

upload_archive:
	set -o pipefail; $(PY) $(SRC)/upload_archive.py --collection $(IA_COLLECTION) | tee $(LOGS)/upload_archive.log

update_archive_metadata:
	set -o pipefail; $(PY) $(SRC)/upload_archive.py --collection $(IA_COLLECTION) --update-metadata | tee $(LOGS)/update_archive_metadata.log

sync_hf_push:
	set -o pipefail; $(PY) $(SRC)/sync_hf.py push | tee $(LOGS)/sync_hf_push.log
