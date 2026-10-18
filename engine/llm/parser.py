"""
Parse LLM responses into candidate heuristics.
"""

import re
import ast
from typing import Optional, List, Tuple

from .models import LLMResponse, ParseResult


def extract_code_blocks(text: str) -> List[str]:
    """
    Extract code from markdown fenced blocks or plain text.
    
    Looks for ```python ... ``` blocks, or treats entire text as code.
    
    Args:
        text: Raw LLM response text
        
    Returns:
        List of extracted code blocks
    """
    # Try to find fenced code blocks (```python or ``` or ```py)
    fenced_pattern = r'```(?:python|py)?\s*\n(.*?)```'
    matches = re.findall(fenced_pattern, text, re.DOTALL)
    
    if matches:
        return [match.strip() for match in matches]
    
    # No fenced blocks - treat entire text as code
    # Remove common markdown artifacts
    cleaned = text.strip()
    
    # Remove leading/trailing backticks without proper fences
    cleaned = re.sub(r'^`+|`+$', '', cleaned).strip()
    
    return [cleaned] if cleaned else []


def extract_function_name(source_code: str) -> Optional[str]:
    """
    Extract the main function name from source code using AST.
    
    Args:
        source_code: Python source code
        
    Returns:
        Function name if found, None otherwise
    """
    try:
        tree = ast.parse(source_code)
        
        # Find all function definitions
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        
        # Prefer "score_candidates" if present
        if "score_candidates" in functions:
            return "score_candidates"
        
        # Otherwise return the first function found
        if functions:
            return functions[0]
        
        return None
    except SyntaxError:
        return None


def validate_function_signature(source_code: str, function_name: str) -> Tuple[bool, List[str]]:
    """
    Validate that the function has the expected signature.
    
    Expected: def score_candidates(context): or def score_candidates(context, **kwargs):
    
    Args:
        source_code: Python source code
        function_name: Name of the function to validate
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    try:
        tree = ast.parse(source_code)
        
        # Find the target function
        target_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                target_func = node
                break
        
        if not target_func:
            errors.append(f"Function '{function_name}' not found in source code")
            return False, errors
        
        # Check arguments
        args = target_func.args
        
        # Must have at least one positional argument (context)
        if len(args.args) < 1:
            errors.append(f"Function must accept at least one argument (context)")
            return False, errors
        
        # First argument should be named 'context' (warning only)
        if args.args[0].arg != "context":
            # This is just a warning - we'll accept it
            pass
        
        return True, errors
        
    except SyntaxError as e:
        errors.append(f"Syntax error: {e}")
        return False, errors


def parse_llm_response(response: LLMResponse) -> ParseResult:
    """
    Parse an LLM response into a candidate heuristic.
    
    Steps:
    1. Extract code blocks from response
    2. Parse and validate syntax
    3. Detect function name
    4. Validate function signature
    5. Check for prohibited constructs (basic check)
    
    Args:
        response: LLM response to parse
        
    Returns:
        ParseResult with extracted source code or errors
    """
    errors = []
    warnings = []
    
    # Extract code blocks
    code_blocks = extract_code_blocks(response.raw_content)
    
    if not code_blocks:
        errors.append("No code found in response")
        return ParseResult(
            success=False,
            errors=errors,
            warnings=warnings
        )
    
    if len(code_blocks) > 1:
        warnings.append(f"Multiple code blocks found ({len(code_blocks)}), using the first")
    
    source_code = code_blocks[0]
    
    # Basic validation: check for obvious prohibited patterns
    prohibited_patterns = [
        (r'\bimport\b', "Contains 'import' statement"),
        (r'\bfrom\b.*\bimport\b', "Contains 'from...import' statement"),
        (r'\bopen\s*\(', "Contains 'open()' call"),
        (r'\bexec\s*\(', "Contains 'exec()' call"),
        (r'\beval\s*\(', "Contains 'eval()' call"),
    ]
    
    for pattern, message in prohibited_patterns:
        if re.search(pattern, source_code):
            errors.append(message)
    
    # Check basic syntax
    try:
        ast.parse(source_code)
    except SyntaxError as e:
        errors.append(f"Syntax error at line {e.lineno}: {e.msg}")
        return ParseResult(
            success=False,
            source_code=source_code,
            errors=errors,
            warnings=warnings
        )
    
    # Extract function name
    function_name = extract_function_name(source_code)
    
    if not function_name:
        errors.append("No function definition found in code")
        return ParseResult(
            success=False,
            source_code=source_code,
            errors=errors,
            warnings=warnings
        )
    
    if function_name != "score_candidates":
        warnings.append(f"Function named '{function_name}' (expected 'score_candidates')")
    
    # Validate signature
    is_valid, sig_errors = validate_function_signature(source_code, function_name)
    errors.extend(sig_errors)
    
    # Return result
    if errors:
        return ParseResult(
            success=False,
            source_code=source_code,
            function_name=function_name,
            errors=errors,
            warnings=warnings
        )
    
    return ParseResult(
        success=True,
        source_code=source_code,
        function_name=function_name,
        errors=[],
        warnings=warnings
    )
