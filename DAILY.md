# Daily job scan — instructions for Claude

This file is what the daily scheduled task follows. Do these steps in order.

1. From the repository root run:

   ```
   python3 scan.py --json > /tmp/scan.json
   ```

   It needs nothing installed. If it fails, run it once more; if it still fails,
   report the error as the day's message.

2. Read `/tmp/scan.json`. For each entry in `matches`, decide whether it really
   fits the person (see **Profile** below). Drop ones that are clearly off-field
   (for example translation, sales or marketing roles that only matched on a word
   like "QA" or "tech"). If `profile/cv.md` or `profile/cv.txt` exists, read it and
   use it to judge fit and to write one short "why it fits" line per job.
   **Drop BPO companies** (call centers, outsourcing / virtual-assistant / staffing
   firms, healthcare or back-office outsourcing). Keep companies that build their own
   product (software, SaaS, tech) even if they also run a support office in Cebu.
   If you can't tell, keep it and add "⚠️ may be BPO" to its line.
   **Watch for fake or spam listings**, mostly from Google Jobs: a posting found only on
   repost sites such as Trabajo.org or Jobrapido, from a company with no real web
   presence or an odd name, with a clickbait title ("Ship Real Code"), or "remote"
   but tagged to Cebu. Drop obvious spam; otherwise add "⚠️ check this company is real".

3. Reply with the day's report as your final message, in this format, and nothing else:

   ```
   🎯 N new internship(s) today

   1. <Title> — <Company>
      📍 <Location> · <Source> · posted <date>
      💡 <one line: why it fits, or what to check>
      🔗 <url>
   ```

   Put the best fits first. If nothing survives filtering, reply with exactly
   `No new matching internships today.` plus one line saying how many postings
   were scanned and any sources listed under `errors`.

4. Do not apply to anything, edit `config.toml`, commit, or push. This run only reports.

## Profile

- Looking for: **internships** (OJT / practicum / trainee) — later also entry-level jobs
- Fields: software development, data / AI / ML, IT (support, networking, security, QA)
- Avoid: **BPO companies** (call centers, outsourcing, virtual-assistant and staffing firms)
- Location: **Cebu City, Philippines** (Cebu metro area) or remote roles open to the Philippines
