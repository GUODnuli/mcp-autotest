# -*- coding: utf-8 -*-
"""
API Testing skill tools package.

This package contains domain-specific tools for API testing:
- doc_parser: Document parsing and API specification extraction
- case_generator: Test case generation (positive, negative, security)
- test_executor: API test execution and validation
- report_tools: Report generation and failure diagnosis

Tools are dynamically loaded by the skill system based on SKILL.md configuration.
"""

from .doc_parser import read_document, extract_api_spec, validate_api_spec
from .case_generator import (
    generate_positive_cases,
    generate_negative_cases,
    generate_security_cases
)
from .test_executor import execute_api_test, validate_response, capture_metrics
from .report_tools import generate_test_report, diagnose_failures, suggest_improvements

__all__ = [
    # Document Parser
    "read_document",
    "extract_api_spec",
    "validate_api_spec",
    # Case Generator
    "generate_positive_cases",
    "generate_negative_cases",
    "generate_security_cases",
    # Test Executor
    "execute_api_test",
    "validate_response",
    "capture_metrics",
    # Report Tools
    "generate_test_report",
    "diagnose_failures",
    "suggest_improvements",
]
