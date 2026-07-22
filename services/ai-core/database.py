import sqlite3
from pathlib import Path
from threading import Lock


DATABASE_PATH = Path(__file__).resolve().parent / "data" / "ai_core.db"


class Database:
    def __init__(self, path: str | Path = DATABASE_PATH) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.lock = Lock()
        self._create_tables()

    def _create_tables(self) -> None:
        with self.lock, self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT,
                    status TEXT NOT NULL,
                    rag_used INTEGER NOT NULL DEFAULT 0,
                    duration_ms INTEGER NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at
                ON agent_runs(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_tool_calls_run_id
                ON tool_calls(run_id);

                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES conversation_sessions(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_messages_session
                ON conversation_messages(session_id, id DESC);

                CREATE TABLE IF NOT EXISTS content_drafts (
                    id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    tone TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    hashtags_json TEXT NOT NULL,
                    source_facts_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
                    review_comment TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_content_drafts_status_created
                ON content_drafts(status, created_at DESC);

                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    id TEXT PRIMARY KEY,
                    suite_name TEXT NOT NULL,
                    suite_version TEXT NOT NULL,
                    total_cases INTEGER NOT NULL,
                    passed_cases INTEGER NOT NULL,
                    failed_cases INTEGER NOT NULL,
                    pass_rate REAL NOT NULL,
                    tool_selection_accuracy REAL NOT NULL,
                    average_duration_ms REAL NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluation_case_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    expected_tools_json TEXT NOT NULL,
                    actual_tools_json TEXT NOT NULL,
                    answer TEXT,
                    duration_ms INTEGER NOT NULL,
                    failures_json TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES evaluation_runs(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created
                ON evaluation_runs(created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_evaluation_results_run
                ON evaluation_case_results(run_id, id);

                CREATE TABLE IF NOT EXISTS data_releases (
                    id TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    version_hash TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('published', 'blocked')),
                    is_active INTEGER NOT NULL DEFAULT 0,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_data_releases_dataset_created
                ON data_releases(dataset, created_at DESC);

                CREATE TABLE IF NOT EXISTS media_assets (
                    id TEXT PRIMARY KEY,
                    asset_type TEXT NOT NULL CHECK (asset_type IN ('image', 'video', 'text')),
                    title TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    product_id TEXT,
                    source TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_media_assets_product_type
                ON media_assets(product_id, asset_type, created_at DESC);
                """
            )


database = Database()
