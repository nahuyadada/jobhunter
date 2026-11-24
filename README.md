# jobhunter

Scans job sites every morning for new **internships** (and later entry-level jobs)
in software, data/AI and IT around **Cebu City, Philippines**, plus remote roles open
to the Philippines, and sends the matches to your phone through the Claude app.

## How it works

```
daily Claude scheduled task (07:47 PH time)
  └─ python3 scan.py --json          ← searches the sites below, filters by config.toml
       └─ Claude reads the matches (DAILY.md), drops poor fits, writes a short list
            └─ push notification to the Claude app on your phone
```

| Source | What it covers |
|---|---|
| LinkedIn (public search) | Cebu postings + remote roles listed for the Philippines |
| JobStreet PH | Cebu postings (the biggest PH job board) |
| Kalibrr | PH postings, kept if in Cebu or work-from-home |
| Google Jobs (via SearchApi.io) | Everything Google Jobs collects, including Indeed and company career sites. Needs a SearchApi key; 2 searches per run |
| Remotive | Remote internships open worldwide / Asia |
| Lever / Ashby / Greenhouse | Company career pages you list in `config.toml` (the trick from the reel) |

Indeed PH and PhilJobNet block automated access, so they aren't included.

## Change what it looks for

Everything is in [`config.toml`](config.toml):

- **Switch to jobs later:** set `job_types = ["internship", "entry"]`.
- **Different city:** edit `locations`.
- **More/fewer fields:** edit `search_terms` and `field_keywords`.
- **Watch specific companies:** add their board names to `lever_companies`, `ashby_companies`
  or `greenhouse_companies`.

To let Claude judge fit against your CV, add it as `profile/cv.md` (plain text is fine).

## Run it yourself

Python 3.11+ and nothing else:

```
python3 scan.py                  # Markdown list of the last 26 hours
python3 scan.py --hours 168      # last week
python3 scan.py --json           # JSON output
python3 scan.py --only jobstreet,kalibrr
python3 scan.py --state data/seen.json   # remember what was already reported
```

## Ideas taken from

- [adarsh-ajay/Job-Hunter](https://github.com/adarsh-ajay/Job-Hunter): the daily schedule → scrape LinkedIn →
  AI match score → phone alert flow (built in n8n with Telegram there).
- [espin086/GPT-Jobhunter](https://github.com/espin086/GPT-Jobhunter): scoring jobs against your resume, and
  throttled, retrying API calls.
- [const-narayan/job-hunter](https://github.com/const-narayan/job-hunter): a MERN job portal (for employers to post jobs),
  so it had little to reuse for scanning.
