# Nestfix

Nestfix helps an employer put money toward housing and show each employee real rentals they can afford after that help. Listings come from Bright Data. Explanations come from Gemini when the key is accepted.

The demo company is Harborlight Logistics. Five employees are loaded on first run. There is no password. Pick the employer desk or an employee view.

## Setup

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- `GEMINI_API_KEY` — a Google AI Studio key. New keys start with `AQ.`. Older keys start with `AIza`.
- `BRIGHT_DATA_API_KEY` — a Bright Data API token.
- `BRIGHT_DATA_SERP_ZONE` and `BRIGHT_DATA_UNLOCKER_ZONE` — optional. If those zones exist, Nestfix searches with the SERP API and can enrich a page with Web Unlocker. Leave them blank to use Bright Data’s Zillow and Google Maps datasets, which do not need a zone name.

Frontend:

```bash
cd frontend
npm install
```

## Run

In one terminal, from the project root:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

In another:

```bash
cd frontend
npm run dev
```

Open http://127.0.0.1:5173. API docs are at http://127.0.0.1:8000/docs.

## Demo script

Use this order with judges. Live collection usually takes one to three minutes. Start it, then talk.

1. Open the home page. Point at the three steps and the Harborlight card.
2. Open **Employer**. Show the five staff rows and the contribution column. Maya Chen is a $600 monthly subsidy. Jordan Hale is 15% of rent. Luis Ortega is one-time assistance spread over 12 months.
3. Optional: upload `sample_employees.csv` (also linked on the page) to show the CSV path. Re-uploading updates the same employee ids.
4. Click **Find homes** on Maya Chen (`HL-1042`, Austin, family of 3, toddler, 2 bedrooms). Leave the loading note on screen. Bright Data is collecting Zillow rentals and Google Maps places.
5. When the row says homes are ready, click **Open their view**.
6. On Maya’s page, start on **Net price**. The large number is rent after Harborlight’s subsidy. Switch on **Show employer contribution** and point at sticker, employer share, and net.
7. Read the “why this fits” line out loud. It should name Maya, Austin, her household, and the subsidy. Pros and cons sit under it. Schools, walk score, or parks come from the Bright Data record.
8. Open **Open listing source** so the room can see the live Zillow page.
9. In the affordability panel, set other monthly expenses to `3200` and desired savings to `700`. Click **Apply to rankings**. Homes that no longer fit drop down and are marked over budget. Rank labels show the move (`#2 · was #1`). Check **Hide homes over this budget** to filter.
10. Select a home and add a short note, for example “Close to a park for the toddler.”
11. Return to **Employer** and show **What staff selected**: address, sticker, employer share, and net.
12. If there is time, open Priya Nair (`HL-1180`, Denver, two children, $800 subsidy) and generate her list. Her notes ask for an elementary school, which is the amenity beat.

## Bright Data

Nestfix calls Bright Data in this order:

1. **SERP API** (`POST https://api.brightdata.com/request`) when `BRIGHT_DATA_SERP_ZONE` is set or a serp zone is on the account. The query is a Google search for rentals in the employee’s city, bedroom count, and budget. A second query asks for schools, parks, hospitals, and transit.
2. **Web Unlocker** on the top listing URL when `BRIGHT_DATA_UNLOCKER_ZONE` is set. The markdown excerpt fills in a missing price when the snippet has one.
3. **Datasets API**, used when no SERP zone is available:
   - Zillow search dataset `gd_m71oxpvxwr113ehqg` with a rentals URL and `searchQueryState` (beds and max price).
   - If that returns too few rows, Zillow listing discovery `gd_lfqkr8wm13ixtbd8f5` (`House for rent` in the employee’s city). Those records include price, beds, address, schools, and walk/transit scores.
   - Google Maps dataset `gd_m8ebnr0q2qlklc02fz`, discovered by keyword for schools, parks, hospitals, and transit.

Calls are logged on the employee page under **Show Bright Data and Gemini log**, and in the `analysis_logs` table.

The token shipped with this project can call the datasets API. It has no SERP or Web Unlocker zone, and it cannot create zones. With that token, step 3 is the live path. Add zone names to `.env` to switch the search over to SERP and Web Unlocker.

## Gemini

`app/services/gemini_service.py` sends the employee (name, salary, family, city, contribution, notes) and the Bright Data rows. It asks for JSON: score, pros, cons, why this fits, an affordability paragraph, and a neighborhood summary. The affordability calculator asks Gemini for a short narrative as well.

The value originally placed in `GEMINI_API_KEY` was the Bright Data token, which Google rejects. Nestfix still calls Gemini on every generation. If Google rejects the key, the screen says so and shows match notes calculated from the live rent, the employer contribution, and that employee’s salary and household. Those notes are labeled as calculated, not as Gemini. Paste the AI Studio key (the one that starts with `AQ.`) into `.env` and click **Refresh live homes** to replace them.

Model default is `gemini-3.5-flash`. If that model is busy, Nestfix tries `gemini-3.5-flash-lite`, then `gemini-flash-lite-latest`. Override with `GEMINI_MODEL`.

## API

- `POST /employers/upload-employees` — CSV upload or JSON list
- `POST /housing/generate-options/{employee_id}` — Bright Data search, Gemini write-up, stored options
- `GET /employees/{employee_id}/options` — matches, net price included
- `POST /employees/{employee_id}/select-option`
- `POST /employees/{employee_id}/affordability-calc`
- `GET /employers/{employer_id}/selections-summary`

`employee_id` may be the internal id or the external id, such as `HL-1042`.

SQLite file: `nestfix.db` in the project root. Delete it to reseed Harborlight.
