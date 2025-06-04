# Enable arbitrary shell commands as "Agent"s

There's no reason we cannot make a simple `BashAgent` that can run arbitrary shell commands.

It would be mediocre in support for understanding if the command were blocked,
but most of the rest of the interface would transfer fairly well.

This feels *slightly* silly (obviously there are already ways to run shell commands),
but it would actually enable some nice workflows:

1. You could easily run long-running commands like experiments, training jobs, etc., and check in on them remotely.
2. You could invoke agents on them (esp via forking) in order to help debug more complex workflows.
