Scripts & their purposes:

maie_discover.py:
    discovers the current MAIE faculty roster from UTRGV/Digital Measures and creates the initial faculty dataset.

maie_enrich.py:
    fetches each faculty member's Digital Measures profile and publication records, preserves raw responses, and produces the enriched faculty/publication dataset.

maie_validate.py:
    performs the 1st broad quality check on the enriched data: counts, missing fields, DOI recovery, suspicious URLs, statuses, pbulication types, authorship, etc.

maie_normalize.py:
    converts the enriched Digital Measures data into the normalized research-ledger representation and merges duplicate publication records while preserving source DM IDs.

maie_authorship_audit.py:
    audits MAIE faculty authorship by comparing Digital Measures faculty IDs/names against the current 14 MAIE faculty.

maie_authorship_diagnose.py:
    earlier diagnostic tool for investigating the relationship between current faculty IDs and historical author names. (archive/diagnostic)

maie_authroship_diagnostic.py:
    another/refined authroship diagnostic used while developing the reconiliation rules (archive/diagnostic)

maie_authorship_reconcile.py:
    makes the explicit authorship-reconiliation decisions: exact matches, name variants, historical ID mismatches, external authors, etc. ***this does not modify the db

maie_build_reconciled.py: 
    combines normalized publications w/ the reconciliation decisions to produce the final import-ready maie_faculty_reconciled.json.

maie_final_integrity.py:
    final pre-import gate. checks faculty/publication/author countrs, DM-record preservation, faculty mappings, reconciliation status, and import safety.

maie_reconcile.py:
    earlier reconcilation implementation from the development process. (archive/legacy)

maie_key_reconcile.py:
    earlier investigation/reconciliation utility for identifying key/record relationships. (archive/diagnostic)

