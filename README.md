# LeetCode Tracker

[![CI](https://github.com/capy-zhiao/leetcode-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/capy-zhiao/leetcode-tracker/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)
![React](https://img.shields.io/badge/react-18-61dafb)

A study tracker for NeetCode 150 plus two LeetCode study plans, Top Interview 150 and
LeetCode 75 (272 problems in total, since the lists overlap). It picks what to practice
each day, schedules
reviews with spaced repetition, and checks your time and space complexity answers.

I built it because my markdown study plan stopped working past a hundred or so problems.
Keeping track of review dates by hand wasn't realistic.

## What's in it

### Today

![Today](docs/screenshots/today.webp)

The home page. It has three lists:

- **Review**: problems due for another pass, ranked by how overdue they are and how often
  you've failed them. At most two per chapter, so a day isn't all one topic
- **New**: the next problems you haven't done: NeetCode 150 first in NeetCode's order,
  then Top Interview 150, then LeetCode 75, each in LeetCode's study-plan order
- **Template drill**: one algorithm template to write from memory before you start

Each row shows the difficulty, the pattern tags, how overdue it is, and how many times
you've failed it. The chart at the bottom shows how many reviews come due over the next two
weeks, plus how long the current backlog will take to clear.

### Solving a problem

Clicking a problem opens the solve page: a timer, a code editor, and a short form. You pick
a grade (again / hard / good / easy, with a suggestion based on your time) and enter the
time and space complexity before you can submit. The grade decides when the problem comes
back.

If an LLM is set up, your complexity answer is then checked against the code you actually
wrote. The result has four parts: whether each answer is right, why it's wrong if it is,
the optimal complexity, and your code rewritten to reach it, shown as a diff. Past results
open from the History list at the bottom of the page.

### Drills

The 15 algorithm templates (union-find, grid DFS, Kahn's algorithm, binary search, and so
on), each on its own review schedule. You write one from memory and it's checked against
the lines that usually go wrong, like `find` using `while` instead of `if`. Renaming
variables is fine; missing one of those lines isn't. You see the reference and a diff after
checking.

### Patterns

Progress grouped by technique instead of by chapter, weakest first. Each pattern shows how
many of its problems you've mastered and links to the template drill for it. Expanding a
pattern lists its problems.

### Mock interview

A random problem with a countdown and your notes hidden. When you're done coding, the LLM
reads your code and asks three follow-up questions about it. You answer each in writing
and get a grade, what you missed, and a model answer.

### Stats

![Stats](docs/screenshots/stats.webp)

Problems started and mastered, your streak, and average time per problem. If an LLM is set
up, it also shows how much API credit is left. Below that is progress by chapter; clicking a
chapter lists its problems, and the search box finds any problem by number or title.

### Other

Dark mode (follows your system setting, or use the toggle in the header) and keyboard
shortcuts for most actions.

## Stack

**Frontend**

- React 18 and TypeScript, built with Vite
- React Router for the pages (Today, Drills, Patterns, Mock Interview, Stats)
- Tailwind CSS. Every color is a CSS variable, which is how dark mode works without
  duplicating styles
- Monaco, the editor from VS Code, for writing solutions. It's bundled locally (works
  offline) and only loads on pages that have an editor

**Backend**

- Python 3.12+, FastAPI, served with Uvicorn
- SQLAlchemy 2.0 with SQLite locally and Postgres in production
- Pydantic v2 for request and response models, pydantic-settings for config from `.env`
- The spaced-repetition rules and the template grader don't touch the database and take
  the date as a parameter, so they're tested directly; the layer that builds the daily
  queue reads the database and takes the date as a parameter too

**AI (optional)**

- DeepSeek through the OpenAI SDK, so any OpenAI-compatible API works, or Claude through
  the Anthropic SDK
- Used for the complexity check, mock interview questions, and grading your answers
- Each task can use its own model, e.g. a cheaper one for complexity checks

**Testing and CI**

- pytest with FastAPI's test client against an in-memory SQLite database, about 200 tests
- GitHub Actions runs on every push to `main` and every pull request against `main`: the
  backend tests on Python 3.12 and 3.13, a type-check and production build of the frontend,
  and a check that the problem set is complete and tagged. It does not deploy anything

## Running it

```bash
./start.sh
```

This installs dependencies, sets up the database, starts both servers and opens the browser.

Or run them separately:

```bash
# backend
cd backend
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env
./.venv/bin/python seed_db.py
./.venv/bin/uvicorn app.main:app --reload

# frontend
cd frontend
npm install
npm run dev
```

Tests: `cd backend && ./.venv/bin/pytest -q`

### With Docker

Needs Docker with Compose v2.24 or newer.

```bash
cp .env.example .env          # optional: timezone, LLM provider, daily caps
docker compose up -d --build
```

Then open http://localhost:8080. Two containers run:

- `backend`: FastAPI on Python 3.12. Each start runs `migrate.py` and `seed_db.py`, the same
  steps as `start.sh`, so the first start creates and fills the database and later starts
  only add what's new. The API docs are at http://localhost:8000/docs, reachable from this
  machine only
- `web`: nginx serving the built frontend and passing `/api` to the backend, the same
  mapping as the Vite dev proxy

The SQLite database lives in the `tracker-data` volume, so it survives restarts and
rebuilds. `migrate.py` keeps its dated backups in the same volume, under `/data/.backups`.

```bash
docker compose cp backend:/data/tracker.db ./tracker-backup.db   # copy the database out
docker compose up -d --build                                     # update after git pull
docker compose down                                              # stop; data is kept
docker compose down -v                                           # stop AND delete the data
```

Settings come from `.env` (see `.env.example`). Containers run in UTC, so set `TIMEZONE`,
or an evening session is filed under the next day. API keys are read at run time and are
never built into the images. The one exception is `VITE_API_KEY`, which is compiled into
the frontend's JavaScript; see the deployment notes before using it.

## AI setup

In `backend/.env` (or the root `.env` when running with Docker):

```bash
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com     # any OpenAI-compatible endpoint
DEEPSEEK_MODEL=deepseek-v4-pro                  # mock interviews
DEEPSEEK_COMPLEXITY_MODEL=deepseek-v4-flash     # complexity checks (cheaper)
```

For Claude, set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`.

With `LLM_PROVIDER=none` everything else still works, and complexity answers are checked
against a built-in answer table instead. When a provider is set, the Stats page shows how
much API credit is left.

## How scheduling works

After each attempt you pick a grade: again, hard, good or easy. The app suggests one from
how long you took, whether you had bugs, and whether you looked at the solution. The grade
sets the next review interval, similar to Anki's SM-2, with shorter intervals for hard
problems.

When more is due than you can do in a day, reviews are ranked by how overdue they are and
how often you've failed them before. A day gets at most two reviews from the same chapter,
so you don't end up with four graph problems in a row.

New problems cover the NeetCode 150 first, in NeetCode's order, then Top Interview 150, then
LeetCode 75. The two LeetCode lists follow their own study-plan order, and a problem in
more than one list only shows up once.
Hard problems come last.

Most of this can be adjusted in `backend/.env` (see `.env.example`).

## Shortcuts

Space starts and stops the timer, 1 to 4 pick a grade, Cmd+Enter submits, J and K move
through the queue. Press `?` in the app for the full list.

## Data

The problem list combines two sources:

- NeetCode 150, from my NeetCode notes. `python3 scripts/extract_seed.py` turns the
  markdown into `data/seed.json`, including my notes and solutions
- LeetCode's [Top Interview 150](https://leetcode.com/studyplan/top-interview-150/) and
  [LeetCode 75](https://leetcode.com/studyplan/leetcode-75/).
  `python3 scripts/fetch_study_plans.py` saves both to `data/`

`backend/seed_db.py` builds the problem set from these. Problems that drop out of every
list are removed, unless you've already practiced them. Problems in a LeetCode study plan
link to LeetCode; the rest link to NeetCode.

## Deploying

Nothing here has been deployed yet; these are the options and what each still needs.

### One server with Docker Compose (for example AWS EC2)

The Docker setup above, tested locally, runs unchanged on a single Linux server:

1. Launch an instance with a recent Ubuntu or Amazon Linux. A small instance is enough
   (the backend is one process with SQLite). EC2 is billed while the instance runs.
2. In the security group, allow SSH only from your own IP. Don't open the web port to
   everyone: the app has no user accounts, and `API_KEY` only helps against people who
   can't read the page's JavaScript.
3. Install Docker Engine and the Compose plugin, clone this repository, then
   `cp .env.example .env`, set `TIMEZONE`, and run `docker compose up -d --build`.
4. Reach it through an SSH tunnel, `ssh -L 8080:localhost:8080 <user>@<instance>`, then
   open http://localhost:8080. Alternatively, open port 8080 to your IP only.
5. Back up `tracker-data` (see the commands above) or snapshot the volume; it holds the
   only copy of your practice history.

### Vercel + Railway or Render (not verified)

The frontend calls `/api` on its own origin, and `frontend/vercel.json` currently sends
every path to `index.html`, so a Vercel frontend can't reach a backend elsewhere until
`vercel.json` also rewrites `/api/(.*)` to the backend's URL. The `Procfile` only starts
the server: run `python seed_db.py` once against the production database to load the
problems, and install `psycopg[binary]` for Postgres. If it's public, set `API_KEY` on the
backend and the same value as `VITE_API_KEY` on the frontend.
