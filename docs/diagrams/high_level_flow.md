User [icon: monitor, color: gray]
Server [icon: server, color: blue]
Agent [icon: tool, color: green]

User > Server: create task
activate Server
Server > Agent: start agent
activate Agent
loop [label: while not blocked, color: green] {
  Agent > Agent: write code & run tools
}

User <-- Agent: stream outputs
User > Agent: send inputs

loop [label: while not blocked, color: green] {
  Agent > Agent: write code & run tools
}

User < Agent: send merge request

deactivate Agent
deactivate Server
