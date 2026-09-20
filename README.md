# Cowboy Compass

An intelligent course schedule optimizer for Oklahoma State University students.

## Overview

Cowboy Compass helps students find better class schedules by analyzing available course sections and ranking possible schedules based on their preferences.

The primary goal is to minimize the amount of time students spend waiting between classes while respecting required courses and scheduling constraints.

## Current Features

- Retrieves course section data from Oklahoma State University's public registration system
- Processes thousands of course sections
- Filters courses by subject, course number, instructor, enrollment, and meeting information
- Parses lecture and lab meeting components
- Handles multiple meeting times within a course section
- Converts OSU's time format into usable scheduling data
- Identifies potential schedule conflicts
- Generates every one-section-per-course schedule
- Removes schedules with overlapping meeting times
- Calculates total idle time between classes
- Scores and ranks conflict-free schedules

## Web app

The React interface is live at [cowboycompass.vercel.app](https://cowboycompass.vercel.app/). It lets students enter courses, request schedules, review the top ten ranked options, copy CRNs, and open instructor names in Rate My Professors.

## How It Works

Cowboy Compass is being developed as a constraint-based scheduling system.

```text
OSU Course Data
       ↓
Data Processing
       ↓
Course & Section Filtering
       ↓
Constraint Checking
       ↓
Schedule Generation
       ↓
Schedule Scoring
       ↓
Ranked Schedules
```

The scheduling engine treats course availability and schedule conflicts as hard constraints. Preferences such as minimizing gaps and class days influence the ranking of valid schedules.

## Data

Course data is retrieved from Oklahoma State University's public class registration system.
Generated course-data JSON files are intentionally excluded from this repository because they are large and can become outdated. Render downloads current data during its build instead.

## Tech stack

- Python 3.14
- React 19 and Vite
- REST API with Python's standard library HTTP server
- JSON data processing
- Git and GitHub
- Vercel (frontend) and Render (API hosting)

The reusable scheduling logic lives in `scheduler.py`; both the terminal program and API import it.

## Project status

The scheduling engine and first React web app are working. Fall 2026 and Spring 2027 are supported in the API, terminal program, and web term selector.

## Running locally

Clone the repository:
```bash
git clone https://github.com/JackHildebrand/CowboyCompass.git
cd CowboyCompass
```

Install the dependency and run the terminal program with Python 3.14:
```bash
python3.14 -m pip install requests
python3.14 prepare_render_data.py
python3.14 OSU_Class_Optimizer.py --term spring-2027
python3.14 -m unittest discover -s tests -v
```

### React web app

The React interface in `web/` connects to the local Python scheduling API. Run the API in one terminal, then start Vite in another:

```bash
# Terminal 1, from the project root
python3 api.py

# Terminal 2
cd web
pnpm install
pnpm dev
```

Open the local web address printed by Vite, add courses, and choose **Find schedules**. The browser sends the requested course list to Python, and the returned conflict-free schedules replace the sample results.

## Deployment

The repository includes `render.yaml` for the Python API and `web/vercel.json` for the React site.

The production frontend is deployed on Vercel and the Python API is deployed on Render:

- Frontend: [cowboycompass.vercel.app](https://cowboycompass.vercel.app/)
- API health check: [cowboy-compass.onrender.com/health](https://cowboy-compass.onrender.com/health)

To reproduce the deployment:

1. Create a Render **Web Service** from this repository. Render uses `render.yaml`; copy the API URL after the service deploys.
2. Create a Vercel project from this repository and set its **Root Directory** to `web`.
3. In Vercel, add `VITE_API_URL` with the Render URL ending in `/api/schedules`.
4. In Render, set `ALLOWED_ORIGIN` to the deployed Vercel URL and redeploy the API.

The API listens on Render's `PORT` environment variable and exposes `/health` for automatic service checks. During its build, Render runs `prepare_render_data.py` to download current OSU sections; generated JSON remains on the service and is never committed.

## Future direction

Planned improvements include customizable ranking preferences and additional travel-aware scheduling options.

## Spring 2027 data and refresh

`course_data.py` is the shared term registry and import pipeline. The data store is
an unmodified JSON list of Banner section records per term; there is no SQL database
or schema migration. Fall 2026 uses `202660` / `fall_2026_sections.json`; Spring 2027
uses `202720` / `spring_2027_sections.json`. All `meetingsFaculty` records, dates,
faculty, seats, and course attributes are retained. Both datasets are downloaded
by the existing Render build command. To refresh just Spring locally:

```bash
python3 prepare_render_data.py --term spring-2027
python3 OSU_Class_Optimizer.py --term spring-2027
python3 -m unittest discover -s tests -v
```

The API accepts `{"courses": ["CS1113", "MATH2144"], "term": "spring-2027"}` at
`POST /api/schedules`; requests without a term retain the Fall 2026 default.
Switching terms clears results from the previous term. Returned calendar meetings
include start/end dates, and weekend columns appear when needed.

Imports start fresh, use a separate temporary public search session for each term,
request 500 records per page, and advance by the actual page length. They reject
unsuccessful responses, empty or changing totals, missing/duplicate CRNs, wrong-term
records, malformed meetings, and incomplete pagination. Each completed dataset is
atomically replaced, so an interrupted download preserves that term's previous file.
Old offset checkpoints are intentionally not resumed: they can silently skip records
when OSU's catalog changes. Transient GET failures receive up to three retries.
A generated `.meta.json` sidecar records source, UTC retrieval time, and counts.
Full catalogs remain ignored by Git; a three-section public Spring snapshot is
committed under `tests/fixtures` for offline regression testing.

The September 20, 2026 import contains 7,877 Spring sections (2,648 distinct course
codes), 9,159 meeting records, and 957 sections with multiple meetings. The Fall
refresh contains 8,498 sections. These are snapshots, not live enrollment guarantees.

## Scheduling scope and limitations

- The optimizer offers sections with at least one Stillwater instructional meeting.
  It checks all meetings rather than trusting the first meeting's campus. The full
  catalog is stored, but fully online/off-campus and no-meeting records are not
  currently offered by this campus-focused filter.
- Standalone `Lab` sections are excluded case-insensitively; combined lecture/lab
  sections retain every component. Choosing linked lecture/lab CRNs separately is
  not implemented. OSU reported no linked-section flags in this Spring snapshot.
- All instructional meeting pairs are checked, including weekends. Date ranges
  must share an actual meeting day to conflict; missing/invalid dates conservatively
  use weekly conflict checks. Back-to-back meetings remain permitted.
- Common exams remain excluded from conflict checks, scoring, and the web calendar
  under the existing policy. Unknown/TBA or invalid times cannot be conflict-checked.
- Gap/day ranking still uses a composite weekly calendar, not a date-weighted
  semester calendar. Meetings from different parts of term can appear together;
  their date ranges are displayed. Prerequisites, seat availability, reserved seats,
  registration eligibility, travel time, and internal conflicts within one CRN are
  not enforced. Review schedules against OSU before registering.
- Schedule enumeration still builds every one-section-per-course combination in
  memory; very large requests can be expensive. Datasets refresh when the import
  command runs (including Render builds), not automatically while the API runs.
