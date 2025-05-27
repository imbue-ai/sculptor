# Sandbox Design Doc

## Motivation
We are creating a minimal interface to create and manage sandboxes. The goal is to support creating sandbox containers and running commands in them. We cut out much of the unneeded complexity from the old sandbox service.

## Core Types

### Image
A pre-built environment that sandboxes are created from.

- **Local**: Path to source code directory
  - The entire directory is copied verbatim, including dependencies (venv, node_modules, etc.)
  - No build step - assumes the directory is self-contained and ready to run
  - For more sophisticated setups (system dependencies, build steps), use Modal or Docker providers

- **Modal**: Container image with dependencies
  - Built from Dockerfile with full dependency management
  - Supports system packages, build steps, and complex environments

- **Docker**: Dockerfile-based image
  - Built from local Dockerfile
  - Full control over base image and dependencies
  - Runs locally with Docker daemon

### Sandbox
An isolated environment for running code.
- **Local**: Directory in `~/.crafty/local_sandboxes/`
- **Modal**: Remote container on Modal infrastructure
- **Docker**: Local Docker container with persistent state

### Process
A command running inside a sandbox with its own tmux session.

## Architecture

### Executor Pattern
Abstract interface implemented by each provider:
```python
class Executor:
    def run_command(command: str) -> CommandProcess
    def is_alive() -> bool
    def read_file(path: str) -> str
    def write_file(path: str, content: str) -> None
```

### Key Design Decisions

1. **Unified Process Model**: Every process gets its own tmux session, regardless of provider. This enables consistent attach/detach behavior.

3. **Streaming Output**:
   - **Local**: Direct stdout/stderr capture
   - **Docker**: Captures output via temporary files in container
   - **Modal**: Two-phase approach for foreground processes:
     ```bash
     # Phase 1: Create tmux session with output piping
     tmux new-session -d -s {name} "tmux pipe-pane 'cat >> /root/output_{name}.log'; bash"
     tmux send-keys -t {name} "{command}" C-m

     # Phase 2: Stream output back (runs in foreground)
     tail -f /root/output_{name}.log
     ```

## Usage Flow

1. Create image from code
2. Create sandbox from image
3. Launch processes in sandbox (foreground or background)
4. Attach to running processes
5. Kill processes or entire sandbox

## Interface

```python
# Image operations
create_image(file_path: str, clean: bool, provider: Provider) -> str
list_images() -> Tuple[str, ...]

# Sandbox operations
create_sandbox(image_id: str, provider: Provider) -> str
list_sandboxes(list_all: bool = False) -> Tuple[str, ...]
connect_to_sandbox(sandbox_id: str) -> None
terminate_sandbox(sandbox_id: str) -> None

# Process operations
launch_background_process(name: str, sandbox_id: str, command: str) -> None
launch_and_stream_process(name: str, sandbox_id: str, command: str) -> Generator[str, None, None]
list_processes(list_all: bool = False) -> Tuple[str, ...]
attach_to_process(name: str, sandbox_id: str) -> None
kill_process(name: str, sandbox_id: str) -> None
```

## Implementation Notes

### Database Schema

```python
# Base classes
class ImageRecord(BaseDataModel):
    pass

class SandboxRecord(BaseDataModel):
    is_closed: bool = False

class ProcessRecord(BaseDataModel):
    name: str
    sandbox_id: str
    is_terminated: bool = False

# Provider-specific records
class LocalImageRecord(ImageRecord):
    image_path: Path

class ModalImageRecord(ImageRecord):
    modal_image_id: str

class LocalSandboxRecord(SandboxRecord):
    sandbox_path: Path
    tmux_session_name: str

class ModalSandboxRecord(SandboxRecord):
    modal_sandbox_id: str

class DockerImageRecord(ImageRecord):
    docker_image_id: str
    docker_image_tag: str

class DockerSandboxRecord(SandboxRecord):
    container_id: str
    container_name: str
```

### Other Notes

- Process names must be unique within a sandbox
- Database tracks all entities with their provider-specific IDs
- Local sandboxes copy code to avoid mutations
- Modal sandboxes run SSH server for interactive access
