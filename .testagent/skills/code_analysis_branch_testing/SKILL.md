---
name: code-analysis-branch-testing
description: >
  Code analysis and branch testing skill based on pre-built code index.
  Uses Coordinator to dispatch multiple Workers for concurrent analysis,
  leveraging code symbol index, call graph, and annotation index to locate
  transaction entry points, analyze UCC/BS/DAO call chains layer by layer,
  identify code branch conditions, generate test data (SQL + request messages)
  covering different branches, execute tests and verify results.
  Suitable for Java 8 + Spring + MyBatis architecture with SOA service registry.
version: 2.0.0
tools_dir: tools
required_workers:
  - entry_locator
  - call_tracer
  - branch_analyzer
  - sql_generator
  - request_builder
  - test_executor
  - report_generator
allowed_tools:
  - search_symbol
  - get_call_chain
  - find_by_annotation
  - read_method_source
  - connect_database
  - query_table_structure
  - execute_sql
  - send_request
tags: [code-analysis, branch-testing, java, spring, mybatis, coverage, coordinator-workers]
---

# Code Analysis and Branch Testing Expert

## Overview

End-to-end branch testing for Java Spring projects based on **pre-built code index + multi-Worker concurrent analysis**:

- **Smart Entry Location**: Locate transaction entry points via annotation index (`@TransCode`) or symbol search
- **Call Chain Tracing**: Unfold complete UCC → BS → DAO linkages using pre-built call graphs
- **Branch Analysis**: Identify IF/ELSE/SWITCH branches, map request parameters to branch conditions
- **Data Generation**: Generate DELETE/INSERT SQL covering various branches
- **Test Execution**: Assemble request messages, execute tests and verify responses

## Architecture

```
User: "Analyze transaction code LN_LOAN_APPLY"
  ↓
Phase 1: [EntryLocator] → @TransCode("LN_LOAN_APPLY") / Spring route
Phase 2: [CallTracer]   → get_call_chain(entry_fqn, depth=5)
Phase 3: [BranchAnalyzer]→ read_method_source, identify IF/SWITCH conditions
Phase 4: [SQLGenerator]  → query_table_structure, generate SQL
Phase 5: [RequestBuilder]→ assemble JSON request messages
Phase 6: [TestExecutor]  → execute SQL → send_request → verify
Phase 7: [ReportGenerator]→ aggregate and generate report
```

## Prerequisites

- **Code Index Built**: Codebase parsed by tree-sitter (symbol table, call graph, annotation index)
- **Database Accessible**: Test environment database connection available
- **Service Reachable**: Target service endpoint accessible

## Worker Division and Tool Usage

### EntryLocator Worker
**Goal**: Locate entry method for transaction code

**Tools**: `find_by_annotation("@TransCode", "LN_LOAN_APPLY")` → `search_symbol("*LN_LOAN_APPLY*", type="METHOD")` (fallback)

**Output**: `{ "entry_point": { "fqn": "...", "file": "...", "line": N, "method_signature": "..." }, "confidence": 0.95 }`

### CallTracer Worker
**Goal**: Unfold complete call chain (UCC → BS → DAO)

**Tools**: `get_call_chain(entry_fqn, direction="downstream", depth=5)` → `read_method_source(fqn)`

**Output**: `{ "call_chain": [{ "depth": N, "layer": "UCC|BS|DAO", "fqn": "...", "summary": "..." }], "external_calls": [...] }`

### BranchAnalyzer Worker
**Goal**: Analyze branch logic in each layer

**Tools**: `read_method_source(fqn, include_body=true)`

**Output**:
```json
{
  "branches": [{
    "fqn": "com.bank.loan.LoanService.submitApplication",
    "conditions": [{
      "type": "IF",
      "expression": "request.getAmount() > 1000000",
      "branches": { "true": "Risk control approval", "false": "Auto approval" },
      "input_mapping": { "amount": { "trigger_true": "> 1000000", "trigger_false": "<= 1000000" } }
    }]
  }]
}
```

### SQLGenerator Worker
**Goal**: Generate test SQL covering all branches

**Tools**: `connect_database(connection_string)` → `query_table_structure("TABLE")` → `write_file`

**Strategy**: DELETE (clean by business PK) → INSERT (data for each branch scenario)

### RequestBuilder Worker
**Goal**: Assemble HTTP request messages from branch analysis results

**Output**: `{ "request": { "method": "POST", "url": "...", "headers": {...}, "body": {...} } }`

### TestExecutor Worker
**Goal**: Execute complete test flow

**Tools**: `execute_sql` → `send_request` → validate response

**Validation**: Status code 200, response code "SUCCESS", database state matches expectation

### ReportGenerator Worker
**Goal**: Aggregate and generate Markdown test report from all phase results

## Error Handling Strategy

| Worker | Failure Impact | Degradation |
|--------|---------------|-------------|
| EntryLocator | Critical | Fast fail — cannot locate entry |
| CallTracer | Severe | Continue with limited symbol search, note incomplete chain |
| BranchAnalyzer | Moderate | Generate basic SQL from known chain |
| SQLGenerator | Moderate | Continue with template SQL |
| TestExecutor | Minor | Record failure, continue report (include unexecuted cases) |

## Best Practices

1. **Worker Context Isolation**: Each Worker receives structured results from previous phases, not raw code
2. **Code Index Dependency**: If index missing, Worker falls back to `read_file` (performance degrades)
3. **Branch Coverage Priority**: Main flow → Exception branches → Boundary conditions
4. **Data Safety**: Test environment only; DELETE + INSERT (avoid UPDATE); clean up after test
