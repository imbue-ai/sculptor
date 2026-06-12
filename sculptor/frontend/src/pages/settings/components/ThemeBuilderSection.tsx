import { Button, Flex, SegmentedControl, Select, Switch, Tooltip } from "@radix-ui/themes";
import { useAtom, useSetAtom } from "jotai";
import { LayoutGrid } from "lucide-react";
import type { ChangeEvent, KeyboardEvent, ReactElement } from "react";

import { ElementIds } from "~/api";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import type {
  AccentColor,
  ColorSettingKey,
  FontOption,
  GrayColor,
  HexOverride,
  PanelBackground,
  Radius,
  Scaling,
} from "~/common/state/atoms/themeBuilder.ts";
import {
  ACCENT_COLORS,
  DEFAULT_HEX_OVERRIDES,
  DEFAULT_THEME_BUILDER_SETTINGS,
  FONT_OPTIONS,
  GRAY_COLORS,
  PANEL_BACKGROUNDS,
  RADII,
  SCALINGS,
  themeBuilderSettingsAtom,
} from "~/common/state/atoms/themeBuilder.ts";
import { ensurePseudoTabAtom } from "~/common/state/atoms/workspaces.ts";
import type { AppearanceMode } from "~/common/theme/appearanceModes.ts";
import { APPEARANCE_MODES } from "~/common/theme/appearanceModes.ts";
import { isValidHex } from "~/common/theme/generateColorScale.ts";
import { getColorHex9, resolveGrayColor } from "~/common/theme/radixColorHexMap.ts";
import type { ShikiThemePairName } from "~/common/theme/shikiThemes.ts";
import { SHIKI_THEME_PAIR_NAMES } from "~/common/theme/shikiThemes.ts";
import { useResolvedTheme } from "~/common/Utils.ts";
import { COMPONENT_GALLERY_TAB_ID } from "~/components/workspaceTabIds.ts";

import { SettingRow } from "./SettingRow.tsx";
import { SettingsSectionLayout } from "./SettingsSection.tsx";
import styles from "./ThemeBuilderSection.module.scss";

const RADIUS_PREVIEW_VALUES: Record<Radius, string> = {
  none: "0px",
  small: "4px",
  medium: "8px",
  large: "12px",
  full: "9999px",
};

const ICON_SIZE = 16;

const handleRadioKeyDown = (event: KeyboardEvent, callback: () => void): void => {
  if (event.key === " " || event.key === "Enter") {
    event.preventDefault();
    callback();
  }
};

const ColorSwatchPicker = <T extends string>({
  colors,
  value,
  onChange,
  testId,
  appearance,
  isHexOverrideEnabled,
}: {
  colors: ReadonlyArray<T>;
  value: T;
  onChange: (color: T) => void;
  testId: string;
  appearance: "light" | "dark";
  isHexOverrideEnabled: boolean;
}): ReactElement => {
  return (
    <div role="radiogroup" data-testid={testId} className={styles.swatchGrid}>
      {colors.map((color) => {
        const bgColor = getColorHex9(color === "auto" ? "gray" : color, appearance);
        const isSelected = value === color && !isHexOverrideEnabled;
        return (
          <Tooltip content={color} key={color}>
            <div
              role="radio"
              tabIndex={0}
              aria-checked={value === color}
              aria-label={color}
              onClick={() => onChange(color)}
              onKeyDown={(e) => handleRadioKeyDown(e, () => onChange(color))}
              style={{ backgroundColor: bgColor }}
              className={`${styles.swatch} ${isSelected ? styles.swatchSelected : ""}`}
            />
          </Tooltip>
        );
      })}
    </div>
  );
};

const RadiusPreviewPicker = ({
  value,
  onChange,
  testId,
}: {
  value: Radius;
  onChange: (radius: Radius) => void;
  testId: string;
}): ReactElement => (
  <div role="radiogroup" data-testid={testId} className={styles.radiusGrid}>
    {RADII.map((radius) => (
      <Tooltip content={radius} key={radius}>
        <div
          role="radio"
          tabIndex={0}
          aria-checked={value === radius}
          aria-label={radius}
          onClick={() => onChange(radius)}
          onKeyDown={(e) => handleRadioKeyDown(e, () => onChange(radius))}
          style={{ borderRadius: RADIUS_PREVIEW_VALUES[radius] }}
          className={`${styles.radiusPreview} ${value === radius ? styles.radiusPreviewSelected : ""}`}
        />
      </Tooltip>
    ))}
  </div>
);

/** Strip the leading '#' and any non-hex characters from a user's input. */
const sanitizeHexInput = (raw: string): string => raw.replace(/[^0-9a-fA-F]/g, "").slice(0, 6);

/** Format a stored hex value (with #) for display in the input (without #). */
const hexForDisplay = (hex: string): string => hex.replace(/^#/, "");

const HexColorInput = ({
  colorName,
  accentColor,
  hexOverride,
  onHexChange,
  onToggle,
  testId,
  isGray,
}: {
  colorName: string;
  accentColor: AccentColor;
  hexOverride: HexOverride;
  onHexChange: (mode: "lightHex" | "darkHex", value: string) => void;
  onToggle: (enabled: boolean) => void;
  testId: string;
  isGray: boolean;
}): ReactElement => {
  const resolvedColor = isGray ? resolveGrayColor(colorName as GrayColor, accentColor) : colorName;
  const defaultLightHex = getColorHex9(resolvedColor, "light");
  const defaultDarkHex = getColorHex9(resolvedColor, "dark");

  const displayLightHex = hexOverride.enabled && hexOverride.lightHex !== "" ? hexOverride.lightHex : defaultLightHex;
  const displayDarkHex = hexOverride.enabled && hexOverride.darkHex !== "" ? hexOverride.darkHex : defaultDarkHex;

  const isLightHexInvalid = hexOverride.enabled && hexOverride.lightHex !== "" && !isValidHex(hexOverride.lightHex);
  const isDarkHexInvalid = hexOverride.enabled && hexOverride.darkHex !== "" && !isValidHex(hexOverride.darkHex);

  const handleLightChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const cleaned = sanitizeHexInput(e.target.value);
    onHexChange("lightHex", cleaned === "" ? "" : `#${cleaned}`);
  };

  const handleDarkChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const cleaned = sanitizeHexInput(e.target.value);
    onHexChange("darkHex", cleaned === "" ? "" : `#${cleaned}`);
  };

  return (
    <div className={styles.hexInputRow} data-testid={testId}>
      <label className={styles.hexToggleLabel}>
        <Switch size="1" checked={hexOverride.enabled} onCheckedChange={onToggle} aria-label="Toggle custom hex" />
        <span className={styles.hexToggleLabelText}>Custom</span>
      </label>
      <div className={styles.hexInputGroup}>
        <div className={styles.hexPreviewSwatch} style={{ backgroundColor: displayLightHex }} />
        <span className={styles.hexModeLabel}>Light</span>
        <div className={`${styles.hexInputWrapper} ${!hexOverride.enabled ? styles.hexInputWrapperDisabled : ""}`}>
          <span className={styles.hexPrefix}>#</span>
          <input
            className={`${styles.hexInput} ${isLightHexInvalid ? styles.hexInputInvalid : ""}`}
            value={hexForDisplay(displayLightHex)}
            onChange={handleLightChange}
            disabled={!hexOverride.enabled}
            placeholder={hexForDisplay(defaultLightHex)}
            aria-label="Light mode hex"
          />
        </div>
      </div>
      <div className={styles.hexInputGroup}>
        <div className={styles.hexPreviewSwatch} style={{ backgroundColor: displayDarkHex }} />
        <span className={styles.hexModeLabel}>Dark</span>
        <div className={`${styles.hexInputWrapper} ${!hexOverride.enabled ? styles.hexInputWrapperDisabled : ""}`}>
          <span className={styles.hexPrefix}>#</span>
          <input
            className={`${styles.hexInput} ${isDarkHexInvalid ? styles.hexInputInvalid : ""}`}
            value={hexForDisplay(displayDarkHex)}
            onChange={handleDarkChange}
            disabled={!hexOverride.enabled}
            placeholder={hexForDisplay(defaultDarkHex)}
            aria-label="Dark mode hex"
          />
        </div>
      </div>
    </div>
  );
};

const HEX_TEST_IDS: Record<ColorSettingKey, string> = {
  accentColor: ElementIds.SETTINGS_THEME_BUILDER_HEX_ACCENT_COLOR,
  grayColor: ElementIds.SETTINGS_THEME_BUILDER_HEX_GRAY_COLOR,
  dangerColor: ElementIds.SETTINGS_THEME_BUILDER_HEX_DANGER_COLOR,
  successColor: ElementIds.SETTINGS_THEME_BUILDER_HEX_SUCCESS_COLOR,
  warningColor: ElementIds.SETTINGS_THEME_BUILDER_HEX_WARNING_COLOR,
  infoColor: ElementIds.SETTINGS_THEME_BUILDER_HEX_INFO_COLOR,
};

export const ThemeBuilderSection = (): ReactElement => {
  const [settings, setSettings] = useAtom(themeBuilderSettingsAtom);
  const ensurePseudoTab = useSetAtom(ensurePseudoTabAtom);
  const { navigateToComponentGallery } = useImbueNavigate();
  const appearance = useResolvedTheme();

  const updateSetting = <TK extends keyof typeof settings>(key: TK, value: (typeof settings)[TK]): void => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const getHexOverrides = (prev: typeof settings): typeof DEFAULT_HEX_OVERRIDES =>
    prev.hexOverrides ?? DEFAULT_HEX_OVERRIDES;

  const handleColorSwatchChange = (key: ColorSettingKey, color: string): void => {
    setSettings((prev) => {
      const overrides = getHexOverrides(prev);
      return {
        ...prev,
        [key]: color,
        hexOverrides: {
          ...overrides,
          [key]: { ...overrides[key], enabled: false },
        },
      };
    });
  };

  const handleHexChange = (key: ColorSettingKey, mode: "lightHex" | "darkHex", value: string): void => {
    setSettings((prev) => {
      const overrides = getHexOverrides(prev);
      return {
        ...prev,
        hexOverrides: {
          ...overrides,
          [key]: { ...overrides[key], [mode]: value },
        },
      };
    });
  };

  const handleHexToggle = (key: ColorSettingKey, enabled: boolean): void => {
    setSettings((prev) => {
      const overrides = getHexOverrides(prev);
      return {
        ...prev,
        hexOverrides: {
          ...overrides,
          [key]: { ...overrides[key], enabled },
        },
      };
    });
  };

  const handleResetToDefaults = (): void => {
    setSettings((prev) => ({ ...DEFAULT_THEME_BUILDER_SETTINGS, appearance: prev.appearance }));
  };

  const handleOpenComponentGallery = (): void => {
    ensurePseudoTab(COMPONENT_GALLERY_TAB_ID);
    navigateToComponentGallery();
  };

  const hexOverrides = settings.hexOverrides ?? DEFAULT_HEX_OVERRIDES;

  const renderHexInput = (key: ColorSettingKey, isGray: boolean = false): ReactElement => (
    <HexColorInput
      colorName={settings[key]}
      accentColor={settings.accentColor}
      hexOverride={hexOverrides[key]}
      onHexChange={(mode, value) => handleHexChange(key, mode, value)}
      onToggle={(enabled) => handleHexToggle(key, enabled)}
      testId={HEX_TEST_IDS[key]}
      isGray={isGray}
    />
  );

  return (
    <SettingsSectionLayout
      description={
        <>
          <strong>Experimental:</strong> Customize colors, fonts, and visual style.
        </>
      }
    >
      <SettingRow title="Appearance" description="Control light mode, dark mode, or follow system preference.">
        <SegmentedControl.Root
          value={settings.appearance}
          onValueChange={(v) => updateSetting("appearance", v as AppearanceMode)}
          size="2"
          className={styles.appearanceToggle}
          data-testid={ElementIds.SETTINGS_THEME_BUILDER_APPEARANCE}
        >
          {APPEARANCE_MODES.map((mode) => {
            const Icon = mode.icon;
            return (
              <SegmentedControl.Item key={mode.id} value={mode.id}>
                <Flex align="center" gap="1">
                  <Icon size={ICON_SIZE} />
                  {mode.label}
                </Flex>
              </SegmentedControl.Item>
            );
          })}
        </SegmentedControl.Root>
      </SettingRow>

      <SettingRow title="Primary font" description="The font used for UI text, labels, and body content.">
        <Select.Root
          value={settings.primaryFont ?? "System default"}
          onValueChange={(v) => updateSetting("primaryFont", v as FontOption)}
          size="2"
        >
          <Select.Trigger variant="soft" data-testid={ElementIds.SETTINGS_THEME_BUILDER_DEFAULT_FONT} />
          <Select.Content>
            {FONT_OPTIONS.map((font) => (
              <Select.Item key={font} value={font} style={font !== "System default" ? { fontFamily: font } : undefined}>
                {font}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </SettingRow>

      <SettingRow title="Code font" description="The monospace font used for code, diffs, and terminal output.">
        <Select.Root
          value={settings.codeFont ?? "System default"}
          onValueChange={(v) => updateSetting("codeFont", v as FontOption)}
          size="2"
        >
          <Select.Trigger variant="soft" data-testid={ElementIds.SETTINGS_THEME_BUILDER_MONO_FONT} />
          <Select.Content>
            {FONT_OPTIONS.map((font) => (
              <Select.Item key={font} value={font} style={font !== "System default" ? { fontFamily: font } : undefined}>
                {font}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </SettingRow>

      <SettingRow title="Code theme" description="The syntax highlighting theme used for code blocks and diffs.">
        <Select.Root
          value={settings.codeTheme ?? "GitHub"}
          onValueChange={(v) => updateSetting("codeTheme", v as ShikiThemePairName)}
          size="2"
        >
          <Select.Trigger variant="soft" />
          <Select.Content>
            {SHIKI_THEME_PAIR_NAMES.map((name) => (
              <Select.Item key={name} value={name}>
                {name}
              </Select.Item>
            ))}
          </Select.Content>
        </Select.Root>
      </SettingRow>

      <div className={styles.colorSection}>
        <SettingRow
          title="Accent color"
          description="The primary color used for interactive elements throughout the app."
          footer={
            <>
              <ColorSwatchPicker
                colors={ACCENT_COLORS}
                value={settings.accentColor}
                onChange={(v) => handleColorSwatchChange("accentColor", v)}
                testId={ElementIds.SETTINGS_THEME_BUILDER_ACCENT_COLOR}
                appearance={appearance}
                isHexOverrideEnabled={hexOverrides.accentColor.enabled}
              />
              {renderHexInput("accentColor")}
            </>
          }
        >
          <span className={styles.selectedLabel}>{settings.accentColor}</span>
        </SettingRow>
      </div>

      <div className={styles.colorSection}>
        <SettingRow
          title="Gray color"
          description="The neutral color scale used for backgrounds, borders, and muted text."
          footer={
            <>
              <ColorSwatchPicker
                colors={GRAY_COLORS}
                value={settings.grayColor}
                onChange={(v) => handleColorSwatchChange("grayColor", v)}
                testId={ElementIds.SETTINGS_THEME_BUILDER_GRAY_COLOR}
                appearance={appearance}
                isHexOverrideEnabled={hexOverrides.grayColor.enabled}
              />
              {renderHexInput("grayColor", true)}
            </>
          }
        >
          <span className={styles.selectedLabel}>{settings.grayColor}</span>
        </SettingRow>
      </div>

      <SettingRow title="Radius" description="The border radius applied to buttons, cards, and other elements.">
        <Flex align="center" gap="3">
          <span className={styles.selectedLabel}>{settings.radius}</span>
          <RadiusPreviewPicker
            value={settings.radius}
            onChange={(v) => updateSetting("radius", v)}
            testId={ElementIds.SETTINGS_THEME_BUILDER_RADIUS}
          />
        </Flex>
      </SettingRow>

      <SettingRow title="Scaling" description="Global size multiplier for all UI elements.">
        <SegmentedControl.Root
          value={settings.scaling}
          onValueChange={(v) => updateSetting("scaling", v as Scaling)}
          size="2"
          data-testid={ElementIds.SETTINGS_THEME_BUILDER_SCALING}
        >
          {SCALINGS.map((s) => (
            <SegmentedControl.Item key={s} value={s}>
              {s}
            </SegmentedControl.Item>
          ))}
        </SegmentedControl.Root>
      </SettingRow>

      <SettingRow title="Panel background" description="Whether panel backgrounds are solid or translucent.">
        <SegmentedControl.Root
          value={settings.panelBackground}
          onValueChange={(v) => updateSetting("panelBackground", v as PanelBackground)}
          size="2"
          data-testid={ElementIds.SETTINGS_THEME_BUILDER_PANEL_BACKGROUND}
        >
          {PANEL_BACKGROUNDS.map((bg) => (
            <SegmentedControl.Item key={bg} value={bg}>
              {bg}
            </SegmentedControl.Item>
          ))}
        </SegmentedControl.Root>
      </SettingRow>

      <div className={styles.colorSection}>
        <SettingRow
          title="Danger color"
          description="Color used for destructive actions like delete buttons and error states."
          footer={
            <>
              <ColorSwatchPicker
                colors={ACCENT_COLORS}
                value={settings.dangerColor}
                onChange={(v) => handleColorSwatchChange("dangerColor", v)}
                testId={ElementIds.SETTINGS_THEME_BUILDER_DANGER_COLOR}
                appearance={appearance}
                isHexOverrideEnabled={hexOverrides.dangerColor.enabled}
              />
              {renderHexInput("dangerColor")}
            </>
          }
        >
          <span className={styles.selectedLabel}>{settings.dangerColor}</span>
        </SettingRow>
      </div>

      <div className={styles.colorSection}>
        <SettingRow
          title="Success color"
          description="Color used for success indicators and confirmation badges."
          footer={
            <>
              <ColorSwatchPicker
                colors={ACCENT_COLORS}
                value={settings.successColor}
                onChange={(v) => handleColorSwatchChange("successColor", v)}
                testId={ElementIds.SETTINGS_THEME_BUILDER_SUCCESS_COLOR}
                appearance={appearance}
                isHexOverrideEnabled={hexOverrides.successColor.enabled}
              />
              {renderHexInput("successColor")}
            </>
          }
        >
          <span className={styles.selectedLabel}>{settings.successColor}</span>
        </SettingRow>
      </div>

      <div className={styles.colorSection}>
        <SettingRow
          title="Warning color"
          description="Color used for warnings and attention-needed indicators."
          footer={
            <>
              <ColorSwatchPicker
                colors={ACCENT_COLORS}
                value={settings.warningColor}
                onChange={(v) => handleColorSwatchChange("warningColor", v)}
                testId={ElementIds.SETTINGS_THEME_BUILDER_WARNING_COLOR}
                appearance={appearance}
                isHexOverrideEnabled={hexOverrides.warningColor.enabled}
              />
              {renderHexInput("warningColor")}
            </>
          }
        >
          <span className={styles.selectedLabel}>{settings.warningColor}</span>
        </SettingRow>
      </div>

      <div className={styles.colorSection}>
        <SettingRow
          title="Info color"
          description="Color used for informational badges and notices."
          footer={
            <>
              <ColorSwatchPicker
                colors={ACCENT_COLORS}
                value={settings.infoColor}
                onChange={(v) => handleColorSwatchChange("infoColor", v)}
                testId={ElementIds.SETTINGS_THEME_BUILDER_INFO_COLOR}
                appearance={appearance}
                isHexOverrideEnabled={hexOverrides.infoColor.enabled}
              />
              {renderHexInput("infoColor")}
            </>
          }
        >
          <span className={styles.selectedLabel}>{settings.infoColor}</span>
        </SettingRow>
      </div>

      <Flex justify="between" py="4">
        <Button
          data-testid={ElementIds.SETTINGS_THEME_BUILDER_COMPONENT_GALLERY}
          variant="soft"
          size="2"
          onClick={handleOpenComponentGallery}
        >
          <LayoutGrid size={ICON_SIZE} />
          Component gallery
        </Button>
        <Button
          data-testid={ElementIds.SETTINGS_THEME_BUILDER_RESET}
          variant="soft"
          size="2"
          onClick={handleResetToDefaults}
        >
          Reset to defaults
        </Button>
      </Flex>
    </SettingsSectionLayout>
  );
};
