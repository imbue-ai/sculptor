CREATE INDEX `agent_workspace_id_idx` ON `agent` (`workspace_id`);--> statement-breakpoint
CREATE INDEX `agent_message_agent_id_idx` ON `agent_message` (`agent_id`);--> statement-breakpoint
CREATE INDEX `workspace_project_id_idx` ON `workspace` (`project_id`);
