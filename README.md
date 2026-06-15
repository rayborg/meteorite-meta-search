# Meteorite Meta Search

Static meteorite inventory search site powered by a scheduled scraper.

Target repo name: `meteorite-meta-search`

Default public URL after GitHub Pages is enabled:

`https://rayborg.github.io/meteorite-meta-search/`

## What this does

- Scrapes a maintained list of private meteorite seller websites.
- Normalizes inventory into `data/listings.json`.
- Extracts likely meteorite type/subtype from title and description:
  - pallasite
  - chondrite
  - carbonaceous chondrite
  - ordinary chondrite
  - H/L/LL subtype
  - iron
  - achondrite
  - lunar
  - Martian
  - eucrite / diogenite / howardite
  - ureilite / aubrite / angrite
  - mesosiderite
  - tektite / impactite
- Extracts price, weight, and estimated price per gram when present.
- Displays a searchable, sortable static dashboard.
- Runs automatically with GitHub Actions every 6 hours.

## Initial sites

Configured in `data/sites.json`:

- SV Meteorites
- Meteorlab
- Meteorite and More

You can add more seller inventory pages by editing `data/sites.json`.

## How to publish

1. Create a new **public** GitHub repo named:

   `meteorite-meta-search`

2. Upload these files to that repo.

3. In the repo, go to:

   **Settings → Pages → Build and deployment → Source → GitHub Actions**

4. Go to:

   **Actions → Scrape and publish meteorite inventory → Run workflow**

5. After the workflow finishes, the site should be visible at:

   `https://rayborg.github.io/meteorite-meta-search/`

## Notes

This is intentionally polite and conservative:
- Uses a normal user-agent.
- Has a delay between requests.
- Does not bypass logins, CAPTCHAs, or anti-bot systems.
- Stores short normalized listing facts, not full seller pages.

If a site blocks scraping or disallows it in its terms, remove it from `data/sites.json`.
