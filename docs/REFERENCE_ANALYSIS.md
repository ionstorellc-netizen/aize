# Reference analysis, architecture and integrations

## 1. Reference 1 — your avatar (IMG_4917.MOV)

| Property | Finding (measured) |
|---|---|
| File | HEVC, 1990×3538 portrait, 60 fps, 68.5 s, AAC stereo |
| Framing | Centered medium shot, eye level, head in upper third, both hands visible |
| Setting | Desk, dark city-view window + white curtains, warm downlights, RGB podcast mic in frame |
| Look | Short dark curly hair, trimmed beard, dark overshirt over black tee |
| Delivery | Direct to camera, energetic, constant two-hand gestures, eyebrows for emphasis |
| Language | Urdu/Hindi code-mixed with English business terms (Amazon, business start, training, mentorship, video courses, "at the end they will be in the loss") |
| Topic in clip | Why live mentorship beats buying video courses before starting an Amazon business |
| Pace | ~2.6 words/s |
| Audio | Clean but **very quiet**: −32.4 LUFS, peak −12.5 dBFS → engine adds ~+17 dB with loudness normalisation |

Transcription test: Whisper in *Urdu* mode outputs Urdu script (not allowed). Whisper with an English language hint plus a Roman-Urdu prompt outputs clean **Roman Urdu** directly ("Toh jo training hum provide kar rahe hain…"). That is the subtitle engine's default; Claude then polishes spelling when the key is configured.

Saved as `backend/app/defaults/avatar_profile.json`.

## 2. Reference 2 — editing style (IMG_4762.MP4)

| Technique | What the reference does | How the engine reproduces it |
|---|---|---|
| Rhythm | 58 s, ~150 words (~2.8 w/s), a visual change every ~1.2 s | Pause removal (gaps > 0.32 s), new framing every 3–6 s, overlay every 1–2.5 s |
| Angles | 4 hard angle changes (close → wide → close-up), plus punch-ins | Digital re-framing cycle wide 1.0× / medium 1.14× / close 1.32×, slow push-in inside each shot |
| Hook titles | Giant serif words over/behind the head ("I DIDN'T EDIT", "CLAUDE", "NEVER"), mixed with bold sans + gold serif italic | Hook title card: giant serif cream text, second line gold italic |
| Keyword callouts | Inter-Black-style caps on forest-green bar ("BIGGER") + serif italic line ("captions.") | Keyword callout cards in the same two-font system |
| Subtitles | Small serif (Playfair-like), cream on solid forest-green box (#18362A), ~70% down the frame, 2–4 words per phrase, spoken words cream / upcoming muted green | Same: ASS subtitles, phrase-by-phrase with per-word colour highlight, Playfair Display |
| B-roll | Mostly floating **cards** in the upper third (screenshots, UI, thumbnails) with presenter still visible; a few full-screen inserts and a thumbnail montage | Card B-roll (rounded, green border, pop-in) ≈65%, full-screen ≈35%, target ≈45% coverage |
| UI motion graphics | Typing chat box, app icons crossed out, timeline panel, timer card, file card | Generated typographic cards (labelled as graphics, never as real evidence) |
| CTA | White rounded box at top: "Comment 'EDIT' and I'll send you…", comment bubble, follow card, then fade to dark | CTA card on last ~6 s + fade-out |
| Colour | Warm, slightly desaturated, lifted greens, soft vignette | eq contrast 1.06 / saturation 0.92, warm shift, vignette |
| Audio | Loud master −13.9 LUFS, subtle whoosh/click under overlays | Voice normalised to −15 LUFS, true peak −3 dB; music −27 dB ducked under speech; SFX −22 dB at every overlay/angle change |
| Branding | Creator's @handle + Instagram logo | **Not copied** |

Saved as `backend/app/defaults/style_profile.json` (editable in Settings → Editing Style).

## 3. Architecture

```
React dashboard (Vite)  ──HTTP──>  FastAPI backend ──> SQLite (or PostgreSQL via DATABASE_URL)
                                       │
                                       ├─ Master Agent (pipeline, 12 stages, approvals, retry-from-stage)
                                       │    Research · Strategist · Script · Avatar · B-roll
                                       │    Editor · Subtitle · Audio · QC agents
                                       ├─ Job worker (DB-backed queue, survives restarts)
                                       ├─ Providers: Claude · YouTube Data · Instagram Graph · HeyGen · Pexels · Whisper (local)
                                       ├─ Engine: FFmpeg + Pillow + libass (EDL → MP4)
                                       └─ Encrypted secret store (server only, never sent to browser)
```

Central data structure: the **Edit Decision List (EDL)**. The Editor agent writes it, the timeline editor changes it (with undo/redo), the renderer turns it into the MP4. Re-editing never re-runs research, scripts or avatar generation.

## 4. Integrations and credentials

| Service | Used for | Needed | Status |
|---|---|---|---|
| Anthropic Claude API | Ideas, scripts, B-roll matching, Roman Urdu polish, QC vision check | `ANTHROPIC_API_KEY` | **Missing** |
| YouTube Data API v3 | Viral research, competitor channels, verified view/like/comment counts | `YOUTUBE_API_KEY` (free quota 10k units/day) | **Missing** |
| Instagram Graph API (Business Discovery) | Public metrics of other business/creator accounts | `INSTAGRAM_ACCESS_TOKEN` + `INSTAGRAM_BUSINESS_ID` (needs your IG Business account + Meta app) | Optional, missing |
| TikTok | Research | Official Research API is limited to approved researchers | Not available — manual competitor entry instead |
| HeyGen | Avatar video with your Digital Twin + cloned voice | `HEYGEN_API_KEY`, your `avatar_id`, `voice_id` (paid plan with API access) | **Missing** |
| Pexels | Licensed stock B-roll | `PEXELS_API_KEY` (free) | **Missing** |
| Whisper (faster-whisper) | Transcription + word timing | Runs locally, no key | Working |
| FFmpeg | Rendering | Installed locally | Working |
