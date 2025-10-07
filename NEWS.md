# 0.2.15

### Shared context between terminal and agent

Did you ever have a quick task that you thought you could run real quick using the Terminal tab, but ended up not working and you wish you had given the Sculptor agent the task to begin with?

One of our team members did - and now we have a fix for it! As of 0.2.15, Sculptor is now aware of the commands and bash history in your terminal.

This should also make it a smoother experience to run simple terminal commands that you know should work -- for instance, instead of asking sculptor to "run apt install ffmpeg and fix any issues", you can optimistically run that command yourself in the terminal, and only tell Sculptor to help if your command fails.

This works because we run terminal inside a tmux pane inside the container - which means it's easy to save the bash output into `~/tmux-session-logs` inside the container.

<img width="886" height="800" alt="terminal" src="https://github.com/user-attachments/assets/4b0745c3-2aac-419d-9ca4-fa6757b8b805" />


### Other features:

* Diff view now explicitly shows new files, deleted files, and renamed files. 
<img width="1033" height="840" alt="filename_changes" src="https://github.com/user-attachments/assets/225e158d-ed09-4737-8552-d0d156fb33e1" />

* The sculptor window should now remember its size and location between restarts.
* Improvements to the (beta) suggestions UI.
* Re-enabled accessing sculptor via web browser via localhost:5050 exposed port.

### Fixes and improvements:

* Silence loud exception when Docker socket connection fails during background setup [PROD-2549] (!6720 (merged)) (@DanverImbue, @thad2)
  - Fixed a bug where a missing docker socket during startup would emit excessive error logs.
* Standardize error parsing between merge_from_ref and pull_from_remote operations [PROD-2491] (!6657 (merged)) (@maciek12, @micimize)
  - Improved logic of parsing error states when pulling from remote or merging using the merge modal.
* Fix issue with dropping commits [PROD-2574] (!6729 (merged)) (@millan5, @bowei2, @samgeo) https://discord.com/channels/1391837726583820409/1423397772505387069
  - Fixed a bug where starting an agent against a branch with uncommitted changes would sometimes drop commits or fail to copy in unrelated changes.
* Fix startup crash when git ref files don't exist in local sync service [PROD-1817] (!6716 (merged)) (@micimize, @bowei2, @millan5)
  - Fixed a crash during agent startup when a previously created sculptor/* branch was deleted.
* Fix snapshot after local sync not working properly (!6715 (merged)) (@josh_albrecht, @bowei2, @guinness2)
  - Fixed an issue where snapshotting agent state was not working at all while pairing mode was enabled, making it dangerous to fork or restart tasks.
* Prevent stderr output from blocking diff artifact creation (!6722 (merged)) (@amy.hu1, @bowei2)
  - Fixed an issue where snapshotting agent state was not working at all while pairing mode was enabled.
* Add loading state for forked blocks and fix vertical spacing [PROD-2590] (!6745 (merged)) (@guinness2, @millan5)
  - Added loading state and improved UI for showing forking actions in the chat history.
* Clean up temporary git tags after merge operations and prevent tag propagation (!6660 (merged)) (@maciek12, @micimize)
  - Stopped leaving around temporary git tags in the repo after merge operations using merge panel.
* Make backend notices expandable with detailed git output for better error inspection [PROD-2491] (!6657 (merged)) (@maciek12, @micimize)
  - Improved information content of the merge panel when hitting certain errors or edge cases.
* Make model names consistent in task modal [PROD-2567] (!6735 (merged)) (@samgeo, @bowei2) https://discord.com/channels/1391837726583820409/1423065994833825912/1423430992143585320
  - Copy fixes.
* Remove base commit parameter from agent configuration (!6725 (merged)) (@egunter, @mark604)
  - Improve suggestions behavior when the base branch is a branch other than main.




