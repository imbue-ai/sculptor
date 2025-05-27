# job_control

job_control is a distributed job control orchestrator.

It is designed to manage images, sandboxes, and processes running locally or in the cloud.

## Features

- Create and manage images, sandboxes, and both local and remote processes
- Snapshot existing sandboxes and restore them later
- Easily connect to any running sandbox or process
- Runs processes in tmux in order to collect output from interactive processes (while enabling stdin)
- Supports fully hierarchical trees of sandboxes and processes with "structured concurrency" semantics
- Continually syncs logs and output from remote processes
- Support modal, fly.io, docker, and "local" sandboxes

# Architecture

- Uses tmux to run processes remotely in a way where they can be attached to later
- Uses rsync to sync files and directories between local and remote machines
- Uses SSH to connect to remote machines

# Interface

```
image: commands related to sandbox images
    create: create a new image
        file_path: the path to the file to use for defining the commands with which to build the image.  If not defined, will search for a file with the correct name (ex: Dockerfile)
        --provider=(local|modal|fly|docker)
        --clean=(false/f/0|true/t/1): if false (default), may re-use cached layers.  If true, will rebuild the image from scratch.
        --shared=(true/t/1|false/f/0): if true (default), only allows a single image to build at once.  If false, will always build the image independently.
        --sandbox-*: prefix to all sandbox args, since sandboxes sometimes need to be created in order to create an image
        --arg key=value: in order to specify non-standard arguments for any given provider
    list: list all images
        --provider=(local|modal|fly|docker|all)
        --fields=...: specify which fields you want to display, in order (comma-separated)
        --format=(table|json): how to output the list
    destroy: destroy some image(s)
        image_id(s): the id(s) of the image(s) to destroy
sandbox: commands related to sandboxes
    create: create a new sandbox
        image_id: if defined, use the specified image. Otherwise will first build the image (see `image create`)
        --provider=(local|modal|fly|docker)
        --cpus=int: min CPU count in the sandbox
        --mem|--mem-gb=float: min GB of memory to require in the sandbox
        --mem-mb: min MB of memory to require in the sandbox
        --arg key=value: in order to specify non-standard arguments for any given provider
        --image-*: the image args (in order to customize any call to `image create`)
    list: list all sandboxes
        (same as image listing, but for sandboxes)
    connect: connect to a sandbox via SSH
        sandbox_id: required. specifies which sandbox to connect to
        --ssh-*: will be passed through as an ssh arg
    snapshot: create a snapshot of a sandbox
        sandbox_id
    sync [up|down]: sync files to/from a sandbox
        sandbox_id
        --rsync-*: passed through to rsync
    destroy: destroy some sandbox(es)
        sandbox_id(s): the id(s) of the sandbox(es) to destroy
process: commands related to processes
    create: create a new process
        image_id: if defined, use the specified image. Otherwise will first build the image (see `image create`)
        sandbox_id: if defined, use the specified sandbox. Otherwise will first create the sandbox (see `sandbox create`)
        --image-*: the image args (in order to customize any call to `image create`)
        --sandbox-*: prefix to all sandbox args, since sandboxes sometimes need to be created in order to create an image
    list: list all processes
        (same as image listing, but for sandboxes)
    attach: attach to a process via SSH
        process_id: required. specifies which process to connect to
        --ssh-*: will be passed through as an ssh arg
    destroy: destroy some process(es)
        process_id(s): the id(s) of the process(es) to destroy
```
