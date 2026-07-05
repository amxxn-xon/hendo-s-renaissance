# olam-enml.tsv — provenance

English→Malayalam dataset from the **Olam** project (olam.in), licensed
**ODbL 1.0**. Columns match the official dump documented at
`https://olam.in/p/open/enml`: English entry, part of speech, Malayalam
definition (tab-separated).

This copy was extracted on 2026-07-02 from the SQLite bundle in
`github.com/sandeep-s-s/Malayalam_Dictionary` (table `DATA`, 216,918 rows),
which repackages the Olam open dataset. One row had internal whitespace
flattened to single spaces; text is otherwise verbatim, including the
older ZWJ-style chillu encoding (e.g. ന്‍ rather than atomic ൻ) — do not
"normalise" it.

**Preferred long-term source:** the official dump from olam.in — it drops
in here unchanged. Attribution required by ODbL: "Contains data from Olam
(olam.in), made available under the Open Database License."
