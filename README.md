# salaty-data

Prayer-time data and tooling for [SalahLK](https://github.com/riyajkm/salah-tv), the offline mosque prayer clock for Android TV.
This repo converts the official **ACJU (All Ceylon Jamiyyathul Ulama)** prayer timetable PDFs into one JSON file
(and one CSV per zone) that SalahLK reads.

## What is here

| Path | What |
|---|---|
| `data/prayer_times.json` | All 13 ACJU zones, daily Fajr / Sunrise / Dhuhr / Asr / Maghrib / Isha. This is the file SalahLK bundles. |
| `data/zone_01.csv` … `zone_13.csv` | The same data, one spreadsheet-friendly CSV per zone. |
| `convert_acju.py` | PDF → JSON/CSV converter with a validation report and a self-test. |

**Current coverage:** 1 October – 31 December 2026 (92 days × 13 zones).

### Zones

`01` Colombo, Gampaha, Kalutara · `02` Jaffna, Nallur · `03` Mullaitivu (except Nallur), Kilinochchi, Vavuniya · `04` Mannar, Puttalam ·
`05` Anuradhapura, Polonnaruwa · `06` Kurunegala · `07` Kandy, Matale, Nuwara Eliya · `08` Batticaloa, Ampara · `09` Trincomalee ·
`10` Badulla, Monaragala, Padiyatalawa, Dehiaththakandiya · `11` Ratnapura, Kegalle · `12` Galle, Matara · `13` Hambantota

### JSON shape

```json
{
  "source": "ACJU (All Ceylon Jamiyyathul Ulama)",
  "generated": "2026-10-03T19:23:44",
  "sahr_end_minutes_before_fajr": 2,
  "apartment_adjustments": [ { "floors": "06-35", "meters": "24-140", "fajr": -1, "sunrise": -1, "maghrib": 1, "isha": 1 } ],
  "regions": {
    "01": { "name": "Colombo, Gampaha, Kalutara",
            "days": { "10-01": { "fajr": "04:42", "sunrise": "05:59", "dhuhr": "12:02", "asr": "15:16", "maghrib": "18:03", "isha": "19:12" } } }
  }
}
```

Times are 24-hour, Sri Lanka time (UTC+5:30). Day keys are `MM-DD`. `apartment_adjustments` are minute offsets for high-rise buildings.

## Regenerating the data

```bash
pip install -r requirements.txt
python convert_acju.py --self-test                      # no PDFs needed
python convert_acju.py <folder-of-pdfs> data/prayer_times.json --csv
```

PDFs must be named `NN-REGION-MM-Mon.pdf` (e.g. `01-COLOMBO-DISTRICT-GAMPAHA-DISTRICT-KALUTARA-DISTRICT-10-Oct.pdf`).
The script prints a validation report and exits `1` if it finds problems (the JSON is still written for inspection).
The source PDFs are ACJU's publications and are **not** included in this repo; download them from ACJU.

## Using the data in SalahLK

Copy `data/prayer_times.json` to `assets/prayer_times.json` in SalahLK, or import it from the app's settings.

## Branches & releases

`dev` → `stage` → `main`; data releases are tagged `vYYYY.Q` (e.g. `v2026.4` = Oct–Dec 2026) and attach the JSON and a zip of all files.
See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## Accuracy, attribution & license

The times come from the official ACJU timetables; **the ACJU publications are the authority**. Please verify against them, and report
differences with the *Data correction* issue template. ACJU is the source and owner of the timetable content; this project is not
affiliated with or endorsed by ACJU.

The converter code and repository tooling are licensed under the [MIT License](LICENSE).
