-- Version 2 of the long-memory store. Initialize through long_memory.py.
-- Large traces, code, and screenshots remain in files referenced by this store.

CREATE TABLE trajectories (
    trajectory_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL CHECK (length(trim(task_id)) > 0),
    agent_id TEXT NOT NULL CHECK (length(trim(agent_id)) > 0),
    attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
    split_group TEXT NOT NULL CHECK (split_group IN ('g1', 'g3')),
    task_request TEXT NOT NULL CHECK (length(trim(task_request)) > 0),
    run_config TEXT NOT NULL
        CHECK (json_valid(run_config) AND json_type(run_config) = 'object'),
    trace_path TEXT NOT NULL CHECK (length(trim(trace_path)) > 0),
    artifact_refs TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(artifact_refs) AND json_type(artifact_refs) = 'array'),
    run_status TEXT NOT NULL DEFAULT 'running'
        CHECK (run_status IN ('running', 'completed', 'interrupted', 'execution_error')),
    evaluation_results TEXT
        CHECK (evaluation_results IS NULL OR
               (json_valid(evaluation_results) AND json_type(evaluation_results) = 'array')),
    agent_turn_count INTEGER CHECK (agent_turn_count >= 0),
    api_retry_count INTEGER CHECK (api_retry_count >= 0),
    repair_round_count INTEGER CHECK (repair_round_count >= 0),
    token_usage TEXT
        CHECK (token_usage IS NULL OR
               (json_valid(token_usage) AND json_type(token_usage) = 'object')),
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    UNIQUE (agent_id, task_id, attempt_no),
    CHECK (repair_round_count IS NULL OR agent_turn_count IS NULL OR
           repair_round_count <= agent_turn_count),
    CHECK ((run_status = 'running' AND finished_at IS NULL) OR
           (run_status <> 'running' AND finished_at IS NOT NULL))
) STRICT;

CREATE TABLE experiences (
    record_id TEXT PRIMARY KEY,
    experience_id TEXT NOT NULL CHECK (length(trim(experience_id)) > 0),
    agent_id TEXT NOT NULL CHECK (length(trim(agent_id)) > 0),
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    condition TEXT NOT NULL CHECK (length(trim(condition)) > 0),
    lesson TEXT CHECK (length(trim(lesson)) > 0),
    recommended_action TEXT CHECK (length(trim(recommended_action)) > 0),
    avoid_action TEXT CHECK (length(trim(avoid_action)) > 0),
    verification TEXT NOT NULL CHECK (length(trim(verification)) > 0),
    limitations TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'active', 'rejected', 'archived')),
    embedding BLOB,
    embedding_model TEXT,
    embedding_dim INTEGER,
    embedding_text_hash TEXT,
    restored_from_record_id TEXT REFERENCES experiences(record_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    archived_at TEXT,
    UNIQUE (agent_id, experience_id, version_no),
    CHECK (lesson IS NOT NULL OR recommended_action IS NOT NULL OR avoid_action IS NOT NULL),
    CHECK ((status <> 'archived' AND archived_at IS NULL) OR
           (status = 'archived' AND archived_at IS NOT NULL)),
    CHECK (
        (embedding IS NULL AND embedding_model IS NULL AND
         embedding_dim IS NULL AND embedding_text_hash IS NULL)
        OR
        (embedding IS NOT NULL AND embedding_model IS NOT NULL AND
         length(trim(embedding_model)) > 0 AND embedding_dim IS NOT NULL AND
         embedding_dim > 0 AND length(embedding) = embedding_dim * 4 AND
         embedding_text_hash IS NOT NULL AND length(embedding_text_hash) = 64 AND
         embedding_text_hash NOT GLOB '*[^0-9a-f]*')
    )
) STRICT;

CREATE UNIQUE INDEX experiences_one_active_version
    ON experiences(agent_id, experience_id) WHERE status = 'active';
CREATE INDEX experiences_retrieval
    ON experiences(agent_id, embedding_model, embedding_dim) WHERE status = 'active';

CREATE TABLE skills (
    record_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL CHECK (length(trim(skill_id)) > 0),
    agent_id TEXT NOT NULL CHECK (length(trim(agent_id)) > 0),
    version_no INTEGER NOT NULL CHECK (version_no >= 1),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    goal TEXT NOT NULL CHECK (length(trim(goal)) > 0),
    conditions TEXT NOT NULL CHECK (length(trim(conditions)) > 0),
    inputs TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(inputs) AND json_type(inputs) = 'object'),
    workflow TEXT NOT NULL
        CHECK (json_valid(workflow) AND json_type(workflow) = 'array' AND
               json_array_length(workflow) > 0),
    tool_templates TEXT
        CHECK (tool_templates IS NULL OR
               (json_valid(tool_templates) AND json_type(tool_templates) = 'array')),
    completion_checks TEXT NOT NULL
        CHECK (json_valid(completion_checks) AND json_type(completion_checks) = 'array' AND
               json_array_length(completion_checks) > 0),
    limitations TEXT NOT NULL DEFAULT '',
    experience_refs TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(experience_refs) AND json_type(experience_refs) = 'array'),
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate', 'active', 'rejected', 'archived')),
    embedding BLOB,
    embedding_model TEXT,
    embedding_dim INTEGER,
    embedding_text_hash TEXT,
    restored_from_record_id TEXT REFERENCES skills(record_id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    archived_at TEXT,
    UNIQUE (agent_id, skill_id, version_no),
    CHECK ((status <> 'archived' AND archived_at IS NULL) OR
           (status = 'archived' AND archived_at IS NOT NULL)),
    CHECK (
        (embedding IS NULL AND embedding_model IS NULL AND
         embedding_dim IS NULL AND embedding_text_hash IS NULL)
        OR
        (embedding IS NOT NULL AND embedding_model IS NOT NULL AND
         length(trim(embedding_model)) > 0 AND embedding_dim IS NOT NULL AND
         embedding_dim > 0 AND length(embedding) = embedding_dim * 4 AND
         embedding_text_hash IS NOT NULL AND length(embedding_text_hash) = 64 AND
         embedding_text_hash NOT GLOB '*[^0-9a-f]*')
    )
) STRICT;

CREATE UNIQUE INDEX skills_one_active_version
    ON skills(agent_id, skill_id) WHERE status = 'active';
CREATE INDEX skills_retrieval
    ON skills(agent_id, embedding_model, embedding_dim) WHERE status = 'active';

CREATE TABLE memory_sources (
    source_id TEXT PRIMARY KEY,
    experience_record_id TEXT REFERENCES experiences(record_id) ON DELETE RESTRICT,
    skill_record_id TEXT REFERENCES skills(record_id) ON DELETE RESTRICT,
    trajectory_id TEXT REFERENCES trajectories(trajectory_id) ON DELETE RESTRICT,
    source_experience_record_id TEXT REFERENCES experiences(record_id) ON DELETE RESTRICT,
    source_skill_record_id TEXT REFERENCES skills(record_id) ON DELETE RESTRICT,
    evidence_refs TEXT NOT NULL
        CHECK (json_valid(evidence_refs) AND json_type(evidence_refs) = 'array' AND
               json_array_length(evidence_refs) > 0),
    relation TEXT NOT NULL CHECK (relation IN ('supports', 'counterexample')),
    note TEXT NOT NULL CHECK (length(trim(note)) > 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((experience_record_id IS NOT NULL) + (skill_record_id IS NOT NULL) = 1),
    CHECK ((trajectory_id IS NOT NULL) + (source_experience_record_id IS NOT NULL)
           + (source_skill_record_id IS NOT NULL) = 1)
) STRICT;

CREATE INDEX memory_sources_by_trajectory ON memory_sources(trajectory_id);
CREATE UNIQUE INDEX memory_sources_unique_parent
    ON memory_sources(COALESCE(experience_record_id, ''), COALESCE(skill_record_id, ''),
                      COALESCE(source_experience_record_id, ''),
                      COALESCE(source_skill_record_id, ''), relation)
    WHERE trajectory_id IS NULL;
-- Canonicalize JSON before inserting; these indexes detect exact duplicates.
CREATE UNIQUE INDEX memory_sources_unique_experience_evidence
    ON memory_sources(experience_record_id, trajectory_id, relation, evidence_refs)
    WHERE experience_record_id IS NOT NULL;
CREATE UNIQUE INDEX memory_sources_unique_skill_evidence
    ON memory_sources(skill_record_id, trajectory_id, relation, evidence_refs)
    WHERE skill_record_id IS NOT NULL;

-- Identity cannot change after evidence has been attributed to an attempt.
CREATE TRIGGER trajectories_immutable_identity
BEFORE UPDATE OF trajectory_id, task_id, agent_id, attempt_no, split_group ON trajectories
BEGIN
    SELECT RAISE(ABORT, 'Trajectory identity is immutable');
END;

-- Content is versioned. Only status and archived_at may change in place.
CREATE TRIGGER experiences_immutable_content
BEFORE UPDATE OF record_id, experience_id, agent_id, version_no, title, condition,
    lesson, recommended_action, avoid_action, verification, limitations, embedding,
    embedding_model, embedding_dim, embedding_text_hash, restored_from_record_id,
    created_at ON experiences
BEGIN
    SELECT RAISE(ABORT, 'Create a new experience version instead of editing content');
END;

CREATE TRIGGER skills_immutable_content
BEFORE UPDATE OF record_id, skill_id, agent_id, version_no, name, goal, conditions,
    inputs, workflow, tool_templates, completion_checks, limitations, experience_refs,
    embedding, embedding_model, embedding_dim, embedding_text_hash,
    restored_from_record_id, created_at ON skills
BEGIN
    SELECT RAISE(ABORT, 'Create a new skill version instead of editing content');
END;

CREATE TRIGGER experiences_no_reactivation
BEFORE UPDATE OF status ON experiences
WHEN NEW.status <> OLD.status AND NOT (
    (OLD.status = 'candidate' AND NEW.status IN ('active', 'rejected')) OR
    (OLD.status = 'active' AND NEW.status = 'archived'))
BEGIN
    SELECT RAISE(ABORT, 'Restore archived content as a new experience version');
END;

CREATE TRIGGER skills_no_reactivation
BEFORE UPDATE OF status ON skills
WHEN NEW.status <> OLD.status AND NOT (
    (OLD.status = 'candidate' AND NEW.status IN ('active', 'rejected')) OR
    (OLD.status = 'active' AND NEW.status = 'archived'))
BEGIN
    SELECT RAISE(ABORT, 'Restore archived content as a new skill version');
END;

CREATE TRIGGER experiences_validate_restoration
BEFORE INSERT ON experiences
WHEN NEW.restored_from_record_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Restoration must reference an older version of the same experience')
    WHERE NOT EXISTS (
        SELECT 1 FROM experiences
        WHERE record_id = NEW.restored_from_record_id AND agent_id = NEW.agent_id
          AND experience_id = NEW.experience_id AND version_no < NEW.version_no
    );
END;

CREATE TRIGGER experiences_admission_requires_evidence
BEFORE UPDATE OF status ON experiences
WHEN OLD.status = 'candidate' AND NEW.status = 'active'
BEGIN
    SELECT RAISE(ABORT, 'Admission requires provenance') WHERE NOT EXISTS (
        SELECT 1 FROM memory_sources WHERE experience_record_id = NEW.record_id
    );
END;

CREATE TRIGGER skills_admission_requires_evidence
BEFORE UPDATE OF status ON skills
WHEN OLD.status = 'candidate' AND NEW.status = 'active'
BEGIN
    SELECT RAISE(ABORT, 'Admission requires provenance') WHERE NOT EXISTS (
        SELECT 1 FROM memory_sources WHERE skill_record_id = NEW.record_id
    );
END;

CREATE TRIGGER skills_validate_restoration
BEFORE INSERT ON skills
WHEN NEW.restored_from_record_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Restoration must reference an older version of the same skill')
    WHERE NOT EXISTS (
        SELECT 1 FROM skills
        WHERE record_id = NEW.restored_from_record_id AND agent_id = NEW.agent_id
          AND skill_id = NEW.skill_id AND version_no < NEW.version_no
    );
END;

CREATE TRIGGER memory_sources_same_agent_insert
BEFORE INSERT ON memory_sources
BEGIN
    SELECT RAISE(ABORT, 'Memory and source must belong to the same agent')
    WHERE NOT EXISTS (
        SELECT 1 FROM (
            SELECT agent_id FROM experiences WHERE record_id = NEW.experience_record_id
            UNION ALL SELECT agent_id FROM skills WHERE record_id = NEW.skill_record_id
        ) AS target JOIN (
            SELECT agent_id FROM trajectories WHERE trajectory_id = NEW.trajectory_id
            UNION ALL SELECT agent_id FROM experiences WHERE record_id = NEW.source_experience_record_id
            UNION ALL SELECT agent_id FROM skills WHERE record_id = NEW.source_skill_record_id
        ) AS source ON target.agent_id = source.agent_id
    );
    SELECT RAISE(ABORT, 'Memory provenance must be acyclic') WHERE EXISTS (
        WITH RECURSIVE ancestors(kind, id) AS (
            SELECT 'experience', NEW.source_experience_record_id WHERE NEW.source_experience_record_id IS NOT NULL
            UNION SELECT 'skill', NEW.source_skill_record_id WHERE NEW.source_skill_record_id IS NOT NULL
            UNION
            SELECT CASE WHEN m.source_experience_record_id IS NOT NULL THEN 'experience' ELSE 'skill' END,
                   COALESCE(m.source_experience_record_id, m.source_skill_record_id)
            FROM memory_sources m JOIN ancestors a ON
                (a.kind = 'experience' AND m.experience_record_id = a.id) OR
                (a.kind = 'skill' AND m.skill_record_id = a.id)
            WHERE m.trajectory_id IS NULL
        ) SELECT 1 FROM ancestors WHERE
            (kind = 'experience' AND id = NEW.experience_record_id) OR
            (kind = 'skill' AND id = NEW.skill_record_id)
    );
END;

CREATE TRIGGER memory_sources_immutable_update
BEFORE UPDATE ON memory_sources
BEGIN
    SELECT RAISE(ABORT, 'Provenance is append-only');
END;

CREATE TRIGGER memory_sources_immutable_delete
BEFORE DELETE ON memory_sources
BEGIN
    SELECT RAISE(ABORT, 'Provenance is append-only');
END;
