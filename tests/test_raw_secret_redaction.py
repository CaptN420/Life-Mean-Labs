"""Regression: RAW recorder must redact credentials echoed by a backend.

LM Studio's 401 body replays the API token (seen in real runs: turns.response
and storage/raw_data/*.json held `sk-lm-…`). record_agent_call/record_debate_event
go through redact_secrets() so no secret can ever be persisted again — either to
RAW or to debate runtime DBs.
"""

from philosophical_council.raw_protocol import RawDebateRecorder, redact_secrets


class TestRedactSecrets:
    def test_sk_lm_token_stripped(self):
        s = ("[401 Invalid LM Studio API token provided: "
             "sk-lm-hvpuABCdef123456789 the rest. Learn more.")
        out = redact_secrets(s)
        assert "sk-lm-hvpuABCdef123456789" not in out
        assert "[REDACTED]" in out
        # surrounding context preserved
        assert "the rest." in out

    def test_github_tokens_stripped(self):
        for tok in ("ghp_" + "a" * 30, "gho_" + "b" * 30,
                    "github_pat_" + "c" * 30):
            out = redact_secrets(f"creds {tok}; use securely")
            assert tok not in out
            assert "[REDACTED]" in out

    def test_plain_text_untouched(self):
        s = "the tenth fibonacci number is 55; no secret here"
        assert redact_secrets(s) == s

    def test_non_string_passthrough(self):
        assert redact_secrets(None) is None
        assert redact_secrets(42) == 42


class TestRecorderRedact:
    def test_agent_call_output_redacted(self):
        r = RawDebateRecorder()
        m = r.start_experiment(task_id="t", dataset_source="code_lab", random_seed=1)
        c = r.record_agent_call(
            m.experiment_id, "a1", "developer",
            input_sent="prompt",
            output_received="[401 token sk-lm-hvpuZzYyXxWwVvUu1234567]",
            status="error",
        )
        assert "sk-lm-" not in c.output_received
        assert "[REDACTED]" in c.output_received
        # input never carries secrets by construction, but is guarded too

    def test_debate_event_content_redacted(self):
        r = RawDebateRecorder()
        m = r.start_experiment(task_id="t", dataset_source="code_lab", random_seed=1)
        e = r.record_debate_event(
            m.experiment_id, "verification", "a1",
            "error echoed sk-lm-hvpuAbCdEf1234567890",
            round_num=1,
        )
        assert "sk-lm-" not in e.content
        assert "[REDACTED]" in e.content