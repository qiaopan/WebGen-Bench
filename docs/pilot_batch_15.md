# WebGen-Bench Pilot Batch (15 Websites)

This fixed pilot batch is selected from `data/test.jsonl` for the first-stage
baseline and memory-method experiments. The selection must not be changed after
seeing experimental results.

## Selection

| ID | Primary category | Application type | UI tests | Main coverage |
|---|---|---|---:|---|
| 000001 | Data Management | Analytics Platforms/Dashboards | 7 | stock search, reports, validation |
| 000002 | Content Presentation | Analytics Platforms/Dashboards | 5 | maps, comparisons, charts |
| 000009 | User Interaction | Browser-Based Games | 9 | chess actions, history, settings |
| 000017 | Content Presentation | Company Brochure Sites | 6 | one-page content and carousel |
| 000022 | Data Management | CRM Systems | 8 | call logs, CRUD, reporting |
| 000029 | User Interaction | Discussion Forums | 7 | posts, replies, search, user centre |
| 000034 | Content Presentation | E-commerce Web Applications | 6 | property search, filters, details |
| 000037 | User Interaction | E-commerce Web Applications | 8 | product customisation, order, payment |
| 000046 | Data Management | ERP Platforms | 11 | hospital finance, inventory, records |
| 000051 | User Interaction | Job Search Platforms | 9 | forms, accounts, job workflow |
| 000066 | Content Presentation | News and Information Sites | 6 | restaurants, recipes, reviews |
| 000079 | User Interaction | Productivity Applications | 9 | diagram editing and drag-and-drop |
| 000080 | Data Management | Productivity Applications | 8 | to-do CRUD, filtering, search |
| 000094 | User Interaction | Streaming and Interactive Platforms | 6 | recognition records and alerts |
| 000096 | User Interaction | Travel Booking Portals | 5 | search, booking, payment, orders |

Totals: 15 websites and 110 UI test cases. Category allocation: 4 Content
Presentation, 7 User Interaction, and 4 Data Management.

## Fixed pilot protocol

1. Baseline: run the unmodified memory-free agent on all 15 test websites.
2. Memory construction: use only a separately selected subset of
   `data/train.jsonl`; never use pilot/test trajectories, scores, screenshots,
   or evaluator feedback to create or update memory.
3. Freeze the resulting memory before evaluation.
4. Treatment: run the memory-enabled agent on the same 15 websites with the
   same generator model, evaluator model, prompts, iteration limits, and seeds.
5. Compare paired per-website and per-test-case results. Keep all failures and
   do not change the selected IDs after observing outcomes.

The pilot batch is for method development and early signal detection. Final
paper claims should be validated on a larger held-out subset or the complete
101-website, 647-test WebGen-Bench test set.

## Leakage and memory notes

- All 6,667 records in `data/train.jsonl` have empty `ui_instruct.task` and
  `expected_result` fields. Training-memory feedback therefore has to come from
  train-only build/runtime checks, appearance evaluation, self-reflection, or
  separately generated train-only tests; official test cases must not be copied
  into the memory-building stage.
- Test artifacts and scores may be saved for reporting, but they must never be
  inserted into retrievable memory or used to update memory between test cases.
- If this 15-website batch is repeatedly used to tune the method, it becomes a
  development set. After freezing the method, use the remaining 86 websites as
  the held-out final test set (or clearly separate pilot and final results).
