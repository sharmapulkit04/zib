# Spec: Pipeline Manager

**Status:** Draft v0.2
**Owner:** [you]
**Last updated:** 2026-05-25

**Changelog:**
- v0.2: Reframed from "AI component manager" to "project capability manager." Components may be AI-powered or pure infrastructure. Install model now supports deterministic, agent-driven, and hybrid modes.
- v0.1: Initial draft, AI-component-focused.

---

## 1. Problem

I am building agentic applications composed of multiple project capabilities — some AI-powered (spec generators, task planners, executors, code reviewers, test designers), some pure infrastructure (observability, auth, cost tracking, deployment scaffolding). Each capability evolves independently: I want to try new approaches, new implementations, new versions, without disrupting the others.

Today, swapping any of these means editing code in place, losing the prior version, and hoping I remember which approach was which. There is no mechanism to:

- Declare what version of each capability the project uses
- Install a new capability or upgrade an existing one in a structured way
- Detect when an installed capability has been hand-edited
- Roll back to a previous version
- Verify all capabilities are in a consistent state
- Discover what versions are available for each capability
- Share a capability between projects with version tracking

I want a tool that treats project capabilities like package dependencies: declared in a manifest, installed reproducibly, tracked in a lockfile, swappable by changing one line.

The novel piece is that capabilities are heterogeneous. Some are pure methodology (an approach doc and a system prompt). Some are code drops with config patches. Some require project-specific judgment that a deterministic script cannot make — and those installs are best performed by an AI coding agent following written instructions. The orchestrator provides deterministic structure (manifest parsing, dependency resolution, lockfile management, parallelism control) around two execution modes: deterministic scripts for mechanical installs and AI agents for installs that require judgment.

---

## 2. Goals

- A single manifest at the project root declares which capabilities at which versions are installed
- An auto-maintained lockfile records the actual state, with fingerprints
- A `plan` command shows what would change before any changes are applied
- An `apply` command executes the plan, using either deterministic scripts or AI coding agents per-capability based on the capability's declared install mode
- Each install runs on its own git branch and produces a reviewable diff
- Independent capabilities install in parallel; conflicting ones serialize
- The tool itself is small enough to own — under 1000 LOC for v1
- Works on a developer's local machine; no server required
- Treats AI-powered and non-AI capabilities uniformly at the orchestrator level, while supporting their different install ergonomics

---

## 3. Non-goals

- Not a hosted registry. Capabilities live in local directories or git repos in v1
- Not a marketplace. No public discovery, ratings, or social features
- Not a runtime. The tool installs capabilities and exits; running them is the application's responsibility
- Not a multi-user system. One developer, one machine, in v1
- Not a build system. Does not compile code or run tests beyond what the capability's manifest declares for verification
- Not a replacement for `apm`, `npm`, `pip`, or Terraform. Those manage runtime agent configuration, code libraries, or cloud infrastructure. This manages project-level capability composition.

---

## 4. Out-of-scope for v1

- Remote capability registries (git URLs accepted in v2)
- Capability publishing workflow
- Cross-machine state sync (use git)
- Idempotent reinstall optimization (always re-runs the installer in v1)
- Capability marketplaces or catalogs
- Multi-target deployment (one project per invocation)
- Cost or token tracking (handled by the control plane in a separate spec)

---

## 5. Users

One user: a developer building a multi-capability application on a single machine. Familiar with package managers (npm, pip, cargo, terraform). Has Claude Code installed and on PATH for agent-driven installs. Uses git for version control.

---

## 6. Concepts

### 6.1 Capability (also called "component")

A versioned unit of project functionality. Lives as a folder in the capability registry. Has a manifest (`capability.yaml`) declaring what it is, what it depends on, and how to install it.

Capabilities are heterogeneous in nature:

- **AI-powered capability**: contains prompts, model configuration, agent loops, or eval datasets. Spec generators, code reviewers, planners.
- **Infrastructure capability**: pure code or configuration that cross-cuts the project. Observability layers, auth modules, cost tracking, deployment scripts.
- **Hybrid**: AI-powered capability bundled with the infrastructure it depends on (e.g., a code reviewer with its own trace instrumentation).

The tool does not distinguish between these at the orchestrator level. The distinction matters only for the capability's author, who chooses how the install should run.

Capabilities are also heterogeneous in form. They may contain:

- Methodology documents (markdown describing how to do something)
- System prompts and prompt templates
- Source code to be dropped into the project
- Configuration files or fragments
- Scripts (build, install, verify)
- Schema definitions, types, contracts
- Eval datasets and golden sets

A capability is whatever set of files constitutes one versioned unit of behavior. The tool does not constrain what's inside.

### 6.2 Capability manifest (`capability.yaml`)

A small YAML file at the root of each capability version. Declares metadata, dependencies, files-touched hints used for parallelism arbitration, and crucially the install mode.

Example: AI-powered capability with agent-driven install.

~~~yaml
name: spec-generation
version: v4-multi-perspective
kind: ai-powered
description: |
  Spec generator using three rotating perspectives.

requires:
  - name: task-planning
    version: ">=v2"

touches:
  - src/pipelines/spec/
  - pipeline.config.yaml
  - docs/approaches/

install:
  mode: agent-driven
  instructions: INSTALL.md
~~~

Example: infrastructure capability with deterministic install.

~~~yaml
name: observability
version: v3-with-otel
kind: infrastructure
description: |
  OpenTelemetry instrumentation with Langfuse-compatible export.

requires: []

touches:
  - src/observability/
  - package.json
  - .env.example

install:
  mode: deterministic
  steps:
    - copy:
        from: ./otel/
        to: src/observability/
    - patch:
        file: package.json
        merge:
          dependencies:
            "@opentelemetry/api": "^1.7.0"
            "@opentelemetry/sdk-node": "^0.45.0"
          scripts:
            trace: "node --require ./src/observability/otel.ts"
    - append:
        file: .env.example
        content: |
          OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
    - run: pnpm install

verify:
  - command: pnpm tsc --noEmit
  - command: node -e "require('./src/observability/otel')"
~~~

If a capability has facets (see Section 9), the manifest declares them explicitly.

### 6.3 Install modes

A capability declares one of three install modes.

**Deterministic**: the manifest lists explicit, mechanical steps the orchestrator executes directly. Operations include:

- `copy`: copy files or directories from the capability folder to the project
- `patch`: structurally merge content into an existing file (JSON, YAML, TOML, package.json)
- `append`: append text to a file
- `template`: render a template with project context and write to disk
- `run`: execute a shell command in the project root

Deterministic installs are fast, reproducible, and don't need an LLM. Good for capabilities whose install is genuinely mechanical: infrastructure, config drops, type definitions, scaffolding.

**Agent-driven**: the manifest points to an `INSTALL.md` written for an AI coding agent. The orchestrator dispatches the agent in a worktree with the capability folder and `INSTALL.md` as context. The agent decides how to apply the capability to the specific project.

Agent-driven installs are slower and more variable, but handle cases where the install needs project-specific judgment: integrating an AI component into an existing pipeline, adapting a prompt to the project's conventions, deciding how to wire a new stage into an existing graph.

**Hybrid**: the manifest declares both — deterministic steps that run first (mechanical setup), then an `INSTALL.md` the agent follows for the adaptive parts.

~~~yaml
install:
  mode: hybrid
  steps:
    - copy:
        from: ./base/
        to: src/components/code-reviewer/
  instructions: INSTALL.md
~~~

The orchestrator runs the deterministic steps first, then dispatches the agent. Both must succeed for the capability to be considered installed.

### 6.4 Install instructions (`INSTALL.md`)

For agent-driven and hybrid capabilities. A Markdown file at the root of each capability version. Written for an AI coding agent to follow. Describes what files to add, what existing files to modify, what config keys to set, what verification commands to run.

The orchestrator passes `INSTALL.md` + the capability folder + the project context to the agent and lets it do the work.

### 6.5 Capability registry

A directory containing all available capabilities. Default location: `~/capabilities/` (or `~/components/`, configurable). Layout:

~~~
~/capabilities/
├── spec-generation/
│   ├── v1-single-prompt/
│   ├── v2-with-context/
│   └── v4-multi-perspective/
├── task-planning/
│   └── v1-flat-list/
├── code-review/
│   └── v1-spec-aware/
├── observability/
│   └── v3-with-otel/
└── auth/
    └── v1-jwt-basic/
~~~

Each version is a separate immutable folder. New versions are new folders; versions are never overwritten.

### 6.6 Pipeline manifest (`pipeline.yaml`)

A YAML file at the project root declaring which capabilities at which versions the project wants installed.

~~~yaml
pipeline:
  spec-generation: v4-multi-perspective
  task-planning: v2-with-deps
  code-review: v1-spec-aware
  observability: v3-with-otel
  auth: v1-jwt-basic

registry: ~/capabilities/
~~~

The name `pipeline` is historical. It captures "the set of capabilities this project composes." It's not strictly a pipeline in the data-flow sense — observability and auth aren't pipeline stages — but the term fits because most of these capabilities collaborate to process work.

### 6.7 Pipeline lockfile (`pipeline.lock.yaml`)

Auto-maintained file at the project root recording what is actually installed. Generated by `apply`, never hand-edited.

~~~yaml
installed:
  spec-generation:
    version: v4-multi-perspective
    kind: ai-powered
    install_mode: agent-driven
    content_hash: abc123def456
    install_hash: 789ghi
    installed_at: 2026-05-25T10:00:00Z
    files_touched:
      - src/pipelines/spec/main.ts
      - pipeline.config.yaml
    installer: claude-code
    diff_hash: jkl012
  observability:
    version: v3-with-otel
    kind: infrastructure
    install_mode: deterministic
    content_hash: mno345
    install_hash: pqr678
    installed_at: 2026-05-25T10:01:00Z
    files_touched:
      - src/observability/otel.ts
      - package.json
      - .env.example
    installer: deterministic
    diff_hash: stu901
~~~

The `installer` field records whether the deterministic engine or a named AI agent performed the install. This is what audit and reinstall commands reference.

### 6.8 Plan

The computed difference between `pipeline.yaml` (desired) and `pipeline.lock.yaml` (actual). A list of operations: install, upgrade, reinstall, remove. Topologically ordered by capability dependencies, grouped into stages by file-touch overlap.

### 6.9 Apply

The act of executing a plan. For each operation, the orchestrator chooses the execution path based on the capability's declared install mode: deterministic engine for `mode: deterministic`, AI agent dispatch for `mode: agent-driven`, both in sequence for `mode: hybrid`. Both paths run on their own git branch and produce a reviewable diff.

### 6.10 Facet

A subdivision of a capability that touches a distinct layer (backend, UI, shared types, etc.). A capability may have multiple facets, each with its own install spec and its own touches. Facets are installed as part of a single capability-level operation but may dispatch separate installers and may run in parallel within the capability. See Section 9.

---

## 7. Functional requirements

### 7.1 Commands

The CLI is `pipeline`. Each command is a verb operating on the project in the current working directory.

#### `pipeline init`

Scaffold a new project. Creates `pipeline.yaml` (empty), creates `pipeline.lock.yaml` (empty), creates `.pipeline/` for internal state. Idempotent — refuses to overwrite existing files.

#### `pipeline plan`

Compute the difference between desired and actual. Print as a table. Does not modify anything.

Output format:

~~~
Plan (3 operations, 2 stages):

Stage 1 (parallel: 2):
  install      observability         v3-with-otel        [deterministic]
  install      task-planning         v2-with-deps        [agent-driven]

Stage 2 (parallel: 1):
  upgrade      spec-generation       v3 → v4-multi-perspective  [agent-driven]
~~~

The install mode is displayed in the plan so the user knows which operations will use deterministic steps and which will dispatch an agent.

Flags:

- `--capability <name>`: plan changes for one capability only
- `--output json`: machine-readable output

#### `pipeline apply`

Execute the plan. Prompts for confirmation unless `--yes`. For each operation, dispatches to the appropriate executor based on install mode. Updates lockfile incrementally as each succeeds.

For each operation:

1. Create a git worktree at `.pipeline-worktrees/<capability>-<version>/`
2. If `install.mode` is `deterministic` or `hybrid`: run the declared deterministic steps in the worktree
3. If `install.mode` is `agent-driven` or `hybrid`: spawn the AI coding agent in the worktree with `INSTALL.md` and capability path as input
4. Capture the resulting git diff
5. Run verification commands declared in the manifest
6. Merge the worktree's branch back into the working branch
7. Update lockfile entry

Flags:

- `--yes`: skip confirmation
- `--dry-run`: do everything except merge (leave branches for review)
- `--agent <name>`: which agent to use for agent-driven installs (default: claude-code)
- `--parallel <n>`: max parallel installer processes (default: 4)
- `--capability <name>`: apply only operations affecting one capability

On failure of any operation in a stage:

- The installer's branch and worktree are preserved for inspection
- Subsequent stages do not run
- The lockfile reflects partial state (succeeded operations are recorded)
- Exit code is non-zero with a clear error pointing to the preserved worktree

#### `pipeline status`

Show what's currently installed. Reads from lockfile.

~~~
Installed capabilities (5):

  spec-generation     v4-multi-perspective   ai-powered      clean
  task-planning       v2-with-deps           ai-powered      clean
  code-review         v1-spec-aware          ai-powered      DRIFT (2 files)
  observability       v3-with-otel           infrastructure  clean
  auth                v1-jwt-basic           infrastructure  clean
~~~

#### `pipeline audit`

Check for drift: rehash files declared in lockfile's `files_touched` and compare to the recorded `content_hash` and `diff_hash`. Report per-capability.

Flags:

- `--fix`: offer to reinstall any drifted capabilities

#### `pipeline reinstall <capability>`

Re-run the installer for one capability, even if its version hasn't changed. Useful when the capability was tweaked in place or drift was detected. Uses the install mode declared by the capability.

`<capability>` may be `name` for the whole capability or `name:facet` for one facet.

#### `pipeline rollback <capability>`

Revert a capability to its previous version (as recorded in `.pipeline/history/`). Equivalent to changing `pipeline.yaml` back and applying.

#### `pipeline list`

List capabilities available in the registry.

Flags:

- `--capability <name>`: list versions of one capability
- `--installed`: show only what's in the current project's lockfile
- `--kind <ai-powered|infrastructure|hybrid>`: filter by kind

#### `pipeline doctor`

Verify the environment: registry directory exists, `pipeline.yaml` parses, every declared capability exists in the registry, every capability's dependencies are satisfied. For agent-driven capabilities, also verifies the configured agent is on PATH. Report issues.

### 7.2 Cross-cutting capabilities

**Idempotence of declarations.** Running `pipeline apply` when the lockfile already matches the manifest is a no-op. The plan is empty.

**Atomic per-capability installs.** A capability install either succeeds fully (lockfile updated) or fails fully (worktree preserved, lockfile unchanged). Partial state is never written to the lockfile.

**Branch hygiene.** Every install runs on a branch named `pipeline/install-<capability>-<version>`. Successful branches are merged with `--no-ff` so the install is visible in git history. Failed branches are preserved for inspection until `pipeline clean` is run.

**Fingerprint verification.** Before applying, the tool verifies that each capability's content hash matches what's recorded in the lockfile (if previously installed). A mismatch means the capability was edited in place; the user is warned and asked if they want to reinstall.

**Dependency resolution.** Capabilities declare `requires` with semver-style version constraints (`>=v2`, `~v3.1`, exact match). The resolver:

1. Builds a directed graph from declared dependencies
2. Verifies no cycles
3. Verifies all version constraints are satisfiable
4. Produces a topological ordering
5. Within each topological level, groups operations by file-touch non-overlap into parallel batches

**Touch-overlap arbitration.** Two operations whose `touches` declarations intersect must run serially. The tool detects this from declared touches in the capability manifests; users are responsible for declaring touches accurately.

**Mixed-mode parallelism.** Deterministic and agent-driven installs may run in the same stage in parallel as long as their touches don't overlap. The two execution paths are independent; the orchestrator coordinates both.

### 7.3 Configuration precedence

Settings resolve in this order, first match wins:

1. CLI flag
2. Environment variable (`PIPELINE_*`)
3. Project-local `pipeline.yaml` `config:` section
4. Built-in defaults

---

## 8. Execution paths

The orchestrator has two execution backends. Both produce the same output (a diff in a worktree, ready for merge) and report results in the same shape.

### 8.1 Deterministic backend

For capabilities with `install.mode: deterministic` (and the deterministic phase of `mode: hybrid`).

The backend supports these operations, declared in the manifest's `install.steps` list:

- **copy**: copy a file or directory from the capability folder into the project. Source paths are relative to the capability root; destination paths are relative to the project root.
- **patch**: structurally merge content into an existing structured file. Supports JSON, YAML, TOML, and `package.json`. Merge semantics are deep merge for objects, append for arrays (with optional deduplication).
- **append**: append text to a text file. The text is inserted at the end unless `after:` or `before:` markers are specified.
- **template**: render a template file using project context (project name, declared variables) and write to the destination.
- **run**: execute a shell command in the project root. Output captured; non-zero exit fails the operation.

Each step is applied in sequence in the worktree. Failure of any step fails the operation; subsequent steps don't run.

The backend does not call LLMs. It's pure file manipulation plus shell. Fast, reproducible, fully testable without network.

### 8.2 Agent-driven backend

For capabilities with `install.mode: agent-driven` (and the agent phase of `mode: hybrid`).

The backend dispatches an AI coding agent in the worktree:

1. Constructs a prompt containing:
   - Operation type (install / upgrade / reinstall)
   - Capability name and version
   - The full text of `INSTALL.md`
   - The path to the capability's source folder
   - The path to the project being modified
   - Any relevant lockfile state (current version, prior `files_touched`) for upgrade operations
2. Spawns the agent in headless mode with the worktree as cwd
3. Restricts the agent to file modification tools (Read, Write, Edit, Glob, Grep) and Bash for verification commands declared in `INSTALL.md`
4. Waits for completion (timeout: 10 minutes default, configurable)
5. Returns control to the orchestrator

#### 8.2.1 Agent contract

Any agent that conforms to the following contract can be used:

- Accepts a prompt via stdin or `-p` flag
- Accepts a working directory
- Accepts a list of allowed tools
- Exits 0 on success, non-zero on failure
- Writes file modifications to disk in the working directory
- Does not commit, push, or otherwise mutate git state

Default agent: Claude Code (headless mode). Alternate agents listed in v1 config but not required to work in v1: Codex CLI, Aider, Cursor agent.

#### 8.2.2 What the agent sees vs. what it doesn't

The agent sees:

- The capability's `INSTALL.md` and folder
- The project's source tree (in the worktree)
- The relevant lockfile entry for upgrade operations

The agent does not see:

- Other capabilities being installed in parallel
- The pipeline manifest
- The history of previous installs

#### 8.2.3 What the agent must not do

`INSTALL.md` and the system prompt make clear:

- Do not commit changes (the orchestrator handles git)
- Do not push to remote
- Do not modify files outside what `INSTALL.md` describes
- Do not invent files or scope creep
- Do not modify the lockfile (orchestrator owns it)
- Do not modify `pipeline.yaml` (user owns it)

These constraints are stated in the prompt but not technically enforced in v1. v2 may add a file-scope sandbox.

### 8.3 Hybrid backend

For capabilities with `install.mode: hybrid`. The orchestrator runs the deterministic backend first (per Section 8.1), then the agent-driven backend (per Section 8.2). The agent sees the post-deterministic state in the worktree and `INSTALL.md` describes the remaining adaptive work.

If the deterministic phase fails, the agent phase does not run. If the agent phase fails, the deterministic phase's changes are preserved in the worktree for inspection but not merged.

### 8.4 Verification

Both backends run the capability's verification commands after install:

~~~yaml
verify:
  - command: pnpm tsc --noEmit
  - command: pnpm test --filter observability
~~~

Verification failure marks the operation failed; the worktree is preserved for inspection; the lockfile is not updated.

---

## 9. Cross-cutting capabilities: facets

Some capabilities touch multiple layers of a project (backend, UI, shared types). Treating them as a single install produces large, hard-to-review diffs. Splitting them into separate capabilities shifts coordination outside, where it's harder to manage.

The compromise: a capability may declare facets. Each facet has its own install spec and touches. Facets within a capability install together but each facet is one installer invocation. Different facets within the same capability may use different install modes.

### 9.1 Faceted capability manifest

~~~yaml
name: observability
version: v3-with-trace-viewer
kind: hybrid
description: |
  Full-stack observability with OTel backend instrumentation
  and a UI trace viewer.

facets:
  - name: shared-types
    install:
      mode: deterministic
      steps:
        - copy:
            from: ./facets/shared-types/
            to: src/shared/types/
    touches:
      - src/shared/types/observability.ts

  - name: backend
    install:
      mode: deterministic
      steps:
        - copy:
            from: ./facets/backend/
            to: src/api/middleware/
        - patch:
            file: src/api/app.ts
            insert_after: "// middleware"
            content: "app.use(observabilityMiddleware);"
    touches:
      - src/api/middleware.ts
      - src/api/app.ts
    requires:
      - shared-types

  - name: ui
    install:
      mode: agent-driven
      instructions: facets/ui/INSTALL.md
    touches:
      - src/ui/admin/trace-viewer.tsx
    requires:
      - shared-types
~~~

This example shows the value of mixed-mode within a facet group: `shared-types` and `backend` are pure mechanical drops; the UI piece needs to wire into the project's existing admin layout, which requires project-specific judgment best handled by an agent.

### 9.2 Facet installation semantics

1. Facets are topologically sorted by their declared `requires`
2. Within a topological level, facets may run in parallel if their `touches` don't overlap
3. Each facet is one installer invocation using that facet's install mode
4. All facets must succeed for the capability to be considered installed
5. On any facet failure: all sibling facets' worktrees are preserved for inspection; the capability's lockfile entry records partial state

### 9.3 Lockfile representation

~~~yaml
installed:
  observability:
    version: v3-with-trace-viewer
    kind: hybrid
    state: complete
    facets:
      shared-types:
        install_mode: deterministic
        installed_at: 2026-05-25T10:00:00Z
        files_touched: [src/shared/types/observability.ts]
        diff_hash: abc123
        installer: deterministic
      backend:
        install_mode: deterministic
        installed_at: 2026-05-25T10:00:15Z
        files_touched: [src/api/middleware.ts, src/api/app.ts]
        diff_hash: def456
        installer: deterministic
      ui:
        install_mode: agent-driven
        installed_at: 2026-05-25T10:00:30Z
        files_touched: [src/ui/admin/trace-viewer.tsx]
        diff_hash: ghi789
        installer: claude-code
~~~

### 9.4 Facet-targeted operations

`pipeline reinstall observability:ui` reinstalls one facet without touching the others. `pipeline audit` reports drift per facet.

### 9.5 When to use facets vs. separate capabilities

Facets when:

- The pieces must move in lockstep (you would never want backend v3 with UI v2)
- The pieces are part of one conceptual capability
- The capability is the natural unit of evolution

Separate capabilities when:

- The pieces have independent lifecycles
- Different consumers (other projects) want them separately
- The version numbers naturally diverge

If you find yourself wishing facets had independent versions, that's the signal to split them into separate capabilities.

---

## 10. Non-functional requirements

### 10.1 Performance

- `pipeline plan` must complete in under 1 second for projects with up to 20 capabilities
- Deterministic installs typically complete in under 10 seconds
- Agent-driven installs are dominated by agent latency, typically 1-10 minutes
- `pipeline status` must complete in under 200ms

### 10.2 Reliability

- Crashes during apply must leave the project in a recoverable state: successful operations recorded in lockfile, failed operations' worktrees preserved
- The lockfile is written atomically (temp file + rename)
- A corrupt lockfile is detected on read and the user is offered recovery options
- `pipeline apply` is resumable: rerunning after a crash picks up from the last successfully-applied operation
- Deterministic installs are bit-for-bit reproducible given the same inputs; agent-driven installs are not, and the tool acknowledges this in its audit output

### 10.3 Observability

- Every install dispatch emits OpenTelemetry spans
- Spans are tagged with `pipeline.capability`, `pipeline.version`, `pipeline.operation`, `pipeline.install_mode`, `pipeline.facet` (if applicable)
- Agent-driven installs additionally emit `gen_ai.*` attributes for the agent's LLM calls
- Logs are written to `.pipeline/logs/<timestamp>-<capability>.log`
- Default trace destination is the local Langfuse instance if available; configurable via `PIPELINE_OTEL_ENDPOINT`

### 10.4 Portability

- macOS and Linux first-class; Windows best-effort
- Python 3.11+
- Single-binary distribution preferred (PyInstaller); `pip install` fallback

### 10.5 Security

- The tool does not transmit project contents over the network except via the agent's LLM calls (for agent-driven installs)
- Deterministic installs are fully offline
- Agent invocations inherit the user's existing credentials (e.g. `ANTHROPIC_API_KEY`); the tool does not store or proxy them
- The tool refuses to modify files outside the project root
- Hidden Unicode / prompt-injection scanning on `INSTALL.md` before dispatching an agent

### 10.6 Footprint

- Internal state in `.pipeline/` at project root and in git worktrees adjacent to the project
- No background daemons
- No global state outside the registry directory
- `rm -rf .pipeline/` removes all per-project state cleanly

---

## 11. Architecture

The tool has six internal modules. Each is intended to be small (~200-400 LOC).

### 11.1 Manifest (`pipeline/manifest.py`)

Loads and validates `pipeline.yaml` and `capability.yaml` files. Pydantic models for both. Surface-level validation only — semantic validation (do dependencies exist, are versions consistent) happens in the resolver.

### 11.2 Registry (`pipeline/registry.py`)

Reads the capability registry directory. Provides queries:

- List all capabilities
- List all versions of a capability
- Load a specific capability (manifest + folder)
- Compute content hash of a capability
- Resolve version constraints (`>=v2`) to concrete versions

### 11.3 Resolver (`pipeline/resolver.py`)

Given a desired manifest and current lockfile, computes the plan:

1. Diff declared vs. installed
2. For each changed capability, load the target version
3. Build dependency graph from `requires`
4. Topologically sort
5. Group into stages by `touches` non-overlap
6. Return the plan as a list of stages, each containing operations

Pure logic, no I/O, no installer calls. Heavily testable.

### 11.4 Executor (`pipeline/executor.py`)

Executes a plan stage by stage. Dispatches to deterministic or agent-driven backends based on each operation's install mode:

- Creates worktrees
- Calls the appropriate backend
- Captures diffs
- Runs verification commands
- Merges branches on success
- Updates lockfile incrementally

The only module that talks to git.

### 11.5 Backends (`pipeline/backends/`)

Two sibling modules:

- `pipeline/backends/deterministic.py`: implements copy, patch, append, template, run operations
- `pipeline/backends/agent.py`: implements agent dispatch (subprocess to Claude Code or alternates)

Both expose a uniform `install(capability, worktree) -> InstallResult` interface.

### 11.6 Lockfile (`pipeline/lockfile.py`)

Reads, writes, and atomically updates `pipeline.lock.yaml`. Pydantic models for entries. Atomic writes (temp + rename).

### 11.7 CLI (`pipeline/cli.py`)

Click-based. Each command in Section 7.1 is one function. Composes the other modules. Output formatted with Rich.

### 11.8 Integration points (boundaries)

- **Git**: subprocess. The tool runs `git worktree add`, `git diff`, `git merge`, `git worktree remove`.
- **AI agent**: subprocess. The tool runs `claude -p <prompt> --cwd ...` or equivalent. Agent name is configurable. Default is Claude Code.
- **Capability registry**: filesystem. Reads files. Could later be extended to git URLs, HTTP, etc.
- **Observability**: OpenTelemetry SDK. Spans emitted via OTLP to configured endpoint.

---

## 12. Data flow: a complete `apply` walkthrough

User has `pipeline.yaml` declaring four capabilities. Currently nothing is installed.

1. User runs `pipeline apply`
2. CLI calls `Resolver.compute_plan(manifest, lockfile, registry)`
3. Resolver loads all four capabilities from the registry
4. Resolver builds dependency graph and topologically orders
5. Resolver outputs:
   ~~~
   Stage 1: [install observability v3-with-otel (deterministic),
             install auth v1-jwt-basic (deterministic)]
   Stage 2: [install task-planning v2-with-deps (agent-driven)]
   Stage 3: [install spec-generation v4-multi-perspective (agent-driven)]
   ~~~
6. CLI prints the plan with install modes visible, asks confirmation
7. CLI calls `Executor.apply_plan(plan)`
8. Executor starts Stage 1, both operations in parallel:
   - For observability: creates worktree, calls deterministic backend which runs the declared copy + patch + append + run steps
   - For auth: creates worktree, calls deterministic backend
   - Both complete in ~5 seconds each
   - Both pass verification (typecheck + tests)
   - Both merged; lockfile updated with both entries
9. Executor proceeds to Stage 2:
   - For task-planning: creates worktree, calls agent backend
   - Agent reads `INSTALL.md`, drops code into `src/pipelines/planning/`, registers in `pipeline.config.yaml`
   - Agent exits 0 after 2 minutes
   - Verification passes
   - Merged; lockfile updated
10. Executor proceeds to Stage 3:
    - For spec-generation: same flow as task-planning
11. All stages complete. Lockfile reflects all four installs.
12. CLI prints summary: "Installed 4 capabilities in 3 stages (2 deterministic, 2 agent-driven)."

---

## 13. Failure modes

**Manifest references a capability not in the registry.** `plan` fails fast with "capability spec-generation@v4 not found in registry at ~/capabilities/". Suggests `pipeline list --capability spec-generation` to see available versions.

**Capability's install spec is malformed.** For deterministic capabilities: schema validation fails at load time; the capability is treated as broken. For agent-driven: `INSTALL.md` parsing failures are surfaced before dispatching the agent. Lockfile unchanged.

**Deterministic step fails (e.g., file not found, patch conflict).** The step's error is captured; worktree preserved; lockfile not updated. Recovery: fix the capability's manifest or the project state, retry.

**Agent fails to install a capability.** Worktree preserved. Lockfile not updated. Subsequent stages skipped. User can inspect the worktree to see what the agent attempted, then retry with `pipeline apply`.

**Verification fails after install.** Treated as install failure regardless of which backend ran. Same recovery path as above.

**Two capabilities have overlapping touches that weren't declared.** The tool can't detect this. The diff merging may produce conflicts. The merge will fail and the user gets a clear "merge conflict in capability X" error. Recovery: declare overlapping touches accurately.

**The user modifies a file the lockfile says is owned by capability X.** `pipeline audit` detects this and reports drift. The user can choose to keep the edit (which the lockfile no longer tracks) or run `pipeline reinstall X` to revert.

**The registry directory doesn't exist.** `pipeline doctor` flags this. All commands except `init` fail with a clear message.

**The user runs `apply` with uncommitted local changes.** `apply` warns and asks for confirmation. Worktrees branch from HEAD, so uncommitted changes won't conflict with the install — but they'll be hidden from the installer in the worktrees, which may matter.

**Two `apply` invocations run concurrently on the same project.** First one acquires `.pipeline/lock`. Second one fails fast with "another apply in progress".

**Agent-driven install requested but no agent configured or installed.** `pipeline doctor` detects this. If discovered during `apply`, the operation fails with a clear error pointing to `pipeline doctor` for diagnosis.

---

## 14. The capability author workflow

This spec is also about the experience of building new capabilities, not just consuming them. The intended workflow:

1. User decides they want a new version of an existing capability, or a brand new capability
2. User chooses an install mode based on the nature of the install:
   - Deterministic if the install is genuinely mechanical (config drop, code copy, dependency addition)
   - Agent-driven if the install requires project-specific judgment
   - Hybrid if mostly mechanical with some adaptive parts
3. User creates a new folder in the registry: `~/capabilities/spec-gen/v4/`
4. User writes:
   - `capability.yaml` (name, version, kind, dependencies, touches, install mode and steps or instructions)
   - Whatever supporting files the capability contains (code, prompts, methodology docs)
   - `INSTALL.md` if the mode is agent-driven or hybrid
5. User declares the new version in a project's `pipeline.yaml`
6. User runs `pipeline plan` and `pipeline apply` to install
7. If install fails or produces a bad result, user edits the capability and reinstalls

For agent-driven capabilities, this iteration is critical. The first `INSTALL.md` will be wrong. The second will be less wrong. By the time the capability has been installed in two or three projects, the `INSTALL.md` is sturdy.

For deterministic capabilities, iteration is faster: the steps are declarative and most failures surface immediately as schema or merge errors.

The choice of install mode is a design decision the author makes per capability. A useful heuristic: **default to deterministic; reach for agent-driven only when project-specific judgment is genuinely needed.**

To support this iteration:

- `pipeline reinstall <capability>` works even if the lockfile says it's already at the current version (forces a re-run)
- The tool records the previous version's diff in `.pipeline/history/` so rollback is possible

---

## 15. Migration path from "no tool" to "fully adopted"

**Day 1:**

- Implement `pipeline init`, `pipeline doctor`, `pipeline list`
- Create the `~/capabilities/` registry directory
- Author one real capability as the test case — choose a deterministic one (observability is a good first candidate) so the test exercises the simpler backend first

**Day 2-3:**

- Implement `pipeline plan`
- Implement `pipeline apply` for deterministic-only capabilities
- Drive the observability install end-to-end at least once

**Day 4-5:**

- Add the agent-driven backend
- Author an AI-powered capability (spec generator) and install it
- Now both backends are working

**Week 2:**

- Add `pipeline status`, `pipeline audit`
- Add parallel stage execution
- Add `pipeline rollback` and `pipeline reinstall`
- Feel the pain of whatever's missing

**Week 3-4:**

- Add hybrid mode (deterministic + agent in one capability)
- Add facet support if any real capability needs it
- Add OTel instrumentation
- Add resumable apply
- Hardening based on failures observed during real use

**Month 2+:**

- Remote registry support (git URLs)
- Multi-agent support (Codex, Aider)
- Drift auto-fix workflows
- Whatever else daily use demands

The order matters: **build the deterministic backend first**. It's simpler, has no LLM variance, and exercises the manifest/lockfile/plan machinery without depending on agent reliability. Once that's solid, adding the agent-driven backend is additive, not foundational.

---

## 16. Open questions

**Should `INSTALL.md` follow the skill.md format, or its own format?** Its own format. skill.md is designed for runtime agent loading (progressive disclosure, activation hints). `INSTALL.md` is for build-time agent execution. Different concerns. Keep separate.

**Should the registry support remote git URLs in v1?** No. Local filesystem only in v1. Iteration speed matters more than distribution in the first month.

**Should deterministic install steps be Turing-complete (full scripting) or constrained to declarative operations?** Constrained. The deterministic backend supports a fixed set of operations (copy, patch, append, template, run). The `run` operation provides an escape hatch for arbitrary shell. Declarative ops are introspectable, parallelizable, and predictable. Allowing arbitrary scripting in deterministic mode would defeat its purpose.

**Should `apply` block, or kick off in the background?** Block. The user is watching. Background apply is a control-plane concern, not a per-project concern.

**Should the tool know how to call multiple agents (Claude + Codex) for the same install for diversity?** No. One installer per operation in v1. The choice of installer is configurable globally or per-capability.

**Should rollback be inverse-patch-based or git-checkout-based?** git-checkout-based in v1: rollback is "checkout the lockfile from the previous commit, then re-apply." Inverse patches are more elegant but add complexity not worth its weight for v1.

**Should the agent get the contents of `pipeline.yaml`?** No. The agent gets only what it needs: `INSTALL.md`, the capability folder, and the relevant lockfile entry.

**Should there be hooks (`pre-install`, `post-install`) as a separate concept?** Not in v1. They can be expressed as additional steps (for deterministic capabilities) or additional instructions in `INSTALL.md` (for agent-driven). Adding a hook system as a separate concept is overkill for one developer.

**What if I want to install a capability without the registry being on my filesystem?** v2 problem. In v1, registry is filesystem. If you need a colleague's capability, you copy it to your registry first.

**When should something be a capability vs. just code in the project?** Heuristic: a capability is something that has versions worth tracking and an install footprint worth declaring. If you'll only ever have one version and it touches three lines of code, it's not a capability — it's just code. If it has approaches you'll iterate on, files it modifies across the project, or evals you'll run against it, it's a capability.

---

## 17. Success criteria

After 2 weeks of use:

- At least one AI-powered capability has been installed in a real project
- At least one infrastructure capability has been installed in a real project (different install mode exercised)
- At least 3 versions of one capability exist in the registry
- `pipeline apply` has been used at least 10 times
- At least one rollback has been performed successfully
- The tool itself is under 800 LOC

After 1 month:

- At least 5 capabilities exist in the registry, spanning both AI-powered and infrastructure kinds
- At least 2 projects use capabilities from the registry
- `pipeline audit` has detected at least one drift incident
- The tool has gone at least one full week without modification (it's stable enough)
- Total LOC under 1000

After 3 months:

- The tool has been used to install a capability in a second project of yours
- The lockfile-driven workflow feels natural; you no longer reach for manual cp / edit-in-place
- At least one capability has gone through 5+ versions, demonstrating that independent evolution works
- Both install modes (deterministic and agent-driven) are in active use
- The tool has either remained essentially stable, or evolved in specific ways your daily use demanded

---

## 18. Glossary

- **Apply**: the act of executing a plan; runs the appropriate installer per operation
- **Agent-driven install**: install mode where an AI coding agent performs the work following `INSTALL.md`
- **Capability** (also "component"): a versioned unit of project functionality, AI-powered or infrastructure
- **Capability manifest**: `capability.yaml`, declares name, version, kind, deps, touches, install mode
- **Deterministic install**: install mode where the orchestrator performs declarative steps (copy, patch, append, template, run) directly
- **Facet**: a subdivision of a capability touching one layer
- **Hybrid install**: install mode combining deterministic steps with agent-driven work
- **`INSTALL.md`**: per-capability instructions written for an AI agent (agent-driven and hybrid only)
- **Install mode**: deterministic, agent-driven, or hybrid; declared by the capability
- **Kind**: ai-powered, infrastructure, or hybrid; descriptive label for the capability's nature
- **Lockfile**: `pipeline.lock.yaml`, records what's actually installed
- **Pipeline manifest**: `pipeline.yaml`, declares what's desired
- **Plan**: the diff between desired and actual, ordered into stages
- **Registry**: the directory containing all available capabilities
- **Stage**: a set of operations in a plan that can run in parallel
- **Touches**: file paths or globs a capability modifies during install
- **Worktree**: a git worktree used to isolate one capability's install
