# How my report builder works

Trace turns a CSV file into a report you can understand and trust. It does more than show numbers: it helps you see what is in your data, how each result was calculated, and what someone can access when you share a report.

## 1. First, understand the data

When a CSV is uploaded, Trace checks that the file is valid and within its limits. It supports UTF-8 files, comma/semicolon/tab separators, and checks things like file size, row and column limits, headers, NUL bytes, and malformed CSV syntax.

Trace then looks at every readable row and makes a best guess about each column. A column can be a `number`, `date`, `category`, or `text`.

These guesses are intentionally careful:
- If every non-empty value looks like a finite decimal, the column can be a number.
- Dates must be valid ISO dates or timestamps.
- If numbers and words are mixed, Trace keeps the column as text instead of guessing and changing some values.
- Values like `00123` stay as labels, so their leading zeros are not lost.
- Short text columns with only a few distinct values are usually categories; free-form text is treated as text.

Only empty or whitespace-only cells count as missing. Values such as `NA`, `N/A`, and `null` are kept as literal text.

Bad rows are not quietly thrown away. Trace records what went wrong, the source line or affected range, the reason, and a safe excerpt of the input. If broken quotation marks make it impossible to know exactly where later rows begin and end, Trace marks an unparsed range rather than pretending it knows. The original CSV is kept with the profile, readable rows, and error details.

## 2. From CSV to a number on the screen

The browser displays results; the backend does the maths. This keeps calculations in one place instead of letting different screens calculate things differently.

Here is the journey:

1. Trace checks that the original CSV still matches its saved SHA-256 hash.
2. The backend parses the original file using its saved delimiter.
3. DuckDB builds a typed, in-memory view of the data.
4. Trace applies the report's filters.
5. It runs the required metric, chart, or table query.
6. The backend sends the result and its calculation receipt to the frontend to display.

A metric can show a sum, average, count, minimum, or maximum, with optional grouping. Charts use the same calculation system. For tables, DuckDB chooses the top rows, and Trace restores the original cell strings so the displayed values stay faithful to the CSV.

Every result can explain itself through **“How was this calculated?”**. The panel shows the filters, SQL and parameters used, row counts, dataset hash, report revision, column/type mapping, and parser and calculation-engine versions. It also explains which rows were included or excluded. Averages use exact decimal division and are rounded to six decimal places using `ROUND_HALF_UP`.

Reports are saved as structured definitions in PostgreSQL. Each save uses a revision number, so an older version cannot silently overwrite a newer edit. If that happens, Trace returns a conflict and asks the user to reload.

## 3. Sharing a report without opening up the workspace

Trace shares a **frozen snapshot**, not a live private report. When the owner chooses **Freeze & share**, the backend checks the saved report revision and dataset hash, calculates the complete report, and refuses to publish an incomplete or invalid result.

The snapshot stores the report definition, results, relevant metadata, calculation receipts, revision, dataset hash, and publication time. Trace creates a cryptographically random share token, but stores only the token's SHA-256 hash in the database.

When someone opens a link, Trace checks that the token matches, the link has not expired or been revoked, and the snapshot still exists. Invalid, expired, revoked, and unknown links all return the same `404 Not Found` response. Revoking a link blocks future requests.

The public page is read-only and shows only the snapshot. It does not provide the original CSV, private workspace, or report-editing controls. Private APIs also check the signed-in user's ownership before returning private data.

A share link is still a secret: anyone who gets an active link can view that snapshot. Hashing, expiry, and revocation help protect it, but the owner should only share it with the intended audience. Revocation cannot undo information someone has already seen or copied.

## 4. What could still go wrong?

Type guessing is useful, but it is still a guess. A mixed column might become text even when the user expected numbers. Missing or unreadable records can affect the data available for a calculation, so it is worth checking the profile and calculation receipt before relying on a result.

A calculation can also fail if the data changes unexpectedly, a resource limit is reached, or two people edit different report revisions at the same time. Trace reports these issues rather than silently pretending everything worked.

## 5. What happens if the files become 100× bigger?

Right now, Trace accepts files up to **5 MiB** and **50,000 records**. A file 100 times larger would hit these limits and be rejected. To support it, the limits and the processing design would need to change.

If those limits were raised, the first pressure points would likely be parsing the whole file, profiling every readable row, and rebuilding the data in DuckDB's in-memory relation. Large sorts and groupings could also take longer and use more memory. The calculation engine currently has a 128 MB memory limit, a 20-second deadline, and allows up to two concurrent calculations.

The next step would be to benchmark where time and memory go, then consider streaming ingestion, persistent analytical storage, caching, and background jobs. The goal would be to handle larger files without losing Trace's core promise: clear results, explainable calculations, and controlled access.
