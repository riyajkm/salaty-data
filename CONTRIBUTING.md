# Contributing to salaty-data

This repo holds the converter and the generated ACJU prayer timetable used by
[SalahLK](https://github.com/riyajkm/salah-tv).

## Branches

| Branch | Purpose |
|---|---|
| `main` | Production data. Releases are tagged here. |
| `stage` | Pre-release review. Receives `dev`. |
| `dev` | Integration; default PR target. |

Flow: `feature/*` or `fix/*` → PR → `dev` → PR → `stage` → PR → `main` → tag.

## Updating the timetable (each quarter)
1. Download the new ACJU PDFs (`NN-REGION-MM-Mon.pdf`) into a local folder. **Do not commit them.**
2. `pip install -r requirements.txt`
3. `python convert_acju.py <pdf-folder> data/prayer_times.json --csv` and read the validation report.
4. Add a `CHANGELOG.md` entry and open a PR to `dev`.
5. After merging to `main`, tag `vYYYY.Q` (e.g. `v2027.1`); CI publishes the release with the data files.
6. Copy `data/prayer_times.json` into SalahLK's `assets/`.

## Commits
Conventional Commits (`feat:`, `fix:`, `data:`, `docs:`, `ci:`).
