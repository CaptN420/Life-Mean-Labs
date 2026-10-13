"""
Code Lab Event Logger - P0 Integrity Implementation
Implements authoritative event writing for prospective data collection.

Contract: CODELAB_LORA_DATA_COLLECTION_CONTRACT_v0
Correction: IMPLEMENTATION_PLAN_CORRECTION
"""

import json
import uuid
import hashlib
import threading
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


# Logging integrity levels
LOG_COMPLETE = "LOG_COMPLETE"
LOG_PARTIAL = "LOG_PARTIAL"
LOG_CORRUPTED = "LOG_CORRUPTED"

# Required event fields
REQUIRED_EVENT_FIELDS = [
    "schema_version",
    "collection_contract_version", 
    "event_id",
    "run_id",
    "event_seq",
    "timestamp",
    "event_type"
]

# Schema version
SCHEMA_VERSION = "1.0"
COLLECTION_CONTRACT_VERSION = "v0"


class EventSequencer:
    """
    Authoritative event writer per run_id.
    
    Guarantees:
    - One lock/serialization authority for all event emissions in that run
    - No nested lock acquisition
    - event_seq assigned inside same critical section as append
    - Increment only after successful append
    - JSONL append-only
    - Schema validation before append
    """
    
    def __init__(self, run_id: str, events_path: Path):
        self._run_id = run_id
        self._events_path = Path(events_path)
        self._lock = threading.Lock()
        self._seq = 0
        self._log_completeness = LOG_COMPLETE
        self._terminalized = False
        
        # Ensure directory exists
        self._events_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle restart: if file exists, validate and recover sequence
        self._recover_existing_events()
    
    def _recover_existing_events(self) -> None:
        """
        On writer creation:
        - if file is empty: next_seq = 0
        - if file exists: validate existing event sequence, recover last valid event_seq
        """
        if not self._events_path.exists():
            self._seq = 0
            return
        
        # File exists, validate and recover
        try:
            with open(self._events_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not lines:
                self._seq = 0
                return
            
            # Parse existing events and find last valid seq
            last_valid_seq = -1
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    seq = event.get('event_seq')
                    if isinstance(seq, int) and seq >= 0:
                        last_valid_seq = max(last_valid_seq, seq)
                except json.JSONDecodeError:
                    # Corrupted line, mark as LOG_CORRUPTED
                    self._log_completeness = LOG_CORRUPTED
                    break
            
            if last_valid_seq >= 0:
                self._seq = last_valid_seq + 1
            else:
                self._seq = 0
                
        except Exception:
            # If we can't read the file at all, start fresh but mark as LOG_PARTIAL
            self._log_completeness = LOG_PARTIAL
            self._seq = 0
    
    def _validate_event(self, event: Dict[str, Any]) -> bool:
        """Validate event has all required fields."""
        for field in REQUIRED_EVENT_FIELDS:
            if field not in event:
                return False
        
        # Validate event_id is UUID v4
        try:
            uuid.UUID(event['event_id'], version=4)
        except (ValueError, KeyError):
            return False
        
        # Validate event_seq is non-negative integer
        seq = event.get('event_seq')
        if not isinstance(seq, int) or seq < 0:
            return False
        
        # Validate schema_version
        if event.get('schema_version') != SCHEMA_VERSION:
            return False
        
        # Validate collection_contract_version
        if event.get('collection_contract_version') != COLLECTION_CONTRACT_VERSION:
            return False
        
        return True
    
    def emit(self, event: Dict[str, Any]) -> bool:
        """
        Emit an event with authoritative sequencing.
        
        Single critical section:
        1. reads current seq
        2. assigns event_seq
        3. validates event
        4. appends event
        5. flushes as required
        6. increments seq only after successful append
        
        Returns True if event was successfully emitted, False otherwise.
        """
        with self._lock:
            # Step 1: Check if terminalized
            if self._terminalized:
                return False
            
            # Step 2: Read current sequence number
            current_seq = self._seq
            
            # Step 3: Assign event_seq and required fields
            event['event_seq'] = current_seq
            event['run_id'] = self._run_id
            event['schema_version'] = SCHEMA_VERSION
            event['collection_contract_version'] = COLLECTION_CONTRACT_VERSION
            event['event_id'] = str(uuid.uuid4())
            event['timestamp'] = datetime.now(timezone.utc).isoformat()
            
            # Step 4: Validate event
            if not self._validate_event(event):
                self._log_completeness = LOG_PARTIAL
                return False
            
            # Step 5: Append event to file
            try:
                with open(self._events_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(event, ensure_ascii=False) + '\n')
                
                # Step 6: Flush (rely on OS-level buffering for now)
                pass
                
            except Exception as append_error:
                # Append failure: do NOT increment seq
                self._log_completeness = LOG_PARTIAL
                return False
            
            # Step 7: Increment seq ONLY after successful append
            self._seq += 1
            
            return True
    
    def mark_terminal(self) -> None:
        """Mark the run as terminalized. No more events can be emitted."""
        with self._lock:
            self._terminalized = True
    
    @property
    def log_completeness(self) -> str:
        """Return the logging integrity status."""
        return self._log_completeness
    
    @property
    def final_seq(self) -> int:
        """Return the final sequence number."""
        return self._seq - 1 if self._seq > 0 else 0


class EventLogger:
    """
    High-level event logger that manages EventSequencer instances.
    
    Provides:
    - One authoritative writer per run_id
    - Competing writer protection (best-effort)
    - Task/batch provenance recording
    - Model call provenance
    - Agent trace events
    - Intermediate observations
    - File version provenance
    - Validator lifecycle logging
    - Terminal events
    """
    
    def __init__(self, base_run_dir: Path):
        self._base_run_dir = Path(base_run_dir)
        self._writers: Dict[str, EventSequencer] = {}
        self._lock = threading.Lock()
    
    def _get_events_path(self, run_id: str) -> Path:
        """Get the path to the events.jsonl file for a run."""
        return self._base_run_dir / run_id / "events.jsonl"
    
    def _get_writer(self, run_id: str) -> Optional[EventSequencer]:
        """Get or create an EventSequencer for a run_id."""
        with self._lock:
            if run_id not in self._writers:
                events_path = self._get_events_path(run_id)
                self._writers[run_id] = EventSequencer(run_id, events_path)
            return self._writers[run_id]
    
    def emit(self, run_id: str, event: Dict[str, Any]) -> bool:
        """Emit an event for a run."""
        writer = self._get_writer(run_id)
        if writer is None:
            return False
        return writer.emit(event)
    
    def log_task_received(
        self,
        run_id: str,
        prompt: str,
        task_source: str = "UNKNOWN",
        batch_id: Optional[str] = None,
        created_at: Optional[str] = None
    ) -> bool:
        """Log TASK_RECEIVED event with task provenance."""
        event = {
            "event_type": "TASK_RECEIVED",
            "prompt": prompt,
            "task_hash": hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
            "task_source": task_source,
            "batch_id": batch_id,
            "collection_contract_version": COLLECTION_CONTRACT_VERSION,
            "created_at": created_at or datetime.now(timezone.utc).isoformat()
        }
        return self.emit(run_id, event)
    
    def log_agent_started(
        self,
        run_id: str,
        trace_index: int,
        role: str,
        actual_model: str
    ) -> bool:
        """Log AGENT_STARTED event."""
        event = {
            "event_type": "AGENT_STARTED",
            "trace_index": trace_index,
            "role": role,
            "actual_model": actual_model
        }
        return self.emit(run_id, event)
    
    def log_agent_response(
        self,
        run_id: str,
        trace_index: int,
        role: str,
        actual_model: str,
        attempt_id: Optional[str] = None,
        model_call_id: Optional[str] = None,
        configured_model: Optional[str] = None,
        fallback_reason: Optional[str] = None,
        role_template_id: Optional[str] = None,
        system_prompt_hash: Optional[str] = None,
        sampling_settings_hash: Optional[str] = None,
        input_context_ref: Optional[str] = None,
        input_context_hash: Optional[str] = None,
        response_ref: Optional[str] = None,
        response_hash: Optional[str] = None,
        event_seq_start: Optional[int] = None,
        event_seq_end: Optional[int] = None
    ) -> bool:
        """Log AGENT_RESPONSE event with model call provenance."""
        event = {
            "event_type": "AGENT_RESPONSE",
            "trace_index": trace_index,
            "role": role,
            "actual_model": actual_model,
            "attempt_id": attempt_id or str(uuid.uuid4()),
            "model_call_id": model_call_id or str(uuid.uuid4()),
            "configured_model": configured_model,
            "fallback_reason": fallback_reason,
            "role_template_id": role_template_id,
            "system_prompt_hash": system_prompt_hash,
            "sampling_settings_hash": sampling_settings_hash,
            "input_context_ref": input_context_ref,
            "input_context_hash": input_context_hash,
            "response_ref": response_ref,
            "response_hash": response_hash,
            "event_seq_start": event_seq_start,
            "event_seq_end": event_seq_end
        }
        return self.emit(run_id, event)

    def log_agent_failed(
        self,
        run_id: str,
        trace_index: int,
        role: str,
        actual_model: str,
        attempt_id: Optional[str] = None,
        model_call_id: Optional[str] = None,
        configured_model: Optional[str] = None,
        error_type: Optional[str] = None,
        finish_reason: Optional[str] = None,
        truncated: Optional[bool] = None,
        fallback_reason: Optional[str] = None,
        system_prompt_hash: Optional[str] = None,
        sampling_settings_hash: Optional[str] = None,
        input_context_ref: Optional[str] = None,
        input_context_hash: Optional[str] = None,
        response_ref: Optional[str] = None,
        response_hash: Optional[str] = None,
        event_seq_start: Optional[int] = None,
        event_seq_end: Optional[int] = None
    ) -> bool:
        """Log AGENT_FAILED event with full provenance."""
        event = {
            "event_type": "AGENT_FAILED",
            "trace_index": trace_index,
            "role": role,
            "actual_model": actual_model,
            "attempt_id": attempt_id or str(uuid.uuid4()),
            "model_call_id": model_call_id or str(uuid.uuid4()),
            "configured_model": configured_model,
            "error_type": error_type,
            "finish_reason": finish_reason,
            "truncated": truncated,
            "fallback_reason": fallback_reason,
            "system_prompt_hash": system_prompt_hash,
            "sampling_settings_hash": sampling_settings_hash,
            "input_context_ref": input_context_ref,
            "input_context_hash": input_context_hash,
            "response_ref": response_ref,
            "response_hash": response_hash,
            "event_seq_start": event_seq_start,
            "event_seq_end": event_seq_end
        }
        return self.emit(run_id, event)
    
    def log_file_mutation(
        self,
        run_id: str,
        path: str,
        operation: str,
        before_hash: Optional[str] = None,
        after_hash: Optional[str] = None
    ) -> bool:
        """Log FILE mutation event."""
        event = {
            "event_type": "FILE_MUTATION",
            "path": path,
            "operation": operation,
            "before_hash": before_hash,
            "after_hash": after_hash
        }
        return self.emit(run_id, event)
    
    def log_tool_started(
        self,
        run_id: str,
        tool_name: str,
        input_refs: Optional[List[str]] = None
    ) -> bool:
        """Log TOOL_STARTED event."""
        event = {
            "event_type": "TOOL_STARTED",
            "tool_name": tool_name,
            "input_refs": input_refs
        }
        return self.emit(run_id, event)
    
    def log_tool_result(
        self,
        run_id: str,
        tool_name: str,
        status: str,
        output_refs: Optional[List[str]] = None
    ) -> bool:
        """Log TOOL_RESULT event."""
        event = {
            "event_type": "TOOL_RESULT",
            "tool_name": tool_name,
            "status": status,
            "output_refs": output_refs
        }
        return self.emit(run_id, event)
    
    def log_test_started(
        self,
        run_id: str,
        test_spec: str,
        validator_type: str = "pytest"
    ) -> bool:
        """Log TEST_STARTED event."""
        event = {
            "event_type": "TEST_STARTED",
            "test_spec": test_spec,
            "validator_type": validator_type
        }
        return self.emit(run_id, event)
    
    def log_test_result(
        self,
        run_id: str,
        status: str,
        command: Optional[str] = None,
        input_artifact_refs: Optional[List[str]] = None,
        output_result_refs: Optional[List[str]] = None,
        occurred_after_trace_index: Optional[int] = None,
        occurred_before_trace_index: Optional[int] = None
    ) -> bool:
        """Log TEST_RESULT event."""
        event = {
            "event_type": "TEST_RESULT",
            "status": status,
            "command": command,
            "input_artifact_refs": input_artifact_refs,
            "output_result_refs": output_result_refs,
            "occurred_after_trace_index": occurred_after_trace_index,
            "occurred_before_trace_index": occurred_before_trace_index
        }
        return self.emit(run_id, event)
    
    def log_validator_result(
        self,
        run_id: str,
        validator_type: str,
        status: str,
        lifecycle_state: Optional[str] = None,
        score: Optional[float] = None,
        input_artifact_refs: Optional[List[str]] = None,
        output_result_refs: Optional[List[str]] = None
    ) -> bool:
        """Log VALIDATOR_RESULT event (observability only, no behavior change)."""
        event = {
            "event_type": "VALIDATOR_RESULT",
            "validator_type": validator_type,
            "status": status,
            "lifecycle_state": lifecycle_state,
            "score": score,
            "input_artifact_refs": input_artifact_refs,
            "output_result_refs": output_result_refs
        }
        return self.emit(run_id, event)
    
    def log_repair_started(
        self,
        run_id: str,
        source_trace_index: int,
        repair_type: Optional[str] = None
    ) -> bool:
        """Log REPAIR_STARTED event."""
        event = {
            "event_type": "REPAIR_STARTED",
            "source_trace_index": source_trace_index,
            "repair_type": repair_type
        }
        return self.emit(run_id, event)
    
    def log_run_completed(
        self,
        run_id: str,
        final_status: str = "passed"
    ) -> bool:
        """Log RUN_COMPLETED terminal event."""
        event = {
            "event_type": "RUN_COMPLETED",
            "final_status": final_status
        }
        success = self.emit(run_id, event)
        # Mark as terminal
        writer = self._get_writer(run_id)
        if writer:
            writer.mark_terminal()
        return success
    
    def log_run_failed(
        self,
        run_id: str,
        error_type: Optional[str] = None,
        failure_stage: Optional[str] = None
    ) -> bool:
        """Log RUN_FAILED terminal event."""
        event = {
            "event_type": "RUN_FAILED",
            "error_type": error_type,
            "failure_stage": failure_stage
        }
        success = self.emit(run_id, event)
        # Mark as terminal
        writer = self._get_writer(run_id)
        if writer:
            writer.mark_terminal()
        return success
    
    def get_log_completeness(self, run_id: str) -> str:
        """Get the logging integrity status for a run."""
        writer = self._get_writer(run_id)
        if writer:
            return writer.log_completeness
        return LOG_COMPLETE
    
    def validate_event_sequence(self, run_id: str) -> Dict[str, Any]:
        """
        Validate event sequence integrity.
        
        Returns dict with:
        - is_valid: bool
        - has_duplicates: bool
        - has_gaps: bool
        - is_ordered: bool
        - total_events: int
        """
        events_path = self._get_events_path(run_id)
        if not events_path.exists():
            return {
                "is_valid": False,
                "has_duplicates": False,
                "has_gaps": False,
                "is_ordered": False,
                "total_events": 0
            }
        
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not lines:
                return {
                    "is_valid": True,
                    "has_duplicates": False,
                    "has_gaps": False,
                    "is_ordered": True,
                    "total_events": 0
                }
            
            events = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError:
                    return {
                        "is_valid": False,
                        "has_duplicates": False,
                        "has_gaps": False,
                        "is_ordered": False,
                        "total_events": 0,
                        "error": "Malformed JSON in events file"
                    }
            
            # Check for duplicates
            seqs = [e.get('event_seq') for e in events]
            ids = [e.get('event_id') for e in events]
            has_duplicates = len(seqs) != len(set(seqs)) or len(ids) != len(set(ids))
            
            # Check for gaps and ordering
            has_gaps = False
            is_ordered = True
            for i in range(1, len(seqs)):
                if seqs[i] != seqs[i-1] + 1:
                    has_gaps = True
                    is_ordered = False
                    break
                if seqs[i] < seqs[i-1]:
                    is_ordered = False
            
            return {
                "is_valid": not has_duplicates and not has_gaps and is_ordered,
                "has_duplicates": has_duplicates,
                "has_gaps": has_gaps,
                "is_ordered": is_ordered,
                "total_events": len(events)
            }
            
        except Exception as e:
            return {
                "is_valid": False,
                "has_duplicates": False,
                "has_gaps": False,
                "is_ordered": False,
                "total_events": 0,
                "error": str(e)
            }
