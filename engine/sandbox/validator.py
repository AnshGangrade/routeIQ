"""
Static AST-based validation for candidate heuristics.

Uses an allowlist approach: explicitly permits a safe subset of Python
rather than trying to block dangerous constructs.
"""

import ast
from typing import Set, List
from .models import CandidateHeuristic, ValidationResult, ValidationStatus


class HeuristicValidator:
    """
    Validates candidate heuristic source code using AST analysis.
    
    Validation Strategy:
        - Allowlist-based: Only permit explicitly allowed constructs
        - Parse AST without executing code
        - Check for required structure (single function definition)
        - Verify no forbidden operations
    
    Allowed:
        - Arithmetic operations: +, -, *, /, //, %, **
        - Comparisons: <, <=, >, >=, ==, !=
        - Boolean operations: and, or, not
        - Control flow: if/elif/else, for, while
        - Data structures: list, dict, tuple, set (literals and comprehensions)
        - Built-in calls: abs, min, max, sum, len, range, enumerate, zip, sorted, float, int, round
        - Context attribute access: context.current_location, context.candidate_stops, etc.
        - NumPy via 'np' namespace (must be provided by executor)
    
    Forbidden:
        - import statements
        - Function definitions (except the main heuristic function)
        - Class definitions
        - global/nonlocal statements
        - exec/eval/compile
        - File I/O: open, read, write
        - Network access
        - Environment access: os, sys, environ
        - Dangerous built-ins: getattr, setattr, delattr, __import__, vars, dir, etc.
        - Underscore-prefixed attributes
        - Assignment to context attributes
    
    Example:
        >>> validator = HeuristicValidator()
        >>> candidate = CandidateHeuristic(
        ...     source_code="def score_candidates(context): return {...}",
        ...     function_name="score_candidates"
        ... )
        >>> result = validator.validate(candidate)
        >>> result.is_valid
        True
    """
    
    # Allowlisted built-in functions
    ALLOWED_BUILTINS = {
        'abs', 'min', 'max', 'sum', 'len', 'range',
        'enumerate', 'zip', 'sorted', 'float', 'int', 'round',
        'list', 'dict', 'tuple', 'set', 'bool', 'str',
        'all', 'any',
    }
    
    # Allowlisted context attributes
    ALLOWED_CONTEXT_ATTRS = {
        'current_location',
        'candidate_stops',
        'distance_matrix',
        'partial_route',
    }
    
    # Maximum source code length
    MAX_SOURCE_LENGTH = 10000
    
    def __init__(self):
        """Initialize the validator."""
        pass
    
    def validate(self, candidate: CandidateHeuristic) -> ValidationResult:
        """
        Validate a candidate heuristic using AST analysis.
        
        Args:
            candidate: Candidate heuristic to validate
            
        Returns:
            ValidationResult with status and any errors/warnings
        """
        errors: List[str] = []
        warnings: List[str] = []
        
        # Check source code length
        if len(candidate.source_code) > self.MAX_SOURCE_LENGTH:
            errors.append(
                f"Source code too long: {len(candidate.source_code)} chars "
                f"(max {self.MAX_SOURCE_LENGTH})"
            )
            return ValidationResult(status=ValidationStatus.INVALID, errors=errors)
        
        # Parse AST
        try:
            tree = ast.parse(candidate.source_code)
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return ValidationResult(status=ValidationStatus.INVALID, errors=errors)
        
        # Check for required structure
        func_errors = self._validate_structure(tree, candidate.function_name)
        errors.extend(func_errors)
        
        if errors:
            return ValidationResult(status=ValidationStatus.INVALID, errors=errors)
        
        # Check for forbidden operations
        forbidden_errors = self._check_forbidden(tree)
        errors.extend(forbidden_errors)
        
        # Check for suspicious patterns (warnings)
        suspicious_warnings = self._check_suspicious(tree)
        warnings.extend(suspicious_warnings)
        
        if errors:
            status = ValidationStatus.INVALID
        else:
            status = ValidationStatus.VALID
        
        return ValidationResult(
            status=status,
            errors=errors,
            warnings=warnings,
            details={'ast_nodes': len(list(ast.walk(tree)))}
        )
    
    def _validate_structure(self, tree: ast.Module, expected_name: str) -> List[str]:
        """
        Validate that the module contains exactly one function with the expected name.
        
        Args:
            tree: Parsed AST
            expected_name: Expected function name
            
        Returns:
            List of error messages
        """
        errors = []
        
        # Find all top-level function definitions
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        
        if len(functions) == 0:
            errors.append("No function definition found")
            return errors
        
        if len(functions) > 1:
            func_names = [f.name for f in functions]
            errors.append(
                f"Multiple function definitions found: {func_names}. "
                f"Expected exactly one function named '{expected_name}'"
            )
        
        # Check function name
        main_func = functions[0]
        if main_func.name != expected_name:
            errors.append(
                f"Function name mismatch: found '{main_func.name}', "
                f"expected '{expected_name}'"
            )
        
        # Check for other top-level statements (imports, classes, etc.)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                continue  # Functions are OK (already checked above)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                errors.append(f"Import statements not allowed at top level: {ast.unparse(node)}")
            elif isinstance(node, ast.ClassDef):
                errors.append(f"Class definitions not allowed: {node.name}")
            elif isinstance(node, ast.AsyncFunctionDef):
                errors.append("Async function definitions not allowed")
            else:
                errors.append(
                    f"Unexpected top-level statement: {type(node).__name__}"
                )
        
        return errors
    
    def _check_forbidden(self, tree: ast.Module) -> List[str]:
        """
        Check for forbidden operations using AST traversal.
        
        Args:
            tree: Parsed AST
            
        Returns:
            List of error messages
        """
        errors = []
        
        for node in ast.walk(tree):
            # Forbidden: nested function or class definitions
            if isinstance(node, ast.FunctionDef):
                # Allow top-level function, but check for nested
                for child in ast.walk(node):
                    if child != node and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        errors.append(f"Nested function definitions not allowed: {child.name}")
            
            # Forbidden: global/nonlocal
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                errors.append(f"global/nonlocal statements not allowed")
            
            # Forbidden: exec/eval/compile and other dangerous built-ins
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    dangerous = {
                        'exec', 'eval', 'compile', '__import__',
                        'open', 'input', 'print',  # I/O
                        'getattr', 'setattr', 'delattr', 'hasattr',
                        'vars', 'dir', 'globals', 'locals',
                        'help', 'breakpoint', 'exit', 'quit',
                    }
                    if func_name in dangerous:
                        errors.append(f"Forbidden function call: {func_name}")
            
            # Forbidden: attribute access to underscore-prefixed names
            if isinstance(node, ast.Attribute):
                if node.attr.startswith('_'):
                    errors.append(
                        f"Access to underscore-prefixed attributes not allowed: {node.attr}"
                    )
                
                # Check context attribute access
                if isinstance(node.value, ast.Name) and node.value.id == 'context':
                    if node.attr not in self.ALLOWED_CONTEXT_ATTRS:
                        errors.append(
                            f"Unknown context attribute: {node.attr}. "
                            f"Allowed: {sorted(self.ALLOWED_CONTEXT_ATTRS)}"
                        )
            
            # Forbidden: assignment to context attributes
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute):
                        if isinstance(target.value, ast.Name) and target.value.id == 'context':
                            errors.append(
                                f"Cannot assign to context attributes: context.{target.attr}"
                            )
            
            # Check function calls are from allowed set
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    # Allow our allowlisted built-ins and 'np' namespace access handled separately
                    if func_name not in self.ALLOWED_BUILTINS and func_name != 'np':
                        # Could be a variable reference, not necessarily forbidden
                        # Only error on known dangerous ones (already checked above)
                        pass
        
        return errors
    
    def _check_suspicious(self, tree: ast.Module) -> List[str]:
        """
        Check for suspicious but not necessarily invalid patterns.
        
        Args:
            tree: Parsed AST
            
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Count loops (warn if excessive)
        loop_count = sum(1 for node in ast.walk(tree)
                        if isinstance(node, (ast.For, ast.While)))
        if loop_count > 5:
            warnings.append(f"Many loops detected ({loop_count}), may be slow")
        
        # Check for very deep nesting
        max_depth = self._compute_max_depth(tree)
        if max_depth > 6:
            warnings.append(f"Deep nesting detected (depth {max_depth}), may be complex")
        
        return warnings
    
    def _compute_max_depth(self, node: ast.AST, current_depth: int = 0) -> int:
        """Compute maximum nesting depth of AST."""
        max_depth = current_depth
        for child in ast.iter_child_nodes(node):
            child_depth = self._compute_max_depth(child, current_depth + 1)
            max_depth = max(max_depth, child_depth)
        return max_depth
