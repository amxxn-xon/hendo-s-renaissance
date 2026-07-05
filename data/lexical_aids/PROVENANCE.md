# lexical-aids-3rd-ed-2024.pdf — provenance

**Lexical Aids to the Syriac New Testament**, Third Expanded Edition,
edited by George Anton Kiraz and Timothy A. Lee (Gorgias Press, 2024).
ISBN 978-1-4632-4603-7 (paperback) / 978-1-4632-4604-4 (eBook).

Copyright page states: *"Copyright © 2024 by Gorgias Press LLC. All
rights reserved under International and Pan-American Copyright
Conventions. No part of this publication may be reproduced, stored in a
retrieval system or transmitted in any form or by any means, electronic,
mechanical, photocopying, recording, scanning or otherwise without the
prior written permission of Gorgias Press LLC."* This is a fully
proprietary commercial work — unlike every other vendored source in
this repo (SEDRA III has an academic-use carve-out; QAC, camel_morph,
Olam are GPL/MIT/ODbL), there is no permissive licence here at all.

**Authorization**: per Ameen (2026-07-05), Gorgias Press has partnered
with IIT Goa and approved use of this work in this project. This is
recorded as attested, not independently verified — **flagged for
Dr. Amaldev** to attach the written agreement/MOU, same pattern as
DECISIONS.md №2 and №24 for other unresolved licensing questions. Do not
treat this book as freely redistributable absent that document.

**Why it's here despite being non-permissive, and how the project's own
rules are still met**: the compiled store and dictpress export never
store or display a single character of this book's own text. `WORDS.TXT`
(SEDRA III, vendored under `data/sedra3/`, already cleared for this
project) remains the sole source of any Syriac text that appears
anywhere in the database. This book is used only as:

1. A **prioritization signal** — its Chapter 1 Word Frequency List
   ranks words by frequency across the *whole* Peshitta NT, which is the
   signal used to decide which additional SEDRA III word-records are
   worth compiling beyond Matthew's own top-N cutoff (see
   `suriyani/lexical_aids.py`, DECISIONS.md №27).
2. A **citation** — the per-entry provenance record for any word
   selected this way names this book (edition, reference number, its
   own NT-wide frequency count) as the reason that word was included,
   auditable in the app's "Sources & confidence" panel.

**Extraction quality, verified empirically (2026-07-05)**: both
`pdfplumber` and `pymupdf` were tried against Chapter 1; `pymupdf`
extracts noticeably better but roughly 11% of entries still show
font-encoding corruption (stray Greek/Latin glyphs substituted for
Syriac letters that didn't survive the book's embedded font — e.g.
entry 44, "much, many", extracts as `ܣܰΏ݁ܺܝܳܐܐ` with a Greek Ώ mid-word).
`suriyani/lexical_aids.py` validates every extracted Syriac string
against the Syriac Unicode block before using it for anything; anything
that fails is dropped as an honest gap, never corrected by guessing
(project rule: never invent source-language text).

**Scope**: only Chapter 1 (Word Frequency List, pp. 1–42) is parsed.
The book has eight further chapters (proper nouns, Greek loanwords,
homographs, verb paradigms, part-of-speech lists, roots, compounds,
Semitic cognates) — none are used yet; a future extension, not required
for the current fix.
