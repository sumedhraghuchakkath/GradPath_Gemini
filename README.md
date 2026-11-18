# GradPath — Final Gemini project

GradPath is a Streamlit career launchpad for undergraduate students. It combines a daily India fresher-market snapshot, resume analysis, a personalised study roadmap and Gemini-powered career chat.

## Windows setup (VS Code)

1. Extract the ZIP and open the `GradPath_Gemini` folder in VS Code.
2. Open **Terminal → New Terminal** and run:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade pip
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Create your private Gemini settings file:

   ```powershell
   Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
   notepad .streamlit\secrets.toml
   ```

4. Replace `PASTE_YOUR_GEMINI_API_KEY_HERE` with your own Google AI Studio API key. Keep the model as `gemini-2.5-flash`. Never share `secrets.toml` or upload it to a public repository.
5. Run the app:

   ```powershell
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```

6. Open `http://localhost:8501` if it does not open automatically. Stop the app with `Ctrl+C` in the terminal.

## What's included

- **Market trends:** The live section retrieves the public Hopin India fresher hiring JSON report. It shows the publisher's update timestamp, current listing totals, new listings in the last seven days, internship and remote shares, median posting age, leading roles and cities. The supplied 2020–2023 CSV remains available in a clearly separated historical explorer.
- **Daily snapshots and ML:** GradPath stores one snapshot per report date in a local SQLite database. After seven distinct daily snapshots, it fits an experimental linear-regression trend estimate. The estimate is directional, not a hiring prediction.
- **Resume Coach:** Upload PDF, DOCX or TXT (up to 10 MB); review section completeness, detected skills, CGPA/marks, and optional job-description keyword comparison. Select one of the listed roles or describe a custom career goal.
- **Personalised Course Roadmap:** Compare resume-recognised and manually confirmed skills with role suggestions, use CGPA as one learning-pace input, choose 1, 3, 6, 9, 12 or a custom 1–36 month duration, follow staged milestones, and download the complete plan.
- **Career Help Chat:** Uses Google Gemini when a key is configured; the built-in guide remains available when it is not.
- **Data & privacy:** Describes source freshness, daily snapshot behaviour, resume processing and external AI processing.

## Live market data and limitations

The live data source is the [Hopin India Fresher Hiring Report](https://hopinjobs.com/reports/fresher-hiring-india), licensed CC BY 4.0. GradPath displays source attribution and the publisher's `updatedAt` value. Hopin's report says it is rebuilt daily and describes its corpus as public job listings narrowed to fresher and entry-level positions. These figures are **job postings**, not confirmed hires, placements, job offers or cumulative recruitment totals. Report categories and collection coverage are determined by the source provider.

The app checks the report when it opens and caches it for up to six hours. It saves a local observation on a newly seen report date. A local app cannot fetch data while it is closed; open it on later days to collect new snapshots. For unattended daily collection on a hosted deployment, configure persistent storage and a scheduled job. The seven-day ML estimate is hidden until at least seven distinct report dates have been saved. It is a simple exploratory trend, not a reliable forecast or promise of future hiring.

The historical CSV is sample data from 2020–2023 and is intentionally separated from live listing counts. The old historical charts should not be interpreted as current market totals.

## Resume processing, CGPA and privacy

The app extracts resume text in the Streamlit session and does not write the uploaded file or extracted text to disk. Clearing the resume or ending the session removes session data. Text extraction can fail for scanned image-only PDFs; OCR is not built in. The keyword list can miss relevant skills or flag a word without understanding proficiency, so students should review detected skills and gaps manually.

CGPA/marks are used only as one factor to suggest a foundation-first, balanced or specialization-oriented learning pace. They do not measure potential, prove skill, predict selection or determine course/job eligibility. The roadmap is educational guidance; verify actual prerequisites, certificates and job requirements with the original provider or employer.

When Gemini chat is enabled, the app sends the current question, up to 12 recent chat messages and a short profile summary (career goal, CGPA and recognised skills) to Google's Gemini API. It does **not** send the uploaded resume file or the full extracted resume text. Avoid entering sensitive personal information in chat. Gemini model availability, quotas and data terms can change; review Google's current terms before using real student data.

## Project contents

- `app.py` — active Streamlit application
- `hiring_data.csv` — historical sample data for the original market explorer
- `requirements.txt` — Python dependencies
- `.streamlit/secrets.toml.example` — private configuration template
- `GEMINI_SETUP.txt` — quick setup notes
- `MACHINE LEARNING MODEL FOR PLACEMENT & HIRING DATA` — supplied project reference material
- `backups/` — previous app versions retained for reference

The ZIP intentionally does not include a virtual environment, private API key, or generated local SQLite history database.
