# Songbook Romaniser

Converts selectable-text PDF songbooks in the supplied format to red Roman-numeral chord charts. Runs locally without an API key, OCR service or AI credits. Your original PDF is kept intact; the result is a separate file.

## Start on a computer

Install Python 3.10 or newer, unzip this folder, and open a terminal in this folder:

```
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The browser opens an upload page. Select your PDF, click **Convert songbook**, review the preview and download the result. On some computers the Python command is `python3` rather than `python`.

For command-line conversion without the web interface, only PyMuPDF is needed:

```
python -m pip install PyMuPDF==1.26.6
python romanise_pdf.py "my-songbook.pdf"
```

This creates `my-songbook-roman.pdf` and `my-songbook-roman.audit.json` beside the input. The audit lists each original chord, its Roman numeral, page/chord number and any key changes or spacing warnings.

## Use from a phone

Option 1: run the app on your computer on the same Wi-Fi:

```
python -m streamlit run app.py --server.address 0.0.0.0
```

Open the Network URL printed in the terminal on your phone. Your computer must remain running; its firewall may need to allow the connection.

Option 2: for a permanent web address, put **only** `app.py`, `romanise_pdf.py` and `requirements.txt` in a GitHub repository. Deploy that repository on Streamlit Community Cloud at https://share.streamlit.io with `app.py` as the entry point. Then open the app's URL in Safari and optionally add it to your Home Screen. This uses free hosting rather than OpenAI credits. Uploaded PDFs are processed by the hosting server; they are not added to the repository. Do not upload your songbooks to the code repository.

## What it does

- Reads the first key from the large page heading: `[A, 130 bpm, 4/4]`, `[D]`, or `[D-E, ...]`.
- Treats every page independently. Continuation pages without a printed key need an override.
- Reads the left column before the right column. Identifies bold chord-only rows so ordinary lyric words such as “A” are left alone.
- Uses major references: an Em header uses G, so Em becomes vi.
- Preserves suffixes and converts slash bass notes to degrees: in C, G/B becomes V/7; F# becomes bV. An accidental immediately after the letter belongs to the root.
- Uses printed markers such as `KEY E` exactly where written. A D-to-E change produces I (+2), ii (+2), etc. The +/- value is relative to the original page reference, using the shortest signed interval (a tritone is +6).
- For unmarked changes, uses the shortcut's conservative eight-chord look-ahead: seven must fit the new key, no more than four may fit the old key, at least three distinct chords and a V–I cadence are required, and tied candidates are rejected. Once confirmed, it moves the boundary back over preceding consecutive chords that fit the new key, including shared chords, without crossing a prior confirmation boundary.
- Once a printed or manual marker is encountered, automatic guessing stops for the rest of that page; later printed/manual markers still work. This follows the shortcut's explicit-marker priority.
- Keeps lyrics, headings and graphics. Longer labels may move slightly right; exceptionally dense rows shrink. Review the spacing warnings. Key-change tags are slightly smaller to reduce collisions.
- Repairs the split A/C# chord found in your June example.

## Correct a key or boundary

Download the audit first. Page numbers and chord numbers both start at 1, and chord numbers restart on every page. In the app's Optional corrections box, enter:

```json
{"pages":{"4":{"initial_key":"D","changes":[{"chord":79,"key":"E"}]}}}
```

This example matches the June hymn. For another song, substitute its own page and chord numbers. Only specify `initial_key` when you want to replace the header key. To return to the original key, add another change entry.

From the command line:

```
python romanise_pdf.py "my-songbook.pdf" --overrides overrides.example.json
```

Turn off automatic detection in the app, or pass `--no-auto`, to use only printed/manual changes.

## Limits

This is tailored to the selectable-text, bold-chord songbooks you supplied, not every PDF layout. Scans/photos need a separate OCR step. Different fonts, tiny text, inline chords, missing headings or unusual columns may need changes to the extractor. Pages it cannot confidently process remain unchanged and are flagged in the report. Minor-key harmony and brief modulations can be ambiguous; automatic boundaries are estimates, not guaranteed musical analysis. Shared chords alone cannot uniquely identify a boundary.

Run the included checks with `python -m unittest -v test_romanise.py`.

The `examples` folder contains converted copies of both supplied songbooks and their audit reports. Keep these personal documents separate from any public code repository.
