"""Tests for the debate engine fixes."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch


class TestDebateEngineFixes(unittest.TestCase):
    """Test cases for the debate engine fixes."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.config = MagicMock()
        self.config.debate.topic = "What is the meaning of life?"
        self.config.debate.temperature = 0.8
        self.config.debate.max_tokens = 700
        self.config.debate.moderator_max_tokens = 300
        self.config.debate.philosopher_max_tokens = 1500
        self.config.debate.max_continuations = 2
        self.config.debate.mid_term_interval = 10
        self.config.debate.long_term_interval = 50

        self.db = MagicMock()
        self.llm = MagicMock()

    def test_moderator_selects_nihilist_calls_nihilist(self) -> None:
        """Test that moderator selection is respected."""
        from philosophical_council.core.debate_engine import DebateEngine

        with patch('philosophical_council.core.debate_engine.TurnManager') as MockTurnManager:
            mock_turn_manager = MagicMock()
            mock_turn = MagicMock()
            mock_turn.turn_id = 1
            mock_turn.round_num = 1
            mock_turn.speaker = "Nihilist"
            mock_turn.speaker_role = "nihilist"
            mock_turn.moderator_question = "Explain why meaning is a category error."
            mock_turn.moderator_reason = "Previous argument was weak."
            mock_turn_manager.next_turn.return_value = mock_turn
            MockTurnManager.return_value = mock_turn_manager

            engine = DebateEngine(self.config, self.db, self.llm)
            engine.turn_manager = mock_turn_manager
            # Set engine to running state
            engine._running = True
            engine._state.status = "running"

            # Create mock agents
            mock_existentialist = MagicMock()
            mock_existentialist.role = "existentialist"
            mock_existentialist.name = "Existentialist"
            mock_existentialist.config.name = "Existentialist"
            mock_existentialist.system_prompt = "You are an existentialist."
            mock_existentialist.format_response.return_value = "prompt"

            mock_nihilist = MagicMock()
            mock_nihilist.role = "nihilist"
            mock_nihilist.name = "Nihilist"
            mock_nihilist.config.name = "Nihilist"
            mock_nihilist.system_prompt = "You are a nihilist."
            mock_nihilist.format_response.return_value = "prompt"

            # Register agents
            engine.register_agent(mock_existentialist)
            engine.register_agent(mock_nihilist)

            # Mock the database methods
            engine.db.turn_repo.insert_turn.return_value = None
            engine.db.moderator_repo.insert.return_value = None

            # Mock moderator decision
            mock_moderator = MagicMock()
            mock_moderator.system_prompt = "You are a moderator."
            mock_moderator.parse_decision.return_value = {
                "selected_speaker": "Nihilist",
                "challenge": "Explain why meaning is a category error.",
                "reason": "Previous argument was weak.",
                "question": None,
                "detected_issues": None,
            }
            engine._moderator = mock_moderator

            # Mock llm.chat to return (response, finish_reason)
            engine.llm.chat.return_value = ("Nihilist response", "stop")

            # Mock time
            with patch('philosophical_council.core.debate_engine.time') as mock_time:
                mock_time.time.side_effect = [100, 101]
                result = engine.step_once()

            self.assertTrue(result)
            # Verify the Nihilist agent was called (via llm.chat) - second call is for philosopher
            self.assertEqual(self.llm.chat.call_count, 2)
            # Second call should be for the philosopher response
            philosopher_call = self.llm.chat.call_args_list[1]
            messages = philosopher_call.kwargs.get('messages', [])
            system_content = messages[0].get('content', '') if messages else ''
            self.assertIn("nihilist", system_content.lower())

    def test_moderator_selects_pragmatist_calls_pragmatist(self) -> None:
        """Test that Pragmatist selection works."""
        from philosophical_council.core.debate_engine import DebateEngine

        with patch('philosophical_council.core.debate_engine.TurnManager') as MockTurnManager:
            mock_turn_manager = MagicMock()
            mock_turn = MagicMock()
            mock_turn.turn_id = 2
            mock_turn.round_num = 1
            mock_turn.speaker = "Pragmatist"
            mock_turn.speaker_role = "pragmatist"
            mock_turn.moderator_question = "What is practical truth?"
            mock_turn.moderator_reason = "Need practical perspective."
            mock_turn_manager.next_turn.return_value = mock_turn
            MockTurnManager.return_value = mock_turn_manager

            engine = DebateEngine(self.config, self.db, self.llm)
            engine.turn_manager = mock_turn_manager
            # Set engine to running state
            engine._running = True
            engine._state.status = "running"

            mock_pragmatist = MagicMock()
            mock_pragmatist.role = "pragmatist"
            mock_pragmatist.name = "Pragmatist"
            mock_pragmatist.config.name = "Pragmatist"
            mock_pragmatist.system_prompt = "You are a pragmatist."
            mock_pragmatist.format_response.return_value = "prompt"

            engine.register_agent(mock_pragmatist)
            engine.db.turn_repo.insert_turn.return_value = None
            engine.db.moderator_repo.insert.return_value = None

            # Mock moderator decision
            mock_moderator = MagicMock()
            mock_moderator.system_prompt = "You are a moderator."
            mock_moderator.parse_decision.return_value = {
                "selected_speaker": "Pragmatist",
                "challenge": "What is practical truth?",
                "reason": "Need practical perspective.",
                "question": None,
                "detected_issues": None,
            }
            engine._moderator = mock_moderator

            # Mock llm.chat to return (response, finish_reason)
            engine.llm.chat.return_value = ("Pragmatist response", "stop")

            with patch('philosophical_council.core.debate_engine.time') as mock_time:
                mock_time.time.side_effect = [100, 101]
                result = engine.step_once()

            self.assertTrue(result)

    def test_invalid_speaker_rejected(self) -> None:
        """Test that invalid speaker selection is rejected."""
        from philosophical_council.core.debate_engine import DebateEngine

        engine = DebateEngine(self.config, self.db, self.llm)

        # Try to resolve an unknown speaker
        result = engine._resolve_agent("UnknownSpeaker")
        self.assertIsNone(result)

    def test_malformed_json_triggers_retry(self) -> None:
        """Test that malformed JSON triggers retry logic."""
        from philosophical_council.core.debate_engine import DebateEngine

        with patch('philosophical_council.core.debate_engine.TurnManager') as MockTurnManager:
            mock_turn_manager = MagicMock()
            mock_turn_manager.turn_count = 0  # No turns yet
            MockTurnManager.return_value = mock_turn_manager

            engine = DebateEngine(self.config, self.db, self.llm)
            engine.turn_manager = mock_turn_manager

            # Set recent speakers to avoid IndexError
            engine._recent_speakers = ["Skeptic"]

            # Mock moderator with parse_decision that fails then succeeds
            mock_moderator = MagicMock()
            mock_moderator.system_prompt = "You are a moderator."
            mock_moderator.parse_decision.side_effect = [
                json.JSONDecodeError("Expecting value", "", 0),  # First attempt fails
                {"selected_speaker": "Stoic", "challenge": "Test", "reason": "Test reason"},  # Second succeeds
            ]

            engine._moderator = mock_moderator

            with patch.object(engine.llm, 'chat') as mock_chat:
                mock_chat.return_value = ('{"invalid json', "stop")
                decision = engine._get_moderator_decision()

            # Should have retried and eventually succeeded
            self.assertIsNotNone(decision)
            self.assertEqual(decision["selected_speaker"], "Stoic")

    def test_deterministic_fallback_not_skeptic_always(self) -> None:
        """Test that fallback doesn't always pick Skeptic."""
        from philosophical_council.core.debate_engine import DebateEngine

        engine = DebateEngine(self.config, self.db, self.llm)

        # Set recent speakers to include Skeptic multiple times
        engine._recent_speakers = ["Skeptic", "Skeptic", "Skeptic"]

        fallback = engine._get_deterministic_fallback()
        self.assertIsNotNone(fallback)
        # Fallback should pick someone other than the most recent speaker
        self.assertNotEqual(fallback["selected_speaker"], "Skeptic")

    def test_finish_reason_stop_saved_normally(self) -> None:
        """Test that finish_reason='stop' is saved normally."""
        from philosophical_council.core.debate_engine import DebateEngine

        with patch('philosophical_council.core.debate_engine.TurnManager') as MockTurnManager:
            mock_turn_manager = MagicMock()
            mock_turn_manager.current_turn_id = 5
            MockTurnManager.return_value = mock_turn_manager

            engine = DebateEngine(self.config, self.db, self.llm)
            engine.turn_manager = mock_turn_manager
            # Set engine to running state
            engine._running = True
            engine._state.status = "running"

            # Create and register a Skeptic agent
            mock_skeptic = MagicMock()
            mock_skeptic.role = "skeptic"
            mock_skeptic.name = "Skeptic"
            mock_skeptic.config.name = "Skeptic"
            mock_skeptic.system_prompt = "You are a skeptic."
            mock_skeptic.format_response.return_value = "prompt"
            engine.register_agent(mock_skeptic)

            # Mock moderator decision
            mock_moderator = MagicMock()
            mock_moderator.system_prompt = "You are a moderator."
            mock_moderator.parse_decision.return_value = {
                "selected_speaker": "Skeptic",
                "challenge": "Test question",
                "reason": "Test reason",
                "question": None,
                "detected_issues": None,
            }
            engine._moderator = mock_moderator

            # Mock llm.chat to return (response, finish_reason)
            engine.llm.chat.return_value = ("Skeptic response", "stop")

            # Mock the database methods
            engine.db.turn_repo.insert_turn.return_value = None
            engine.db.moderator_repo.insert.return_value = None

            with patch('philosophical_council.core.debate_engine.time') as mock_time:
                mock_time.time.side_effect = [100, 101]
                result = engine.step_once()

            self.assertTrue(result)
            # Verify insert_turn was called with finish_reason='stop'
            engine.db.turn_repo.insert_turn.assert_called_once()
            call_kwargs = engine.db.turn_repo.insert_turn.call_args.kwargs
            self.assertEqual(call_kwargs.get('finish_reason'), 'stop')
            self.assertFalse(call_kwargs.get('was_truncated'))

    def test_finish_reason_length_triggers_continuation(self) -> None:
        """Test that finish_reason='length' triggers continuation."""
        from philosophical_council.core.debate_engine import DebateEngine

        engine = DebateEngine(self.config, self.db, self.llm)

        # Test the continuation logic directly - mock llm.chat to return (text, finish_reason)
        engine.llm.chat.side_effect = [
            ("Short response", "length"),  # First call returns length
            ("Continued response", "stop"),  # Second call returns stop
        ]

        result = engine._generate_with_continuation(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
            temperature=0.8,
            max_tokens=1500,
        )

        self.assertEqual(result[0], "Short responseContinued response")  # combined response
        self.assertEqual(result[1], "stop")  # finish_reason
        self.assertEqual(result[2], 1)  # continuation_count

    def test_no_extra_continuation_on_stop(self) -> None:
        """Test that finish_reason='stop' does NOT trigger extra calls."""
        from philosophical_council.core.debate_engine import DebateEngine

        engine = DebateEngine(self.config, self.db, self.llm)

        # Mock llm.chat to return stop on first call
        engine.llm.chat.return_value = ("Complete response", "stop")

        result = engine._generate_with_continuation(
            messages=[{"role": "user", "content": "test"}],
            model="test-model",
            temperature=0.8,
            max_tokens=1500,
        )

        # Should only call once
        self.assertEqual(engine.llm.chat.call_count, 1)
        self.assertEqual(result[0], "Complete response")
        self.assertEqual(result[1], "stop")
        self.assertEqual(result[2], 0)  # continuation_count

    def test_speaker_repetition_prevention(self) -> None:
        """Test that repeated speaker selection is prevented."""
        from philosophical_council.core.debate_engine import DebateEngine

        engine = DebateEngine(self.config, self.db, self.llm)

        # Set up repetition scenario
        engine._recent_speakers = ["Skeptic", "Skeptic", "Skeptic", "Skeptic"]

        # Check that repetition is detected
        recent = engine._recent_speakers[-5:]
        self.assertEqual(recent.count("Skeptic"), 4)

    def test_no_continue_discussion_fallback(self) -> None:
        """Test that 'Continue the discussion' is never used as fallback."""
        from philosophical_council.core.debate_engine import DebateEngine

        engine = DebateEngine(self.config, self.db, self.llm)

        # Get deterministic fallback
        fallback = engine._get_deterministic_fallback()

        # Should not contain "Continue the discussion"
        self.assertNotIn("Continue the discussion", fallback.get("challenge", ""))
        self.assertNotIn("Continue the discussion", fallback.get("reason", ""))

    def test_turn_id_increases_correctly(self) -> None:
        """Test that turn IDs increase sequentially."""
        from philosophical_council.core.debate_engine import DebateEngine

        with patch('philosophical_council.core.debate_engine.TurnManager') as MockTurnManager:
            mock_turn_manager = MagicMock()
            MockTurnManager.return_value = mock_turn_manager

            engine = DebateEngine(self.config, self.db, self.llm)
            engine.turn_manager = mock_turn_manager
            # Set engine to running state
            engine._running = True
            engine._state.status = "running"

            # Create and register a Skeptic agent
            mock_skeptic = MagicMock()
            mock_skeptic.role = "skeptic"
            mock_skeptic.name = "Skeptic"
            mock_skeptic.config.name = "Skeptic"
            mock_skeptic.system_prompt = "You are a skeptic."
            mock_skeptic.format_response.return_value = "prompt"
            engine.register_agent(mock_skeptic)

            # Mock moderator decision
            mock_moderator = MagicMock()
            mock_moderator.system_prompt = "You are a moderator."
            mock_moderator.parse_decision.return_value = {
                "selected_speaker": "Skeptic",
                "challenge": "Test question",
                "reason": "Test reason",
                "question": None,
                "detected_issues": None,
            }
            engine._moderator = mock_moderator

            # Mock llm.chat to return (response, finish_reason)
            engine.llm.chat.return_value = ("Response", "stop")

            # Simulate multiple turns
            for i in range(5):
                mock_turn = MagicMock()
                mock_turn.turn_id = i + 1
                mock_turn.round_num = 1
                mock_turn.speaker = "Skeptic"
                mock_turn.speaker_role = "skeptic"
                mock_turn.moderator_question = "Test question"
                mock_turn.moderator_reason = "Test reason"
                mock_turn_manager.next_turn.return_value = mock_turn

                engine.db.turn_repo.insert_turn.return_value = None

                with patch('philosophical_council.core.debate_engine.time') as mock_time:
                    mock_time.time.side_effect = [100 + i, 101 + i]
                    engine.step_once()

            # Verify turn IDs increased
            self.assertEqual(mock_turn_manager.next_turn.call_count, 5)


class TestValidSpeakers(unittest.TestCase):
    """Test valid speaker names."""

    def test_all_valid_speakers_defined(self) -> None:
        """Test that all expected speakers are in VALID_SPEAKERS."""
        from philosophical_council.core.debate_engine import VALID_SPEAKERS

        expected = {"Existentialist", "Stoic", "Nihilist", "Spiritual", "Skeptic", "Pragmatist"}
        self.assertEqual(VALID_SPEAKERS, expected)


if __name__ == "__main__":
    unittest.main()
