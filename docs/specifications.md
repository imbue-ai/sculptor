# Goal

Create a system by which we can ensure that both our current designs, and proposals to changes to those designs, are clearly communicated to everyone on the team.

# Proposal

Put it all in the repository (see below for details)

# Rationale

The proposed setup allows both us and AI agents to interact with those artifacts

# Definitions

"Specifications" ("specs") shall be used to broadly refer to all:
- user personas
- user stories
- high level test descriptions
- visual designs
- architecture docs
- style guides
- service interfaces
- data types
- dependencies
- routes (and their args)
- CLI commands (and their args)

# Specifications

All "specs" should be written as .md files.

All current "specs" should represent the *current* state of the system

All current "specs" should be documented in their canonical location:
- user personas:
    - `docs/users/personas/**/*.md`
- user stories:
    - `docs/users/stories/**/*.md`
- high level test descriptions:
    - `docs/test_plans/**/*.md`
- visual designs:
    - `docs/designs/**/*.md`  (should link out to stable Figma URLs that show up as screenshots in a .md file)
- architecture docs:
    - `docs/architecture/**/*.md`  (for the highest level descriptions of system components. Files should include links to renderable Eraser diagrams, the code for which is included in the repo)
    - `sculptor/**/readme.md`  (for the module-level documentation)
- style guides:
    - `sculptor/**/style.md`
- service interfaces:
    - `sculptor/services/*/api.py`
- data types
    - `sculptor/core/data_types/*.py` (for the very lowest level data types)
    - `sculptor/services/*/data_types.py` (for service-specific types)
- dependencies
    - `pyproject.toml` (for python dependencies, alphabetically sorted + with minimal version specifications)
    - `sculptor/web/frontend/package.json` (for frontend dependencies)
- routes (and their args)
    - `sculptor/web/routes.py`
- CLI commands (and their args)
    - `sculptor/cli/main.py`

# Proposal Process

All proposals for changes to specs should go through the "Proposal" process, which works as follows:

## Definitions:
- "spec files" are those defined above (for each type of spec)
- "Proposal PRs" are those that change any "spec file". The branch name must start with "proposal/"
- "Implementation PRs" are those that implement "accepted" proposals. The branch name must start with "implement/"

## Process

1. Create a "Proposal PR" by:
    A. checking out main
    B. making any change to the spec files that you want
    C. making a commit and saving that as a branch (ex: proposal/proposal_name)
    D. making a PR against main for that branch
2. Debate and discuss the changes
3. Once the PR is approved / accepted, an "Implementation PR" can be created that builds on the previous PR changes.

## Rules:

1. No "spec files" should be changed *without* going through the proposal process
2. "Proposal PRs" MUST NOT change anything *except* "spec files"
3. Non-"Proposal PRs" MUST NOT change any "spec files" UNLESS this is an "Implementation PR"
