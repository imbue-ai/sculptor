user [icon: person, color: white]
browser [icon: monitor, color: gray]
sculptor [icon: server, color: blue]
worktask [icon: tool, color: green]
executor [icon: box, color: purple]

# TODO: some onboarding and setup to describe

user > browser: "load main page"
    activate browser
    browser > sculptor: GET /
        activate sculptor
        sculptor > browser: HTTP 200
        deactivate sculptor
    browser > sculptor: GET /project_stream/
        activate sculptor
        sculptor > browser: HTTP SSE 200
    browser > user: render HTML for "/"

user > browser: "start new task"
    browser > sculptor: POST /api/v1/task/
        activate sculptor
        sculptor > worktask: start task
            activate worktask
        sculptor > browser: HTTP 200
        sculptor > browser: HTTP SSE 200
        deactivate sculptor
    browser > user: react.render()

# TODO: some repo fetching logic to set up in here
worktask > worktask: create image
worktask > worktask: create volume
worktask > executor: start executor
activate executor
worktask > executor: start claude code

executor > executor: write some code
executor > worktask: receive message(s)
worktask > worktask: add to DB
executor > worktask: fetch repo
sculptor > browser: HTTP SSE 200
browser > user: react.render()

executor > executor: run some tools
executor > worktask: receive message(s)
worktask > worktask: add to DB
sculptor > browser: HTTP SSE 200
browser > user: react.render()

user > browser: "load individual task page"
    activate browser
    browser > sculptor: GET /(task_id/
        activate sculptor
        sculptor > browser: HTTP 200
        deactivate sculptor
    deactivate sculptor
    browser > sculptor: GET /task_stream/
        activate sculptor
        sculptor > browser: HTTP SSE 200
    browser > user: render HTML for "/(task_id/)"

user > browser: "send message to agent"
    activate browser
    browser > sculptor: POST /api/v1/task/(task_id)/message/
        activate sculptor
        sculptor > sculptor: add to DB
        worktask > executor: send message to agent
        executor > worktask: new log event
        worktask > worktask: add to DB
    sculptor > browser: HTTP SSE 200
    browser > user: react.render()

executor > executor: write some code
executor > worktask: receive message(s)
worktask > worktask: add to DB
executor > worktask: fetch repo
sculptor > browser: HTTP SSE 200
browser > user: react.render()

executor > worktask: done
worktask > worktask: add to DB
executor > worktask: fetch repo
deactivate executor
sculptor > browser: HTTP SSE 200
browser > user: react.render()
worktask > worktask: save done to DB
deactivate worktask

user > user: "git diff agent/branch_name"

user > browser: "merge agent changes"
browser > sculptor: POST /api/v1/task/(task_id)/merge/
activate sculptor
sculptor > sculptor: merge changes
sculptor > sculptor: push to repo
deactivate sculptor
sculptor > browser: HTTP SSE 200
browser > user: react.render()

deactivate sculptor
deactivate browser








browser > browser: make commit out of changes
browser > sculptor: ensure sync (FUTURE)
sculptor > sculptor: fetch repo if necessary (FUTURE)
sculptor > browser: ack (FUTURE)

worktask > worktask: create image
worktask > executor: start executor
activate executor
worktask > executor: update executor to user_task git hash with dependencies

worktask > executor: prompt claude code
loop [label: claude, color: green] {
  executor > executor: iterates
}
worktask --> sculptor: stream results
executor > worktask: blocked on input (FUTURE)
worktask --> user: notify via DB (FUTURE)

user > browser: "tasks"
activate browser
browser > sculptor: GET /user_tasks/
activate sculptor
sculptor > browser: all tasks
deactivate sculptor
browser > user: display all tasks
deactivate browser

user > browser: "pair"
activate browser
browser > sculptor: GET /user_task/id
activate sculptor
sculptor > browser: task with ssh details
deactivate sculptor
browser > executor: ssh in and tmux attach
user > executor: send input
executor > user: observe changes
user > executor: detach
deactivate browser

loop [label: claude, color: green] {
  executor > executor: iterates
}
executor > worktask: done
deactivate executor

worktask --> sculptor: stream results
worktask > sculptor: done
deactivate worktask

sculptor --> user: notify that task is done (FUTURE)

user > browser: "tasks"
activate browser
browser > sculptor: GET /user_tasks/
activate sculptor
sculptor > browser: all tasks
deactivate sculptor
browser > browser: git fetch all branches
browser > user: display all tasks
deactivate browser

user > browser: "apply" (FUTURE)
activate browser
browser > sculptor: GET /user_tasks/
activate sculptor
sculptor > browser: all tasks
deactivate sculptor
browser > user: display all tasks
deactivate browser
