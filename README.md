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

Instructions for Mac Silicon (OSX arm64) follow. Linux build and instructions will be updated shortly!

## 1. Dependencies

### Install git

```bash
brew install git
```

### Install mutagen

```bash
brew install mutagen-io/mutagen/mutagen
```

OR - install the [appropriate latest released binary for Mutagen](https://github.com/mutagen-io/mutagen/releases)

### Install docker

**On Mac**:
[Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/)

- Ensure your Docker version is 27 or higher according to `docker --version`
- Go to Settings > General > Virtual Machine Options after download and set “Virtual Machine Manager” to `Docker VMM`

**On Linux**:
Do *not* install Docker Desktop.

- Instead, install Docker Engine by [following the instructions here](https://docs.docker.com/engine/install/)


### 2. Run Sculptor
*Note: You'll need an Anthropic account to use Sculptor.*

Download the .dmg from https://imbue-sculptor-releases.s3.us-west-2.amazonaws.com/sculptor/Sculptor.dmg and double-click to unpack it into your /Applications folder.

<img width="770" height="632" alt="Screenshot 2025-09-16 at 8 10 10 PM" src="https://github.com/user-attachments/assets/fcd800b5-37e1-46e2-be4a-1c0433107bb7" />

Enter your email and you should get to the installation wizard. This will tell you if we've found your installed docker, git, and mutagen. As a beta tester, you'll be opted in to send error logs and telemetry data. Let us know if this is an issue or if you need more information about this! 🙏

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 07 09 PM" src="https://github.com/user-attachments/assets/05d9a6fe-d91a-49e3-9b01-2ff31362c5e0" />

Provide the Anthropic credentials you'll be using. We plan on pushing out an update soon that allows Claude auth sign-in!

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 08 09 PM" src="https://github.com/user-attachments/assets/a3e5c4cd-b4be-411e-9a76-3b3aa0f35a72" />

Select the repo you wish to work on. Don't worry, you can select a second repo later and switch between them freely! If there's no git repo installed there, we'll install one.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 08 35 PM" src="https://github.com/user-attachments/assets/07e3cb62-b9ae-440a-a25a-f021453b879b" />

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 09 31 PM" src="https://github.com/user-attachments/assets/f2b02171-4329-4aef-b69f-ab6ab7fd21a0" />

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

```
missing image
```

4. From within the task, hit "cmd-N" or click "new agent" to open the new task prompt. You can create multiple tasks in quick succession from here, or return to your ongoing task. You can also move between different tasks, or archive/delete them.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 27 10 PM" src="https://github.com/user-attachments/assets/83e249e0-38ea-4231-baf9-9e4495edae6e" />

## Working on a different repo

1. Open the repo selector in the bottom right. Here you can choose between your loaded repos, or point Sculptor at a new one.
<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 24 51 PM" src="https://github.com/user-attachments/assets/610de94d-3d29-4f2e-885f-10d321cd3eee" />

## Check on your task status

1. To see what's going on, check on the Log tab for the build logs.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 29 22 PM" src="https://github.com/user-attachments/assets/a0dc530f-e918-41bd-9838-f777571e3414" />

2. To debug what's going on inside the container, use the terminal tab. This places you inside a tmux inside the agent container. Leave and come back anytime and your terminal state will stick around!

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 29 57 PM" src="https://github.com/user-attachments/assets/cc089899-9e99-49a5-8f84-2172f972f44c" />

3. Check out the "Plan" tab to see the multistep thinking progress, or the "Suggestions" tab to see code quality and code verification results.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 34 48 PM" src="https://github.com/user-attachments/assets/b526ce4d-4b35-4c37-85eb-938007de7177" />

4. Open the "Changes" tab to see the diff of file changes made in the task, either uncommited or committed, relative to the base branch the task was created from.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 35 18 PM" src="https://github.com/user-attachments/assets/39d780a7-40d5-4e20-8913-c2b4fee98023" />

Commit the agent's changes with your custom commit message.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 43 17 PM" src="https://github.com/user-attachments/assets/c3067a30-0f9e-461f-afe1-1248a94243ad" />

## Live sync with agent changes

1. Click the black "Live Sync" button in the top right of the repo to sync the agent repo state over to your copy of the repo.
2. While synced, make as many changes as you like by following up with the agent in the task chat, or switching to your IDE or terminal of choice to edit code, run tests, etc.
4. Click the green spinner to stop sync and return your local repo to its original state.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 55 04 PM" src="https://github.com/user-attachments/assets/c1aa25ac-3fbb-416d-97b3-52d0b2cb0c99" />

3. While one task is working, add instructions and follow-ups to other agents. When those agents get stuck, swap live sync over to those tasks instead from the task sidebar, or using the black "Live Sync" button in top right.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 8 54 52 PM" src="https://github.com/user-attachments/assets/e23c9ab1-b526-44b6-bb3b-06f83a54c0d9" />


## Merging the agent’s changes

(Note that merging is disabled while Live Sync is active.)

1. When you're satisfied with your task progress (don't forget to commit the changes!), you can merge those changes back to your local base branch. Open the "Merge" dropdown and select "Pull" to merge the agent's changes into your own. From there, make any finishing touches yourself and ship it off to wherever it goes next - merge request for review, QA for more testing, or straight to production...?

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 9 00 52 PM" src="https://github.com/user-attachments/assets/4cc2aa04-391c-4174-8c41-829ac93ea113" />

2. If you've made changes locally, e.g. from pulling in changes from another task, and want to push those to the agent, select "Push" to send those to the agent's copy of the repo.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 9 01 51 PM" src="https://github.com/user-attachments/assets/752333e0-265f-4039-b872-8e5c375d0323" />

3. If you prefer to operate directly on the sculptor/* git branch, select your local mirror as the Target and push/pull at will.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 9 03 00 PM" src="https://github.com/user-attachments/assets/bfd7aa3a-1be3-4889-874a-4c18cdebf494" />

4. Need to pull in changes from colleague who recently pushed to main and caused merge conflicts? No worry, you can select any recent branch to push into the agent repo. Push those merge conflicts in and let the agent resolve them for you!

```
i dont have a repo right now but i swear it works
```

# Advanced workflows

## Compaction

If your task conversation gets too long, click into the context meter and choose "compact".

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 9 05 58 PM" src="https://github.com/user-attachments/assets/cef578cd-c6d0-4bf5-8e81-26713f889a05" />


## @autocomplete file and folder names

Anytime during a task, @mention a part of a filename to autocomplete it.

<img width="1312" height="912" alt="Screenshot 2025-09-16 at 9 07 40 PM" src="https://github.com/user-attachments/assets/778b8821-624a-4f1d-96aa-c056840bcb1b" />

## Custom dockerfile

Have project-specific dependencies you want in your agent environment? We support specifying a Dockerfile or image as per the devcontainer spec.

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
  },
}
```

```Dockerfile
FROM node:latest

# if you need environment variables -- inject them here
ENV NODE_OPTIONS='--max-old-space-size=4096'

RUN node --version

```

## Task error recovery

Hit an unexpected error with Sculptor? Contact us on discord to report the issue and see if others have hit it -- but in the meanwhile, try asking Sculptor to restart the task from the latest snapshot.

<img width="993" height="802" alt="Screenshot 2025-09-16 at 9 12 16 PM" src="https://github.com/user-attachments/assets/68fe0e15-e364-4f87-9572-5ce9731eea76" />

## Autoupdate

Get notified when a new sculptor version is available:

<img width="1205" height="803" alt="Updating in progress" src="https://github.com/user-attachments/assets/a6405147-af55-43a1-94ee-f8d9fb103cab" />

Note that you currently have to restart sculptor to get the new version. We recommend you wait until tasks are completed - Sculptor is still in active development!

<img width="1202" height="802" alt="Update complete" src="https://github.com/user-attachments/assets/b2b1498c-6edd-4a88-abb9-c2fb1f605cb5" />

## Factory reset your sculptor

```bash
mv ~/.sculptor ~/.sculptor.bkp."$(date +%s)"
```


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
```
missing image
```

Updating the system prompt from an individual task page:
```
missing image
```

## Steering with inline TODOs

Inline TODOs or FIXMEs are one of the most reliable ways to steer the agent when iterating on real code. Because LLMs attend better to instructions **near the relevant code**, inline notes are often more effective than chat prompts alone.

To use inline TODOs:

- Local sync to the task you want to update
- Add TODOs or comments near the code you want the agent to modify
- Tell the agent where to look (e.g. “Check foo.py for TODOs”)

# License
© Imbue, Inc. All rights reserved. Use is subject to Imbue's [Research Preview Terms of Service](https://imbue.com/terms/).
