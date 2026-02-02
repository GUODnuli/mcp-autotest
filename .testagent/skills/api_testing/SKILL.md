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
allowed_tools:
  - read_document
  - extract_api_spec
  - validate_api_spec
  - generate_positive_cases
  - generate_negative_cases
  - generate_security_cases
  - execute_api_test
  - validate_response
  - capture_metrics
  - generate_test_report
  - diagnose_failures
  - suggest_improvements
  - list_uploaded_files
  - safe_view_text_file
  - safe_write_text_file
tags: [api, testing, quality-assurance, test-generation, test-execution, report]
---

# API Testing Specialist

## Overview

This skill provides end-to-end API testing capabilities:

- **Document Parsing**: Parse multi-format API documentation (OpenAPI/Swagger, Postman, HAR, Word) and extract structured interface specifications.
- **Test Case Generation**: Automatically generate comprehensive test cases covering positive, negative, boundary, and security scenarios.
- **Test Execution**: Execute API tests against target endpoints, validate responses, and capture performance metrics.
- **Reporting & Diagnosis**: Generate test reports, diagnose failures, and suggest improvements.

## Prerequisites

- Uploaded API documentation or specification files
- Target API endpoint accessible for test execution
- For file operations: retrieve file paths via `list_uploaded_files` before accessing files

## Workflow

### Step 1: Access Uploaded Files

1. Extract `user_id` and `conversation_id` from the `[SYSTEM CONTEXT]` block
2. Call `list_uploaded_files(user_id, conversation_id)` to get correct file paths
3. Use `safe_view_text_file` with the returned paths to read file contents

### Step 2: Parse Documentation

1. Use `read_document` to parse the uploaded API documentation
2. Use `extract_api_spec` to extract structured interface specifications
3. Use `validate_api_spec` to verify the extracted spec is complete and valid

### Step 3: Generate Test Cases

Based on the extracted API spec, generate test cases using appropriate strategies:

- `generate_positive_cases` — Normal input, typical business scenarios
- `generate_negative_cases` — Illegal input, missing parameters, type errors, business rule violations
- `generate_security_cases` — SQL injection, XSS, authorization bypass, sensitive data leakage

### Step 4: Execute Tests

1. Use `execute_api_test` to run the generated test cases
2. Use `validate_response` to check responses against assertions
3. Use `capture_metrics` to collect performance data

### Step 5: Report & Diagnose

1. Use `generate_test_report` to produce a structured test report
2. Use `diagnose_failures` to analyze failed test cases
3. Use `suggest_improvements` to recommend fixes

## Interface Specification Schema

When extracting API interfaces from documents, output must follow this JSON schema:

```json
{
  "interfaces": [
    {
      "name": "string (unique identifier)",
      "path": "string (e.g. /api/loans/{id})",
      "method": "GET | POST | PUT | DELETE | PATCH",
      "description": "string",
      "tags": ["string"],
      "parameters": [
        {
          "name": "string",
          "in": "path | query | header | body",
          "type": "string | integer | number | boolean | array | object",
          "required": true,
          "description": "string",
          "enum": [],
          "format": "string",
          "minimum": 0,
          "maximum": 0,
          "minLength": 0,
          "maxLength": 0
        }
      ],
      "request_body": {
        "content_type": "application/json | application/x-www-form-urlencoded | multipart/form-data",
        "schema": {},
        "example": {}
      },
      "responses": {
        "200": { "description": "string", "schema": {}, "example": {} },
        "400": { "description": "string", "schema": {} }
      }
    }
  ]
}
```

## Test Case Schema

Generated test cases must follow this JSON schema:

```json
{
  "testcases": [
    {
      "name": "string",
      "description": "string",
      "strategy": "positive | negative | boundary | security | performance",
      "priority": "high | medium | low",
      "tags": ["string"],
      "request": {
        "method": "GET | POST | PUT | DELETE | PATCH",
        "url": "string (full URL or path)",
        "headers": { "key": "value" },
        "params": { "key": "value" },
        "body": {},
        "timeout": 30
      },
      "assertions": [
        {
          "type": "status_code | response_time | header | body | json_path | schema",
          "target": "string (JSONPath, header name, etc.)",
          "operator": "equals | not_equals | contains | not_contains | greater_than | less_than | matches | exists | not_exists",
          "expected": "any",
          "description": "string"
        }
      ],
      "setup": ["string (pre-steps)"],
      "teardown": ["string (cleanup steps)"]
    }
  ]
}
```

## Best Practices

- Follow RESTful conventions for interface extraction
- Keep parameter naming style consistent (camelCase or snake_case)
- Error responses must include `code` and `message` fields
- Enum values must explicitly list all possible values
- Generate at least 3-5 test cases per interface
- Test data should be realistic and close to business scenarios
- Assertions should be precise and verifiable
- Every test case must have a clear description

## Troubleshooting

**Problem: Cannot find uploaded files**
- Ensure `list_uploaded_files` is called first to get correct paths
- Verify `user_id` and `conversation_id` from system context

**Problem: Incomplete interface extraction**
- Check that the source document is a supported format
- Use `validate_api_spec` to identify missing fields
- For Word documents, ensure business entities and CRUD operations are clearly described

**Problem: Test execution failures**
- Verify target API endpoint is accessible
- Check request headers (authentication tokens, content-type)
- Review timeout settings for slow endpoints
