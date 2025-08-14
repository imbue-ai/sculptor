# Sculptor: run parallel Claude Code agents in safe, local sandboxes

Sculptor lets you run simultaneous Claude Code agents in safe, isolated sandboxes. Sculptor runs locally, letting you iterate quickly in your chosen IDE without going through PRs. We’re currently alpha testing Sculptor and are excited to hear what you think!

### Kick off agents in parallel

Sculptor is a web UI for creating and managing multiple agents. Each agent runs in its own isolated sandbox with a clone of your repo, so you can experiment and make changes safely. Desktop app coming soon!

### Test & edit agent changes locally

Sync to any agent’s sandbox to instantly see its file changes in your local IDE. This lets you review, run, test, and edit the agent’s changes in your local environment while it's working in a sandbox, giving you the best of both worlds.

### Easily merge changes & resolve conflicts

Quickly merge the agent branches that you like. Sculptor agents can help you resolve any merge conflicts that arise.

### See the power of Sculptor in this behind-the-scenes demo 🤓
See it all come together in this behind-the-scenes demo from one of our product engineers, Guinness:

[![A demo of what is possible with Sculptor](https://img.youtube.com/vi/ESZH7hd1sMY/0.jpg)](https://www.youtube.com/watch?v=ESZH7hd1sMY)

Sculptor is built by all of us at [Imbue](https://imbue.com).

# Installation & setup
> [!IMPORTANT]
> Join our [Discord](https://discord.gg/sBAVvHPUTE) for dedicated support and up-to-date info from the Imbue team! Our whole team's in Discord with you, building Sculptor with Sculptor 🙂

### 1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [mutagen](https://mutagen.io/documentation/introduction/installation/):

**Via Homebrew (Mac or Linux)**:

```bash
brew install uv
brew install mutagen-io/mutagen/mutagen
```

**On Linux**:

```bash
pipx install uv # OR pip install uv
```

Install the [appropriate latest released binary for Mutagen](https://github.com/mutagen-io/mutagen/releases)


### 2. Install [Docker](https://www.docker.com/get-started/):

**On Mac**:
[Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/)

- Ensure your Docker version is 27 or higher according to `docker --version`
- Go to Settings > General > Virtual Machine Options after download and set “Virtual Machine Manager” to `Docker VMM`

**On Linux**:
Do *not* install Docker Desktop.

- Instead, install Docker Engine by [following the instructions here](https://docs.docker.com/engine/install/)


### 3. Run Sculptor
*Note: You'll need an Anthropic API key and git repository to use Sculptor.*

```bash
# Change directory to your code repository
cd /to/your/repo

# Run Sculptor
uvx --with https://imbue-sculptor-latest.s3.us-west-2.amazonaws.com/sculptor.tar.gz --refresh sculptor .
```

### 4. Configure your settings
As a beta tester, you'll be opted in to send error logs and telemetry data. Let us know if this is an issue or if you need more information about this! 🙏


# Community
### Discord

As an early tester, we highly recommend that you join our [Discord](https://discord.gg/sBAVvHPUTE) community to get direct support from the Imbue team. Some interesting channels:

- `#bugs-and-support`: Get quick support from the Imbue team
- `#behind-the-scenes`: Watch how the sausage gets made as our team uses Sculptor to build Sculptor
- `#show-and-tell`: See what other people have created with Sculptor, and share your own Sculptures

### Talk with us

We’re always here for you! If you run into any issues or just want to chat with the team, [book time](https://calendly.com/nicseo/sculptor-chat) with us!


# Basic workflows

## Starting your first task

1. On the main task list page, describe your task to the agent.
2. Press “Start task” or cmd+Enter to start the task.
    1. Simply pressing Enter will start a new line in your task description.
3. Your new task will appear in the task list. Click into it to see the changes as the agent works.

<img width="2048" height="1326" alt="image" src="https://github.com/user-attachments/assets/d39dc6f7-91fe-4819-9954-0755f3d79778" />


## Reviewing the agent’s changes

1. Local sync to the agent’s task branch. Its changes are now synced to your local repository so you can review them in your IDE of choice!
2. While synced, make as many changes as you like by following up with the agent in the task chat or making changes by hand in your IDE.
3. Once you’re happy, unsync from the agent’s task branch.

Local sync from the main task list:
<img width="1024" height="663" alt="image" src="https://github.com/user-attachments/assets/d9605813-6d3a-48a6-a438-fbff46e01464" />

Local sync from a task’s page:
<img width="1024" height="663" alt="image" src="https://github.com/user-attachments/assets/b96d8900-7750-4b70-951d-a403d8e0354f" />

## Merging the agent’s changes

1. **Make sure you are unsynced from the agent’s task branch before proceeding.**
2. Ask the agent to commit and push changes in the task chat.
    1. Tip: Add the instruction `commit and push your changes to the sculptor remote when you're done` to your system prompt!
3. Check out the branch you want to merge into, e.g. `git switch main`.
4. Copy the merge command and run in your terminal. The command is:
    1. `git merge sculptor/your-task-branch-name`

## Resolving merge conflicts

Follow these steps if you run into merge conflicts when merging the agent’s changes:

**With git (recommended)**

1. Run `git merge --abort` to back out of the merge conflict in your repo.
2. Run `git push sculptor main` in your terminal.
3. In the task chat, tell the agent to pull, merge `sculptor/main`, resolve conflicts, commit, and push.
4. From your repo, run the usual merge command (`git merge sculptor/your-task-branch-name`)
- **With local sync**
    1. Run `git merge --abort` to back out of the merge conflict in your repo.
    2. Local sync to the conflicting task.
    3. Run `git merge main` in your terminal.
    4. Ask the agent to resolve the conflict but not to commit.
        1. If it does commit accidentally, no sweat! Run `git merge -s ours main` in your terminal instead of the next step.
    5. Run `git commit` in your terminal when it is done.
    6. Un-sync and run `git merge sculptor/your-task-branch-name`.

# Advanced workflows

## Changing the system prompt

Agents follow explicit directions extremely well, so the system prompt is the perfect place to include general context like project details, relevant subdirectories, or specific coding guidelines. You can customize your system prompts at any time, either for all messages or on a per-message basis.

- **Example system prompts**
    
    ```markdown
    # Planning system prompt
    
    Don't write any code until I've approved the implementation or design strategy. For each request, propose 2-3 alternative strategies, architectures, or designs, clearly outlining tradeoffs for each. Recommend the best approach and actively ask clarifying questions to resolve ambiguities. I'd prefer extra discussion over incorrect assumptions.
    
    # Code implementation system prompt
    
    Implement the task exactly as described. If you encounter any ambiguity (unknown unknowns), pause immediately to request clarification. I'd rather clarify upfront than proceed based on incorrect assumptions. Write self-documenting code, adding comments only when necessary to explain the "why" behind specific implementation choices.
    
    # Debugging system prompt
    
    Thoroughly review all relevant code, deeply analyze potential causes, and formulate 2-3 hypotheses explaining the bug. For each hypothesis, identify specific locations for adding detailed logging to empirically validate them. Insert extensive logs accordingly. After adding logs, prompt me clearly about what tests or actions I should perform. I'll run these tests and share the logs with you. Use these results to draw conclusions and report back with your findings.
    ```
    
Updating the system prompt from the main task list page:
<img width="2048" height="1326" alt="image" src="https://github.com/user-attachments/assets/497b44a8-430e-4c45-b249-a66017b10f7e" />

Updating the system prompt from an individual task page:
<img width="2048" height="1326" alt="image" src="https://github.com/user-attachments/assets/63b6f810-4f39-47b5-8382-efc4c63226b8" />

## Steering with inline TODOs

Inline TODOs or FIXMEs are one of the most reliable ways to steer the agent when iterating on real code. Because LLMs attend better to instructions **near the relevant code**, inline notes are often more effective than chat prompts alone. 

To use inline TODOs:

- Local sync to the task you want to update
- Add TODOs or comments near the code you want the agent to modify
- Tell the agent where to look (e.g. “Check foo.py for TODOs”)

## Adding custom dependencies

If you’re trying to run Sculptor on languages that aren’t pre-baked into the Docker container, follow these instructions! We have some upcoming features that will make this flow nicer, but for now, this should do the trick.

1. Make a `<repo>/.sculptor/user_setup.sh` file and commit it in your local repo.
    1. Inside it, place any set up commands you need, e.g. `pip install ...` as well as sudo commands like `sudo apt update && sudo apt install -y vim`.
    2. Tip: A good way to make this script is to ask Sculptor to write the script inside the task where it’s having trouble with dependencies. For example:
        
        ```markdown
        Give me a /.sculptor/user_setup.sh script for prebaking useful dependencies for a project that involves <java/kotlin/maven/gradle>. For use on an ubuntu dockerfile. It will run as a non-root user but that user will have passwordless sudo privileges. Then commit that file as ~/.sculptor/user_setup.sh
        ```
        
2. Start a new task. 
    1. Note: There is currently no way to retroactively install dependencies that require sudo into an existing task.
    2. After the container for your task finishes building, go to the “Logs” tab. The output of your `user_setup.sh` script should appear there.
    3. All other future tasks will also have the `user_setup.sh` run on task creation.

*More advanced workflows coming soon!*

# License
© Imbue, Inc. All rights reserved. Use is subject to Imbue's [Research Preview Terms of Service](https://imbue.com/terms/).
