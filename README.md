# Hash Marks — hosted setup

This turns Hash Marks from a single file into a real (free) website where
lines can be refreshed with one click instead of copy-pasting.

## What's in this folder

- `index.html` — the app itself
- `data/ratings.json`, `data/offdefst.json` — current SP+ ratings (manually updated when you get a new spreadsheet, same as before)
- `data/games.json` — board/lines data. This is what the "Update Hash Marks lines" workflow refreshes automatically.
- `scripts/` — your existing Python scripts, slightly extended to also write JSON output for the site
- `.github/workflows/update-lines.yml` — the manual-trigger automation

## One-time setup (do this once)

1. **Create a GitHub account** at github.com if you don't have one — free.

2. **Create a new repository**:
   - Click the "+" in the top right → "New repository"
   - Name it something like `hash-marks`
   - Leave it Public (simpler for free GitHub Pages; the API key stays protected either way — see step 4)
   - Click "Create repository"

3. **Upload these files**:
   - On the new repo's page, click "uploading an existing file" (or "Add file" → "Upload files")
   - Drag in everything from this folder, **keeping the folder structure** — `data/`, `scripts/`, and `.github/` need to stay as folders, not get flattened
   - Commit the upload

4. **Add your CFBD API key as a secret** (this keeps it out of the code entirely):
   - Repo → Settings → Secrets and variables → Actions → "New repository secret"
   - Name: `CFBD_API_KEY`
   - Value: your key
   - **Use a freshly-regenerated key here**, not the one from earlier — that one's been pasted in chat and a screenshot a couple of times, so it's worth rotating before it becomes the key your live site depends on. Get a new one at collegefootballdata.com/key.

5. **Turn on GitHub Pages**:
   - Repo → Settings → Pages
   - Under "Source," pick "Deploy from a branch"
   - Branch: `main`, folder: `/ (root)`
   - Save
   - GitHub will give you a URL like `https://yourusername.github.io/hash-marks/` — takes a minute or two to go live the first time

## Using it during the season

**To refresh lines:**
1. Go to your repo → "Actions" tab
2. Click "Update Hash Marks lines" in the left sidebar
3. Click "Run workflow" (top right), fill in year/week, click the green "Run workflow" button
4. Wait ~30 seconds — refresh the Actions page to see it finish
5. Open your site URL, go to the Ratings tab, click "Sync latest data" — this pulls the freshly-updated `games.json` into your board (merges with anything you already added; won't duplicate)

**To update SP+ ratings** (still manual, since CFBD doesn't have SP+):
- Same as before — get an updated spreadsheet, send it to Claude, get updated `ratings.json`/`offdefst.json` files back, upload them into the `data/` folder on GitHub (this replaces the old files), then click "Sync latest data" on the site.

## Cross-device sync setup (Supabase)

Without this section, the site still works, but your board/bets stay stuck to whichever browser you're using — no sync between your phone and laptop. This is what fixes that.

1. **Create a free account** at [supabase.com](https://supabase.com).
2. **Create a new project** (pick any name/region, generate a database password and save it somewhere — you likely won't need it again for this setup, but don't lose it).
3. Wait ~2 minutes for the project to finish provisioning.
4. **Run the setup script**: in your project, go to the "SQL Editor" in the left sidebar → "New query" → paste in the entire contents of `supabase_setup.sql` from this folder → click "Run." This creates the one table the app needs. **Read the security note in that file before running it** — it explains exactly what level of protection this does and doesn't give you.
5. **Get your two keys**: Project Settings (gear icon) → "API" → copy the **Project URL** and the **anon public** key (not the `service_role` one — that one's more powerful and shouldn't go in a public page).
6. **Paste them into `index.html`**: open the file, find this near the top of the `<script>` section:
   ```js
   const SUPABASE_URL = "";        // e.g. "https://abcdefgh.supabase.co"
   const SUPABASE_ANON_KEY = "";   // the "anon public" key from your project's API settings
   ```
   Paste your values between the quotes, save, and re-upload `index.html` to your GitHub repo (overwriting the old copy).
7. Reload your site. Near the top right, you should now see **"Data: Supabase (synced across devices)"** instead of "This browser only." That confirms it's working — add a bet or a game, then check the same site from your phone; it should show up there too.

**One thing worth knowing:** Supabase's free tier pauses a project after about a week with no activity (likely during your offseason). Waking it back up is a couple of clicks from the project dashboard — not a big deal, just don't be surprised if the site briefly shows "This browser only" after a long gap until you've woken the project up.

## Notes

- Without the Supabase setup above, your bet log and personal picks stay in your browser's local storage on whatever device you're using — they don't sync between devices. With it, they do.
- If you ever want the lines refresh to happen automatically on a schedule instead of manually, that's a one-line change to `update-lines.yml` (adding a `schedule:` trigger) — just ask.
- If you later want real access control (a login) instead of the "anyone with your URL can read/write" model described in `supabase_setup.sql`, that's a bigger but doable step — ask and we can add Supabase Auth.
