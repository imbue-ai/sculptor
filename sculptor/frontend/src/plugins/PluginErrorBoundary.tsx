import { Flex, Text } from "@radix-ui/themes";
import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  pluginId: string;
  pluginName: string;
  children: ReactNode;
};

type State = { error: Error | null };

/**
 * Backstop for plugin render-time crashes. Catches any throw from the
 * wrapped plugin component, renders a small fallback, and lets the rest
 * of the workspace continue functioning. The global Sentry ErrorBoundary
 * at the app root would crash the whole window — this boundary scopes
 * the failure to the offending panel.
 */
export class PluginErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`Plugin "${this.props.pluginId}" crashed during render`, error, info);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <Flex direction="column" gap="2" p="3">
          <Text size="2" weight="medium">
            {this.props.pluginName} stopped responding
          </Text>
          <Text size="1" color="gray">
            {this.state.error.message}
          </Text>
        </Flex>
      );
    }
    return this.props.children;
  }
}
