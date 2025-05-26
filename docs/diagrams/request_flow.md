user [icon: person, color: white]
browser [icon: monitor, color: gray]
sculptor [icon: server, color: blue]
ServerTask [icon: tool, color: green]
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
        sculptor > ServerTask: start task
            activate ServerTask
        sculptor > browser: HTTP 200
        sculptor > browser: HTTP SSE 200
        deactivate sculptor
    browser > user: react.render()

# TODO: some repo fetching logic to set up in here
ServerTask > ServerTask: create image
ServerTask > ServerTask: create volume
ServerTask > executor: start executor
activate executor
ServerTask > executor: start claude code

executor > executor: write some code
executor > ServerTask: receive message(s)
ServerTask > ServerTask: add to DB
executor > ServerTask: fetch repo
sculptor > browser: HTTP SSE 200
browser > user: react.render()

executor > executor: run some tools
executor > ServerTask: receive message(s)
ServerTask > ServerTask: add to DB
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
        ServerTask > executor: send message to agent
        executor > ServerTask: new log event
        ServerTask > ServerTask: add to DB
    sculptor > browser: HTTP SSE 200
    browser > user: react.render()

executor > executor: write some code
executor > ServerTask: receive message(s)
ServerTask > ServerTask: add to DB
executor > ServerTask: fetch repo
sculptor > browser: HTTP SSE 200
browser > user: react.render()

executor > ServerTask: done
ServerTask > ServerTask: add to DB
executor > ServerTask: fetch repo
deactivate executor
sculptor > browser: HTTP SSE 200
browser > user: react.render()
ServerTask > ServerTask: save done to DB
deactivate ServerTask

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
