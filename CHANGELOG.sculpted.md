# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
All changes are based on merge commits since the last release commit, with gitlab-style MR links.


## [0.0.2rc3] (current)
#### changes since `0.0.2rc2`

### Added
- Copy filename functionality to diff viewer for easier file reference (!5195)
- Onboarding guidelines link to startup check failures for better user guidance (!5193)

### Changed
- Remote configuration checking on task setup to ensure proper git repository state (!5245)

### Fixed
- Review modal button tooltip display issue (!5247)
- Error display for numerical serialized exception arguments on frontend (!5236)
- Error handling to prevent timeout errors from masking Docker errors (!5262)

### Internal updates
- Integration test README updates (!5254)
- Sentry test route fixes (!5267)
- CI timeout adjustments for test_sculptor jobs (!5258)


## [0.0.2rc2]
#### changes since `0.0.2rc1`

### Added
- UI for environment crash detection and display to show Docker task errors (!5222)
- Validation for Anthropic API key to ensure ASCII character compatibility (!5228)

### Changed
- Markdown links now open in new tabs for better user experience (!5201)
- Frontend state consistency improved via request ID tracking to prevent race conditions (!5169)

### Fixed
- Duplicate messages bug that occurred when event source reconnects (!5231)

### Internal updates
- Version bump to 0.0.2rc2 (!5234)


## [0.0.2rc1]
#### changes since `0.0.1rc9`

### Added
- Token refresh functionality for better authentication handling (!5127)
- PostHog logging for task creation events (!5212)
- Agentic issue identifier v0 functionality (!5153)

### Changed
- Log level adjustment from debug to trace to reduce confusing error messages (!5177)
- Branch dropdown now refreshes available branches when opened (!5130)
- Event source implementation switched to fetch-event-source to bypass browser limitations (!5208)
- Improved error handling for environment failures (!5207, !5172)

### Fixed
- Database migration script to work with null pools (!5183)
- Rancher Desktop compatibility and virtualization detection (!5198)
- FastAPI logging integration with loguru in v1 (!5106)
- Artifact path naming for better clarity (!5185)

### Unreleased

### Internal updates
- Remote repository setup for sculptor's controlled bare repository (!5079)
- Documentation improvements for build metadata function (!5199)
- Test stability improvements by skipping flaky tests (!5200, !5188)
- Build process improvements excluding build/ and _vendor directories (!5210)
- Minor V1 cleanups and improvements (!5181)
- Precommit hook for rate limit validation to ensure Prefect rate limits stay in sync (!5180)
- Make command for 2-session Sculptor setup (sos) to start dist and dev Sculptor instances (!5179)
- Test logging duplicate issues (!5187)
- Integration tests for distributions with snapshot updates (!5115)


## [0.0.1rc9](https://gitlab.com/generally-intelligent/generally_intelligent/-/merge_requests/5175) (de12417a)
#### changes since `0.0.1rc8`

### Added
- Ability to remove queued messages from UI (!5171)
- Docker startup check bypass option when `SCULPTOR_ALLOW_ALL_DOCKER_SETTINGS` is set (!5175)

### Changed
- Improved onboarding error messages for better user experience (!5175)

### Fixed

### Unreleased

### Internal updates
- Integration test stability improvements using stable file access (!5162)

## [0.0.1rc8](https://gitlab.com/generally-intelligent/generally_intelligent/-/merge_requests/5167) (c008a86a)
#### changes since `0.0.1rc7`

### Added
- prevent single request failure (AgentCrashedError) from bringing down task  (!5144)
- Also improve retry-request and reload-task buttons (!5144)

### Changed
- Enhanced error isolation to prevent single request failures from crashing tasks (!5144)

### Fixed
- Fixed task existence API after projectID refactoring (!5158)
- Fixed JSON encoding error handling (!5126)

### Unreleased
- Playwright MCP integration for scout with image support (!5159)
- Image rendering support in generated HTML reports (!5159)
- Fixed image file handling in scout integration (!5166)
- Precision-recall scoring for each issue type with CSV export (!5071)
- Removed login requirement for root path access (!5149)

### Internal updates
- Fixed type errors in sculptor/testing module (!5151)
- Fixed type errors in sculptor/web module (!5152)
- Fixed type errors in sculptor/services module (!5126)
- Fixed missing import in computing_environment.py (!5151)
- Fixed type annotation issues with splinter.Browser (!5151)
- Fixed environment builder error behavior to match docstring (!5126)
- Re-enabled snapshot updates by correcting snapshot capture logic (!5156)
- Improved goal parameter passing in prompts (!5159)
- Database engines migrated to NullPool for better connection management (!5157)
- Converted Splinter to Playwright for integration tests (!5167)
- Added enabled identifiers enum for issue type awareness (!5071)
- Updated scorer to be aware of relevant issue codes (!5071)
- Enhanced FastAPI subclassing for better type safety (!5152)
- Improved error handling in various modules (!5154)

## [0.0.1rc7](https://gitlab.com/generally-intelligent/generally_intelligent/-/merge_requests/5147) (e52d6065)
#### changes since `0.0.1rc6`

### Added
- Multi-project support with project ID filtering to enable simultaneous sculptor instances (!5114)
- Updated cleanup logic to work with multi-project mutagen sync (!5147)
- Improved exception handling with expected error types (!5140)

### Changed
- Refactored agent artifact creation logic for better code organization and testing isolation (!5135, !5137)
- Refactored agent output parsing and message sending (!5135)
- Enhanced error type detection using last message in agent output (!5140)

### Fixed
- Fixed missing attribute error when instantiating ServerReadyAgentMessage (!5121)
- Resolved error by adding missing attribute (!5121)

### Unreleased
- New `imbue-scout` CLI tool to generate scout reports (!5084)
-
### Internal updates
- HOW-TO.md documentation for adding new tools to imbue_cli project (!5134)
- Added bowei code to interview repository (!5142)

## [0.0.1rc6](https://gitlab.com/generally-intelligent/generally_intelligent/-/merge_requests/5133) (2469d344)
#### changes since `0.0.1rc5`

### Added
- Basic error display infrastructure in frontend (!5110)
- Fixed serialization issues in web derived module (!5128)

### Changed
- Enhanced MCP server configuration and added caching support for better Claude SDK performance (!5062)
- Separated style and correctness issue identification with dataset improvements (!5104)

### Fixed
- Timeout functionality to `run_local_command` with git diff migration (!5108)
- Updated default_tools.toml with correct imbue_verify configuration (!5131)
- Added documentation for `enabled_identifiers` in imbue_verify tool configuration (!5133)
- Fixed space handling in git stash operations and untracked file retrieval (!5117)
- Ensured log exceptions properly reach Sentry for better error tracking (!5116)
- Fixed bug where line numbers were incorrectly shifted in context display (!5109)
- Fixed weird loading behavior on page reload and improved navigation (!5107)

### Removed

### Unreleased
- User authentication UI with login indicator and logout button for better user experience (!5101)

### Internal updates
- Fixed multiple typing errors in request_context.py, npm_run.py, and user_config.py (!5124, !5125, !5122)
- Added safety check to raise error when live debugging is enabled (!5129)
- Improved user config handling by removing fake field initialization (!5102)
- Fixed frontend-dist directory creation in build process (!5120)
- Fixed quoting issues in Sculptor Makefile (!5132)
- Coverage configuration file `.coveragerc` to Sculptor for better test coverage analysis (!4976)
- Replaced all threads with observable threads to prevent silenced exceptions and improve error handling (!5112)
- Pre-push hook for ratchet testing to catch failures earlier (!4983)
- Playwright for integration testing, replacing Splinter (!5111)
- Removed redundant integration testing code after migrating to fixture-based approach (!5098)

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
- Fixed sentry integration (!5093)

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
