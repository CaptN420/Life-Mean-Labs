"""
SQLite storage layer for Life_mean Studio.

Provides persistent storage for:
  - Workflows (configurations)
  - Prompts (library)
  - Session metadata
  - Event references

All data is stored in a dedicated database file.
No existing Life_mean databases are accessed.
Secrets are never stored in plaintext.
"""

from __future__ import annotations

import sqlite3
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import contextmanager

logger = logging.getLogger("LifeMean.Studio.Storage")

# Schema version for migrations
SCHEMA_VERSION = 1


class StudioStorage:
    """
    SQLite storage layer for Life_mean Studio.
    
    Usage:
        storage = StudioStorage(db_path="life_mean_studio.db")
        workflow_id = storage.create_workflow({"name": "test", "config": {...}})
        prompt_id = storage.create_prompt({"name": "test", "content": "...", "category": "coding"})
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize storage with a database path.
        
        Args:
            db_path: Path to SQLite database. Defaults to life_mean_studio_data.db in project root.
        """
        if db_path is None:
            # Default path in Life_mean root, outside the source tree
            db_path = str(Path(__file__).parent.parent / "life_mean_studio_data.db")
        
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._schema_initialized = False
    
    def connect(self) -> sqlite3.Connection:
        """Connect to the database, creating tables if needed.

        Reuses an already-open connection to avoid leaking handles on the
        same SQLite file (Windows locks the file while a handle is open).
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if self._conn is not None:
            return self._conn

        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row

        if not self._schema_initialized:
            self._create_schema_direct()
            self._schema_initialized = True

        return self._conn
    
    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._schema_initialized = False
    
    @contextmanager
    def _transaction(self):
        """Context manager for transactions."""
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
    
    def _create_schema_direct(self):
        """Create schema tables directly without recursion."""
        if not self._conn:
            return
        
        self._conn.executescript("""
            -- Workflows table
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                version TEXT NOT NULL DEFAULT '1.0',
                config TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Prompts table
            CREATE TABLE IF NOT EXISTS prompts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL,
                variables TEXT,
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Sessions table
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                workflow_id TEXT,
                status TEXT NOT NULL DEFAULT 'idle',
                metadata TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (workflow_id) REFERENCES workflows(id)
            );
            
            -- Event references table
            CREATE TABLE IF NOT EXISTS event_references (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                session_id TEXT,
                run_id TEXT,
                event_type TEXT NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                payload_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Agents table
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                persona TEXT NOT NULL DEFAULT 'general',
                system_prompt TEXT NOT NULL,
                model TEXT,
                provider TEXT,
                config TEXT,
                tools TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                version INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Schema version tracking
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Update schema version
        self._conn.execute("DELETE FROM schema_version")
        self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    
    # ---- Workflow operations ----
    
    def create_workflow(self, name: str, config: Dict[str, Any], description: str = "") -> str:
        """
        Create a new workflow.
        
        Args:
            name: Workflow name
            config: Workflow configuration dict
            description: Optional description
            
        Returns:
            Workflow ID
            
        Raises:
            ValueError: If config is invalid
        """
        import uuid
        
        # Validate config
        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")
        
        required_keys = ["mode"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Config missing required key: {key}")
        
        if config["mode"] not in ("single", "multi"):
            raise ValueError("Config mode must be 'single' or 'multi'")
        
        workflow_id = str(uuid.uuid4())
        
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO workflows (id, name, description, version, config, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                (workflow_id, name, description, "1.0", json.dumps(config, ensure_ascii=False))
            )
        
        logger.debug("Created workflow: %s", workflow_id)
        return workflow_id
    
    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get a workflow by ID."""
        conn = self.connect()
        row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        
        if not row:
            return None
        
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "version": row["version"],
            "config": json.loads(row["config"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all workflows."""
        conn = self.connect()
        rows = conn.execute("SELECT * FROM workflows ORDER BY created_at DESC").fetchall()
        
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "version": row["version"],
                "config": json.loads(row["config"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    
    def update_workflow(self, workflow_id: str, updates: Dict[str, Any]) -> bool:
        """Update a workflow."""
        set_clauses = []
        params = []
        
        for key in ["name", "description", "config"]:
            if key in updates:
                set_clauses.append(f"{key} = ?")
                if key == "config":
                    params.append(json.dumps(updates[key], ensure_ascii=False))
                else:
                    params.append(updates[key])
        
        if not set_clauses:
            return False
        
        set_clauses.append("updated_at = datetime('now')")
        params.append(workflow_id)
        
        with self._transaction() as conn:
            conn.execute(
                f"UPDATE workflows SET {', '.join(set_clauses)} WHERE id = ?",
                params
            )
        
        return True
    
    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow."""
        with self._transaction() as conn:
            cursor = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            return cursor.rowcount > 0
    
    # ---- Prompt operations ----
    
    def create_prompt(self, name: str, content: str, category: str = "general", 
                      variables: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a new prompt.
        
        Args:
            name: Prompt name
            content: Prompt content
            category: Prompt category
            variables: Optional template variables
            
        Returns:
            Prompt ID
        """
        import uuid
        prompt_id = str(uuid.uuid4())
        
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO prompts (id, name, category, content, variables, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, datetime('now'), datetime('now'))""",
                (prompt_id, name, category, content, 
                 json.dumps(variables, ensure_ascii=False) if variables else None)
            )
        
        logger.debug("Created prompt: %s", prompt_id)
        return prompt_id
    
    def get_prompt(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Get a prompt by ID."""
        conn = self.connect()
        row = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        
        if not row:
            return None
        
        return {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "content": row["content"],
            "variables": json.loads(row["variables"]) if row["variables"] else {},
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    
    def list_prompts(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List prompts, optionally filtered by category."""
        conn = self.connect()
        
        if category:
            rows = conn.execute(
                "SELECT * FROM prompts WHERE category = ? ORDER BY created_at DESC",
                (category,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM prompts ORDER BY created_at DESC").fetchall()
        
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "category": row["category"],
                "content": row["content"],
                "variables": json.loads(row["variables"]) if row["variables"] else {},
                "version": row["version"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    
    def search_prompts(self, query: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search prompts by name or content."""
        conn = self.connect()
        
        if category:
            rows = conn.execute(
                """SELECT * FROM prompts 
                   WHERE (name LIKE ? OR content LIKE ?) AND category = ?
                   ORDER BY created_at DESC""",
                (f"%{query}%", f"%{query}%", category)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM prompts 
                   WHERE name LIKE ? OR content LIKE ?
                   ORDER BY created_at DESC""",
                (f"%{query}%", f"%{query}%")
            ).fetchall()
        
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "category": row["category"],
                "content": row["content"],
                "variables": json.loads(row["variables"]) if row["variables"] else {},
                "version": row["version"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
    
    def update_prompt(self, prompt_id: str, updates: Dict[str, Any]) -> bool:
        """Update a prompt."""
        set_clauses = []
        params = []
        
        for key in ["name", "content", "category"]:
            if key in updates:
                set_clauses.append(f"{key} = ?")
                params.append(updates[key])
        
        if "variables" in updates:
            set_clauses.append("variables = ?")
            params.append(json.dumps(updates["variables"], ensure_ascii=False))
        
        if not set_clauses:
            return False
        
        # Increment version
        set_clauses.append("version = version + 1")
        set_clauses.append("updated_at = datetime('now')")
        params.append(prompt_id)
        
        with self._transaction() as conn:
            conn.execute(
                f"UPDATE prompts SET {', '.join(set_clauses)} WHERE id = ?",
                params
            )
        
        return True
    
    def delete_prompt(self, prompt_id: str) -> bool:
        """Delete a prompt."""
        with self._transaction() as conn:
            cursor = conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
            return cursor.rowcount > 0
    
    # ---- Session operations ----
    
    def create_session(self, workflow_id: Optional[str] = None) -> str:
        """Create a new session."""
        import uuid
        session_id = str(uuid.uuid4())
        
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO sessions (id, run_id, workflow_id, status, started_at, created_at)
                   VALUES (?, NULL, ?, 'idle', datetime('now'), datetime('now'))""",
                (session_id, workflow_id)
            )
        
        return session_id
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update a session."""
        set_clauses = []
        params = []
        
        for key in ["run_id", "status", "metadata"]:
            if key in updates:
                set_clauses.append(f"{key} = ?")
                if key == "metadata":
                    params.append(json.dumps(updates[key], ensure_ascii=False))
                else:
                    params.append(updates[key])
        
        if "status" in updates and updates["status"] in ("completed", "failed", "cancelled"):
            set_clauses.append("completed_at = datetime('now')")
        
        if not set_clauses:
            return False
        
        params.append(session_id)
        
        with self._transaction() as conn:
            conn.execute(
                f"UPDATE sessions SET {', '.join(set_clauses)} WHERE id = ?",
                params
            )
        
        return True
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session by ID."""
        conn = self.connect()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        
        if not row:
            return None
        
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "workflow_id": row["workflow_id"],
            "status": row["status"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "created_at": row["created_at"],
        }
    
    def list_sessions(self, workflow_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """List sessions."""
        conn = self.connect()
        
        if workflow_id:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE workflow_id = ? ORDER BY created_at DESC LIMIT ?",
                (workflow_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        
        return [
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "workflow_id": row["workflow_id"],
                "status": row["status"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    
    # ---- Event reference operations ----
    
    def add_event_reference(self, event_type: str, session_id: Optional[str] = None,
                           run_id: Optional[str] = None, 
                           correlation_id: Optional[str] = None,
                           payload: Optional[Dict[str, Any]] = None) -> str:
        """
        Add an event reference.
        
        The actual event data is stored in JSONL files, this table provides indexing.
        """
        import hashlib
        import uuid
        
        event_id = str(uuid.uuid4())
        payload_hash = hashlib.sha256(json.dumps(payload or {}, ensure_ascii=False).encode()).hexdigest()[:16]
        
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO event_references (id, event_id, session_id, run_id, event_type, timestamp, payload_hash)
                   VALUES (?, ?, ?, ?, ?, datetime('now'), ?)""",
                (event_id, event_id, session_id, run_id, event_type, payload_hash)
            )
        
        return event_id
    
    def get_events(self, session_id: Optional[str] = None, 
                   event_type: Optional[str] = None,
                   limit: int = 100) -> List[Dict[str, Any]]:
        """Get event references."""
        conn = self.connect()
        
        if session_id and event_type:
            rows = conn.execute(
                "SELECT * FROM event_references WHERE session_id = ? AND event_type = ? ORDER BY timestamp DESC LIMIT ?",
                (session_id, event_type, limit)
            ).fetchall()
        elif session_id:
            rows = conn.execute(
                "SELECT * FROM event_references WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
        elif event_type:
            rows = conn.execute(
                "SELECT * FROM event_references WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM event_references ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        
        return [
            {
                "id": row["id"],
                "event_id": row["event_id"],
                "session_id": row["session_id"],
                "run_id": row["run_id"],
                "event_type": row["event_type"],
                "timestamp": row["timestamp"],
                "payload_hash": row["payload_hash"],
            }
            for row in rows
        ]

    # ---- Agent operations ----

    def create_agent(self, name: str, system_prompt: str, persona: str = "general",
                     description: str = "", model: Optional[str] = None,
                     provider: Optional[str] = None, config: Optional[Dict[str, Any]] = None,
                     tools: Optional[List[str]] = None) -> str:
        """Create a new agent."""
        import uuid
        agent_id = str(uuid.uuid4())

        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO agents (id, name, description, persona, system_prompt, model, provider,
                   config, tools, enabled, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, datetime('now'), datetime('now'))""",
                (agent_id, name, description, persona, system_prompt, model, provider,
                 json.dumps(config, ensure_ascii=False) if config else None,
                 json.dumps(tools, ensure_ascii=False) if tools else None)
            )

        logger.debug("Created agent: %s", agent_id)
        return agent_id

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get an agent by ID."""
        conn = self.connect()
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "persona": row["persona"],
            "system_prompt": row["system_prompt"],
            "model": row["model"],
            "provider": row["provider"],
            "config": json.loads(row["config"]) if row["config"] else {},
            "tools": json.loads(row["tools"]) if row["tools"] else [],
            "enabled": bool(row["enabled"]),
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_agents(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """List all agents."""
        conn = self.connect()
        if enabled_only:
            rows = conn.execute("SELECT * FROM agents WHERE enabled = 1 ORDER BY created_at DESC").fetchall()
        else:
            rows = conn.execute("SELECT * FROM agents ORDER BY created_at DESC").fetchall()

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "persona": row["persona"],
                "system_prompt": row["system_prompt"],
                "model": row["model"],
                "provider": row["provider"],
                "config": json.loads(row["config"]) if row["config"] else {},
                "tools": json.loads(row["tools"]) if row["tools"] else [],
                "enabled": bool(row["enabled"]),
                "version": row["version"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> bool:
        """Update an agent."""
        set_clauses = []
        params = []

        updatable = ["name", "description", "persona", "system_prompt", "model", "provider"]
        for key in updatable:
            if key in updates and updates[key] is not None:
                set_clauses.append(f"{key} = ?")
                params.append(updates[key])

        if "config" in updates:
            set_clauses.append("config = ?")
            params.append(json.dumps(updates["config"], ensure_ascii=False))

        if "tools" in updates:
            set_clauses.append("tools = ?")
            params.append(json.dumps(updates["tools"], ensure_ascii=False))

        if "enabled" in updates:
            set_clauses.append("enabled = ?")
            params.append(1 if updates["enabled"] else 0)

        if not set_clauses:
            return False

        set_clauses.append("version = version + 1")
        set_clauses.append("updated_at = datetime('now')")
        params.append(agent_id)

        with self._transaction() as conn:
            conn.execute(
                f"UPDATE agents SET {', '.join(set_clauses)} WHERE id = ?",
                params
            )

        return True

    def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent."""
        with self._transaction() as conn:
            cursor = conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            return cursor.rowcount > 0

    def duplicate_agent(self, agent_id: str, new_name: Optional[str] = None) -> Optional[str]:
        """Duplicate an agent with a new name."""
        original = self.get_agent(agent_id)
        if not original:
            return None

        import uuid
        new_id = str(uuid.uuid4())
        display_name = new_name or f"{original['name']} (Copy)"

        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO agents (id, name, description, persona, system_prompt, model, provider,
                   config, tools, enabled, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, datetime('now'), datetime('now'))""",
                (new_id, display_name, original["description"], original["persona"],
                 original["system_prompt"], original["model"], original["provider"],
                 json.dumps(original["config"], ensure_ascii=False),
                 json.dumps(original["tools"], ensure_ascii=False))
            )

        logger.debug("Duplicated agent %s to %s", agent_id, new_id)
        return new_id

    def search_agents(self, query: str) -> List[Dict[str, Any]]:
        """Search agents by name or description."""
        conn = self.connect()
        rows = conn.execute(
            """SELECT * FROM agents
               WHERE name LIKE ? OR description LIKE ? OR system_prompt LIKE ?
               ORDER BY created_at DESC""",
            (f"%{query}%", f"%{query}%", f"%{query}%")
        ).fetchall()

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "persona": row["persona"],
                "system_prompt": row["system_prompt"],
                "model": row["model"],
                "provider": row["provider"],
                "config": json.loads(row["config"]) if row["config"] else {},
                "tools": json.loads(row["tools"]) if row["tools"] else [],
                "enabled": bool(row["enabled"]),
                "version": row["version"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
