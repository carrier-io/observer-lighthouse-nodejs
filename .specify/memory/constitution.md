<!--
  SYNC IMPACT REPORT

  Version Change: N/A → 1.0.0 (Initial constitution)
  Date: 2026-02-10

  Modified Principles: N/A (initial creation)
  Added Sections:
    - All core principles (5 principles)
    - Multi-Version Support Policy
    - Governance framework

  Removed Sections: N/A

  Templates Status:
    ✅ .specify/templates/plan-template.md - Compatible (Constitution Check section present)
    ✅ .specify/templates/spec-template.md - Compatible (User story focus aligns with testing principle)
    ✅ .specify/templates/tasks-template.md - Compatible (Test-first structure aligns)
    ✅ .claude/commands/*.md - Compatible (Generic guidance, no agent-specific references found)

  Follow-up TODOs: None
-->

# Observer Lighthouse Constitution

## Core Principles

### I. Multi-Version Compatibility

The Observer Lighthouse tool MUST support multiple Lighthouse major versions concurrently to accommodate diverse client requirements and migration paths.

**Rules:**
- Each supported Lighthouse version (currently LH11 and LH12) MUST maintain independent Docker images with explicit version tagging
- Version-specific code branches MUST be clearly named (e.g., `ibombit_updated_v11`, `ibombit_updated_v12.8.2`)
- Metrics extraction logic MUST account for version-specific differences in Lighthouse output formats
- New Lighthouse features (e.g., CSV reports in LH12) MUST be conditionally supported without breaking compatibility with earlier versions
- All API integrations MUST handle both legacy and new metric formats transparently

**Rationale:** Clients operate on different upgrade schedules. Forcing simultaneous upgrades creates adoption friction and operational risk. Multi-version support enables gradual migration while maintaining service continuity.

### II. Integration Contracts (NON-NEGOTIABLE)

All external integrations MUST define explicit, versioned contracts that are independently testable and backward compatible.

**Rules:**
- Galloper/Carrier API contracts MUST be documented and validated via contract tests
- Data upload formats (JSON, HTML, CSV) MUST maintain stable schemas across versions
- Environment variable contracts MUST be explicitly documented with validation on startup
- Metric naming and units MUST remain consistent across internal processing and external reporting
- Breaking changes to integration contracts require MAJOR version bump and migration documentation

**Rationale:** This tool is a critical component in CI/CD pipelines. Integration failures cascade across testing infrastructure. Explicit contracts enable independent evolution of components while preventing runtime surprises.

### III. Quality Gates & Threshold Validation

Performance thresholds are the core value proposition. Threshold evaluation MUST be deterministic, auditable, and correctly implemented.

**Rules:**
- Threshold validation logic MUST have 100% test coverage
- Threshold comparison algorithms MUST handle edge cases (null values, missing metrics, zero values)
- Quality gate failures MUST produce actionable, structured error messages
- Degradation rate and missed threshold calculations MUST be independently verifiable from logs
- JUnit report generation MUST accurately reflect pass/fail status based on threshold evaluation

**Rationale:** Incorrect threshold evaluation undermines trust in the entire testing pipeline. False positives waste engineering time investigating non-issues. False negatives allow performance regressions into production.

### IV. Observability & Debugging

All processing stages MUST emit structured logs that enable root cause analysis without code inspection.

**Rules:**
- Every file operation (read, rename, upload) MUST log the file path and operation result
- Metric extraction MUST log source values and transformations applied
- API interactions MUST log request/response summaries (excluding sensitive tokens)
- Error handling MUST log full exception context including input state
- Loop iteration processing MUST log progress markers for long-running operations

**Rationale:** This tool processes transient data (reports are renamed/moved during processing). When failures occur, logs are often the only forensic evidence. Insufficient logging makes debugging impossible in production environments.

### V. Data Integrity & Idempotency

Report processing MUST be idempotent and preserve data integrity across retries and failures.

**Rules:**
- File renaming MUST use unique timestamps to prevent overwrites
- S3/artifact uploads MUST verify success before marking operations complete
- Aggregated results (`all_results.json`) MUST be atomically updated or rolled back on failure
- Missing or malformed reports MUST NOT corrupt existing aggregated data
- Retry logic MUST not duplicate data or double-count metrics

**Rationale:** Performance test results feed into dashboards, SLO tracking, and release decisions. Data corruption or duplication invalidates historical trends and undermines confidence in the testing system.

## Multi-Version Support Policy

### Version Lifecycle

- **Supported**: Lighthouse versions actively maintained with bug fixes and integration updates (currently LH11.x and LH12.x)
- **Deprecated**: Versions in maintenance mode, receiving only critical security fixes (announcement required 90 days prior)
- **End-of-Life**: Versions no longer maintained (announcement required 180 days prior)

### Version-Specific Requirements

- Each supported version MUST have:
  - Dedicated Docker base image with pinned Lighthouse version
  - Separate git branch for version-specific code
  - Independent test suite validating metric extraction for that version
  - Documentation of version-specific quirks or limitations

### Deprecation Process

1. Announce deprecation with migration guide (180 days notice)
2. Update documentation to mark version as deprecated
3. Provide automated migration tooling or scripts where feasible
4. Move to End-of-Life after deprecation period
5. Archive branch but do not delete (historical reference)

## Governance

### Constitutional Authority

This constitution supersedes all other development practices, coding standards, and architectural preferences. When conflicts arise, constitutional principles take precedence.

### Amendment Process

1. Proposed amendments MUST document:
   - Rationale for change
   - Impact on existing principles
   - Migration plan for affected code/practices
   - Version bump justification (MAJOR, MINOR, or PATCH)

2. Amendments require approval from project maintainers and stakeholders

3. Approved amendments MUST:
   - Update constitution version following semantic versioning
   - Update `LAST_AMENDED_DATE`
   - Propagate changes to dependent templates (plan, spec, tasks)
   - Generate migration checklist for existing features

### Compliance Verification

- All pull requests MUST include constitutional compliance verification
- Code reviews MUST explicitly validate adherence to applicable principles
- Quality gate failures or integration contract violations MUST block merges
- Complexity additions (new abstractions, dependencies) MUST be justified against constitutional simplicity guidance

### Version Semantics

- **MAJOR**: Backward-incompatible changes (principle removal, redefined core requirements)
- **MINOR**: Additive changes (new principles, expanded guidance, new sections)
- **PATCH**: Clarifications, typo fixes, non-semantic refinements

**Version**: 1.0.0 | **Ratified**: 2026-02-10 | **Last Amended**: 2026-02-10
