import { Theme } from "@radix-ui/themes";
import { act, cleanup, render, type RenderResult, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import { ElementIds } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import type { VoiceEngine, VoiceEngineEvents } from "~/common/voice/types.ts";

import { VoiceEntryButton } from "./VoiceEntryButton.tsx";

// The speech engine is dynamically imported; mocking its module stands in for
// the engine and captures its listeners so a test can drive
// state/segment/error transitions.
const engineHarness = vi.hoisted(() => ({
  events: null as VoiceEngineEvents | null,
  start: vi.fn(async (): Promise<void> => {}),
  stop: vi.fn(async (): Promise<void> => {}),
  dispose: vi.fn(),
}));

vi.mock("~/common/voice/engine.ts", () => ({
  createVoiceEngine: (events: VoiceEngineEvents): VoiceEngine => {
    engineHarness.events = events;
    return { start: engineHarness.start, stop: engineHarness.stop, dispose: engineHarness.dispose };
  },
}));

// Stub only the two managed-install calls; keep the rest of the generated client
// (notably ElementIds) real.
const apiHarness = vi.hoisted(() => ({
  installDependency: vi.fn(async () => ({ data: { success: true, in_progress: true } })),
  getDependenciesStatus: vi.fn(async () => ({ data: undefined })),
}));

vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    installDependency: apiHarness.installDependency,
    getDependenciesStatus: apiHarness.getDependenciesStatus,
  };
});

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const makeStatus = (voiceModels?: DependencyInfo): DependenciesStatus => ({
  git: makeInfo({ installed: true }),
  claude: makeInfo({ installed: true }),
  pi: makeInfo({ installed: true }),
  gh: makeInfo({ installed: true }),
  voiceModels: voiceModels ?? makeInfo({ installed: false }),
});

type RenderedButton = RenderResult & { onAppendTranscript: ReturnType<typeof vi.fn> };

type ExtraButtonProps = {
  onPreviewChange?: (preview: string) => void;
  onCaptureLockChange?: (locked: boolean) => void;
};

const renderButton = (voiceModels?: DependencyInfo, extraProps?: ExtraButtonProps): RenderedButton => {
  const store = createStore();
  store.set(dependenciesStatusAtom, makeStatus(voiceModels));
  const onAppendTranscript = vi.fn();
  const view = render(
    <Provider store={store}>
      <Theme>
        <VoiceEntryButton onAppendTranscript={onAppendTranscript} {...extraProps} />
      </Theme>
    </Provider>,
  );
  return { ...view, onAppendTranscript };
};

const getToggle = (): HTMLElement => screen.getByTestId(ElementIds.VOICE_ENTRY_TOGGLE);

const startListening = async (): Promise<VoiceEngineEvents> => {
  await userEvent.click(getToggle());
  await waitFor(() => expect(engineHarness.events).not.toBeNull());
  return engineHarness.events as VoiceEngineEvents;
};

beforeAll(() => {
  // getUserMedia requires a secure context; the button self-hides otherwise, and
  // jsdom defaults isSecureContext to false.
  Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
  Element.prototype.scrollIntoView = (): void => {};
});

beforeEach(() => {
  engineHarness.events = null;
  engineHarness.start.mockClear();
  engineHarness.stop.mockClear();
  engineHarness.dispose.mockClear();
  apiHarness.installDependency.mockClear();
  apiHarness.getDependenciesStatus.mockClear();
});

afterEach(() => {
  cleanup();
});

describe("VoiceEntryButton", () => {
  it("renders nothing outside a secure context", () => {
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: false });
    renderButton(makeInfo({ installed: true }));
    expect(screen.queryByTestId(ElementIds.VOICE_ENTRY_TOGGLE)).toBeNull();
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
  });

  it("offers to load the models when the voice bundle is absent, and installs on click", async () => {
    renderButton();
    expect(getToggle()).toHaveAttribute("data-voice-state", "not-installed");
    await userEvent.click(getToggle());
    expect(apiHarness.installDependency).toHaveBeenCalledWith(
      expect.objectContaining({ query: { tool: "VOICE_MODELS" } }),
    );
  });

  it("shows a determinate progress ring and a percent tooltip while installing", () => {
    const info = makeInfo({
      installed: false,
      installProgress: { tool: "VOICE_MODELS", bytesDownloaded: 40, totalBytes: 100 },
    });
    renderButton(info);
    const toggle = getToggle();
    expect(toggle).toHaveAttribute("data-voice-state", "installing");
    expect(toggle).toHaveAttribute("data-progress-percent", "40");
    expect(toggle).toHaveAttribute("data-tooltip", "Voice models 40% loaded");
    // The determinate ring is an overlaid SVG (Radix has no determinate primitive).
    expect(toggle.querySelector("svg")).not.toBeNull();
  });

  it("does not re-trigger an install while one is in progress", async () => {
    renderButton(
      makeInfo({ installed: false, installProgress: { tool: "VOICE_MODELS", bytesDownloaded: 1, totalBytes: 4 } }),
    );
    // The installing button is disabled (its hover/test target is the wrapping
    // span), so a click cannot reach the install path.
    await userEvent.click(getToggle());
    expect(apiHarness.installDependency).not.toHaveBeenCalled();
  });

  it("shows a retry affordance carrying the error, and retries the install on click", async () => {
    renderButton(makeInfo({ installed: false, installError: "network down" }));
    const toggle = getToggle();
    expect(toggle).toHaveAttribute("data-voice-state", "install-error");
    expect(toggle).toHaveAttribute("data-tooltip", expect.stringContaining("network down"));
    await userEvent.click(toggle);
    expect(apiHarness.installDependency).toHaveBeenCalledTimes(1);
  });

  it("starts the engine and adopts the listening treatment when toggled on", async () => {
    renderButton(makeInfo({ installed: true }));
    expect(getToggle()).toHaveAttribute("data-voice-state", "idle");
    expect(getToggle()).toHaveAttribute("data-tooltip", "Start voice entry");

    const events = await startListening();
    expect(engineHarness.start).toHaveBeenCalledTimes(1);

    act(() => events.onStateChange("listening"));
    const active = getToggle();
    expect(active).toHaveAttribute("data-voice-state", "listening");
    expect(active).toHaveAttribute("data-tooltip", "Stop voice entry");
    expect(active).toHaveAttribute("aria-pressed", "true");
  });

  it("stops the engine when toggled off from the listening state", async () => {
    renderButton(makeInfo({ installed: true }));
    const events = await startListening();
    act(() => events.onStateChange("listening"));

    await userEvent.click(getToggle());
    expect(engineHarness.stop).toHaveBeenCalledTimes(1);
  });

  it("forwards each transcribed segment verbatim to the caller", async () => {
    const { onAppendTranscript } = renderButton(makeInfo({ installed: true }));
    const events = await startListening();
    act(() => events.onSegment("hello world"));
    expect(onAppendTranscript).toHaveBeenCalledWith("hello world");
  });

  it("explains that microphone access is blocked on a permission error", async () => {
    renderButton(makeInfo({ installed: true }));
    const events = await startListening();
    act(() => events.onError({ kind: "mic-permission-denied", message: "denied" }));
    const toggle = getToggle();
    expect(toggle).toHaveAttribute("data-voice-state", "voice-error");
    expect(toggle).toHaveAttribute("data-tooltip", expect.stringContaining("Microphone access is blocked"));
  });

  it("relays previews and holds the capture lock through listening and stopping", async () => {
    const onPreviewChange = vi.fn();
    const onCaptureLockChange = vi.fn();
    renderButton(makeInfo({ installed: true }), { onPreviewChange, onCaptureLockChange });
    const events = await startListening();

    act(() => events.onStateChange("listening"));
    await waitFor(() => expect(onCaptureLockChange).toHaveBeenLastCalledWith(true));

    act(() => events.onPreview("partial wo"));
    expect(onPreviewChange).toHaveBeenLastCalledWith("partial wo");

    act(() => events.onStateChange("stopping"));
    await waitFor(() => expect(getToggle()).toHaveAttribute("data-voice-state", "stopping"));
    expect(onCaptureLockChange).toHaveBeenLastCalledWith(true);

    act(() => events.onStateChange("idle"));
    await waitFor(() => expect(onCaptureLockChange).toHaveBeenLastCalledWith(false));
  });

  it("disposes the engine on unmount so the mic never outlives the button", async () => {
    const view = renderButton(makeInfo({ installed: true }));
    await startListening();
    view.unmount();
    expect(engineHarness.dispose).toHaveBeenCalledTimes(1);
  });
});
