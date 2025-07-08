# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
All changes are based on merge commits since the last release commit, with gitlab-style MR links.

## [0.0.1rc5](https://gitlab.com/generally-intelligent/generally_intelligent/-/merge_requests/5089) (4ecb8f30)
#### changes since `0.0.1rc4`

### Added
- Loading skeleton for long user prompts in the frontend (!5089)
- Anthropic API key validation to startup checks (!5090)
- 30-second timeout for Docker cleanup operations (!5080)
- React Router fallback to fix route serving issues (!5086)
- ObservableThread primitive for better exception handling in threaded operations (!5063)
- Diff truncation to handle overly long diffs (!5049)

### Changed
- Enhanced system prompt to prevent Claude from hallucinating file names (!5088)
- Expanded conditions for sending branch artifacts (!5078)
- Enhanced error message UI with prominent system error blocks and improved styling (!5082)
- Updated development script dependencies (!5068)

### Fixed
- Fixed navigation to reroute to home when deleting tasks (!5091)
- Fixed version indicator layering to display below sync footer (!5027)
- Fixed error block corner styling (!5082)
- Fixed skeleton truncation issues (hotfix)

## [0.0.1rc4](https://gitlab.com/generally-intelligent/generally_intelligent/-/merge_requests/5066) (4136094f)
#### changes since `0.0.1rc3`

### Added
- Browser auto-launch functionality when server is ready to prevent 404 errors on first load (!5064)

### Changed
- Optimized initial JavaScript bundle loading performance from 6s to 0.3s (!5066)

## [0.0.1rc3](https://gitlab.com/generally-intelligent/generally_intelligent/-/merge_requests/5061) (2b099f40)
#### changes since `0.0.1rc2`

### Added
- Git repository root directory validation during startup (!5055)
- Root access for ttyd terminal sessions to handle package installations (!5054)
- Enhanced error message display even when exceptions occur (!5053)
- Comprehensive Docker configuration validation with settings-store.json support (!5051)
- Improved startup checks for development environments (!5043)
- Todo list artifact display functionality (!5037)
- Container name uniqueness for task restoration (!5042)
- Node.js version validation in ESLint pre-commit hooks (!5039)

### Changed
- Refactored v1 initialization code into modular components (!5036)
- Reduced log verbosity by limiting command output length (!5050)
- Updated Docker container images to use Imbue's GHCR repository (!5044)
- Improved last processed message ID tracking to prevent duplicate processing (!5031)
- Enhanced error handling to prevent chat thread death on recoverable errors (!5041)

### Fixed
- Fixed Docker Desktop settings detection for newer versions (4.35+) (!5051)
- Resolved temporary tool failure reporting issues (!5045)
- Fixed meta task thread stability to prevent crashes (!5032)
- Corrected Docker username argument handling in Claude dockerfile (!5038)
- Fixed integration test execution in local environments (!5030)

## [0.0.1rc2](https://gitlab.com/generally-intelligent/generally_intelligent/-/merge_requests/5029) (79da8fb5)
#### changes since `0.0.1rc1` (3175d049)

### Added
- Favicon support for the web interface (!5019)
- Support for proper diff viewing with selectable content (!5017)
- Browser auto-launch to localhost:5174 instead of localhost:5050 (!4984)
- Tooltip consistency improvements for UI elements (!5022, !5018)
- All diff tab implementation in the artifacts panel (!4989)
- Pre-built Docker image support via GHCR for faster first-time setup (!5011)
- Comprehensive integration test suite for imbue_verify functionality (!4980)
- Mac-specific Docker Desktop VirtioFS startup checks (!4985)
- System prompt injection for improved Claude instructions (!5013)
- Input scrolling with max-height constraints for better UX (!5028)
- tmux installation instructions in onboarding materials (!4929)
- PostHog telemetry integration with proper token handling (!4940)
- Two separate MCP servers (internal and tools.toml configuration) (!4970)
- Schema migrations with Alembic database support (!4910)
- JSON schema migration detection and automation (!4957)
- Comprehensive startup checks for proper Docker configuration (!4985)
- Task rollback functionality to restore thread snapshots (!4990)

### Changed
- Switched PostHog project configuration to use Imbue project (!5001)
- Updated Claude Code SDK agent to use in-memory snapshots instead of git operations (!4955)
- Improved DiffTracker to eliminate git subprocess calls during agent execution (!4955)
- Enhanced error display with code block wrapping for better readability (!4986)
- Refactored frontend state management using Jotai atoms (!4972)
- Tasks are now always clickable even during build process (!5008)
- Updated README with internal wizard configuration instructions (!5006)
- Switched to SQLite file-based database during integration tests (!5002)
- Improved ESLint pre-commit hook with proper preprocessing (!4978)
- Enhanced artifact syncing to only sync up to snapshot point (!5003)
- Fixed queueing logic by removing internal queue from Claude Code SDK agent (!5009)
- Made diff gutter lines non-selectable for better copy/paste experience (!5017)
- Consistent icon sizing across UI elements (!5018)

### Fixed
- Fixed filename handling with spaces by adding proper quoting (!4965)
- Resolved 404 errors in frontend routing (!5025)
- Fixed user config file creation during tests (!5016)
- Improved SQL database backup condition checking (!4994)
- Fixed artifact snapshotting and restoration functionality (!5003)
- Resolved memory spikes when reading large log files (!4979)
- Fixed integration test state management and mocking (!4993, !4998)
- Improved mutagen sync cleanup on startup to handle dangling sessions (!4981)
- Fixed telemetry configuration propagation into containers (!4940)
- Enhanced error reporting and validation in various components (!4999)

### Removed
- Removed all v0 support code and conditional logic (!4972)
- Eliminated git operations that could interfere with agent commands (!4955)
- Removed unnecessary API polling in favor of event-driven updates (!4972)
