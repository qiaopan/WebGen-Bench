# WebGen long-memory experiment: five-group staged split

## What “five-fold” means here

The 101 WebGen-Bench websites are divided into five mutually exclusive,
approximately equal groups (21/20/20/20/20). This is a **five-group stratified
staged split**, not standard five-fold cross-validation. Standard five-fold
cross-validation would rebuild an independent memory database five times, each
time using four folds for memory and the remaining fold for testing. That option
remains possible with these same group files, but it is not the primary protocol
because it is much more expensive and does not leave a separate development set.

## Data groups and stages

| Group | Websites | Role | May write memory? |
| --- | ---: | --- | --- |
| Group 01 | 21 | Initial long-memory examples | Yes |
| Group 02 | 20 | Development evaluation, reused while the method is being debugged | No |
| Group 03 | 20 | Additional long-memory examples | Yes |
| Group 04 | 20 | Final-test replicate A | No |
| Group 05 | 20 | Final-test replicate B | No |

### Application-type counts by group

| Application type | G1 | G2 | G3 | G4 | G5 | Memory (G1+G3) | Final (G4+G5) | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Analytics Platforms/Dashboards | 2 | 1 | 1 | 1 | 1 | 3 | 2 | 6 |
| Browser-Based Games | 0 | 1 | 3 | 1 | 2 | 3 | 3 | 7 |
| CRM Systems | 1 | 1 | 1 | 0 | 1 | 2 | 1 | 4 |
| Company Brochure Sites | 2 | 1 | 2 | 1 | 2 | 4 | 3 | 8 |
| Discussion Forums | 2 | 1 | 2 | 1 | 2 | 4 | 3 | 8 |
| E-commerce Web Applications | 2 | 1 | 2 | 2 | 1 | 4 | 3 | 8 |
| ERP Platforms | 1 | 1 | 1 | 0 | 1 | 2 | 1 | 4 |
| Email Clients | 0 | 1 | 0 | 1 | 0 | 0 | 1 | 2 |
| Internal Tools | 1 | 1 | 0 | 1 | 0 | 1 | 1 | 3 |
| Job Search Platforms | 1 | 1 | 1 | 1 | 0 | 2 | 1 | 4 |
| Learning Platforms | 3 | 1 | 1 | 2 | 1 | 4 | 3 | 8 |
| News and Information Sites | 1 | 1 | 1 | 2 | 1 | 2 | 3 | 6 |
| Personal Blog Sites | 0 | 1 | 0 | 1 | 0 | 0 | 1 | 2 |
| Personal Portfolio Sites | 1 | 1 | 2 | 1 | 1 | 3 | 2 | 6 |
| Productivity Applications | 1 | 1 | 1 | 0 | 2 | 2 | 2 | 5 |
| Project Management Tools | 0 | 1 | 1 | 2 | 0 | 1 | 2 | 4 |
| Publishing/Blogging Platforms | 1 | 1 | 0 | 0 | 2 | 1 | 2 | 4 |
| Social Media Platforms | 0 | 1 | 1 | 1 | 1 | 1 | 2 | 4 |
| Streaming and Interactive Platforms | 0 | 1 | 0 | 1 | 0 | 0 | 1 | 2 |
| Travel Booking Portals | 2 | 1 | 0 | 1 | 2 | 2 | 3 | 6 |
| **Total websites** | **21** | **20** | **20** | **20** | **20** | **41** | **40** | **101** |

### Other balancing checks

| Set | Websites | UI tasks | Data Management sites | Content Presentation sites | User Interaction sites | Functional tasks | Data-display tasks | Design-validation tasks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| G1 | 21 | 137 | 5 | 6 | 10 | 74 | 35 | 28 |
| G2 | 20 | 130 | 6 | 5 | 9 | 69 | 38 | 23 |
| G3 | 20 | 130 | 6 | 4 | 10 | 66 | 42 | 22 |
| G4 | 20 | 126 | 3 | 6 | 11 | 67 | 35 | 24 |
| G5 | 20 | 124 | 4 | 7 | 9 | 63 | 36 | 25 |
| Memory (G1+G3) | 41 | 267 | 11 | 10 | 20 | 140 | 77 | 50 |
| Final (G4+G5) | 40 | 250 | 7 | 13 | 20 | 130 | 71 | 49 |

The experiment proceeds in three stages:

1. **Method development.** Start with an empty database. Process Group 01 in a
   fixed order, generate each website, execute its official UI tasks, obtain
   feedback, and allow only that feedback to update long memory. Compare
   no-memory and long-memory on Group 02. Development attempts may reuse Groups
   01 and 02; if the memory schema or algorithm changes, rebuild the database
   from empty.
2. **Memory expansion and freeze.** After selecting the method, append Group 03
   to the existing memory database in its fixed order. Run one paired
   confirmation on Group 02, then freeze the prompts, retrieval settings,
   stopping rules, evaluator configuration, and memory database.
3. **Final evaluation.** Generate and evaluate Groups 04 and 05 once under both
   no-memory and long-memory conditions. Report the combined 40-website result
   as the primary result and the two 20-website groups as replicate summaries.
   No final-test information is written back to memory.

## Stratification and fairness

The split is deterministic with seed `792`. It searches 50,000 valid candidate
partitions and selects the one that best balances four observed dimensions:

- application type;
- website technical primary category;
- UI-task primary category;
- total number of UI tasks.

Group 02 contains exactly one website from each of the 20 application types, and
the combined Groups 04+05 contain every application type at least once. It is
mathematically impossible for all five groups to contain every type because
Email Clients, Personal Blog Sites, and Streaming and Interactive Platforms have
only two websites each.

Fair comparison between conditions is paired: the no-memory and long-memory
branches receive the same website prompt, the same frozen UI tasks and expected
results, the same generation limits, the same evaluator, and the same evaluation
order. Group 02 and Groups 04/05—including their prompts, task trajectories,
screenshots, scores, and feedback—must never update memory.

## Reproduction

Run `python scripts/create_experiment_splits.py`. The generated manifest records
the source SHA-256 hash, seed, selected IDs, group distributions, task counts,
hard constraints, and leakage controls.

Because development now uses part of the official 101-site set, the final score
must be described as a **held-out 40-site WebGen-Bench-derived evaluation**, not
as the official full-101 WebGen-Bench score.
