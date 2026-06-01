# Hankyung PDF Temp Metadata

## Purpose

The temporary Hankyung Consensus PDF flow stores extracted PDF text together with
server-controlled report metadata. The metadata is configured on each seed and is
copied into `raw.hankyung_consensus_pdf_temp_files` during ingest.

This remains a temp/test flow. It is not the final production analyst-report model.

## Seed configuration

`PDF_TEMP_SEED_REGISTRY_JSON` is a JSON array. Clients can request registered
`seedIds`, but they cannot submit arbitrary URLs, local paths, or metadata in the
ingest request.

Example:

```json
[
  {
    "seed_id": "hankyung-628514",
    "source_type": "url",
    "label": "Hankyung Consensus report 628514",
    "source_url": "https://consensus.hankyung.com/analysis/downpdf?report_idx=628514",
    "report_idx": "628514",
    "title": null,
    "company": null,
    "ticker": null,
    "broker": null,
    "report_date": null
  }
]
```

Rules:

- `report_idx` is optional. If omitted and `seed_id` matches `hankyung-<digits>`,
  the backend derives it from the seed ID.
- `title`, `company`, `ticker`, `broker`, and `report_date` are optional.
- `ticker` is stored as a string so leading zeroes are preserved.
- `report_date` must be a real ISO date in `YYYY-MM-DD` format.
- Metadata values must come from server-side seed config, not from API request bodies.

## DB columns

Migration `DE/migrations/009_hankyung_consensus_pdf_temp_metadata.sql` adds:

- `report_idx TEXT`
- `report_title TEXT`
- `company_name TEXT`
- `ticker TEXT`
- `broker TEXT`
- `report_date DATE`

The migration also backfills `report_idx` for existing `hankyung-<digits>` seed
rows without overwriting non-null values.

## API response fields

Seed responses expose safe metadata:

- `reportIdx`
- `title`
- `company`
- `ticker`
- `broker`
- `reportDate`

File/list/detail/ingest responses expose:

- `reportIdx`
- `reportTitle`
- `companyName`
- `ticker`
- `broker`
- `reportDate`

Source URLs and local paths remain hidden.
