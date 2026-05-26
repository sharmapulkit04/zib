# Build Spec: Pipeline Manager

**Purpose:** Implementation blueprint. The product spec (`pipeline-manager-spec.md`) defines _what_. This defines _how_.

---

## 1. Technology Choices

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Spec says 3.11+. 3.12 has better error messages, faster startup |
| Project layout | `src/pipeline/` with pyproject.toml | Standard Python packaging, editable install |
| CLI framework | Click | Spec says Click. Simple, composable, well-documented |
| Output formatting | Rich | Spec says Rich. Tables, colors, spinners |
| Schema validation | Pydantic v2 | Spec says Pydantic. Fast, strict, good error messages |
| YAML | PyYAML | Standard. ruamel.yaml if we need round-trip preservation later |
| JSON patching | deepmerge | For `patch` step deep-merge semantics |
| TOML | tomli + tomli-w | Read + write TOML (for patch step) |
| Hashing | hashlib (stdlib) | SHA-256 for content hashing |
| Git | subprocess | Spec says subprocess. No library needed |
| Agent dispatch | subprocess | `claude -p` invocation via subprocess |
| Testing | pytest | Standard. parametrize for scenarios |
| Linting | ruff | Fast, replaces flake8 + isort + black |
| Type checking | pyright | Strict mode |

---

## 2. Project Structure

```
truss/
├── pyproject.toml
├── src/
│   └── pipeline/
│       ├── __init__.py
│       ├── cli.py                  ← Click commands (init, plan, apply, status, list, doctor, audit, reinstall, rollback)
│       ├── models.py               ← Pydantic models (manifest, lockfile, capability, plan, install result)
│       ├── registry.py             ← Read registry dir, list capabilities, resolve versions, hash content
│       ├── resolver.py             ← Diff manifest vs lockfile, dependency graph, topological sort, stage grouping
│       ├── executor.py             ← Run plan: worktrees, dispatch backends, verify, merge, update lockfile
│       ├── lockfile.py             ← Read/write/update pipeline.lock.yaml atomically
│       └── backends/
│           ├── __init__.py
│           ├── deterministic.py    ← copy, patch, append, template, run
│           └── agent.py            ← Agent subprocess dispatch
├── tests/
│   ├── conftest.py                 ← Shared fixtures (tmp registry, tmp project, git setup)
│   ├── test_models.py              ← Schema validation, parsing edge cases
│   ├── test_registry.py            ← Registry reading, version resolution, hashing
│   ├── test_resolver.py            ← Plan computation, dependency ordering, stage grouping
│   ├── test_executor.py            ← Worktree lifecycle, merge, lockfile updates (faked backends)
│   ├── test_lockfile.py            ← Atomic write, read, corruption detection
│   ├── test_deterministic.py       ← Each deterministic step: copy, patch, append, template, run
│   ├── test_agent.py               ← Agent dispatch, timeout, exit code handling
│   └── test_cli.py                 ← Click runner integration tests
├── pipeline-manager-spec.md
├── build-spec.md
└── decisions.md
```

**Not hexagonal.** This is a ~1000 LOC CLI tool. The architecture from CLAUDE.md applies to the projects this tool manages, not to this tool itself. Simple module decomposition is the right fit.

---

## 3. Data Models

### 3.1 Capability Manifest (`capability.yaml`)

```python
class CopyStep(BaseModel):
    copy: dict  # {from: str, to: str}

class PatchStep(BaseModel):
    patch: dict  # {file: str, merge: dict}

class AppendStep(BaseModel):
    append: dict  # {file: str, content: str}

class TemplateStep(BaseModel):
    template: dict  # {from: str, to: str, vars: dict}

class RunStep(BaseModel):
    run: str  # shell command

InstallStep = CopyStep | PatchStep | AppendStep | TemplateStep | RunStep

class InstallSpec(BaseModel):
    mode: Literal["deterministic", "agent-driven", "hybrid"]
    steps: list[InstallStep] | None = None        # deterministic + hybrid
    instructions: str | None = None                 # agent-driven + hybrid

class VerifyCommand(BaseModel):
    command: str

class FacetSpec(BaseModel):
    name: str
    install: InstallSpec
    touches: list[str]
    requires: list[str] | None = None

class Dependency(BaseModel):
    name: str
    version: str  # ">=v2", "~v3.1", exact

class CapabilityManifest(BaseModel):
    name: str
    version: str
    kind: Literal["ai-powered", "infrastructure", "hybrid"]
    description: str | None = None
    requires: list[Dependency] = []
    touches: list[str] = []
    install: InstallSpec | None = None              # absent if faceted
    facets: list[FacetSpec] | None = None            # absent if non-faceted
    verify: list[VerifyCommand] = []
```

### 3.2 Pipeline Manifest (`pipeline.yaml`)

```python
class PipelineManifest(BaseModel):
    pipeline: dict[str, str]     # {capability_name: version}
    registry: str = "~/capabilities/"
    config: dict[str, Any] = {}  # optional overrides
```

### 3.3 Lockfile (`pipeline.lock.yaml`)

```python
class FacetLockEntry(BaseModel):
    install_mode: str
    installed_at: datetime
    files_touched: list[str]
    diff_hash: str
    installer: str

class LockEntry(BaseModel):
    version: str
    kind: str
    install_mode: str | None = None             # non-faceted
    content_hash: str
    install_hash: str | None = None
    installed_at: datetime | None = None        # non-faceted
    files_touched: list[str] | None = None      # non-faceted
    installer: str | None = None                # non-faceted
    diff_hash: str | None = None                # non-faceted
    state: str | None = None                    # faceted: "complete" | "partial"
    facets: dict[str, FacetLockEntry] | None = None

class PipelineLockfile(BaseModel):
    installed: dict[str, LockEntry] = {}
```

### 3.4 Plan

```python
class Operation(BaseModel):
    type: Literal["install", "upgrade", "reinstall", "remove"]
    capability: str
    from_version: str | None = None
    to_version: str | None = None
    install_mode: str
    capability_manifest: CapabilityManifest

class Stage(BaseModel):
    operations: list[Operation]

class Plan(BaseModel):
    stages: list[Stage]

    @property
    def total_operations(self) -> int: ...

    @property
    def is_empty(self) -> bool: ...
```

### 3.5 Install Result

```python
class InstallResult(BaseModel):
    success: bool
    files_touched: list[str]
    diff_hash: str | None = None
    error: str | None = None
    installer: str
```

---

## 4. Module Contracts

### 4.1 `registry.py`

```python
def load_registry(registry_path: Path) -> dict[str, list[str]]
    """Returns {capability_name: [version1, version2, ...]}"""

def load_capability(registry_path: Path, name: str, version: str) -> CapabilityManifest
    """Load and validate one capability manifest."""

def content_hash(registry_path: Path, name: str, version: str) -> str
    """SHA-256 of all files in the capability folder."""

def resolve_version(available: list[str], constraint: str) -> str | None
    """Resolve a version constraint to a concrete version."""
```

### 4.2 `resolver.py`

```python
def compute_plan(
    manifest: PipelineManifest,
    lockfile: PipelineLockfile,
    registry_path: Path,
) -> Plan
    """Diff desired vs actual, build dependency graph, topological sort, group into stages."""
```

Pure function. No I/O except registry reads (passed in or loaded).

### 4.3 `executor.py`

```python
def execute_plan(
    plan: Plan,
    project_root: Path,
    lockfile_path: Path,
    registry_path: Path,
    parallel: int = 4,
    dry_run: bool = False,
    agent_name: str = "claude-code",
) -> list[InstallResult]
    """Execute plan stage by stage. Returns results per operation."""
```

Owns git worktree lifecycle. Dispatches to backends. Updates lockfile.

### 4.4 `backends/deterministic.py`

```python
def execute_deterministic(
    steps: list[InstallStep],
    capability_root: Path,
    worktree_root: Path,
) -> InstallResult
    """Execute deterministic install steps in sequence."""
```

### 4.5 `backends/agent.py`

```python
def execute_agent(
    install_md_path: Path,
    capability_root: Path,
    worktree_root: Path,
    operation_type: str,
    capability_name: str,
    capability_version: str,
    lock_entry: LockEntry | None,
    agent_name: str = "claude-code",
    timeout: int = 600,
) -> InstallResult
    """Dispatch AI agent in headless mode."""
```

### 4.6 `lockfile.py`

```python
def read_lockfile(path: Path) -> PipelineLockfile
    """Read and validate lockfile. Returns empty if not found."""

def write_lockfile(path: Path, lockfile: PipelineLockfile) -> None
    """Atomic write: temp file + rename."""

def update_entry(path: Path, name: str, entry: LockEntry) -> None
    """Update one entry atomically."""
```

---

## 5. Implementation Phases

### Phase 1: Foundation (init, list, doctor, plan)

**What:** Project scaffolding, registry reading, plan computation. No installation yet.

**Build order:**
1. `pyproject.toml` + project skeleton
2. `models.py` — all Pydantic schemas
3. `registry.py` — read registry, list capabilities, content hashing
4. `lockfile.py` — read/write lockfile
5. `resolver.py` — compute plan (diff, dependency graph, stages)
6. `cli.py` — `init`, `list`, `doctor`, `plan` commands

**Tests:**
- `test_models.py` — valid/invalid manifests, edge cases
- `test_registry.py` — registry discovery, version resolution
- `test_lockfile.py` — atomic write, read, empty state
- `test_resolver.py` — plan computation scenarios (install, upgrade, remove, dependencies, staging)
- `test_cli.py` — CLI smoke tests via Click test runner

**Checkpoint:** `pipeline init` creates files. `pipeline list` reads registry. `pipeline plan` prints a correct plan.

### Phase 2: Deterministic Backend (apply for deterministic capabilities)

**What:** Execute deterministic installs. Full git worktree lifecycle.

**Build order:**
1. `backends/deterministic.py` — copy, patch, append, run steps
2. `executor.py` — worktree create, dispatch backend, capture diff, verify, merge, lockfile update
3. `cli.py` — `apply` command, `status` command

**Tests:**
- `test_deterministic.py` — each step type in isolation (copy files, merge JSON/YAML, append text, run commands)
- `test_executor.py` — full install flow with faked backend (worktree lifecycle, merge, lockfile)

**Checkpoint:** `pipeline apply` installs a deterministic capability end-to-end. Lockfile updated. Git branch merged.

### Phase 3: Agent Backend (apply for agent-driven capabilities)

**What:** Dispatch AI agent for installs.

**Build order:**
1. `backends/agent.py` — construct prompt, spawn subprocess, capture result
2. Update `executor.py` to dispatch to agent backend based on install mode
3. Handle hybrid mode (deterministic then agent)

**Tests:**
- `test_agent.py` — prompt construction, subprocess mock, timeout handling, exit code mapping

**Checkpoint:** `pipeline apply` works for all three install modes.

### Phase 4: Remaining Commands (audit, reinstall, rollback)

**What:** Drift detection, reinstall, rollback.

**Build order:**
1. `cli.py` — `audit` command (rehash files, compare to lockfile)
2. `cli.py` — `reinstall` command (force re-run)
3. `cli.py` — `rollback` command (revert to previous version)
4. History tracking in `.pipeline/history/`

**Tests:**
- Drift detection scenarios
- Reinstall with version unchanged
- Rollback to previous version

**Checkpoint:** Full command suite operational.

---

## 6. Git Operations

The executor owns all git interactions. Exact commands:

```bash
# Create worktree for a capability install
git worktree add .pipeline-worktrees/{name}-{version} -b pipeline/install-{name}-{version}

# After install, capture diff
git -C .pipeline-worktrees/{name}-{version} diff HEAD

# Add and commit changes in worktree
git -C .pipeline-worktrees/{name}-{version} add -A
git -C .pipeline-worktrees/{name}-{version} commit -m "pipeline: install {name} {version}"

# Merge back to working branch
git merge --no-ff pipeline/install-{name}-{version} -m "pipeline: install {name} {version}"

# Clean up worktree
git worktree remove .pipeline-worktrees/{name}-{version}
git branch -d pipeline/install-{name}-{version}
```

---

## 7. Agent Dispatch

The prompt sent to the agent for an install:

```
You are installing a project capability. Follow the instructions exactly.

Operation: {install|upgrade|reinstall}
Capability: {name} {version}
Capability folder: {path}

{contents of INSTALL.md}

Rules:
- Do NOT commit changes (the orchestrator handles git)
- Do NOT push to remote
- Do NOT modify files outside what INSTALL.md describes
- Do NOT modify pipeline.yaml or pipeline.lock.yaml
- Stay within scope. Do not invent features.
```

For upgrades, append:

```
Previous version: {from_version}
Previously touched files: {files_touched from lockfile}
```

Invocation:

```bash
claude -p "{prompt}" \
  --cwd {worktree_path} \
  --allowedTools "Read,Write,Edit,Glob,Grep,Bash" \
  --permission-mode acceptEdits \
  --max-turns 25
```

---

## 8. Testing Strategy

**No hexagonal testing pyramid.** This is a CLI tool. Testing is practical:

| Level | What | How | Count |
|---|---|---|---|
| Unit | Models, registry, resolver, lockfile, deterministic steps | Pure pytest, no I/O fixtures | 40-60 |
| Integration | Executor (worktree lifecycle), CLI commands | tmp_path + real git repo fixture | 15-25 |
| E2E | Full `pipeline apply` flow | Real registry, real git, mocked agent subprocess | 5-10 |

**Key fixture:** A reusable pytest fixture that creates:
- A tmp directory as project root with `git init`
- A tmp directory as registry with sample capabilities (deterministic + agent-driven)
- Pre-populated `pipeline.yaml`

**Agent tests mock subprocess** — we don't call real Claude in tests. The mock verifies prompt construction and handles exit codes.

---

## 9. What's Deferred

These are explicitly NOT in the first build:

- Facets (Section 9 of product spec) — build when a real capability needs it
- `template` step — build when a real capability needs it
- Parallel stage execution — build after serial works
- OTel instrumentation — build after core works
- Version constraint resolution (semver) — exact match only in v0.1
- `.pipeline/history/` — build with rollback
- File lock for concurrent apply — build when it matters
- Hidden Unicode / prompt-injection scanning — build after core works

---

## 10. Sample Registry for Development

Create this at `~/capabilities/` to test against:

```
~/capabilities/
├── hello-world/
│   └── v1/
│       ├── capability.yaml       ← deterministic, copies one file
│       └── hello.txt
├── observability/
│   └── v1-basic/
│       ├── capability.yaml       ← deterministic, copy + patch + append
│       ├── otel/
│       │   └── setup.py
│       └── verify.sh
└── spec-generation/
    └── v1-simple/
        ├── capability.yaml       ← agent-driven
        └── INSTALL.md
```

This gives us one trivial deterministic, one real deterministic, and one agent-driven capability to develop against.

---

## 11. Dependencies (pyproject.toml)

```toml
[project]
name = "pipeline-manager"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "click>=8.1",
    "rich>=13.0",
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "deepmerge>=1.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-tmp-files>=0.0.2",
    "ruff>=0.4",
    "pyright>=1.1",
]

[project.scripts]
pipeline = "pipeline.cli:cli"
```
