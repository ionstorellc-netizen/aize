# Premium AI E-commerce Video Studio

Your own production platform for 30–50 s Roman Urdu short videos about Amazon, Shopify and China sourcing.
It researches what is working, writes the script, produces the presenter video, adds B-roll, edits everything
in your saved reference style, runs quality control and exports a 1080×1920 MP4 ready for TikTok, Reels and Shorts.

```
React dashboard (Vite) ──> FastAPI ──> SQLite (or PostgreSQL)
                              ├─ Master Agent: 12 stages, approvals, retry from any stage
                              │    Research · Strategist · Ideas · Script · Avatar · B-roll
                              │    Editor · Subtitle · Audio · QC agents
                              ├─ Job workers (DB-backed queue, resumes after restart)
                              ├─ Providers: Claude · YouTube Data · Instagram Graph · HeyGen · Pexels
                              ├─ Engine: faster-whisper + FFmpeg + libass + Pillow (EDL → MP4)
                              └─ Encrypted server-side key store (keys never reach the browser)
```

## Requirements

* Python 3.11+ (tested on 3.13)
* Node.js 18+ (only to build the dashboard)
* FFmpeg 6+ built with libass and libx264 (`ffmpeg -filters | grep subtitles`)
  * macOS: `brew install ffmpeg` · Ubuntu: `sudo apt install ffmpeg` · Windows: `winget install ffmpeg`
* About 2 GB disk for the speech model and renders

## Install and run (development)

```bash
# 1. backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. dashboard
cd ../frontend
npm install
npm run build            # the backend serves frontend/dist

# 3. start
cd ../backend
cp ../.env.example ../.env   # optional, see below
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The database, folders, sound effects and default style profile are created on first start.

On first transcription faster-whisper downloads the `small` model (~480 MB) from Hugging Face. For better
Roman Urdu accuracy set `WHISPER_MODEL=medium` or `large-v3` (slower, more RAM).

For frontend hot reload: `cd frontend && npm run dev` (proxies `/api` and `/media` to port 8000) and open http://localhost:5173.

## First-time setup in the app

1. **Integrations**: paste your keys, press **Save**, then **Test connection**. A provider only shows
   *connected* after a successful live test.
2. **AI Avatar Studio**: the avatar reference (your IMG_4917) is shown here. Upload a newer one any time.
3. **Editing Templates**: the style profile measured from IMG_4762 is the default for every project.
4. **Settings**: duration range, markets, categories, Claude model, export quality, approval rules.

## Making a video

Dashboard → **START NEW VIDEO PROJECT** → choose topic, category and presenter source:

* **AI avatar (HeyGen)**: the approved script is sent to your Digital Twin with your cloned voice.
* **My own recording**: record the approved script yourself (phone, 9:16) and upload it. The studio
  removes pauses and repeated takes, then edits it in your style. This also works with no API keys at all.

The project then runs through the 12 stages in **Production Queue**. It pauses for your approval at
topic, script and final export (and at QC if a critical check fails). Every stage's output is saved, so
**Retry** or **Re-run from here** only redoes that stage and the ones after it.

Open **Video Editor** to change anything: shots (framing, trim, split, reorder, delete), B-roll (replace,
card or full screen, timing), text callouts, captions (Roman Urdu text), sound effects, music and SFX
levels, colour grade and the CTA. Undo and redo are supported. Press **Render preview** (fast, half resolution) or
**Export final MP4** (full render, then QC, then your approval).

## What each integration needs

| Service | Used for | Key(s) | Cost |
|---|---|---|---|
| Anthropic Claude | ideas, scripts, B-roll matching, cut selection, Roman Urdu polish, QC vision check | `ANTHROPIC_API_KEY` | pay per use (Opus 5.5: $4 / $20 per M tokens; a full video is typically a few cents) |
| YouTube Data API v3 | viral research, competitor channels, verified metrics | `YOUTUBE_API_KEY` | free, 10,000 units/day; one research run ≈ 1,600 units |
| Pexels | licensed stock B-roll | `PEXELS_API_KEY` | free |
| HeyGen | AI avatar video from your Digital Twin + cloned voice | `HEYGEN_API_KEY`, `HEYGEN_AVATAR_ID`, `HEYGEN_VOICE_ID` | paid plan with API access |
| Instagram Graph API | Instagram competitor metrics (Business Discovery) | `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_BUSINESS_ID` | free; needs an IG Business account + Meta app |
| TikTok | — | official Research API is limited to approved researchers | add TikTok competitors manually (labelled unverified) |
| faster-whisper, FFmpeg | transcription, rendering | none | free, local |

Keys can come from environment variables (they take priority) or be saved in the UI. UI-saved keys are encrypted with
Fernet into `storage/secrets.enc`; the encryption key is `APP_SECRET_KEY` or an auto-generated `storage/.secret_key` (mode 600).
The API never returns key values to the browser, only a masked last four characters.

### Without keys, what still works

| Feature | Without the key |
|---|---|
| Research, competitor discovery | blocked with a clear message (no YouTube key); manual competitor entry works |
| Ideas, script generation | blocked (no Claude); manual ideas and manual scripts work |
| Avatar | "own recording" mode works; HeyGen mode blocked until configured |
| B-roll | your library + typographic graphics; Pexels needs its key |
| Editing, subtitles, audio, QC, export | fully local, always works |

Nothing is ever simulated: a stage either runs for real, is skipped with a reason, or fails with a reason.

## Data honesty rules built in

* Research metrics come only from official APIs and are labelled **verified**. Claude's judgement scores are labelled
  **estimated**. What cannot be measured (for example search volume) is labelled **unavailable**.
* Every opportunity and idea keeps its source links; links Claude returns that were not in the API data are dropped.
* B-roll graphics are typographic cards in your brand colours. The agent never fabricates dashboards, results or statistics.
* The avatar provider only uses your own avatar_id; there is no stock-presenter fallback.

## Environment variables (`.env.example`)

See `.env.example`. All are optional.

## Project layout

```
backend/app/
  main.py               FastAPI app, static dashboard, /media file server
  config.py, db.py      paths, SQLAlchemy models (projects, stages, jobs, research, ideas, scripts, assets, events)
  store.py              settings + encrypted secrets
  routes/api.py         REST API
  agents/               master (pipeline + queue), research, content (ideas/scripts), broll, qc, schemas
  providers/            claude, youtube, pexels, heygen, instagram
  engine/               transcribe, edl (edit decision list), render (FFmpeg), graphics (Pillow), sfx (synthesised)
  defaults/             style_profile.json (from IMG_4762), avatar_profile.json (from IMG_4917)
frontend/src/pages/     the 14 dashboard sections
assets/fonts/           Playfair Display, Instrument Serif, Inter (SIL Open Font License)
storage/                database, projects, library, references, renders (created at runtime)
docs/                   REFERENCE_ANALYSIS.md
```

## Production deployment

Single machine (recommended: 4+ vCPU, 8 GB RAM; rendering is CPU-bound, ~1–2 min per 45 s video at 1080p):

```bash
# build the dashboard once
cd frontend && npm ci && npm run build && cd ..
# run with a password and an explicit encryption key
export STUDIO_PASSWORD='choose-a-strong-password'
export APP_SECRET_KEY="$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

* Keep `--workers 1`: the render workers run as threads inside that process (set `WORKER_THREADS`, default 2).
* Put it behind HTTPS (Caddy: `reverse_proxy 127.0.0.1:8000`, or nginx with `client_max_body_size 2G` for uploads).
* `STUDIO_PASSWORD` turns on HTTP Basic auth for the whole app.
* PostgreSQL: `pip install psycopg[binary]` and set `DATABASE_URL=postgresql+psycopg://user:pass@host/db`.
* Back up `storage/` (database, references, library, exports) and your `APP_SECRET_KEY`.
* A `Dockerfile` is included: `docker build -t ecom-studio . && docker run -p 8000:8000 -v $PWD/storage:/app/storage --env-file .env ecom-studio`.

## Notes and limits

* Transcription quality decides subtitle quality. Whisper `small` gets most Roman Urdu right; low-confidence words are
  listed in QC and with Claude configured every caption is spell-checked against the script. Fix anything left in the editor.
* Lip-sync and identity checks: for your own recordings picture and sound come from the same take. For HeyGen output, QC uses
  Claude vision to compare frames with your reference photo when Claude is configured; otherwise it asks you to confirm.
* Published-video analytics (views of your own posts) need your own platform accounts connected; the Analytics page covers production metrics.
