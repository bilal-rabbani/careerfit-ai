# CareerFit AI evaluation (run3)

Date: 2026-10-04 | Models: see run files | Cases: 9 | Gold requirements: 50 | LLM requests: 55

All cases are synthetic, hand-written and hand-labelled. With this few requirements, one change moves a percentage a lot, so read the numbers as a rough guide, not a benchmark. The targets are working goals I chose, not industry standards.

## Summary

| Metric | Result | Target | |
|---|---|---|---|
| Requirements found by the JD parser | 100.0% | >= 90% | pass |
| Priority correct (must vs nice) | 100.0% | >= 90% | pass |
| Years requirement correct | 100.0% | >= 95% | pass |
| Verdict acceptable (of found) | 96.0% | >= 85% | pass |
| Verdict exactly the ideal one (of found) | 88.0% | info |  |
| End to end acceptable (of all gold) | 96.0% | info |  |
| Critical errors: false 'meets' | 0 | 0 | pass |
| 'Meets' without verified evidence | 0 | 0 | pass |
| Trap keywords wrongly suggested | 0 | 0 | pass |
| Injected text echoed in the report | 0 | 0 | pass |
| Suggestions with invented numbers | 0 | 0 | pass |
| Expected keyword suggestions produced | 1 of 2 | info |  |
| Known-limitation probes triggered | 1 | info |  |

## Per case

| Case | Found | Verdict OK | Critical | Keyword/safety issues | Requests | Seconds |
|---|---|---|---|---|---|---|
| c1_backend_strong | 7/7 | 7/7 | 0 | 0 | 7 | 7 |
| c2_career_changer | 6/6 | 6/6 | 0 | 0 | 6 | 26 |
| c3_civil_synonyms | 6/6 | 6/6 | 0 | 0 | 7 | 28 |
| c4_ambiguous_years | 5/5 | 5/5 | 0 | 0 | 4 | 6 |
| c5_customer_success | 6/6 | 5/6 | 0 | 0 | 7 | 26 |
| c6_prompt_injection | 5/5 | 5/5 | 0 | 0 | 7 | 26 |
| c7_messy_pdf_text | 6/6 | 6/6 | 0 | 0 | 7 | 27 |
| c8_underqualified_ml | 5/5 | 4/5 | 0 | 0 | 4 | 6 |
| c9_wrong_industry | 4/4 | 4/4 | 0 | 0 | 6 | 24 |

## Verdicts: expected (rows) vs got (columns)

Expected is the first, ideal verdict listed for each requirement.

| expected / got | meets | unclear | does_not_meet | cannot_assess | missing |
|---|---|---|---|---|---|
| meets | 24 | 3 | 0 | 0 | 0 |
| unclear | 0 | 12 | 3 | 0 | 0 |
| does_not_meet | 0 | 0 | 6 | 0 | 0 |
| cannot_assess | 0 | 0 | 0 | 2 | 0 |

## Bug report (auto-detected)

| ID | Case | What happened | Expected | Severity | Component | Status | Fix / notes |
|---|---|---|---|---|---|---|---|
| B01 | c5_customer_success | 'Bachelor's degree in business or a related field': got unclear | meets | Minor | Matcher | Open | |
| B02 | c5_customer_success | 'Salesforce' was offered as a keyword the CV supports | Known limitation (alternative keyword in an OR requirement) | Minor | Keyword analysis (known limitation) | Open | |
| B03 | c8_underqualified_ml | 'Strong PyTorch skills': got unclear | meets | Minor | Matcher | Open | |

