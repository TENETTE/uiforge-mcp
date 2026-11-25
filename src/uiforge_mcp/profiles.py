"""Configurable quality tiers and visual style presets that genuinely modulate rendering, geometry,
materials, procedural detail and theme tokens.

Supports 4 quality levels ('simple', 'standard', 'advanced', 'aaa') and 9 visual style presets
('kids', 'cartoon', 'stylized', 'minimal', 'web_saas', 'scifi', 'dark_fantasy', 'realistic',
'photorealistic') so the user or AI agent can choose anything from clean, playful children's UI
to SaaS dashboards to ultra-detailed AAA photorealistic game interfaces.
"""

from __future__ import annotations

from typing import Any

QUALITY_LEVELS: dict[str, dict[str, Any]] = {
    "simple": {
        "label": "Simple / Lightweight",
        "ss_max": 2,
        "pbr_mode": "flat",
        "shader_octaves_cap": 2,
        "noise_scale": 0.0,
        "bevel_scale": 0.55,
        "bump_scale": 0.25,
        "wear_scale": 0.0,
        "ornament_density": "minimal",
        "curve_detail": 0.7,
        "summary": "Fast flat/clean shading, minimal geometry accents, zero surface grain, 2x supersampling.",
    },
    "standard": {
        "label": "Standard / Balanced",
        "ss_max": 3,
        "pbr_mode": "balanced",
        "shader_octaves_cap": 4,
        "noise_scale": 0.55,
        "bevel_scale": 0.85,
        "bump_scale": 0.65,
        "wear_scale": 0.45,
        "ornament_density": "standard",
        "curve_detail": 1.0,
        "summary": "Balanced shading, moderate surface detail, core corner ornaments, 3x supersampling.",
    },
    "advanced": {
        "label": "Advanced / Production",
        "ss_max": 4,
        "pbr_mode": "full",
        "shader_octaves_cap": 6,
        "noise_scale": 1.0,
        "bevel_scale": 1.0,
        "bump_scale": 1.0,
        "wear_scale": 1.0,
        "ornament_density": "rich",
        "curve_detail": 1.0,
        "summary": "Full Cook-Torrance GGX PBR, studio/HDRI IBL, rich procedural ornaments, 4x supersampling.",
    },
    "aaa": {
        "label": "AAA / Photorealistic Studio",
        "ss_max": 4,
        "pbr_mode": "ultra",
        "shader_octaves_cap": 8,
        "noise_scale": 1.15,
        "bevel_scale": 1.15,
        "bump_scale": 1.25,
        "wear_scale": 1.25,
        "ornament_density": "ornate",
        "curve_detail": 1.35,
        "summary": "Maximum geometric detail, deepened micro-bevels, heightened edge wear and crevice AO, full 4x SS.",
    },
}

STYLE_PRESETS: dict[str, dict[str, Any]] = {
    "kids": {
        "label": "Kids & Family",
        "default_quality": "simple",
        "frame_preset": "cartoon_thick",
        "studio": "bright",
        "materials": ["candy_gloss", "clay_3d", "jelly", "plastic"],
        "colors": {
            "bg": "#fff7ed", "surface": "#ffffff", "primary": "#3b82f6", "accent": "#f59e0b",
            "text": "#1e293b", "muted": "#64748b", "success": "#22c55e", "danger": "#ef4444",
        },
        "numbers": {"radius-sm": 14, "radius-md": 20, "radius-lg": 28, "stroke-md": 3.5, "space-md": 16},
        "styles": {
            "panel": {"fill": "$surface", "stroke": {"color": "#1e293b", "width": 3.5, "align": "outside"},
                      "shadow": {"color": "#1e293b@0.22", "blur": 0, "dy": 6}},
            "button": {"fill": "$primary", "stroke": {"color": "#1e293b", "width": 3.5, "align": "outside"},
                       "shadow": {"color": "#1e293b@0.3", "blur": 0, "dy": 5}},
            "title": {"font": "Fredoka", "weight": 700, "size": 30, "fill": "$text"},
            "body": {"font": "Fredoka", "weight": 500, "size": 16, "fill": "$muted"},
        },
    },
    "cartoon": {
        "label": "Cartoon & Arcade",
        "default_quality": "standard",
        "frame_preset": "cartoon_thick",
        "studio": "bright",
        "materials": ["candy_gloss", "clay_3d", "enamel", "rubber"],
        "colors": {
            "bg": "#1e1b4b", "surface": "#312e81", "primary": "#facc15", "accent": "#fb7185",
            "text": "#ffffff", "muted": "#c7d2fe", "success": "#4ade80", "danger": "#f43f5e",
        },
        "numbers": {"radius-sm": 12, "radius-md": 18, "radius-lg": 24, "stroke-md": 4.0, "space-md": 14},
        "styles": {
            "panel": {"fill": "$surface", "stroke": {"color": "#090a14", "width": 4, "align": "outside"},
                      "shadow": {"color": "#090a14@0.65", "blur": 0, "dy": 7}},
            "button": {"material": {"name": "candy_gloss", "color": "$primary"},
                       "stroke": {"color": "#090a14", "width": 4, "align": "outside"}},
            "title": {"font": "Bangers", "weight": 400, "size": 36, "fill": "$text", "letter_spacing": 2},
            "body": {"font": "Fredoka", "weight": 600, "size": 16, "fill": "$muted"},
        },
    },
    "stylized": {
        "label": "Stylized Game",
        "default_quality": "standard",
        "frame_preset": "rpg_gold",
        "studio": "bright",
        "materials": ["enamel", "gem", "wood", "stone", "gold"],
        "colors": {
            "bg": "#111629", "surface": "#1c2541", "primary": "#6366f1", "accent": "#f59e0b",
            "text": "#f8fafc", "muted": "#94a3b8", "success": "#10b981", "danger": "#ef4444",
        },
        "numbers": {"radius-sm": 8, "radius-md": 14, "radius-lg": 20, "stroke-md": 2.0, "space-md": 14},
        "styles": {
            "panel": {"fill": "$surface@0.95", "stroke": {"color": "$primary@0.55", "width": 2, "align": "inside"},
                      "shadow": {"color": "#000000@0.5", "blur": 20, "dy": 8}},
            "button": {"fill": {"type": "linear", "angle": 90, "stops": ["$primary", "#4338ca"]},
                       "stroke": {"color": "#ffffff@0.25", "width": 1.5, "align": "inside"}},
            "title": {"font": "Rajdhani", "weight": 700, "size": 28, "fill": "$text", "letter_spacing": 1.5},
            "body": {"font": "Inter", "weight": 500, "size": 15, "fill": "$muted"},
        },
    },
    "minimal": {
        "label": "Minimal & Clean",
        "default_quality": "standard",
        "frame_preset": "luxury_minimal",
        "studio": "bright",
        "materials": ["glass", "liquid_glass", "paper", "chrome"],
        "colors": {
            "bg": "#f8fafc", "surface": "#ffffff", "primary": "#0f172a", "accent": "#2563eb",
            "text": "#0f172a", "muted": "#64748b", "success": "#16a34a", "danger": "#dc2626",
        },
        "numbers": {"radius-sm": 6, "radius-md": 10, "radius-lg": 16, "stroke-md": 1.0, "space-md": 16},
        "styles": {
            "panel": {"fill": "$surface", "stroke": {"color": "#0f172a@0.10", "width": 1, "align": "inside"},
                      "shadow": {"color": "#0f172a@0.08", "blur": 24, "dy": 8}},
            "button": {"fill": "$primary", "shadow": {"color": "#0f172a@0.15", "blur": 12, "dy": 4}},
            "title": {"font": "Inter", "weight": 700, "size": 24, "fill": "$text"},
            "body": {"font": "Inter", "weight": 400, "size": 14, "fill": "$muted"},
        },
    },
    "web_saas": {
        "label": "Web & Desktop SaaS",
        "default_quality": "standard",
        "frame_preset": "glass_card",
        "studio": "bright",
        "materials": ["liquid_glass", "glass", "chrome", "plastic"],
        "colors": {
            "bg": "#090d16", "surface": "#111827", "primary": "#38bdf8", "accent": "#818cf8",
            "text": "#f1f5f9", "muted": "#94a3b8", "success": "#22c55e", "danger": "#f43f5e",
        },
        "numbers": {"radius-sm": 6, "radius-md": 10, "radius-lg": 14, "stroke-md": 1.0, "space-md": 16},
        "styles": {
            "panel": {"fill": "$surface", "stroke": {"color": "#ffffff@0.10", "width": 1, "align": "inside"},
                      "shadow": {"color": "#000000@0.42", "blur": 24, "dy": 10}},
            "button": {"fill": {"type": "linear", "angle": 90, "stops": ["$primary", "$accent"]}},
            "title": {"font": "Inter", "weight": 700, "size": 22, "fill": "$text"},
            "body": {"font": "Inter", "weight": 400, "size": 14, "fill": "$muted"},
        },
    },
    "scifi": {
        "label": "Sci-Fi & Tactical HUD",
        "default_quality": "advanced",
        "frame_preset": "scifi_hud",
        "studio": "cyberpunk",
        "materials": ["carbon_twill", "hologram", "energy_shield", "liquid_glass", "neon"],
        "colors": {
            "bg": "#060b14", "surface": "#0e1726", "primary": "#22d3ee", "accent": "#f43f5e",
            "text": "#ecfeff", "muted": "#7dd3fc", "success": "#10b981", "danger": "#f43f5e",
        },
        "numbers": {"radius-sm": 4, "radius-md": 10, "radius-lg": 18, "stroke-md": 1.5, "space-md": 12},
        "styles": {
            "panel": {"fill": "$surface@0.92", "stroke": {"color": "$primary@0.5", "width": 1.5, "align": "inside"},
                      "inner_glow": {"color": "$primary@0.12", "blur": 14},
                      "shadow": {"color": "#000000@0.6", "blur": 24, "dy": 10}},
            "button": {"fill": "$primary@0.16", "stroke": {"color": "$primary", "width": 1.5, "align": "inside"},
                       "glow": {"color": "$primary@0.45", "blur": 12}},
            "title": {"font": "Rajdhani", "weight": 700, "size": 26, "fill": "$primary", "letter_spacing": 2.5},
            "body": {"font": "JetBrains Mono", "weight": 400, "size": 13, "fill": "$muted"},
        },
    },
    "dark_fantasy": {
        "label": "Dark Fantasy RPG",
        "default_quality": "aaa",
        "frame_preset": "royal_ornate",
        "studio": "warm",
        "materials": ["hammered_gold", "gold", "iron", "bronze", "obsidian", "aged_parchment", "ruby", "wax_seal"],
        "colors": {
            "bg": "#0b0912", "surface": "#1a1426", "primary": "#d4af37", "accent": "#e11d48",
            "text": "#fef3c7", "muted": "#a8a29e", "success": "#16a34a", "danger": "#dc2626",
        },
        "numbers": {"radius-sm": 4, "radius-md": 10, "radius-lg": 14, "stroke-md": 2.0, "space-md": 14},
        "styles": {
            "panel": {"material": "obsidian", "stroke": {"color": "$primary@0.7", "width": 2, "align": "inside"},
                      "shadow": {"color": "#000000@0.75", "blur": 28, "dy": 12}},
            "button": {"material": "hammered_gold", "shadow": {"color": "#000000@0.7", "blur": 12, "dy": 4}},
            "title": {"font": "Cinzel", "weight": 700, "size": 26, "fill": "$text", "letter_spacing": 2.0},
            "body": {"font": "Inter", "weight": 400, "size": 14, "fill": "$muted"},
        },
    },
    "realistic": {
        "label": "Realistic Simulation & Racing",
        "default_quality": "advanced",
        "frame_preset": "luxury_minimal",
        "studio": "dark",
        "materials": ["carbon_twill", "radial_metal", "steel", "chrome", "leather", "glass"],
        "colors": {
            "bg": "#090b0f", "surface": "#141820", "primary": "#ef4444", "accent": "#f59e0b",
            "text": "#f2f4f7", "muted": "#8b929c", "success": "#22c55e", "danger": "#ef4444",
        },
        "numbers": {"radius-sm": 3, "radius-md": 6, "radius-lg": 10, "stroke-md": 1.2, "space-md": 12},
        "styles": {
            "panel": {"fill": {"type": "linear", "angle": 90, "stops": ["#171a20d9", "#0b0d10d9"]},
                      "stroke": {"color": "#ffffff@0.18", "width": 1.2, "align": "inside"},
                      "shadow": {"color": "#000000@0.55", "blur": 26, "dy": 12}},
            "button": {"material": "steel", "shadow": {"color": "#000000@0.55", "blur": 10, "dy": 4}},
            "title": {"font": "Barlow Condensed", "weight": 700, "size": 28, "fill": "$text", "letter_spacing": 2.2},
            "body": {"font": "JetBrains Mono", "weight": 500, "size": 14, "fill": "$muted"},
        },
    },
    "photorealistic": {
        "label": "Photorealistic Studio PBR",
        "default_quality": "aaa",
        "frame_preset": "luxury_minimal",
        "studio": "bright",
        "materials": ["chrome", "gold", "silver", "copper", "marble", "leather", "wood", "ruby", "emerald"],
        "colors": {
            "bg": "#0d1017", "surface": "#161b26", "primary": "#e6b038", "accent": "#38bdf8",
            "text": "#f8fafc", "muted": "#94a3b8", "success": "#22c55e", "danger": "#ef4444",
        },
        "numbers": {"radius-sm": 6, "radius-md": 12, "radius-lg": 18, "stroke-md": 1.5, "space-md": 16},
        "styles": {
            "panel": {"material": "marble", "shadow": {"color": "#000000@0.65", "blur": 30, "dy": 14}},
            "button": {"material": "gold", "shadow": {"color": "#000000@0.6", "blur": 14, "dy": 5}},
            "title": {"font": "Inter", "weight": 700, "size": 26, "fill": "$text"},
            "body": {"font": "Inter", "weight": 400, "size": 14, "fill": "$muted"},
        },
    },
}


def normalize_quality(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    v = str(value).strip().lower()
    aliases = {
        "basit": "simple", "low": "simple", "draft": "simple", "fast": "simple",
        "orta": "standard", "medium": "standard", "balanced": "standard",
        "gelismis": "advanced", "gelişmiş": "advanced", "high": "advanced", "production": "advanced",
        "profesyonel": "aaa", "pro": "aaa", "ultra": "aaa", "max": "aaa",
    }
    v = aliases.get(v, v)
    if v not in QUALITY_LEVELS:
        raise ValueError(f"quality must be one of {', '.join(QUALITY_LEVELS)} (got {value!r})")
    return v


def normalize_style_preset(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    v = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "cocuk": "kids", "çocuk": "kids", "children": "kids", "playful": "kids",
        "cizgi_film": "cartoon", "çizgi_film": "cartoon", "toon": "cartoon", "arcade": "cartoon",
        "stilize": "stylized",
        "clean": "minimal", "modern": "minimal",
        "web": "web_saas", "saas": "web_saas", "app": "web_saas", "desktop": "web_saas",
        "bilim_kurgu": "scifi", "sci_fi": "scifi", "cyberpunk": "scifi", "hud": "scifi",
        "karanlik_fantastik": "dark_fantasy", "karanlık_fantastik": "dark_fantasy", "fantasy": "dark_fantasy", "rpg": "dark_fantasy",
        "gercekci": "realistic", "gerçekçi": "realistic", "sim": "realistic", "racing": "realistic",
        "fotogercekci": "photorealistic", "fotogerçekçi": "photorealistic", "photo": "photorealistic", "pbr": "photorealistic",
    }
    v = aliases.get(v, v)
    if v not in STYLE_PRESETS:
        raise ValueError(f"style_preset must be one of {', '.join(STYLE_PRESETS)} (got {value!r})")
    return v


def resolve_profile(theme: dict | None, canvas: dict | None = None) -> dict[str, Any]:
    """Return effective quality tier settings + active style preset merged from theme and canvas."""
    t_prof = (theme or {}).get("profile") or {}
    c_prof = (canvas or {}).get("profile") or {}
    style_name = c_prof.get("style_preset") or t_prof.get("style_preset")
    q_name = c_prof.get("quality") or t_prof.get("quality")
    if not q_name and style_name and style_name in STYLE_PRESETS:
        q_name = STYLE_PRESETS[style_name]["default_quality"]
    q_name = q_name if q_name in QUALITY_LEVELS else "advanced"
    q_cfg = dict(QUALITY_LEVELS[q_name])
    q_cfg["quality"] = q_name
    q_cfg["style_preset"] = style_name
    if style_name and style_name in STYLE_PRESETS:
        sp = STYLE_PRESETS[style_name]
        q_cfg["studio"] = sp["studio"]
        q_cfg["frame_preset"] = sp["frame_preset"]
    return q_cfg


def apply_quality_to_pbr(spec: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Modulate PBR spec according to active quality level ('simple', 'standard', 'advanced', 'aaa')."""
    out = dict(spec)
    mode = profile.get("pbr_mode", "full")
    if mode == "flat":
        out["metallic"] = min(0.15, float(out.get("metallic", 0.0)) * 0.2)
        out["roughness"] = max(0.55, float(out.get("roughness", 0.5)))
        out["bevel_depth"] = float(out.get("bevel_depth", 1.0)) * 0.45
        out["bump_strength"] = float(out.get("bump_strength", 0.4)) * 0.2
        out["wear"] = 0.0
        out["clearcoat"] = min(0.15, float(out.get("clearcoat", 0.0)))
        out["env"] = min(0.35, float(out.get("env", 0.8)))
        out["ao_strength"] = min(0.25, float(out.get("ao_strength", 0.45)))
    elif mode == "balanced":
        out["bevel_depth"] = float(out.get("bevel_depth", 1.0)) * 0.82
        out["bump_strength"] = float(out.get("bump_strength", 0.4)) * 0.65
        out["wear"] = float(out.get("wear", 0.0)) * 0.45
    elif mode == "ultra":
        out["bevel_depth"] = float(out.get("bevel_depth", 1.0)) * 1.15
        out["bump_strength"] = float(out.get("bump_strength", 0.4)) * 1.25
        out["wear"] = min(1.0, float(out.get("wear", 0.0)) * 1.25)
        out["ao_strength"] = min(1.0, float(out.get("ao_strength", 0.5)) * 1.18)
    if profile.get("studio") and "studio" not in spec and not spec.get("env_map"):
        out["studio"] = profile["studio"]
    return out
