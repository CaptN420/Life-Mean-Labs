"""Tests for moderator flow, turn numbering, and context propagation."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch


class TestModeratorFlow(unittest.TestCase):
    """Test the complete moderator decision flow."""

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

    def test_moderator_sees_latest_argument(self) -> None:
        """Test that the moderator prompt contains the latest argument."""
        from philosophical_council.core.debate_engine import DebateEngine
        from philosophical_council.agents.moderator import ModeratorAgent

        with patch('philosophical_council.core.debate_engine.TurnManager') as MockTurnManager:
            mock_turn_manager = MagicMock()
            mock_turn = MagicMock()
            mock_turn.turn_id = 1
            mock_turn.response = "Virtue alone can ground meaning because it is self-sufficient."
            mock_turn.speaker = "Stoic"
            mock_turn_manager.get_all_turns.return_value = [mock_turn]
            mock_turn_manager.turn_count = 1
            MockTurnManager.return_value = mock_turn_manager

            engine = DebateEngine(self.config, self.db, self.llm)
            engine.turn_manager = mock_turn_manager
            engine._recent_speakers = ["Stoic"]

            # Create a real moderator
            moderator = ModeratorAgent()
            engine.register_moderator(moderator)

            # Mock llm.chat to return valid JSON
            valid_json = json.dumps({
                "selected_speaker": "Pragmatist",
                "challenge": "Test challenge",
                "reason": "Test reason",
                "question": None,
                "detected_issues": None,
            })
            engine.llm.chat.return_value = (valid_json, "stop")

            # Call the method
            decision = engine._get_moderator_decision()

            # Verify the LLM was called with the context containing the latest argument
            call_args = engine.llm.chat.call_args
            messages = call_args.kwargs.get('messages', [])
            user_content = messages[1].get('content', '') if len(messages) > 1 else ''

            # The prompt should contain the debate topic and reference to recent context
            self.assertIn("What is the meaning of life?", user_content)
            self.assertIn("Stoic", user_content)

    def test_turn_numbers_are_sequential(self) -> None:
        """Test that turn numbers are 1, 2, 3... not 0, 1, 2."""
        from philosophical_council.core.turn_manager import TurnManager

        tm = TurnManager()

        # First turn should be turn_id=1, round_num=1
        turn1 = tm.next_turn(speaker="Stoic", speaker_role="stoic")
        self.assertEqual(turn1.turn_id, 1)
        self.assertEqual(turn1.round_num, 1)

        # Second turn should be turn_id=2, round_num=1
        turn2 = tm.next_turn(speaker="Pragmatist", speaker_role="pragmatist")
        self.assertEqual(turn2.turn_id, 2)
        self.assertEqual(turn2.round_num, 1)

        # Fifth turn should be round 2 (5 % 5 == 0 triggers increment)
        for i in range(3, 6):
            tm.next_turn(speaker="Test", speaker_role="test")
        turn5 = tm.get_turn(5)
        self.assertEqual(turn5.round_num, 2)

        # Sixth turn should be round 2
        turn6 = tm.next_turn(speaker="Test", speaker_role="test")
        self.assertEqual(turn6.round_num, 2)

    def test_fallback_produces_specific_challenge(self) -> None:
        """Test that fallback challenge references actual debate context."""
        from philosophical_council.core.debate_engine import DebateEngine

        with patch('philosophical_council.core.debate_engine.TurnManager') as MockTurnManager:
            mock_turn_manager = MagicMock()
            mock_turn = MagicMock()
            mock_turn.turn_id = 1
            mock_turn.response = "Meaning is a human construct that we impose on an indifferent universe."
            mock_turn.speaker = "Nihilist"
            mock_turn_manager.get_all_turns.return_value = [mock_turn]
            mock_turn_manager.turn_count = 1
            MockTurnManager.return_value = mock_turn_manager

            engine = DebateEngine(self.config, self.db, self.llm)
            engine.turn_manager = mock_turn_manager
            engine._recent_speakers = ["Nihilist"]

            fallback = engine._get_deterministic_fallback()

            # Fallback should reference the actual speaker and their argument
            self.assertIn("Nihilist", fallback["challenge"])
            self.assertNotEqual(fallback["selected_speaker"], "Nihilist")  # Different speaker

    def test_fallback_no_generic_phrases(self) -> None:
        """Test that fallback doesn't use generic phrases."""
        from philosophical_council.core.debate_engine import DebateEngine

        engine = DebateEngine(self.config, self.db, self.llm)
        engine._recent_speakers = ["Skeptic"]

        fallback = engine._get_deterministic_fallback()

        # Should not contain these generic phrases
        generic_phrases = [
            "Respond to the most recent argument",
            "Provide a fresh perspective",
            "Continue the discussion",
            "Address the topic",
        ]

        for phrase in generic_phrases:
            self.assertNotIn(phrase, fallback["challenge"])


class TestTurnNumbering(unittest.TestCase):
    """Test turn numbering is correct throughout."""

    def test_ui_shows_turn_not_round(self) -> None:
        """Test that UI displays TURN N not ROUND N."""
        # Verify the source code contains the fix
        import os
        app_path = os.path.join(
            os.path.dirname(__file__), '..', 'ui', 'app.py'
        )
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Should use turn_id for display, not round_num
        self.assertIn('turn_id', content)
        self.assertIn('TURN', content)
        # Should NOT show ROUND in the transcript display
        self.assertNotIn('ROUND {update.turn.round_num}', content)


class TestModeratorParser(unittest.TestCase):
    """Test moderator parser robustness."""

    def test_parser_handles_valid_json(self) -> None:
        """Test that valid JSON is parsed correctly."""
        from philosophical_council.agents.moderator import ModeratorAgent

        moderator = ModeratorAgent()
        raw = '{"selected_speaker": "Stoic", "challenge": "Test challenge", "reason": "Test reason"}'

        decision = moderator.parse_decision(raw)

        self.assertEqual(decision["selected_speaker"], "Stoic")
        self.assertEqual(decision["challenge"], "Test challenge")

    def test_parser_handles_markdown_fences(self) -> None:
        """Test that markdown code fences are handled."""
        from philosophical_council.agents.moderator import ModeratorAgent

        moderator = ModeratorAgent()
        raw = '```json\n{"selected_speaker": "Stoic", "challenge": "Test", "reason": "Reason"}\n```'

        decision = moderator.parse_decision(raw)

        self.assertEqual(decision["selected_speaker"], "Stoic")

    def test_parser_handles_whitespace(self) -> None:
        """Test that whitespace is handled."""
        from philosophical_council.agents.moderator import ModeratorAgent

        moderator = ModeratorAgent()
        raw = '  \n  {"selected_speaker": "Stoic", "challenge": "Test", "reason": "Reason"}  \n  '

        decision = moderator.parse_decision(raw)

        self.assertEqual(decision["selected_speaker"], "Stoic")


if __name__ == "__main__":
    unittest.main()
