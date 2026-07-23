
# RFC-009 — Part 6
# Plugin Testing, Developer Experience, Observability, Operations & Production Readiness

**Status:** Draft for implementation  
**Audience:** SDK engineering, developer experience, QA, SRE, platform engineering  
**Depends On:** RFC-009 Parts 1–5

---

## 1. Executive Summary

This document completes RFC-009.

It defines the developer workflow and production operating model for Forge
extensions.

A successful extension platform must be:

- safe
- understandable
- testable
- debuggable
- observable
- compatible
- easy to adopt

The SDK should make secure behavior easier than insecure behavior.

---

## 2. Developer Workflow

```text
Initialize → Implement → Test → Validate → Package → Sign → Publish → Install
```

---

## 3. CLI

Suggested commands:

```text
forge plugin init
forge plugin dev
forge plugin test
forge plugin validate
forge plugin package
forge plugin sign
forge plugin publish
forge plugin inspect
```

---

## 4. Project Template

```text
my-plugin/
  plugin.yaml
  src/
  schemas/
  tests/
  fixtures/
  README.md
  CHANGELOG.md
  LICENSE
```

---

## 5. Local Development Runtime

The local runner should provide:

- mock capability clients
- local fixture repository
- deterministic clock
- deterministic random seed
- simulated network
- trace viewer
- schema validation
- permission denial simulation

---

## 6. Test Levels

### Unit

- business logic
- schema transformations
- deterministic helpers

### Contract

- manifest
- input
- output
- capability use
- error codes

### Integration

- broker clients
- external APIs
- artifact writes
- context contribution

### Runtime

- startup
- timeout
- cancellation
- resource limits
- network policy

### Security

- exfiltration
- injection
- capability abuse
- cross-tenant access

---

## 7. Golden Tests

Golden fixtures are useful for:

- analyzer output
- verifier findings
- context ranking
- renderer output
- plan strategy

Golden changes require review.

---

## 8. Compatibility Test Matrix

Test against:

- supported Forge versions
- SDK versions
- runtime architectures
- operating systems
- protocol versions
- configuration versions

---

## 9. Certification Suite

The registry may run a standard suite:

- manifest validation
- startup
- healthy invocation
- denied capability
- timeout
- invalid input
- invalid output
- cancellation
- uninstall cleanup

---

## 10. Developer Documentation

Required guides:

- quick start
- manifest reference
- capability catalog
- runtime model
- security model
- testing
- publishing
- troubleshooting
- examples

---

## 11. Example Plugins

Reference implementations:

- read-only repository analyzer
- verification check
- GitHub issue creator
- context provider
- MCP adapter
- declarative UI renderer

---

## 12. Observability Model

Every invocation should produce:

- trace
- metrics
- structured logs
- audit event
- cost data where applicable

---

## 13. Plugin Metrics

- installation_count
- active_installations
- invocation_count
- success_rate
- latency
- timeout_rate
- cancellation_rate
- capability_denial
- invalid_output
- resource_usage
- artifact_bytes

---

## 14. Publisher Dashboard

Publishers may view:

- version adoption
- invocation reliability
- latency
- crash rate
- deprecation progress
- security notices

No customer-sensitive payloads.

---

## 15. Organization Dashboard

Organizations may view:

- installed plugins
- capabilities
- owners
- usage
- cost
- risk
- health
- pending upgrades
- security findings

---

## 16. Logs

Plugin logs must support:

- invocation filtering
- severity
- time range
- export
- correlation
- retention policy

---

## 17. Traces

Trace spans:

- authorize
- validate input
- schedule
- start runtime
- capability call
- external call
- validate output
- persist artifacts
- complete

---

## 18. Cost Accounting

Cost components:

- CPU
- memory
- sandbox duration
- network
- storage
- external API
- AI tokens

---

## 19. SLOs

Suggested platform SLOs:

| Capability | SLO |
|---|---:|
| Invocation gateway availability | 99.9% |
| Registry availability | 99.9% |
| Invocation scheduling | 99% < 2s |
| Capability broker success | 99.95% |
| Audit event persistence | 99.999% |
| Installation resolution | 99.9% |

Plugin-specific failures do not count as platform failures when correctly
classified.

---

## 20. Alerts

Alert on:

- gateway error rate
- scheduler backlog
- broker failures
- registry outage
- signature validation spike
- sandbox violations
- cross-tenant denial spike
- artifact corruption
- widespread plugin crashes

---

## 21. Operational Runbooks

Required:

- registry outage
- plugin quarantine
- publisher compromise
- runtime capacity shortage
- broker failure
- bad upgrade
- schema incompatibility
- MCP server outage
- secret exposure
- sandbox escape

---

## 22. Runbook — Bad Plugin Upgrade

1. stop rollout
2. disable auto-upgrade
3. rollback installations
4. compare capability changes
5. notify affected organizations
6. preserve diagnostics
7. require fixed release
8. review publisher process

---

## 23. Runbook — Registry Outage

1. preserve installed plugin execution using cached metadata
2. disable new installs and upgrades
3. show degraded status
4. restore metadata service
5. verify package integrity
6. reconcile pending actions

---

## 24. Release Strategy

Extension platform rollout:

### Phase 1

- first-party plugins
- in-process and container runtime
- private registry

### Phase 2

- verified partners
- capability grants
- remote endpoints
- MCP

### Phase 3

- curated marketplace
- organization policies
- automated certification

### Phase 4

- public ecosystem
- advanced analytics
- commercial workflows

---

## 25. Feature Flags

Flags should control:

- third-party installation
- MCP
- remote plugins
- privileged capabilities
- automatic upgrades
- public marketplace

---

## 26. Data Retention

Retention policies for:

- invocation logs
- artifacts
- audit
- configuration
- package versions
- vulnerability evidence

---

## 27. Backup and Recovery

Back up:

- registry metadata
- package metadata
- publisher identity
- installations
- grants
- configuration
- audit logs

Package blobs should be replicated.

---

## 28. Production Readiness Review

Review areas:

- security
- runtime isolation
- capability policy
- registry integrity
- supply chain
- observability
- capacity
- documentation
- support
- incident response

---

## 29. RFC-009 Definition of Done

RFC-009 is complete when:

- plugin SDKs exist
- manifests are validated
- capabilities are brokered
- third-party code is isolated
- invocation contracts are versioned
- MCP is supported through a gateway
- registry publishing is signed
- upgrades are safe
- security policy is enforceable
- plugins are testable locally
- certification exists
- telemetry and audit are complete
- quarantine and rollback work
- production runbooks exist

---

## 30. Recommended Implementation Sequence

### Phase 1 — Core SDK

- manifest
- TypeScript SDK
- Python SDK
- local runner
- capability registry

### Phase 2 — Runtime

- invocation gateway
- container runtime
- broker
- artifact service
- auditing

### Phase 3 — Registry

- publishing
- signing
- scanning
- installation
- upgrades

### Phase 4 — MCP

- server registry
- discovery
- mapping
- sessions
- drift detection

### Phase 5 — Marketplace and Hardening

- certification
- organization policy
- publisher dashboards
- public ecosystem controls

---

## 31. RFC-009 Completion Summary

RFC-009 defines Forge as an extensible platform rather than a closed product.

The architecture allows external capabilities while preserving:

- least privilege
- deterministic contracts
- runtime isolation
- tenant boundaries
- source-code confidentiality
- auditability
- upgrade safety
- operational control

The next RFC should define enterprise security, organizations, RBAC, governance,
audit, compliance, SSO, multi-tenancy, billing boundaries, and administrative
controls.

---

**END OF RFC-009**
