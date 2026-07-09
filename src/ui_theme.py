"""Tema visual centralizado — Nidus."""

import customtkinter as ctk

# ── Paleta ───────────────────────────────────────────────────────────────
BG = "#1a1a2e"
SURFACE = "#16213e"
SURFACE_ALT = "#0f1a30"
ACCENT = "#e94560"
SECONDARY = "#0f3460"
SUCCESS = "#1a6b3a"
DANGER = "#6b1a1a"
DISABLED = "#555555"
TEXT = "#eaeaea"
TEXT_MUTED = "#8899bb"
TEXT_DIM = "#aaaaaa"
BORDER = "#2a2a4a"

FONT = "Segoe UI"
CORNER = 12
CORNER_SM = 8
PAD = 16
PAD_SM = 8


def setup_theme():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


def card(parent, **kwargs):
    opts = dict(fg_color=SURFACE, corner_radius=CORNER)
    opts.update(kwargs)
    return ctk.CTkFrame(parent, **opts)


def section_title(parent, text, **kwargs):
    return ctk.CTkLabel(
        parent, text=text,
        font=(FONT, 13, "bold"),
        text_color=ACCENT,
        anchor="w",
        **kwargs,
    )


def field_label(parent, text, **kwargs):
    return ctk.CTkLabel(
        parent, text=text,
        font=(FONT, 11),
        text_color=TEXT,
        anchor="w",
        **kwargs,
    )


def hint_label(parent, text, **kwargs):
    opts = dict(
        font=(FONT, 10),
        text_color=TEXT_MUTED,
        anchor="w",
        wraplength=400,
        justify="left",
    )
    opts.update(kwargs)
    return ctk.CTkLabel(parent, text=text, **opts)


def primary_btn(parent, text, command, **kwargs):
    opts = dict(
        text=text, command=command,
        font=(FONT, 13, "bold"),
        fg_color=ACCENT, hover_color="#c73a52",
        text_color="white", corner_radius=CORNER_SM,
        height=44,
    )
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


def secondary_btn(parent, text, command, **kwargs):
    opts = dict(
        text=text, command=command,
        font=(FONT, 11),
        fg_color=SECONDARY, hover_color="#1a4a80",
        text_color=TEXT, corner_radius=CORNER_SM,
        height=32,
    )
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


def ghost_btn(parent, text, command, **kwargs):
    opts = dict(
        text=text, command=command,
        font=(FONT, 10),
        fg_color="transparent", hover_color=SURFACE,
        text_color=TEXT_MUTED, corner_radius=CORNER_SM,
        height=28,
    )
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


def success_btn(parent, text, command, **kwargs):
    opts = dict(
        text=text, command=command,
        font=(FONT, 11),
        fg_color=SUCCESS, hover_color="#228b44",
        text_color="white", corner_radius=CORNER_SM,
        height=32,
    )
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


def danger_btn(parent, text, command, **kwargs):
    opts = dict(
        text=text, command=command,
        font=(FONT, 11),
        fg_color=DANGER, hover_color="#8b2222",
        text_color="white", corner_radius=CORNER_SM,
        height=32,
    )
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


def entry(parent, **kwargs):
    opts = dict(
        font=(FONT, 11),
        fg_color=SURFACE_ALT,
        border_color=BORDER,
        text_color=TEXT,
        corner_radius=CORNER_SM,
    )
    opts.update(kwargs)
    return ctk.CTkEntry(parent, **opts)


def combo(parent, values, variable=None, command=None, **kwargs):
    opts = dict(
        values=values,
        variable=variable,
        command=command,
        font=(FONT, 11),
        fg_color=SURFACE_ALT,
        border_color=BORDER,
        button_color=SECONDARY,
        button_hover_color="#1a4a80",
        dropdown_fg_color=SURFACE,
        dropdown_hover_color=SECONDARY,
        dropdown_text_color=TEXT,
        corner_radius=CORNER_SM,
        state="readonly",
    )
    opts.update(kwargs)
    return ctk.CTkComboBox(parent, **opts)
