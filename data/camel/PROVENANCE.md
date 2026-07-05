# camel-msa-glosses.tsv — provenance

Lemma→gloss lexicon distilled from **Camel Morph MSA v1.0**
(`camel_morph_msa_v1.0.db`, ALMOR text format), from the
`CaMeL-Lab/camel_morph` repository, `official_releases/
lrec-coling2024_release/databases/camel-morph-msa/`. Licence: **MIT**,
© 2018–2022 New York University Abu Dhabi.

Columns: `lex` (vocalised lemma, Arabic script) · `pos` · `root`
(dot-separated) · `glosses` (semicolon-separated English senses).
105,274 deduplicated rows from the ###STEMS### section. Reproduce with:

    python3 tools/extract_camel_glosses.py camel_morph_msa_v1.0.db \
        data/camel/camel-msa-glosses.tsv

This database was chosen over the CAMeL Tools default `calima-msa-*`
databases deliberately: those carry LDC/SAMA-heritage redistribution
restrictions; camel_morph's own release is cleanly MIT. (Project decision
on record — licensing is a redistribution-compatibility question.)
