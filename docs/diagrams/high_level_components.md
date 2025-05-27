// Define groups and nodes
User [icon: person]


sculptor server {
  web module {
    create route [icon: aws-ec2]
    stream route [icon: aws-rds]
  }

  DB

  task_service [color: red] {
    task spawner [icon: aws-auto-scaling]
    Worker1 [icon: aws-ec2]
    Worker2 [icon: aws-ec2]
    Worker3 [icon: aws-ec2]
  }
}

environment {
  tmux {
    claude [icon: aws-redshift]
  }
  observer {
    Agent
  }
}


// Define connections
User > create route
create route > DB > task spawner
task spawner > Worker1, Worker2, Worker3
User < stream route
Worker3 > claude
Worker3 <> observer
claude <> observer
Worker3 > stream route
