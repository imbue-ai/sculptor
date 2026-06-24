CREATE TABLE `agent` (
	`object_id` text PRIMARY KEY NOT NULL,
	`created_at` text NOT NULL,
	`project_id` text NOT NULL,
	`workspace_id` text,
	`agent_config` text NOT NULL,
	`starting_git_hash` text,
	`system_prompt` text,
	`default_model` text,
	`run_state` text DEFAULT 'QUEUED' NOT NULL,
	`error` text,
	`title` text,
	`last_processed_message_id` text,
	`claude_session_id` text,
	`pi_session_id` text,
	`terminal_session_id` text,
	`terminal_shell_pid` integer,
	`available_models` text NOT NULL,
	`current_model` text,
	`is_deleted` integer DEFAULT false NOT NULL,
	`is_deleting` integer DEFAULT false NOT NULL,
	`last_read_at` text,
	FOREIGN KEY (`project_id`) REFERENCES `repo`(`object_id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`workspace_id`) REFERENCES `workspace`(`object_id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `agent_message` (
	`object_id` text PRIMARY KEY NOT NULL,
	`created_at` text NOT NULL,
	`agent_id` text NOT NULL,
	`message` text NOT NULL,
	`source` text NOT NULL,
	`is_partial` integer NOT NULL,
	FOREIGN KEY (`agent_id`) REFERENCES `agent`(`object_id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `notification` (
	`object_id` text PRIMARY KEY NOT NULL,
	`created_at` text NOT NULL,
	`message` text NOT NULL,
	`importance` text DEFAULT 'ACTIVE' NOT NULL,
	`agent_id` text,
	`project_id` text,
	FOREIGN KEY (`agent_id`) REFERENCES `agent`(`object_id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`project_id`) REFERENCES `repo`(`object_id`) ON UPDATE no action ON DELETE no action
);
