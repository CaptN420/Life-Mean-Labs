"""
Prompts module — Local prompt collection.

Provides CRUD operations for prompts stored in Studio.
Prompts are configuration data only and do not affect execution permissions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class Prompt:
    """A prompt entry in the local collection."""
    id: str = ""
    name: str = ""
    category: str = "general"
    content: str = ""
    variables: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    
    def render(self, overrides: Optional[Dict[str, Any]] = None) -> str:
        """
        Render the prompt with variables substituted.
        
        Args:
            overrides: Additional variable values to override defaults
            
        Returns:
            Rendered prompt string
        """
        result = self.content
        
        # Apply overrides first, then defaults
        all_vars = {**self.variables, **(overrides or {})}
        
        for key, value in all_vars.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value))
        
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "content": self.content,
            "variables": self.variables,
            "version": self.version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Prompt":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            category=data.get("category", "general"),
            content=data.get("content", ""),
            variables=data.get("variables", {}),
            version=data.get("version", 1),
        )


# Built-in prompt templates by category
DEFAULT_PROMPTS = {
    "coding": [
        Prompt(
            name="Python Function Generator",
            category="coding",
            content="""You are a Python developer. Generate a function with the following specification:

Function: {{{function_name}}}
Purpose: {{{purpose}}}
Parameters: {{{parameters}}}
Returns: {{{returns}}}

Requirements:
- Follow PEP 8 style guidelines
- Include type hints
- Add docstring with description, parameters, and returns
- Handle edge cases

Output ONLY the function code between triple backticks.""",
            variables={
                "function_name": "calculate_statistics",
                "purpose": "Calculate basic statistics from a list of numbers",
                "parameters": "data: List[float]",
                "returns": "Dict[str, float]",
            },
        ),
        Prompt(
            name="Code Review",
            category="coding",
            content="""Review the following code for:
- Correctness
- Performance
- Security
- Style

Code to review:
```python
{{{code}}}
```

Provide specific suggestions for improvement.""",
            variables={"code": ""},
        ),
    ],
    "security": [
        Prompt(
            name="Security Audit",
            category="security",
            content="""You are a security auditor. Review the following code for security vulnerabilities:

{{{code}}}

Check for:
- Injection vulnerabilities
- Authentication issues
- Data exposure
- Input validation

Provide a severity rating (Critical/High/Medium/Low) for each finding.""",
            variables={"code": ""},
        ),
    ],
    "debug": [
        Prompt(
            name="Debug Assistant",
            category="debug",
            content="""You are a debugging assistant. Analyze the following error and suggest fixes:

Error: {{{error_message}}}
Context: {{{context}}}
Code:
```python
{{{code}}}
```

Provide:
1. Root cause analysis
2. Specific fix suggestion
3. Prevention measures""",
            variables={
                "error_message": "",
                "context": "",
                "code": "",
            },
        ),
    ],
    "audit": [
        Prompt(
            name="Audit Report",
            category="audit",
            content="""Generate an audit report for the following:

Scope: {{{scope}}}
Findings: {{{findings}}}
Recommendations: {{{recommendations}}}

Format the report with clear sections and actionable items.""",
            variables={
                "scope": "",
                "findings": "",
                "recommendations": "",
            },
        ),
    ],
    "refactoring": [
        Prompt(
            name="Refactoring Plan",
            category="refactoring",
            content="""Create a refactoring plan for the following code:

{{{code}}}

Consider:
- Code organization
- Performance improvements
- Maintainability
- Test coverage

Output a step-by-step plan.""",
            variables={"code": ""},
        ),
    ],
    "planning": [
        Prompt(
            name="Project Planner",
            category="planning",
            content="""Plan the implementation of the following project:

Project: {{{project_name}}}
Requirements: {{{requirements}}}
Constraints: {{{constraints}}}

Output:
1. File structure
2. Key components
3. API contracts
4. Test strategy""",
            variables={
                "project_name": "",
                "requirements": "",
                "constraints": "",
            },
        ),
    ],
    "testing": [
        Prompt(
            name="Test Generator",
            category="testing",
            content="""Generate comprehensive tests for the following function:

Function: {{{function_name}}}
Implementation: {{{code}}}

Include:
- Unit tests
- Edge cases
- Error handling
- Performance tests (if applicable)""",
            variables={
                "function_name": "",
                "code": "",
            },
        ),
    ],
}
