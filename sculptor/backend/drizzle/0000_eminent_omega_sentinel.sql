CREATE TABLE `repo` (
	`object_id` text PRIMARY KEY NOT NULL,
	`created_at` text NOT NULL,
	`name` text NOT NULL,
	`user_git_repo_url` text,
	`is_path_accessible` integer DEFAULT true NOT NULL,
	`is_deleted` integer DEFAULT false NOT NULL,
	`default_system_prompt` text,
	`workspace_setup_command` text,
	`naming_pattern` text
);
--> statement-breakpoint
CREATE TABLE `user_settings` (
	`object_id` text PRIMARY KEY NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `workspace` (
	`object_id` text PRIMARY KEY NOT NULL,
	`created_at` text NOT NULL,
	`project_id` text NOT NULL,
	`description` text NOT NULL,
	`initialization_strategy` text NOT NULL,
	`source_branch` text,
	`target_branch` text,
	`environment_id` text,
	`source_git_hash` text,
	`is_deleted` integer DEFAULT false NOT NULL,
	`is_open` integer DEFAULT true NOT NULL,
	`setup_command_triggered` integer DEFAULT false NOT NULL,
	`setup_status` text DEFAULT 'pending' NOT NULL,
	`setup_run_id` text,
	`setup_command` text,
	`setup_exit_code` integer,
	`setup_started_at` real,
	`setup_finished_at` real,
	`setup_log_path` text,
	`setup_log_truncated` integer DEFAULT false NOT NULL,
	`diff_status` text DEFAULT 'NONE' NOT NULL,
	`diff_updated_at` text,
	`requested_branch_name` text,
	FOREIGN KEY (`project_id`) REFERENCES `repo`(`object_id`) ON UPDATE no action ON DELETE no action
);
