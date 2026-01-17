# Sentinel Roadmap

**Goal:** A lightweight, language-agnostic process supervisor with advanced
features for developers and DevOps.

---

## Core Polish and Usability (v0.1.x)

**Focus:** Improve core features, usability, and robustness. **Target:** Q1 2026

- [x] **v0.1.1** ✅ COMPLETED
  - [x] Process Groups: Batch management (start/stop/restart all) ✅
  - [ ] Environment File Support: Load `.env` files for process environment
        variables

- [ ] **v0.1.2**
  - [ ] Log Rotation: Rotate logs based on size limits
  - [ ] Process Health Checks: Add periodic HTTP/TCP checks

- [ ] **v0.1.3**
  - [ ] Process Timeouts: Set timeouts for process startup
  - [ ] Process Priority: Set nice/ionice values

- [ ] **v0.1.4**
  - [ ] Process User: Run processes as specific users
  - [ ] General Bug Fixes and Documentation: Address issues and improve docs

---

## Scalability and Integration (v0.2.x)

**Focus:** Add features for production use and integration with other tools.
**Target:** Q2 2026

- [ ] **v0.2.1**
  - [ ] Basic Cluster Mode: Run multiple instances of the same process
  - [ ] Basic Startup Scripts: Generate systemd scripts

- [ ] **v0.2.2**
  - [ ] Basic Remote Management: Manage processes via SSH
  - [ ] Basic Metrics Export: Export metrics to a file or HTTP endpoint

- [ ] **v0.2.3**
  - [ ] Process Dependencies: Start processes in a specific order
  - [ ] Improved Cluster Mode: Dynamic scaling (e.g., `--scale 2-4`)

- [ ] **v0.2.4**
  - [ ] Advanced Startup Scripts: Support for `init.d` and Windows services
  - [ ] Advanced Metrics Export: Prometheus integration

---

## Advanced Features (v0.3.x)

**Focus:** Advanced features for power users and DevOps. **Target:** Q3 2026

- [ ] **v0.3.1**
  - [ ] Basic Web Dashboard: Simple UI for monitoring
  - [ ] Basic Process Scaling: Scale based on CPU/memory

- [ ] **v0.3.2**
  - [ ] Basic Process Isolation: Docker integration
  - [ ] Basic Configuration File: YAML/TOML support

- [ ] **v0.3.3**
  - [ ] Advanced Web Dashboard: Real-time updates and control
  - [ ] Advanced Process Scaling: Custom scaling policies

- [ ] **v0.3.4**
  - [ ] Advanced Process Isolation: cgroups and resource limits
  - [ ] Advanced Configuration File: Secrets management

---

## Stability and Production-Readiness (v1.0)

**Focus:** Stability, testing, and documentation. **Target:** Q4 2026

- [ ] **v1.0.0**
  - [ ] Full Test Coverage: Unit, integration, and E2E tests
  - [ ] Complete Documentation: API/CLI docs and tutorials
  - [ ] Real-World Adoption: Production verification
  - [ ] Stable API/CLI: Freeze breaking changes

---

## Tentative Timeline

| Version Range | Target Release |
| ------------- | -------------- |
| 0.1.x         | Q1 2026        |
| 0.2.x         | Q2 2026        |
| 0.3.x         | Q3 2026        |
| 1.0           | Q4 2026        |

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for
guidelines.

## Feedback

Have ideas or suggestions? Open an issue or start a discussion!
