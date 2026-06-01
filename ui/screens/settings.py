import pygame

from config import SCREEN_HEIGHT, SCREEN_WIDTH, BG_MID, MUTED_TEXT, NEON_BLUE, NEON_GREEN, WHITE_TEXT
from core.sound_player import apply_audio_settings, play_click
from data.settings_service import (
    categories,
    definitions_by_category,
    get_all_values,
    get_value,
    reset_category,
    reset_to_defaults,
    set_value,
    target_fps,
)
from data.settings_schema import SettingDefinition
from ui.screens.common import close_button_rect, draw_back_hint, draw_background, draw_close_button, draw_panel, draw_title


def _set_fullscreen(enabled: bool) -> pygame.Surface:
    # pygame.SCALED lets pygame upscale our logical SCREEN_WIDTH×SCREEN_HEIGHT
    # to whatever the native display resolution is, so the background covers
    # the full monitor instead of sitting in a 1280×800 box with black bars.
    flags = (pygame.FULLSCREEN | pygame.SCALED) if enabled else 0
    return pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), flags)


def _format_value(defn: SettingDefinition, value: object) -> str:
    if defn.value_type == "bool":
        return "ON" if bool(value) else "OFF"
    if defn.value_type == "float":
        text = f"{float(value):.2f}"
        return text.rstrip("0").rstrip(".")
    return str(value)


def _numeric_step(defn: SettingDefinition) -> float:
    if defn.step is not None:
        return float(defn.step)
    return 1.0


def _apply_special_setting(
    key: str,
    value: object,
    screen: pygame.Surface,
) -> pygame.Surface:
    if key == "display.fullscreen":
        return _set_fullscreen(bool(value))
    if key.startswith("audio."):
        # Live-apply volume / toggle changes without restarting the screen.
        apply_audio_settings()
    return screen


def run_settings(
    screen: pygame.Surface,
    fonts: dict,
    background: pygame.Surface | None,
) -> str | None:
    clock = pygame.time.Clock()
    pad = 26
    tabs_rect = pygame.Rect(pad, 114, SCREEN_WIDTH - pad * 2, 36)
    panel = pygame.Rect(pad, tabs_rect.bottom + 10, SCREEN_WIDTH - pad * 2, SCREEN_HEIGHT - tabs_rect.bottom - 90)
    list_rect = pygame.Rect(panel.x + 10, panel.y + 34, panel.width - 20, panel.height - 80)
    footer_rect = pygame.Rect(panel.x + 10, panel.bottom - 40, panel.width - 20, 28)

    category_keys = tuple(categories())
    grouped = definitions_by_category()
    active_tab = category_keys[0] if category_keys else "General"
    scroll = 0
    status_line = ""
    editing_key: str | None = None
    editing_buffer = ""
    action_rects: list[tuple[pygame.Rect, str, str, float | None]] = []
    tab_rects: dict[str, pygame.Rect] = {}
    reset_all_rect = pygame.Rect(0, 0, 0, 0)
    reset_tab_rect = pygame.Rect(0, 0, 0, 0)

    try:
        set_value("display.fullscreen", bool(pygame.display.get_surface().get_flags() & pygame.FULLSCREEN))
    except Exception:
        pass

    while True:
        clock.tick(target_fps())
        mx, my = pygame.mouse.get_pos()
        close_rect = close_button_rect()

        current_values = get_all_values()
        rows = grouped.get(active_tab, [])
        row_h = 36
        content_h = len(rows) * row_h
        max_scroll = max(0, content_h - list_rect.height)
        scroll = max(0, min(scroll, max_scroll))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if editing_key is not None:
                    editing_key = None
                    editing_buffer = ""
                    status_line = "Edit cancelled."
                    continue
                return "menu"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                try:
                    new_value = not bool(get_value("display.fullscreen"))
                    set_value("display.fullscreen", new_value)
                    screen = _apply_special_setting("display.fullscreen", new_value, screen)
                    status_line = "Fullscreen toggled."
                except Exception as exc:
                    status_line = str(exc)
                continue
            if editing_key is not None and event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    try:
                        committed = set_value(editing_key, editing_buffer)
                        screen = _apply_special_setting(editing_key, committed, screen)
                        status_line = f"Saved: {editing_key}"
                        editing_key = None
                        editing_buffer = ""
                    except Exception as exc:
                        status_line = str(exc)
                    continue
                if event.key == pygame.K_BACKSPACE:
                    editing_buffer = editing_buffer[:-1]
                    continue
                if event.unicode and event.unicode.isprintable() and len(editing_buffer) < 220:
                    editing_buffer += event.unicode
                    continue
            if event.type == pygame.MOUSEWHEEL and list_rect.collidepoint(mx, my):
                scroll = max(0, min(max_scroll, scroll - event.y * 34))
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if close_rect.collidepoint(mx, my):
                    play_click()
                    return "menu"
                if editing_key is not None:
                    editing_key = None
                    editing_buffer = ""
                    status_line = "Edit cancelled."
                    continue
                for cat, rect in tab_rects.items():
                    if rect.collidepoint(mx, my):
                        play_click()
                        active_tab = cat
                        scroll = 0
                        status_line = ""
                        break
                if reset_all_rect.collidepoint(mx, my):
                    play_click()
                    reset_to_defaults()
                    status_line = "All settings reset to defaults."
                    continue
                if reset_tab_rect.collidepoint(mx, my):
                    play_click()
                    reset_category(active_tab)
                    status_line = f"{active_tab} reset to defaults."
                    continue
                for rect, action, key, amount in action_rects:
                    if not rect.collidepoint(mx, my):
                        continue
                    defn = next((item for item in rows if item.key == key), None)
                    if defn is None:
                        continue
                    try:
                        if action == "toggle":
                            updated = set_value(key, not bool(current_values[key]))
                            screen = _apply_special_setting(key, updated, screen)
                            status_line = f"Updated {defn.label}"
                        elif action == "minus":
                            step = amount if amount is not None else _numeric_step(defn)
                            if defn.value_type == "int":
                                updated = set_value(key, int(current_values[key]) - int(step))
                            else:
                                updated = set_value(key, float(current_values[key]) - float(step))
                            screen = _apply_special_setting(key, updated, screen)
                            status_line = f"Updated {defn.label}"
                        elif action == "plus":
                            step = amount if amount is not None else _numeric_step(defn)
                            if defn.value_type == "int":
                                updated = set_value(key, int(current_values[key]) + int(step))
                            else:
                                updated = set_value(key, float(current_values[key]) + float(step))
                            screen = _apply_special_setting(key, updated, screen)
                            status_line = f"Updated {defn.label}"
                        elif action == "edit":
                            editing_key = key
                            editing_buffer = str(current_values[key])
                            status_line = f"Editing {defn.label}. Enter to save."
                    except Exception as exc:
                        status_line = str(exc)
                    break

        draw_background(screen, background)
        draw_title(screen, "SETTINGS", fonts, y=70)
        draw_panel(screen, panel, f"{active_tab} Settings", fonts)

        tab_rects = {}
        tab_w = max(100, int((tabs_rect.width - (len(category_keys) - 1) * 8) / max(1, len(category_keys))))
        for idx, cat in enumerate(category_keys):
            rect = pygame.Rect(tabs_rect.x + idx * (tab_w + 8), tabs_rect.y, tab_w, tabs_rect.height)
            tab_rects[cat] = rect
            active = cat == active_tab
            border = NEON_GREEN if active else (NEON_BLUE if rect.collidepoint(mx, my) else MUTED_TEXT)
            text_color = NEON_GREEN if active else WHITE_TEXT
            pygame.draw.rect(screen, BG_MID, rect)
            pygame.draw.rect(screen, border, rect, width=2)
            label = fonts["small"].render(cat, True, text_color)
            screen.blit(label, label.get_rect(center=rect.center))

        action_rects = []
        prev_clip = screen.get_clip()
        screen.set_clip(list_rect)
        for idx, defn in enumerate(rows):
            row_y = list_rect.y + idx * row_h - scroll
            if row_y + row_h < list_rect.y or row_y > list_rect.bottom:
                continue
            row_rect = pygame.Rect(list_rect.x + 2, row_y, list_rect.width - 4, row_h - 2)
            pygame.draw.rect(screen, BG_MID, row_rect)
            border_color = NEON_BLUE if idx % 2 == 0 else MUTED_TEXT
            pygame.draw.rect(screen, border_color, row_rect, width=1)

            value = current_values.get(defn.key, defn.default)
            label_text = fonts["small"].render(defn.label, True, WHITE_TEXT)
            screen.blit(label_text, (row_rect.x + 8, row_rect.y + 9))

            scope_text = fonts["small"].render(defn.apply_scope.upper(), True, MUTED_TEXT)
            screen.blit(scope_text, (row_rect.x + row_rect.width - 262, row_rect.y + 9))

            if defn.value_type == "bool":
                toggle_rect = pygame.Rect(row_rect.right - 120, row_rect.y + 5, 110, 24)
                state_on = bool(value)
                pygame.draw.rect(screen, BG_MID, toggle_rect)
                pygame.draw.rect(screen, NEON_GREEN if state_on else MUTED_TEXT, toggle_rect, width=2)
                text = fonts["small"].render("ON" if state_on else "OFF", True, WHITE_TEXT)
                screen.blit(text, text.get_rect(center=toggle_rect.center))
                action_rects.append((toggle_rect, "toggle", defn.key, None))
            elif defn.value_type in {"int", "float"}:
                minus_rect = pygame.Rect(row_rect.right - 120, row_rect.y + 5, 24, 24)
                plus_rect = pygame.Rect(row_rect.right - 34, row_rect.y + 5, 24, 24)
                value_rect = pygame.Rect(minus_rect.right + 4, row_rect.y + 5, plus_rect.x - minus_rect.right - 8, 24)
                for btn_rect, symbol, action in (
                    (minus_rect, "-", "minus"),
                    (plus_rect, "+", "plus"),
                ):
                    pygame.draw.rect(screen, BG_MID, btn_rect)
                    pygame.draw.rect(screen, NEON_GREEN if btn_rect.collidepoint(mx, my) else MUTED_TEXT, btn_rect, width=2)
                    sym = fonts["small"].render(symbol, True, WHITE_TEXT)
                    screen.blit(sym, sym.get_rect(center=btn_rect.center))
                    action_rects.append((btn_rect, action, defn.key, _numeric_step(defn)))
                pygame.draw.rect(screen, BG_MID, value_rect)
                pygame.draw.rect(screen, MUTED_TEXT, value_rect, width=1)
                text = fonts["small"].render(_format_value(defn, value), True, WHITE_TEXT)
                screen.blit(text, text.get_rect(center=value_rect.center))
            else:
                value_text = _format_value(defn, value)
                text_rect = pygame.Rect(row_rect.right - 250, row_rect.y + 5, 190, 24)
                edit_rect = pygame.Rect(row_rect.right - 54, row_rect.y + 5, 44, 24)
                pygame.draw.rect(screen, BG_MID, text_rect)
                pygame.draw.rect(screen, MUTED_TEXT, text_rect, width=1)
                render_text = fonts["small"].render(value_text[:32], True, WHITE_TEXT)
                screen.blit(render_text, (text_rect.x + 6, text_rect.y + 4))
                pygame.draw.rect(screen, BG_MID, edit_rect)
                pygame.draw.rect(screen, NEON_GREEN if edit_rect.collidepoint(mx, my) else MUTED_TEXT, edit_rect, width=2)
                edit_label = fonts["small"].render("Edit", True, WHITE_TEXT)
                screen.blit(edit_label, edit_label.get_rect(center=edit_rect.center))
                action_rects.append((edit_rect, "edit", defn.key, None))
        screen.set_clip(prev_clip)

        reset_all_rect = pygame.Rect(footer_rect.x, footer_rect.y, 190, footer_rect.height)
        reset_tab_rect = pygame.Rect(footer_rect.x + 202, footer_rect.y, 190, footer_rect.height)
        for rect, text in (
            (reset_all_rect, "Reset ALL defaults"),
            (reset_tab_rect, f"Reset {active_tab}"),
        ):
            pygame.draw.rect(screen, BG_MID, rect)
            pygame.draw.rect(screen, NEON_BLUE if rect.collidepoint(mx, my) else MUTED_TEXT, rect, width=2)
            label = fonts["small"].render(text, True, WHITE_TEXT)
            screen.blit(label, label.get_rect(center=rect.center))

        status_color = MUTED_TEXT if not status_line else NEON_GREEN
        status = fonts["small"].render(status_line or "Click values to edit. Esc — Back. F11 — Fullscreen.", True, status_color)
        screen.blit(status, (footer_rect.x + 404, footer_rect.y + 6))

        if editing_key is not None:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            screen.blit(overlay, (0, 0))
            modal = pygame.Rect((SCREEN_WIDTH - 760) // 2, (SCREEN_HEIGHT - 140) // 2, 760, 140)
            pygame.draw.rect(screen, BG_MID, modal)
            pygame.draw.rect(screen, NEON_GREEN, modal, width=2)
            prompt = fonts["small"].render(f"Editing {editing_key}. Enter to save, Esc to cancel.", True, WHITE_TEXT)
            screen.blit(prompt, (modal.x + 14, modal.y + 18))
            input_rect = pygame.Rect(modal.x + 14, modal.y + 52, modal.width - 28, 34)
            pygame.draw.rect(screen, (10, 10, 20), input_rect)
            pygame.draw.rect(screen, NEON_BLUE, input_rect, width=2)
            typed = fonts["small"].render(editing_buffer, True, WHITE_TEXT)
            screen.blit(typed, (input_rect.x + 8, input_rect.y + 8))

        draw_close_button(screen, fonts, hovered=close_rect.collidepoint(mx, my))
        draw_back_hint(screen, fonts)
        pygame.display.flip()
