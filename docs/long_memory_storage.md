# Long memory: schema version 2

The store retains exactly four SQLite tables and isolates all records by
`agent_id`. The experiment remains **No Memory vs Long Memory**. Validation,
consolidation and evidence-aware retrieval are internal Long Memory mechanisms.
No cross-agent memory space or provider/plugin framework is introduced.

`src/long_memory.py` handles opening and initialization of the current schema.
`src/long_memory_runtime.py` implements extraction, automatic admission,
independent consolidation, provenance traversal and exact cosine retrieval using
only the standard library. SQLite 3.38+ with JSON support is required.

## Setup and existing data

```shell
python3 scripts/init_long_memory.py --db outputs/memory/bolt/memory.db
```

Use separate files for independent agent/experiment runs and frozen evaluation
snapshots. Initialization validates the current schema and preserves existing
records. Historical schema files, migration commands and migration backups are
not retained. An incompatible database is rejected; use a fresh database rather
than silently deleting records. The schema version marker identifies the current
format; it does not enable historical-version compatibility.

Memory content versions and provenance remain part of the current design. They
are required to trace learned knowledge and must not be confused with old schema
implementations.

## Four-table changes

| Table | v2 changes |
| --- | --- |
| `trajectories` | None. Keep task attempts, agent identity, G1/G3 restriction, trace paths, run configuration, outcomes and usage. |
| `experiences` | Add nullable `lesson`. A lesson/observation/warning/insight may stand alone without an action. Existing recommended/avoid action fields remain compatible. Status defaults to `candidate`; add `rejected`. |
| `skills` | Status defaults to `candidate`; add `rejected`. Existing `conditions`, `workflow`, `completion_checks` express When/How/Done. No minimum source count defines a Skill. |
| `memory_sources` | Make `trajectory_id` nullable; add foreign keys `source_experience_record_id` and `source_skill_record_id`. Exactly one source is required: trajectory OR experience version OR skill version. |

Every source association still targets exactly one experience or skill version.
Same-agent constraints now cover both direct trajectory links and memory links.
Cycle rejection and append-only source triggers prevent lost or cyclic lineage.
`supports` and `counterexample` describe the evidence's relationship to a claim;
neither is inferred from the trajectory's success/failure outcome.

For example, E20 points to E1/E7/E13 with three `memory_sources` rows; each source
memory retains its own trajectory links. `provenance(E20)` returns the graph
edges and the original trajectories including their recorded outcomes. Evidence
is not replaced with a flattened list. Confidence counts distinct trajectory IDs
reachable along supports-only paths, so diamonds in the graph do not double count
and counterexample paths do not provide a confidence boost.

Memory content and embedding metadata remain immutable and versioned. Existing
unique active-version and restoration constraints remain. Allowed transitions:
`candidate -> active/rejected`, and `active -> archived`. Archived/rejected rows
cannot be reactivated. Candidate activation requires provenance. Runtime-created
generalisations use fresh identities, preserving every original memory and its
status. This initial implementation generates new generalised Experience/Skill
records rather than implementing an automatic in-place refinement/version policy.

Experience has no required `skill_id`. The old optional `skills.experience_refs`
JSON field is retained for compatibility but the new core does not write it;
new derivation relationships use the foreign-key-backed provenance links.

## Thin interfaces and evidence input

Inject three application-specific implementations:

- `MemoryLLM.generate(operation, payload)` returns a structured dictionary for
  extraction, validation, semantic judgement, consolidation or task aspects.
  The payload includes operation instructions and supported content fields.
  Set provider `model_id` for run attribution and log provider token usage and
  provider-specific prompt changes in the same experiment log.
- `Embedder.model_id` and `embed(texts)` provide vectors; use a frozen model
  revision/encoding configuration. The core checks finite, nonzero vectors and
  batch dimensions, normalizes vectors, and stores float32 plus content hash.
- `AgentAdapter.run(task, MemoryPacket)` converts input formats and runs the
  chosen agent. It must preserve memory content and its Experience/Skill type.
  `MemoryPacket.render()` is deterministic JSON formatting, never an LLM rewrite.
  An empty packet should result in no memory injection for the baseline.

Learning also needs a simple `evidence_loader(trajectory)` callback returning
`[{"ref": {"step_id": "..."}, "content": "actual recorded evidence"}]`.
The caller reads its actual trace format and supplies trustworthy locators and
content. Extraction rejects locators absent from this evidence; validation and
consolidation receive source evidence, provenance and historical outcomes.
Do not include memory-management prompts as task evidence. Missing evidence or
model/provider failures propagate as errors rather than manufacturing knowledge.

Use `log=JsonlRunLog(Path("outputs/<run>/memory-events.jsonl"))` to record operation
results, errors, elapsed time, core prompt version, model identity, retrieval
queries/aspects, scores, selected IDs and packet hash outside the memory database.
Without a supplied log callback the core emits no persisted audit log; experiment
integration must supply it. Unknown model identity remains null, not fabricated.

## Final data flow

1. The experiment runner finishes and records a G1/G3 same-agent trajectory.
   `extract(trajectory_id)` produces zero or more typed candidates with exact
   evidence links. All candidates in one extraction are inserted transactionally.
2. `validate(ref)` automatically checks grounding and knowledge type through the
   injected MemoryLLM. Invalid memory becomes rejected; provider/format errors
   leave a retryable candidate. Relevant active neighbors are discovered by
   similarity and then judged semantically:
   - KEEP: activate valid distinct knowledge.
   - SUPPORT: add evidence to an unchanged same-type active memory; retain the
     duplicate candidate as rejected, with the decision in the run log.
   - CONSOLIDATE: activate valid knowledge and defer the generalisation check.
   - REJECT: reject invalid knowledge.
   `extract_and_validate()` combines these two calls, never consolidation.
3. An independent `consolidate()` pass finds related active memory groups. Only
   groups with the configured number of distinct supporting trajectories reach
   higher-level semantic/evidence judgement. Selected sources are checked against
   the minimum again after judgement. KEEP/REJECT preserve existing records;
   SUPPORT adds provenance; CONSOLIDATE creates a candidate generalisation linked
   to exact source memories and runs the same admission flow. No SPLIT, deletion,
   ID renumbering, automatic similarity merge, or outcome-based reward ranking.
   Consolidation operates on the current frontier: once an active higher-level
   memory cites a source memory, that source remains stored and retrievable through
   provenance but is not repeatedly expanded into later consolidation prompts.
   A later pass combines new frontier evidence with prior higher-level memories.
4. `retrieve(task)` extracts a few task aspects (topics/requirements, not an
   implementation plan). It queries both types with the original task and aspects,
   filters by agent/active status/frozen encoder/dimension/content hash, then uses
   maximum cosine relevance across queries. Below-threshold memories are excluded
   before evidence counting; each type's semantic candidate pool is bounded.
5. Within that relevant pool only, rank by
   `similarity + evidence_weight * min(distinct_supporting_trajectories, evidence_cap)`.
   Return separate Experience/Skill Top-K lists, possibly empty. There is no
   consolidated flag bonus. The adapter receives the original stored content.

Consolidation is an explicit caller-scheduled pass, not a background scheduler.
The threshold controls whether a higher-level check runs during that pass.
Repeated extraction is not an exactly-once job queue: retry already-created
candidates by ID using `validate()`. Semantic SUPPORT handles repeated knowledge;
run orchestration should checkpoint completed extraction calls, including empty
results. This avoids adding an operations/job table in this initial version.

## Configuration

Production runners load `config/long_memory.json` as the single versioned source
for model deployments, request/retry settings and `MemoryConfig`. Secrets and
service endpoints remain in `.env`. All values are validated at startup, and the
configuration SHA-256 is recorded in experiment metadata.

| Parameter | Default | Meaning |
| --- | --- | --- |
| `min_consolidation_evidence` | 3 | Minimum distinct supporting trajectories for a consolidation check. |
| `max_task_aspects` | 3 | Maximum deduplicated retrieval aspects, plus the original task. |
| `retrieval_candidates_per_type` | 20 | Semantic candidate pool per knowledge type, before evidence reranking. |
| `consolidation_candidates` | 4 | Related current-frontier neighbors per seed, in addition to the seed. |
| `retrieval_min_similarity` | 0.35 | Retrieval relevance gate. |
| `consolidation_min_similarity` | 0.55 | Consolidation/duplicate discovery gate; never an automatic merge rule. |
| `top_k_experiences` | 5 | Final Experience limit. |
| `top_k_skills` | 3 | Final Skill limit. |
| `evidence_weight` | 0.05 | Confidence adjustment within the relevant pool. |
| `evidence_cap` | 5 | Cap the confidence adjustment, not the reported evidence count. |
| `max_grounding_trajectories` | 5 | Representative trajectory summaries sent to semantic calls. |
| `max_grounding_edges` | 12 | Direct provenance edges sent to semantic calls. |
| `max_evidence_items` | 12 | Located evidence items supplied from one trajectory. |
| `max_evidence_chars` | 12000 | Total deterministic evidence-text budget per trajectory. |
| `max_outcome_chars` | 2000 | Outcome-summary text budget per representative trajectory. |

Thresholds are initial experiment hyperparameters, not universal constants.
Agent identity, memory mode, database snapshot, model/embedding implementations,
evidence loader and log location are caller configuration. The core prompt version
is a versioned code constant, recorded in logs.

## Mode boundaries and integration

`disabled` opens no database and calls no memory model/embedding provider.
`read_only` opens an existing SQLite file in read-only/query-only mode; retrieval
logs are external. It cannot extract, validate or consolidate. `learn` allows the
same retrieval plus learning writes. The runner must validate task IDs against
the frozen split manifest; G2/G4/G5 outcomes never enter learning storage.

The repository's existing live agent scripts are not rewritten by this module.
They can call `LongMemory.run(task, adapter)` and, after saving an eligible
trajectory, `extract_and_validate(trajectory_id)`. Live provider and agent bindings
must be supplied by that integration; offline tests exercise the complete core
with deterministic fake providers. No live LLM call or experiment is run by setup.

```shell
python3 -m unittest discover -s tests -v
```
