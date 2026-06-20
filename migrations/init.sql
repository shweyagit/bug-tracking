CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Stores each GitHub Actions workflow run
CREATE TABLE test_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    github_run_id BIGINT UNIQUE NOT NULL,
    github_repo VARCHAR(255) NOT NULL,
    branch VARCHAR(255),
    commit_sha VARCHAR(40),
    commit_message TEXT,
    pr_number INTEGER,
    pr_title TEXT,
    triggered_by VARCHAR(255),
    workflow_name VARCHAR(255),
    status VARCHAR(50),       -- queued, in_progress, completed
    conclusion VARCHAR(50),   -- success, failure, cancelled, etc.
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique test cases seen across all runs
CREATE TABLE test_cases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    classname TEXT,
    feature_area VARCHAR(255),   -- derived from classname (first segment)
    suite_name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, classname)
);

-- Individual test result per run
CREATE TABLE test_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    case_id UUID NOT NULL REFERENCES test_cases(id),
    status VARCHAR(20) NOT NULL,   -- passed, failed, error, skipped
    duration_seconds FLOAT,
    error_message TEXT,
    error_type VARCHAR(255),
    stack_trace TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- AI-analyzed bug reports generated from failed runs
CREATE TABLE bugs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES test_runs(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    summary TEXT,               -- AI-generated summary
    root_cause TEXT,            -- AI hypothesis
    affected_feature VARCHAR(255),
    severity VARCHAR(20),       -- critical, high, medium, low
    failing_test_ids JSONB DEFAULT '[]',
    jira_ticket_key VARCHAR(50),
    jira_ticket_url TEXT,
    status VARCHAR(30) DEFAULT 'draft',  -- draft, pushed, open, resolved, wont_fix
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Aggregated failure stats per test case for trend tracking
CREATE TABLE failure_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID NOT NULL REFERENCES test_cases(id) ON DELETE CASCADE,
    feature_area VARCHAR(255),
    total_runs INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_failed_at TIMESTAMPTZ,
    last_passed_at TIMESTAMPTZ,
    consecutive_failures INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(case_id)
);

-- Releases for tracking unfixed bugs per release
CREATE TABLE releases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    version VARCHAR(100) NOT NULL UNIQUE,
    release_date TIMESTAMPTZ,
    snapshot_bug_ids JSONB DEFAULT '[]',   -- bug IDs open at release time
    unfixed_bug_ids JSONB DEFAULT '[]',    -- bugs still open after release
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_test_results_run_id ON test_results(run_id);
CREATE INDEX idx_test_results_case_id ON test_results(case_id);
CREATE INDEX idx_test_results_status ON test_results(status);
CREATE INDEX idx_bugs_run_id ON bugs(run_id);
CREATE INDEX idx_bugs_status ON bugs(status);
CREATE INDEX idx_bugs_affected_feature ON bugs(affected_feature);
CREATE INDEX idx_failure_stats_feature ON failure_stats(feature_area);
CREATE INDEX idx_test_runs_github_run_id ON test_runs(github_run_id);
CREATE INDEX idx_test_runs_branch ON test_runs(branch);
