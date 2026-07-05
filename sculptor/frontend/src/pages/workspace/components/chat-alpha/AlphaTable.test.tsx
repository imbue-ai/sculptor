import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render as rtlRender } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AlphaTable } from "./AlphaTable.tsx";

const ThemeWrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;
const render = (
  ui: ReactElement,
  options?: Omit<Parameters<typeof rtlRender>[1], "wrapper">,
): ReturnType<typeof rtlRender> => rtlRender(ui, { wrapper: ThemeWrapper, ...options });

let clipboardText: string;

beforeEach(() => {
  clipboardText = "";
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn((text: string) => (clipboardText = text)) },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  cleanup();
});

const twoColumnTable = (): React.ReactElement => {
  return (
    <AlphaTable>
      <thead>
        <tr>
          <th>Name</th>
          <th>Age</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Alice</td>
          <td>30</td>
        </tr>
        <tr>
          <td>Bob</td>
          <td>25</td>
        </tr>
      </tbody>
    </AlphaTable>
  );
};

const clickCopyButton = (container: HTMLElement): void => {
  const button = container.querySelector('button[aria-label="Copy table"]');
  expect(button).toBeTruthy();
  fireEvent.click(button!);
};

describe("AlphaTable", () => {
  it("renders children inside a table element", () => {
    const { container } = render(
      <AlphaTable>
        <thead>
          <tr>
            <th>Name</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Alice</td>
          </tr>
        </tbody>
      </AlphaTable>,
    );
    expect(container.querySelector("table")).toBeTruthy();
    expect(container.querySelector("th")!.textContent).toBe("Name");
    expect(container.querySelector("td")!.textContent).toBe("Alice");
  });

  it("wraps the table in a scrollable container", () => {
    const { container } = render(
      <AlphaTable>
        <tbody>
          <tr>
            <td>data</td>
          </tr>
        </tbody>
      </AlphaTable>,
    );
    const wrapper = container.firstElementChild;
    expect(wrapper).toBeTruthy();
    expect(wrapper!.querySelector("table")).toBeTruthy();
  });

  it("renders a table with multiple columns", () => {
    const { container } = render(
      <AlphaTable>
        <thead>
          <tr>
            <th>A</th>
            <th>B</th>
            <th>C</th>
            <th>D</th>
            <th>E</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>1</td>
            <td>2</td>
            <td>3</td>
            <td>4</td>
            <td>5</td>
          </tr>
          <tr>
            <td>6</td>
            <td>7</td>
            <td>8</td>
            <td>9</td>
            <td>10</td>
          </tr>
        </tbody>
      </AlphaTable>,
    );
    expect(container.querySelectorAll("th")).toHaveLength(5);
    expect(container.querySelectorAll("td")).toHaveLength(10);
  });

  it("renders a table with only a header (no body rows)", () => {
    const { container } = render(
      <AlphaTable>
        <thead>
          <tr>
            <th>Col A</th>
            <th>Col B</th>
          </tr>
        </thead>
      </AlphaTable>,
    );
    expect(container.querySelector("table")).toBeTruthy();
    expect(container.querySelectorAll("th")).toHaveLength(2);
    expect(container.querySelectorAll("td")).toHaveLength(0);
  });

  it("renders header and body cell content correctly", () => {
    const { container } = render(
      <AlphaTable>
        <thead>
          <tr>
            <th>Header</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Body</td>
          </tr>
        </tbody>
      </AlphaTable>,
    );
    expect(container.querySelector("th")!.textContent).toBe("Header");
    expect(container.querySelector("td")!.textContent).toBe("Body");
  });

  describe("copy button", () => {
    it("renders a copy button with 'Copy table' aria-label", () => {
      const { container } = render(twoColumnTable());
      const button = container.querySelector('button[aria-label="Copy table"]');
      expect(button).toBeTruthy();
    });

    it("shows CopyIcon by default, not CheckIcon", () => {
      const { container } = render(twoColumnTable());
      const button = container.querySelector('button[aria-label="Copy table"]');
      // CopyIcon renders an SVG — the CheckIcon would only appear after clicking
      expect(button!.querySelector("svg")).toBeTruthy();
    });
  });

  describe("copies table as markdown", () => {
    it("formats a standard table with header, separator, and body rows", () => {
      const { container } = render(twoColumnTable());
      clickCopyButton(container);

      const expected = ["| Name | Age |", "| --- | --- |", "| Alice | 30 |", "| Bob | 25 |"].join("\n");
      expect(clipboardText).toBe(expected);
    });

    it("formats a header-only table with separator row", () => {
      const { container } = render(
        <AlphaTable>
          <thead>
            <tr>
              <th>Col A</th>
              <th>Col B</th>
            </tr>
          </thead>
        </AlphaTable>,
      );
      clickCopyButton(container);

      const expected = ["| Col A | Col B |", "| --- | --- |"].join("\n");
      expect(clipboardText).toBe(expected);
    });

    it("formats a single-column table", () => {
      const { container } = render(
        <AlphaTable>
          <thead>
            <tr>
              <th>Item</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Apple</td>
            </tr>
          </tbody>
        </AlphaTable>,
      );
      clickCopyButton(container);

      const expected = ["| Item |", "| --- |", "| Apple |"].join("\n");
      expect(clipboardText).toBe(expected);
    });

    it("formats a table with many columns", () => {
      const { container } = render(
        <AlphaTable>
          <thead>
            <tr>
              <th>A</th>
              <th>B</th>
              <th>C</th>
              <th>D</th>
              <th>E</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>1</td>
              <td>2</td>
              <td>3</td>
              <td>4</td>
              <td>5</td>
            </tr>
          </tbody>
        </AlphaTable>,
      );
      clickCopyButton(container);

      const expected = ["| A | B | C | D | E |", "| --- | --- | --- | --- | --- |", "| 1 | 2 | 3 | 4 | 5 |"].join("\n");
      expect(clipboardText).toBe(expected);
    });

    it("handles empty cells", () => {
      const { container } = render(
        <AlphaTable>
          <thead>
            <tr>
              <th>Key</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td></td>
              <td>filled</td>
            </tr>
          </tbody>
        </AlphaTable>,
      );
      clickCopyButton(container);

      const expected = ["| Key | Value |", "| --- | --- |", "|  | filled |"].join("\n");
      expect(clipboardText).toBe(expected);
    });

    it("handles cells with whitespace", () => {
      const { container } = render(
        <AlphaTable>
          <thead>
            <tr>
              <th>Name</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td> spaced </td>
            </tr>
          </tbody>
        </AlphaTable>,
      );
      clickCopyButton(container);

      // textContent captures the whitespace as rendered by the DOM
      expect(clipboardText).toContain("| Name |");
      expect(clipboardText).toContain("spaced");
    });

    it("treats body-only table (no thead) the same — first row gets separator", () => {
      const { container } = render(
        <AlphaTable>
          <tbody>
            <tr>
              <td>Row 1</td>
              <td>A</td>
            </tr>
            <tr>
              <td>Row 2</td>
              <td>B</td>
            </tr>
          </tbody>
        </AlphaTable>,
      );
      clickCopyButton(container);

      const expected = ["| Row 1 | A |", "| --- | --- |", "| Row 2 | B |"].join("\n");
      expect(clipboardText).toBe(expected);
    });

    it("formats a table with multiple body rows", () => {
      const { container } = render(
        <AlphaTable>
          <thead>
            <tr>
              <th>Layer</th>
              <th>Technologies</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Backend</td>
              <td>Python, FastAPI</td>
            </tr>
            <tr>
              <td>Frontend</td>
              <td>React, TypeScript</td>
            </tr>
            <tr>
              <td>Desktop</td>
              <td>Electron</td>
            </tr>
          </tbody>
        </AlphaTable>,
      );
      clickCopyButton(container);

      const expected = [
        "| Layer | Technologies |",
        "| --- | --- |",
        "| Backend | Python, FastAPI |",
        "| Frontend | React, TypeScript |",
        "| Desktop | Electron |",
      ].join("\n");
      expect(clipboardText).toBe(expected);
    });
  });

  describe("copy feedback", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("shows CheckIcon after clicking copy", () => {
      const { container } = render(twoColumnTable());
      const button = container.querySelector('button[aria-label="Copy table"]')!;

      // Grab the initial SVG path to compare after click
      const iconBefore = button.querySelector("svg")!.innerHTML;
      fireEvent.click(button);
      const iconAfter = button.querySelector("svg")!.innerHTML;

      expect(iconBefore).not.toBe(iconAfter);
    });

    it("reverts to CopyIcon after 1500ms", () => {
      const { container } = render(twoColumnTable());
      const button = container.querySelector('button[aria-label="Copy table"]')!;
      const iconBefore = button.querySelector("svg")!.innerHTML;

      fireEvent.click(button);
      expect(button.querySelector("svg")!.innerHTML).not.toBe(iconBefore);

      act(() => vi.advanceTimersByTime(1500));
      expect(button.querySelector("svg")!.innerHTML).toBe(iconBefore);
    });

    it("still shows CheckIcon before 1500ms have elapsed", () => {
      const { container } = render(twoColumnTable());
      const button = container.querySelector('button[aria-label="Copy table"]')!;
      const iconBefore = button.querySelector("svg")!.innerHTML;

      fireEvent.click(button);
      act(() => vi.advanceTimersByTime(1000));

      // Should still show CheckIcon — not yet reverted
      expect(button.querySelector("svg")!.innerHTML).not.toBe(iconBefore);
    });

    it("resets the timer on rapid double-click", () => {
      const { container } = render(twoColumnTable());
      const button = container.querySelector('button[aria-label="Copy table"]')!;
      const iconBefore = button.querySelector("svg")!.innerHTML;

      fireEvent.click(button);
      act(() => vi.advanceTimersByTime(1000));

      // Click again — should reset the 1500ms timer
      fireEvent.click(button);
      act(() => vi.advanceTimersByTime(1000));

      // Only 1000ms since last click — should still show CheckIcon
      expect(button.querySelector("svg")!.innerHTML).not.toBe(iconBefore);

      // Advance remaining 500ms — now it should revert
      act(() => vi.advanceTimersByTime(500));
      expect(button.querySelector("svg")!.innerHTML).toBe(iconBefore);
    });

    // Regression: the revert timer cleanup used to live in the ResizeObserver/wrap
    // effect, so toggling wrap re-ran that effect's cleanup and cancelled the pending
    // revert — leaving the CheckIcon ("copied") stuck. The cleanup is now in its own
    // unmount-only effect, so a wrap toggle no longer cancels the revert.
    it("still reverts to CopyIcon after a wrap toggle (wrap does not cancel the revert timer)", () => {
      const { container } = render(twoColumnTable());
      const copyButton = container.querySelector('button[aria-label="Copy table"]')!;
      const iconBefore = copyButton.querySelector("svg")!.innerHTML;

      fireEvent.click(copyButton);
      expect(copyButton.querySelector("svg")!.innerHTML).not.toBe(iconBefore);

      // Toggle wrap while the revert timer is pending. In the old code this re-ran
      // the ResizeObserver effect cleanup, clearing the timer so it never fired.
      const wrapButton = container.querySelector('button[data-testid="ALPHA_CHAT_TABLE_WRAP_TOGGLE"]')!;
      fireEvent.click(wrapButton);

      act(() => vi.advanceTimersByTime(1500));

      // The icon must revert — proving the timer survived the wrap toggle.
      const copyButtonAfter = container.querySelector('button[aria-label="Copy table"]')!;
      expect(copyButtonAfter.querySelector("svg")!.innerHTML).toBe(iconBefore);
    });

    it("does not leak timers on unmount", () => {
      const { container, unmount } = render(twoColumnTable());
      clickCopyButton(container);

      // Unmount while the timer is still pending — should not throw
      unmount();
      vi.advanceTimersByTime(2000);
    });
  });

  describe("wrap toggle", () => {
    it("renders the toggle button with 'Switch to scroll' tooltip in wrap mode (default)", () => {
      const { container } = render(twoColumnTable());
      const button = container.querySelector('button[aria-label="Switch to scroll"]');
      expect(button).toBeTruthy();
    });

    it("applies the wrap class to the wrapper by default", () => {
      const { container } = render(twoColumnTable());
      const wrapper = container.querySelector("table")!.parentElement!;
      expect(wrapper.className).toMatch(/wrap/);
      expect(wrapper.className).not.toMatch(/scroll/);
    });

    it("flips to scroll mode when clicked", () => {
      const { container } = render(twoColumnTable());
      const button = container.querySelector('button[aria-label="Switch to scroll"]')!;

      fireEvent.click(button);

      expect(container.querySelector('button[aria-label="Switch to wrap"]')).toBeTruthy();
      const wrapper = container.querySelector("table")!.parentElement!;
      expect(wrapper.className).toMatch(/scroll/);
      expect(wrapper.className).not.toMatch(/wrap/);
    });

    it("flips back to wrap mode on a second click", () => {
      const { container } = render(twoColumnTable());
      const button = container.querySelector('button[aria-label="Switch to scroll"]')!;

      fireEvent.click(button);
      const flipped = container.querySelector('button[aria-label="Switch to wrap"]')!;
      fireEvent.click(flipped);

      expect(container.querySelector('button[aria-label="Switch to scroll"]')).toBeTruthy();
      const wrapper = container.querySelector("table")!.parentElement!;
      expect(wrapper.className).toMatch(/wrap/);
      expect(wrapper.className).not.toMatch(/scroll/);
    });

    it("each AlphaTable owns its own wrap state", () => {
      const { container } = render(
        <>
          <AlphaTable>
            <tbody>
              <tr>
                <td>first</td>
              </tr>
            </tbody>
          </AlphaTable>
          <AlphaTable>
            <tbody>
              <tr>
                <td>second</td>
              </tr>
            </tbody>
          </AlphaTable>
        </>,
      );
      const toggles = container.querySelectorAll('button[aria-label="Switch to scroll"]');
      expect(toggles).toHaveLength(2);

      fireEvent.click(toggles[0]);

      // First flipped, second still in default wrap mode.
      expect(container.querySelectorAll('button[aria-label="Switch to wrap"]')).toHaveLength(1);
      expect(container.querySelectorAll('button[aria-label="Switch to scroll"]')).toHaveLength(1);
    });
  });
});
