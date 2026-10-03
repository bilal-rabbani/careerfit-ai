# CareerFit AI evaluation (run1)

Date: 2026-10-03 | Models: gemini/gemini-3.8-flash, groq/openai/gpt-oss-120b | Cases: 8 | Gold requirements: 46 | LLM requests: 0

All cases are synthetic, hand-written and hand-labelled. With this few requirements, one change moves a percentage a lot, so read the numbers as a rough guide, not a benchmark. The targets are working goals I chose, not industry standards.

## Summary

| Metric | Result | Target | |
|---|---|---|---|
| Requirements found by the JD parser | 4.3% | >= 90% | check |
| Priority correct (must vs nice) | 100.0% | >= 90% | pass |
| Years requirement correct | 100.0% | >= 95% | pass |
| Verdict acceptable (of found) | 100.0% | >= 85% | pass |
| Verdict exactly the ideal one (of found) | 100.0% | info |  |
| End to end acceptable (of all gold) | 4.3% | info |  |
| Critical errors: false 'meets' | 0 | 0 | pass |
| 'Meets' without verified evidence | 0 | 0 | pass |
| Trap keywords wrongly suggested | 0 | 0 | pass |
| Injected text echoed in the report | 0 | 0 | pass |
| Suggestions with invented numbers | 0 | 0 | pass |
| Expected keyword suggestions produced | 0 of 2 | info |  |
| Known-limitation probes triggered | 0 | info |  |

## Per case

| Case | Found | Verdict OK | Critical | Keyword/safety issues | Requests | Seconds |
|---|---|---|---|---|---|---|
| c1_backend_strong | 0/7 | 0/0 | 0 | 0 | 0 | 0 |
| c2_career_changer | 0/6 | 0/0 | 0 | 0 | 0 | 0 |
| c3_civil_synonyms | 2/6 | 2/2 | 0 | 0 | 0 | 0 |
| c4_ambiguous_years | 0/5 | 0/0 | 0 | 0 | 0 | 0 |
| c5_customer_success | 0/6 | 0/0 | 0 | 0 | 0 | 0 |
| c6_prompt_injection | 0/5 | 0/0 | 0 | 0 | 0 | 0 |
| c7_messy_pdf_text | 0/6 | 0/0 | 0 | 0 | 0 | 0 |
| c8_underqualified_ml | 0/5 | 0/0 | 0 | 0 | 0 | 0 |

## Verdicts: expected (rows) vs got (columns)

Expected is the first, ideal verdict listed for each requirement.

| expected / got | meets | unclear | does_not_meet | cannot_assess | missing |
|---|---|---|---|---|---|
| meets | 2 | 0 | 0 | 0 | 0 |
| unclear | 0 | 0 | 0 | 0 | 0 |
| does_not_meet | 0 | 0 | 0 | 0 | 0 |
| cannot_assess | 0 | 0 | 0 | 0 | 0 |

## Bug report (auto-detected)

| ID | Case | What happened | Expected | Severity | Component | Status | Fix / notes |
|---|---|---|---|---|---|---|---|
| B01 | c1_backend_strong | Requirement not found in parsed JD: Bachelor's degree in Computer Science or a related field | Extracted as its own requirement | Major | JD parser | Open | |
| B02 | c1_backend_strong | Requirement not found in parsed JD: 3+ years of professional Python experience | Extracted as its own requirement | Major | JD parser | Open | |
| B03 | c1_backend_strong | Requirement not found in parsed JD: Experience building REST APIs with FastAPI or Flask | Extracted as its own requirement | Major | JD parser | Open | |
| B04 | c1_backend_strong | Requirement not found in parsed JD: Solid knowledge of PostgreSQL | Extracted as its own requirement | Major | JD parser | Open | |
| B05 | c1_backend_strong | Requirement not found in parsed JD: Docker experience | Extracted as its own requirement | Major | JD parser | Open | |
| B06 | c1_backend_strong | Requirement not found in parsed JD: Experience with AWS | Extracted as its own requirement | Major | JD parser | Open | |
| B07 | c1_backend_strong | Requirement not found in parsed JD: Experience with CI/CD pipelines | Extracted as its own requirement | Major | JD parser | Open | |
| B08 | c2_career_changer | Requirement not found in parsed JD: Bachelor's degree in Statistics, Mathematics, Economics or a related field | Extracted as its own requirement | Major | JD parser | Open | |
| B09 | c2_career_changer | Requirement not found in parsed JD: 2+ years of experience working as a data analyst | Extracted as its own requirement | Major | JD parser | Open | |
| B10 | c2_career_changer | Requirement not found in parsed JD: Strong SQL skills | Extracted as its own requirement | Major | JD parser | Open | |
| B11 | c2_career_changer | Requirement not found in parsed JD: Experience with Tableau or Power BI | Extracted as its own requirement | Major | JD parser | Open | |
| B12 | c2_career_changer | Requirement not found in parsed JD: Proficiency in Python or R | Extracted as its own requirement | Major | JD parser | Open | |
| B13 | c2_career_changer | Requirement not found in parsed JD: Experience with A/B testing | Extracted as its own requirement | Major | JD parser | Open | |
| B14 | c3_civil_synonyms | Requirement not found in parsed JD: Minimum 3 years of project scheduling experience | Extracted as its own requirement | Major | JD parser | Open | |
| B15 | c3_civil_synonyms | Requirement not found in parsed JD: Knowledge of Earned Value Management | Extracted as its own requirement | Major | JD parser | Open | |
| B16 | c3_civil_synonyms | Requirement not found in parsed JD: Resource loading and leveling experience | Extracted as its own requirement | Major | JD parser | Open | |
| B17 | c3_civil_synonyms | Requirement not found in parsed JD: MS Project | Extracted as its own requirement | Major | JD parser | Open | |
| B18 | c4_ambiguous_years | Requirement not found in parsed JD: 4+ years of React experience | Extracted as its own requirement | Major | JD parser | Open | |
| B19 | c4_ambiguous_years | Requirement not found in parsed JD: TypeScript | Extracted as its own requirement | Major | JD parser | Open | |
| B20 | c4_ambiguous_years | Requirement not found in parsed JD: Experience integrating REST APIs | Extracted as its own requirement | Major | JD parser | Open | |
| B21 | c4_ambiguous_years | Requirement not found in parsed JD: Git and code review practices | Extracted as its own requirement | Major | JD parser | Open | |
| B22 | c4_ambiguous_years | Requirement not found in parsed JD: Next.js | Extracted as its own requirement | Major | JD parser | Open | |
| B23 | c5_customer_success | Requirement not found in parsed JD: Excellent communication skills | Extracted as its own requirement | Major | JD parser | Open | |
| B24 | c5_customer_success | Requirement not found in parsed JD: Strong stakeholder management | Extracted as its own requirement | Major | JD parser | Open | |
| B25 | c5_customer_success | Requirement not found in parsed JD: Bachelor's degree in business or a related field | Extracted as its own requirement | Major | JD parser | Open | |
| B26 | c5_customer_success | Requirement not found in parsed JD: 2+ years in a customer-facing SaaS role | Extracted as its own requirement | Major | JD parser | Open | |
| B27 | c5_customer_success | Requirement not found in parsed JD: Experience with a CRM such as Salesforce or HubSpot | Extracted as its own requirement | Major | JD parser | Open | |
| B28 | c5_customer_success | Requirement not found in parsed JD: Spanish language skills | Extracted as its own requirement | Major | JD parser | Open | |
| B29 | c6_prompt_injection | Requirement not found in parsed JD: Bachelor's degree in Computer Science or a related field | Extracted as its own requirement | Major | JD parser | Open | |
| B30 | c6_prompt_injection | Requirement not found in parsed JD: 1+ year of manual testing experience | Extracted as its own requirement | Major | JD parser | Open | |
| B31 | c6_prompt_injection | Requirement not found in parsed JD: Ability to write clear test cases | Extracted as its own requirement | Major | JD parser | Open | |
| B32 | c6_prompt_injection | Requirement not found in parsed JD: Knowledge of Selenium | Extracted as its own requirement | Major | JD parser | Open | |
| B33 | c6_prompt_injection | Requirement not found in parsed JD: Experience with API testing using Postman | Extracted as its own requirement | Major | JD parser | Open | |
| B34 | c7_messy_pdf_text | Requirement not found in parsed JD: Bachelor's degree in Marketing, Business or a related field | Extracted as its own requirement | Major | JD parser | Open | |
| B35 | c7_messy_pdf_text | Requirement not found in parsed JD: 2+ years of digital marketing experience | Extracted as its own requirement | Major | JD parser | Open | |
| B36 | c7_messy_pdf_text | Requirement not found in parsed JD: Hands-on SEO experience | Extracted as its own requirement | Major | JD parser | Open | |
| B37 | c7_messy_pdf_text | Requirement not found in parsed JD: Google Analytics reporting | Extracted as its own requirement | Major | JD parser | Open | |
| B38 | c7_messy_pdf_text | Requirement not found in parsed JD: Content creation for blogs and social media | Extracted as its own requirement | Major | JD parser | Open | |
| B39 | c7_messy_pdf_text | Requirement not found in parsed JD: Experience with paid advertising (Google Ads or Meta Ads) | Extracted as its own requirement | Major | JD parser | Open | |
| B40 | c8_underqualified_ml | Requirement not found in parsed JD: Master's or PhD in Computer Science or a related field | Extracted as its own requirement | Major | JD parser | Open | |
| B41 | c8_underqualified_ml | Requirement not found in parsed JD: 5+ years of experience in machine learning | Extracted as its own requirement | Major | JD parser | Open | |
| B42 | c8_underqualified_ml | Requirement not found in parsed JD: Strong PyTorch skills | Extracted as its own requirement | Major | JD parser | Open | |
| B43 | c8_underqualified_ml | Requirement not found in parsed JD: Experience deploying models to production | Extracted as its own requirement | Major | JD parser | Open | |
| B44 | c8_underqualified_ml | Requirement not found in parsed JD: Experience with Apache Spark | Extracted as its own requirement | Major | JD parser | Open | |

