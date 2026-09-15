# Feedback River

Feedback River is a dependency-light, public-safe dashboard for Medallia payment feedback. It is plain HTML/CSS/JS with a Python standard-library data pipeline, designed for GitHub Pages and easy transfer to `dktunited` later.

## Local usage

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=. python3 scripts/build_public_data.py
python3 -m http.server 8000 --directory public
```

Open <http://localhost:8000>. Without credentials the pipeline uses `data/fixture.json`, so the dashboard works immediately. `public/data.json` is generated and should be committed when refreshing data.

## Medallia adapter and secrets

The official Medallia API endpoint is deliberately configurable: this repository does **not** invent or assume a Medallia URL, API version, authentication scheme beyond an optional bearer token, pagination model, or response field names. Set these GitHub Actions secrets (or environment variables locally):

* `MEDALLIA_API_URL`: the approved tenant-specific endpoint.
* `MEDALLIA_API_TOKEN`: optional token sent as `Authorization: Bearer ...`.
* `ANONYMIZATION_SALT`: stable private salt; use the same value for consistent public pseudonyms.

The endpoint must return JSON containing either a top-level array or a `feedback` array. Each item must use this canonical mapping:

`id`, `created_at` (ISO-8601), `country`, `payment_method`, `channel`, `rating` (0–5), and `comment` (string). The adapter validates this contract and fails explicitly on malformed data. If your approved Medallia response uses different names or nesting, implement that tenant-specific field mapping in `map_medallia_response()` after confirming it with the API owner; do not guess.

## Privacy model

Only transformed records are written to `public/data.json`. The pipeline deterministically replaces email addresses, phone numbers, URLs, order references, and optional direct-identifier fields with salted SHA-256 tokens. The salt is never written to public artifacts. This is pseudonymization, not a guarantee of anonymity: review source fields and add a reviewed redaction rule before exposing new data. Do not put raw API responses, credentials, or salts in the repository.

## Workflows

* **Build feedback data** runs daily and weekly, and can be started with `workflow_dispatch`. It uses the fixture when API secrets are absent, validates and anonymizes data, then commits `public/data.json`.
* **Deploy Feedback River** publishes `public/` through GitHub Pages on pushes to `main` or manually. Enable Pages with **GitHub Actions** as the source in repository settings.

The dashboard provides daily highlights and a Monday-to-current weekly summary, with country, payment method, and channel filters.

## Transfer note

This public fallback currently lives at `brunovalcke/digital-payment-feedback-river` because the requested `dktunited` repository could not be created due to permissions. To transfer it, create the destination repository, push this history, update the Pages settings and secrets, then review the approved Medallia mapping and anonymization salt with the destination owners. No repository-specific URLs are embedded in the implementation.
