---
name: api-testing
description: >
  Specialized in API testing and quality assurance. Parses API documentation
  (OpenAPI/Swagger, Postman, HAR, Word) to extract interface specifications,
  generates comprehensive test cases (positive, negative, boundary, security),
  executes API tests, and produces test reports with failure diagnosis.
  Use this skill when users ask about API testing, test case generation,
  test execution, or test report analysis.
version: 1.0.0
tools_dir: tools
allowed_tools:
  - extract_api_spec
  - validate_api_spec
  - generate_positive_cases
  - generate_negative_cases
  - generate_security_cases
  - apply_business_rules
  - execute_api_test
  - validate_response
  - capture_metrics
  - generate_test_report
  - diagnose_failures
  - suggest_improvements
tags: [api, testing, quality-assurance, test-generation, test-execution, report]
---

# API Testing Specialist

## Overview

End-to-end API testing: document parsing → spec extraction → test case generation → execution → reporting.

## Prerequisites

- Uploaded API documentation or specification files
- Target API endpoint accessible for test execution
- For file operations: retrieve file paths via `list_uploaded_files` before accessing files

## Workflow

1. **Access Files**: Extract `user_id`/`conversation_id` from `[SYSTEM CONTEXT]` → `list_uploaded_files` → `safe_view_text_file`
2. **Parse Documentation**: `read_document` → `extract_api_spec` → `validate_api_spec`
3. **Generate Test Cases**:
   - `generate_positive_cases` — Normal input, typical business scenarios
   - `generate_negative_cases` — Illegal input, missing parameters, type errors
   - `generate_security_cases` — SQL injection, XSS, authorization bypass
4. **Execute Tests**: `execute_api_test` → `validate_response` → `capture_metrics`
5. **Report & Diagnose**: `generate_test_report` → `diagnose_failures` → `suggest_improvements`

## Interface Specification Schema

Extracted API interfaces must follow this structure:

```json
{
  "interfaces": [{
    "name": "string",
    "path": "/api/loans/{id}",
    "method": "GET|POST|PUT|DELETE|PATCH",
    "description": "string",
    "parameters": [{
      "name": "string",
      "in": "path|query|header|body",
      "type": "string|integer|number|boolean|array|object",
      "required": true,
      "description": "string"
    }],
    "request_body": { "content_type": "string", "schema": {}, "example": {} },
    "responses": { "200": { "description": "string", "schema": {} } }
  }]
}
```

## Test Case Schema

```json
{
  "testcases": [{
    "name": "string",
    "description": "string",
    "strategy": "positive|negative|boundary|security",
    "priority": "high|medium|low",
    "request": {
      "method": "POST",
      "url": "/api/path",
      "headers": {},
      "body": {},
      "timeout": 30
    },
    "assertions": [{
      "type": "status_code|response_time|json_path|schema",
      "target": "string",
      "operator": "equals|contains|greater_than|exists",
      "expected": "any"
    }]
  }]
}
```

## Best Practices

- Follow RESTful conventions for interface extraction
- Keep parameter naming style consistent (camelCase or snake_case)
- Generate at least 3-5 test cases per interface
- Assertions should be precise and verifiable
- Test data should be realistic and close to business scenarios
