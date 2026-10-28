"""Tests for coding_generator tool."""
import pytest
from library.tools.coding import coding_generator, _extract_function_name


class TestCodingGenerator:
    """Test the code generator with various task descriptions."""

    def test_fibonacci_detection(self):
        result = coding_generator(description="Write code to solve this fibonacci problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "fibonacci" in result["function_name"]
        assert "def fibonacci" in result["source"]

    def test_factorial_detection(self):
        result = coding_generator(description="Write code to solve this factorial problem (difficulty 3)", difficulty=3)
        assert result["valid"] is True
        assert "factorial" in result["function_name"]
        assert "def factorial" in result["source"]

    def test_gcd_detection(self):
        result = coding_generator(description="Write code to solve this gcd problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "gcd" in result["function_name"]
        assert "def gcd" in result["source"]

    def test_lcm_detection(self):
        result = coding_generator(description="Write code to solve this lcm problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "lcm" in result["function_name"]
        assert "def lcm" in result["source"]

    def test_prime_detection(self):
        result = coding_generator(description="Write code to solve this prime problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "prime" in result["function_name"]
        assert "def is_prime" in result["source"]

    def test_sort_detection(self):
        result = coding_generator(description="Write code to solve this sort problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "sort_array" in result["function_name"]
        assert "def sort_array" in result["source"]

    def test_search_detection(self):
        result = coding_generator(description="Write code to solve this search problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "binary_search" in result["function_name"]
        assert "def binary_search" in result["source"]

    def test_sum_detection(self):
        result = coding_generator(description="Write code to solve this sum problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "sum_numbers" in result["function_name"]
        assert "def sum_numbers" in result["source"]

    def test_average_detection(self):
        result = coding_generator(description="Write code to solve this average problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "calculate_average" in result["function_name"]
        assert "def calculate_average" in result["source"]

    def test_reverse_detection(self):
        result = coding_generator(description="Write code to solve this reverse problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "reverse_string" in result["function_name"]
        assert "def reverse_string" in result["source"]

    def test_palindrome_detection(self):
        result = coding_generator(description="Write code to solve this palindrome problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "is_palindrome" in result["function_name"]
        assert "def is_palindrome" in result["source"]

    def test_default_function_name(self):
        result = coding_generator(description="Write code to solve this problem (difficulty 2)", difficulty=2)
        assert result["valid"] is True
        assert "solution" in result["function_name"]

    def test_custom_function_name(self):
        result = coding_generator(description="Write code to solve this fibonacci problem", function_name="my_fib")
        assert result["valid"] is True
        assert "def my_fib" in result["source"]

    def test_empty_description(self):
        result = coding_generator(description="", difficulty=2)
        assert result["valid"] is False
        assert "No description provided" in result["error"]

    def test_test_cases_preserved(self):
        result = coding_generator(
            description="Write code to solve this fibonacci problem",
            test_cases="assert fibonacci(5) == [0, 1, 1, 2, 3]"
        )
        assert "test_cases" in result
        assert "fibonacci(5)" in result["test_cases"]

    def test_extract_function_name_from_def(self):
        name = _extract_function_name("def my_function(): pass")
        assert name == "my_function"

    def test_extract_function_name_from_named(self):
        name = _extract_function_name("function named my_fibonacci: pass")
        assert name == "my_fibonacci"


class TestCodingGeneratorIntegration:
    """Test that coding_generator works with the experiment runner."""

    def test_runner_coding_task_detection(self):
        from library.tools.detection import detect_tool
        det = detect_tool("Write code to solve this fibonacci problem (difficulty 2)")
        assert det is not None
        assert "coding_generator" in det["tool_name"]

    def test_runner_returns_source_code(self):
        result = coding_generator(
            description="Write code to solve this fibonacci problem (difficulty 2)",
            difficulty=2
        )
        # Simulate what the runner does for coding tasks
        if isinstance(result, dict):
            answer = result.get("source", "")
        assert "def" in answer
        assert "fibonacci" in answer
