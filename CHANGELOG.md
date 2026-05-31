# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Relicensed from a proprietary license to **MIT** to allow adoption.
- Rewrote the README around the five questions a first-time user needs answered:
  what it is, why it exists, what the agent can do, how to install (Claude Desktop),
  and how to configure auth (Cloud OAuth · On-prem · PAT comparison table).
- Restructured the package from `src/` to `uipath_mcp_python/` so the server is
  importable as `uipath_mcp_python.server` and installable with `pip install`.

### Added
- `pyproject.toml` with project metadata, dependencies, a `uipath-mcp` console
  script, and project URLs — the repo is now `pip install`-able.
- `examples/` with worked agent interactions (on-prem deploy, multi-step
  list-then-schedule, and a cross-domain query).
- `.github/workflows/ci.yml` running ruff across Python 3.10–3.12.
- `.github/MAINTAINER_TODO.md` listing the manual GitHub UI settings (topics,
  description, website).
- `CHANGELOG.md` (this file).
- `main()` entry point in `server.py` for the console script.

### Audited
- `.env.example` now documents all three auth strategies with per-strategy comments.
