# Sculptor: the missing UI for Claude Code

Run parallel Claudes safely in containers. Jump between their environments to instantly test changes. Get suggestions that catch critical issues as you go.

<div align="center">
<table>
<tbody>
<td align="center">
<a href="https://imbue-sculptor-releases.s3.us-west-2.amazonaws.com/sculptor/Sculptor.dmg" target="_blank"><strong>Download for Mac (Apple Silicon)</strong></a>
</td>
<td align="center">
<a href="https://discord.gg/sBAVvHPUTE" target="_blank"><strong>Join us on Discord</strong></a>
</td>
</tbody>
</table>
</div>


<p align="center">
  <img width="1312" height="912" alt="Sculptor Demo" src="assets/demo.gif" />
</p>

### Spin up parallel agents

Each Claude works in its own container. You get safe execution and parallel agents without the hassle of git worktrees. You can even tell them, “Don't come back until my tests pass.”

### Instantly pair with any agent

Toggle Pairing Mode to move between any agents' containers. Run, test, and edit each agent's changes from your normal dev environment — no need to switch workspaces.

### Merge without conflicts

Merge the changes you like and throw out the ones you don't. Sculptor helps you resolve merge conflicts.

### See the power of Sculptor's Pairing Mode 🤓
See it all come together in this behind-the-scenes demo from one of our product engineers, Guinness:

<p align="center">
  <a href="https://www.youtube.com/watch?v=ESZH7hd1sMY">
    <img width="1312" height="738" alt="A demo of what is possible with Sculptor" src="https://img.youtube.com/vi/ESZH7hd1sMY/0.jpg" />
  </a>
</p>

[![A demo of what is possible with Sculptor](https://img.youtube.com/vi/ESZH7hd1sMY/0.jpg)](https://www.youtube.com/watch?v=ESZH7hd1sMY)

Sculptor is built by the team at [Imbue](https://imbue.com).

# Download Sculptor

> [!IMPORTANT]
> Join our [Discord](https://discord.gg/sBAVvHPUTE) for dedicated support and up-to-date info from the Imbue team! Our whole team's in Discord with you, building Sculptor with Sculptor 🙂

<strong>[Download Sculptor for OSX with Apple Silicon here ->](https://imbue-sculptor-releases.s3.us-west-2.amazonaws.com/sculptor/Sculptor.dmg)</strong>

Instructions for Apple Silicon (OSX arm64) follow. Apple Intel and Linux instructions will be updated shortly!

## 1. Running Sculptor
*Note: You'll need an Anthropic account to use Sculptor.*

1. Download the .dmg from [here](https://imbue-sculptor-releases.s3.us-west-2.amazonaws.com/sculptor/Sculptor.dmg) and double-click to unpack it into your /Applications folder.

2. Enter your email and you should get to the installation wizard. To run Sculptor, you'll need to install Docker Desktop. We'll also install git and mutagen for you, if you already don't have them. As a beta tester, you'll be opted in to send error logs and basic product usage data. Let us know if this is an issue or if you need more information about this! 🙏

<p align="center">
  <img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 07 09 PM" src="https://github.com/user-attachments/assets/05d9a6fe-d91a-49e3-9b01-2ff31362c5e0" />
</p>

4. Provide the Anthropic credentials you'll be using. We plan on pushing out an update soon that allows Claude auth sign-in so you can use your Claude Pro and Max plans!

5. Select the repo you wish to work on. Don't worry, you can select a second repo later and switch between them freely! If there's no git repo installed there, we'll install one.

## Installing Docker
**On Mac**:
[Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/)

- Ensure your Docker version is 27 or higher according to `docker --version`
- Go to Settings > General > Virtual Machine Options after download and set “Virtual Machine Manager” to `Docker VMM`

**On Linux**:
Do *not* install Docker Desktop.

- Instead, install Docker Engine by [following the instructions here](https://docs.docker.com/engine/install/)


# Community
### Discord

As an early tester, we highly recommend that you join our [Discord](https://discord.gg/sBAVvHPUTE) community to get direct support from the Imbue team. Some interesting channels:

- `#help-and-bugs`: Get quick support from the Imbue team
- `#show-and-tell`: Share wow moments, workflows, tips, and Sculptures you're creating!
- `#behind-the-scenes`: Watch how the sausage gets made as our team uses Sculptor to build Sculptor

### Talk with us

We’re always here for you! If you run into any issues or just want to chat with the team, [book time](https://calendly.com/nicseo/sculptor-chat) with us!

# Basic workflows

## Creating agents

1. On your projects homepage, describe your task to the agent.
2. Press “Start task” or CMD+Enter to start the task. Press Enter to start a new line in your task description.
3. Your new agent will appear in the sidebar. Click into it to see the changes as the agent works.

<p align="center">
  <img width="1840" height="1191" alt="Screenshot 2025-09-17 at 5 25 12 AM" src="https://github.com/user-attachments/assets/6c94daef-c100-4d4f-9e2b-27a0bff37352" />
</p>

When you’re viewing an agent’s task, you can press the + New Agent button or cmd+N to quickly create a new agent.

<p align="center">
  <img width="2000" height="765" alt="sculptor_new-agent" src="https://github.com/user-attachments/assets/533f6399-a3ef-49d6-96af-5063d1219705" />
</p>

Note: for now, your first agent will take about a minute to start. We're working on making it instant!

## Test the agent’s changes with Pairing Mode
Each agent runs in a safe container with a copy of your repo. Their branch lives in the container. Pairing Mode lets you bring an agent's branch into your IDE so you can instantly test its changes, while it sees your edits in real-time. When you turn it on, it checks out the agent's branch locally and keep your files + git state synced.

1. Click the Pairing Mode button in the sidebar or the top right corner to turn it on

<p align="center">
  <img width="2000" height="632" alt="pairing mode" src="https://github.com/user-attachments/assets/2989e130-9995-48b6-9e50-7657c33bb0b4" />
</p>

2. Run the agent’s code, run terminal commands, make edits in your IDE, or keep working with the agent in chat while in Pairing Mode. Any local changes you make will sync back to the agent’s branch and persist after turning off Pairing Mode.

<p align="center">
  <img width="2000" height="698" alt="Screenshot 2025-09-17 at 5 36 25 AM" src="https://github.com/user-attachments/assets/5bd92f8e-985e-4ac1-afb3-97d643926565" />
</p>

Note: Currently Pairing Mode will be disabled if you have uncommitted or unstashed changes in your current local branch. Stash or commit changes to enable Pairing Mode using `git stash --include-untracked`.

<p align="center">
  <img width="1601" height="506" alt="Screenshot 2025-09-17 at 5 33 27 AM" src="https://github.com/user-attachments/assets/3d8c3ac8-ebb6-412e-b5ef-134b733403b0" />
</p>

## Merging the agent’s changes

1. Turn off Pairing Mode to switch your local state back to where it was.

<p align="center">
  <img src="https://github.com/user-attachments/assets/3e4799fc-a3dc-4783-bc9f-9874661b19de" alt="Image 1" width="45%" style="vertical-align: top;" />
  <img src="https://github.com/user-attachments/assets/ea86c597-15d4-4965-b82c-73b89eee4869" alt="Image 2" width="45%" style="vertical-align: top;"/>
</p>

2. Commit the agent’s changes in Sculptor.

<p align="center">
  <img width="60%" alt="Screenshot 2025-09-17 at 5 37 45 AM" src="https://github.com/user-attachments/assets/c129b2cf-ea60-490f-8379-9fe24c281dd0" />
</p>

3. Press the Merge button in the top right corner, select your target branch, and pull the agent’s changes.

<p align="center">
  <img width="60%" alt="pull agent changes" src="https://github.com/user-attachments/assets/7c30fdb1-fc29-48dd-9b45-1498f90ed386" />
</p>

For power users: you can also commit and merge the agent's changes locally while Pairing Mode is on using `git commit` on the branch, checking out the target branch, and `git merge <source-branch>`.

## Resolving merge conflicts

If you expect merge conflicts, the agent can help you resolve them! 
1. Push your target branch to the agent’s branch using the Merge panel.
2. Tell the agent to resolve any merge conflicts that arise.
3. After it’s done, merge the agent branch into your target branch as described in the last section (Merging the agent’s changes).

<p align="center">
  <img width="60%" alt="push agent changes" src="https://github.com/user-attachments/assets/9b8cf01a-bfd0-48ff-b756-8e5cb457ea9d" />
</p>

<p align="center">
  <img width="2000" height="461" alt="Screenshot 2025-09-17 at 5 48 24 AM" src="https://github.com/user-attachments/assets/e4b55480-76a0-41fd-bfcb-654d0feb2dc4" />
</p>

If you try merging the agent's branch into your target branch, and merge conflicts arise, you will see this dialog. Choose whether to force merge or abort if there are conflicts that can’t be resolved.

<p align="center">
  <img width="1840" height="1191" alt="Screenshot 2025-09-17 at 5 47 04 AM" src="https://github.com/user-attachments/assets/aca9db5b-782b-437b-ae5c-75d9f4268789" />
</p>





# Advanced workflows

## @autocomplete file and folder names

Anytime during a task, @mention a part of a filename to autocomplete it.

<p align="center">
  <img width="1312" height="912" alt="Screenshot 2025-09-16 at 9 07 40 PM" src="https://github.com/user-attachments/assets/778b8821-624a-4f1d-96aa-c056840bcb1b" />
</p>

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

You can update the system prompt from the main task list page, or from an individual task page.

## Steering with inline TODOs

Inline TODOs or FIXMEs are one of the most reliable ways to steer the agent when iterating on real code. Because LLMs attend better to instructions **near the relevant code**, inline notes are often more effective than chat prompts alone.

To use inline TODOs:

- Local sync to the task you want to update
- Add TODOs or comments near the code you want the agent to modify
- Tell the agent where to look (e.g. “Check foo.py for TODOs”)


## Context compaction

If your task conversation gets too long, click into the context meter and choose "compact".

<p align="center">
  <img width="1312" height="912" alt="Screenshot 2025-09-16 at 9 05 58 PM" src="https://github.com/user-attachments/assets/cef578cd-c6d0-4bf5-8e81-26713f889a05" />
</p>

## Custom dockerfile

Sculptor agents use the same environment as your development, CI/CD, and Github Codespaces by supporting devcontainer specifications.

**Quick start:**
- **No dockerfile, using uv + npm + bash?** Things should just work with our default environment
- **Need to preinstall other dependencies but don't have a dockerfile?** Ask Sculptor to generate a devcontainer and Dockerfile, commit it, then start another task
- **Already have a dockerfile?** Check the build logs to see if Sculptor can use it successfully

### How to use it

Sculptor will automatically use your devcontainer configuration if you have a `devcontainer.json` file at either:
- `/.devcontainer/devcontainer.json`
- `/devcontainer.json`

Without a devcontainer file, we use the default Sculptor environment (Ubuntu-based with Python and `uv`).

**Supported devcontainer fields:**
- `build.dockerfile` - Points to a Dockerfile in your repository
- `image` - Single docker image reference (e.g., `ubuntu:24.04`, `python-slim`)

```json
{
  "name": "dev",
  "image": "node:latest"
}
```

or

```json
{
  "name": "dev",
  "build": {
    "dockerfile": "Dockerfile"
  }
}
```

```Dockerfile
FROM node:latest

# if you need environment variables -- inject them here
ENV NODE_OPTIONS='--max-old-space-size=4096'

RUN node --version
```

### Requirements for your image

**Supported base images:** Ubuntu, Debian, and other Linux distributions

**Required tools:** Your image must include `cat`, `chmod`, and `ln` (included in standard distributions)

**Network access:** Internet access required for LLM communication

**For sudo support (optional):**
```dockerfile
RUN apt-get install -y --no-install-recommends sudo
RUN echo "ALL ALL=(ALL:ALL) NOPASSWD:ALL" >> /etc/sudoers
```

### How it works

- We `docker build` your devcontainer for every new Sculptor task
- Build logs are visible in Sculptor's logs panel  
- Uses current code state when the task starts
- Same container persists for the entire task duration
- Processes run with matching user/group IDs from your host (you may see `user501` on macOS)

**Current limitations:**
- No support for custom Linux user IDs
- No post-container start scripts support

## Task error recovery

Hit an unexpected error with Sculptor? Contact us on [Discord](https://discord.gg/sBAVvHPUTE) to report the issue and see if others have hit it — but in the meantime, try asking Sculptor to restart the task from the latest snapshot.

<p align="center">
  <img width="993" height="802" alt="Screenshot 2025-09-16 at 9 12 16 PM" src="https://github.com/user-attachments/assets/68fe0e15-e364-4f87-9572-5ce9731eea76" />
</p>

## Autoupdate

Get notified when a new Sculptor version is available:

<p align="center">
  <img width="60%" alt="Updating in progress" src="https://github.com/user-attachments/assets/a6405147-af55-43a1-94ee-f8d9fb103cab" />
</p>

Note that you currently have to restart Sculptor to get the new version. We recommend you wait until tasks are completed — Sculptor is still in active development!

<p align="center">
  <img width="60%" alt="Update complete" src="https://github.com/user-attachments/assets/b2b1498c-6edd-4a88-abb9-c2fb1f605cb5" />
</p>

## Factory reset your Sculptor

```bash
mv ~/.sculptor ~/.sculptor.bkp."$(date +%s)"
```

## Clean up Docker disk space

Sculptor auto-cleans up its images and containers on a cadence while it's running, so this shouldn't be necessary most of the time. However if you need to, here's a command to remove ALL Docker containers and images (Sculptor or not). You can also use Docker Desktop to clean up specific images.

```bash
docker system prune -af
```

# License
© Imbue, Inc. All rights reserved. Use is subject to Imbue's [Research Preview Terms of Service](https://imbue.com/terms/).
