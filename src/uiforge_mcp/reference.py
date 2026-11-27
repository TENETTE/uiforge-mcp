"""Full reference for the model, served by the guide tool (clients cut long server instructions)."""

TOPICS = {
    "index": """\
Topics: animation, design, export, fills, geometry, layers, reuse, review, shader, style, text. Call guide(topic) for one, guide("all") for everything. Tool docstrings hold the per-tool details.
""",
    "fills": """\
Fill: a color, or a gradient/pattern object:
  {"type":"linear","angle":90,"stops":[[0,"#3b82f6"],[1,"#1d4ed8"]]}   (angle 0 = left->right, 90 = top->bottom)
  {"type":"radial","cx":0.5,"cy":0.5,"r":0.5,"stops":[...]}            (cx/cy/r relative to the element box)
  {"type":"conic","from":135,"to":405,"stops":[...]}                   (sweep around the box centre; angles as in add_arc)
  {"type":"stripes"|"dots"|"grid","color":"#fff@0.08","color2":"transparent","size":8,"angle":45}
  {"type":"carbon","color":"#2a2d33","color2":"#0d0e10","size":4}      (carbon-fibre weave)
  {"type":"brushed","color":"#9aa3ad","color2":"#5c646e","angle":0,"amount":0.5}   (brushed metal)
  {"type":"hex","color":"#fff@0.1","size":16,"line_width":1}           (honeycomb lines)
  {"type":"clouds","color":"#fff@0.3","color2":"transparent","size":48,"octaves":4,"seed":1,"contrast":1.5}
  {"type":"image","path":"C:/textures/metal.png","fit":"cover"|"stretch"|"tile","scale":1}   (your own texture)
  Gradients take "space":"oklab" for vivid, even blends between distant hues (default "srgb").
  A list of fills stacks them bottom to top (Figma fill stack): [gradient, {"type":"stripes",...}, "#fff@0.1"].
  Image fill also takes "zoom" (>= 1) and "focus" [fx, fy] to frame a photo inside any shape.
Ready materials (39 built-in, Cook-Torrance GGX PBR with perspective HDR studio IBL & ACES filmic tone mapping):
  style {"material": "gold"} or {"material": {"name": "wood", "color": "$primary", "scale": 1, "seed": 2,
  "t": 0, "shine": 0.5}} adds a procedural albedo+bump shader plus physical surface lighting; explicit style keys override it.
  Metals: gold, silver, chrome, bronze, copper, steel, iron, radial_metal, hammered_gold, rust.
  Stone & Gems: stone, runic_stone, marble, obsidian, jade, gem, ruby, emerald, lava, ice.
  Organic & Craft: wood, leather, paper, aged_parchment, fabric, carbon_twill, wax_seal, enamel.
  Modern & Sci-Fi: glass, liquid_glass, hologram, energy_shield, foil_holographic, neon, plastic,
  candy_gloss, clay_3d, rubber, jelly.
  Animate lava / jelly / hologram / runic_stone / energy_shield / foil_holographic with "style.material.t",
  or sweep a highlight across any lit material with "style.material.shine" (0..1).
  From scratch: write a shader fill (guide("shader")), pair with style.pbr or style.light, or save custom materials with
  set_theme(materials={"dark_oak": {"material": "wood", "color": "#4a2c18", "scale": 2}, ...}).
Images: add_image takes crop, cutout (removes a flat background), zoom / focus (pan and zoom), animated
  GIF / APNG / WebP or sheet {"cols", "rows", "count"} with frame (keyframe "frame" to play it). Images move
  with sub-pixel precision, so slow pans and slides stay smooth.
""",
    "shader": """\
Shader fill (a fill object):
  {"type":"shader","code":"...","params":{...}} - your own per-pixel formula when no preset fits (plasma,
    energy, hologram scanlines, marble, wood, rust, ripples, scales, cracks, warped patterns...). Write plain
    statements that end by assigning r, g, b (0..1), optionally a (alpha) and height (0..1 surface bump fed
    into style.light for physically lit grain / cracks / pores). Inputs: x, y (units from box top-left),
    u, v (0..1 across box), w, h (box size), px (pixels per unit), pi, d (signed distance inward from the
    shape edge in units), edge (0 at border -> 1 inside). Functions: sin cos tan asin acos atan atan2 sqrt
    abs exp log pow floor ceil round fract mod min max sign clamp mix step smoothstep length hypot where,
    noise(x,y[,seed]), fbm(x,y,octaves[,seed]), ridged(x,y,octaves[,seed]), turbulence(x,y,octaves[,seed]),
    voronoi(x,y[,seed]), rand(x,y[,seed]). No if/loops: use where(). Compiled to fused CUDA on GPU.
    params: numbers become names; colour strings ("$primary", "#ff8800") become name_r name_g name_b name_a.
    Animate any param with set_keyframes, property "style.fill.params.<name>" (e.g. a time param t).
    Example (energy core): {"type":"shader","params":{"c":"#38bdf8","t":0},"code":
      "d = length(u-0.5, v-0.5)*2; n = fbm(x/30+t, y/30, 4); k = clamp(1-d+n*0.4); r = c_r*k+k*k*0.6; g = c_g*k+k*k*0.6; b = c_b*k; a = smoothstep(1, 0.7, d)"}
""",
    "style": """\
Style object (every key optional; `style` may also be a theme style name, or {"use":"name", ...overrides}):
  fill, opacity, noise: 0-1, blur: px (softens the whole element: light blooms, haze),
  stroke {color, width, align: inside|center|outside, offset, join: miter|round|bevel, miter_limit, dash: [on, off],
    dash_offset} - or a list of strokes for double outlines. Polygons/paths default to sharp miter corners,
  blend: normal|add|screen|multiply|overlay|soft-light|hard-light|color-dodge|color-burn|darken|lighten|difference|
    erase (cuts a hole through what is already on the same layer: windows, notches, cut-out lettering),
  shadow {color, blur, dx, dy, spread, knockout}, glow {color, blur, strength, spread},
  inner_shadow {color, blur, dx, dy}, inner_glow {color, blur}, bevel {size, highlight, shadow},
  pbr {metallic, roughness, clearcoat, clearcoat_roughness, ior, anisotropy, brush_angle ("radial" or deg),
    sss, emissive, wear, profile: round|chamfer|machined|dome|facet|engraved|flat, bevel_size, bevel_depth,
    crown, bump_strength, ao, env, env_rotation, studio: bright|warm|dark|sunset|cyberpunk, env_map (path to
    equirectangular .hdr/.png/.jpg panorama), exposure, angle, altitude, shine} - full linear-HDR
    Cook-Torrance GGX PBR + perspective HDRI + ACES filmic tone mapping (also works on merged layers),
  light {angle, altitude, size, depth, profile: round|chisel|machined|pillow|engraved, highlight, shadow,
    gloss, env, env_rotation, anisotropy, brush_angle, fresnel, bump_strength, shine, soften} - stylized 2.5D
    surface bevel lighting (angle = where the light comes from; 225 = top-left; shine = 0..1 sheen sweep),
  mask: a fill spec whose alpha fades the element out (e.g. a linear gradient from opaque to "#000@0");
    mask_mode "luminance" uses its brightness instead. An element's clip_mode "luminance" masks it by the
    brightness of the clip target instead of its shape.
  adjust {brightness, contrast, saturation, exposure, temperature, shadows, highlights: -1..1, hue: degrees,
    tint: color, invert}.
  blur and backdrop_blur take a number or a progressive blur {radius, angle, start, end} (sharp -> soft).
  backdrop_blur blurs what is beneath (frosted glass); glass {refraction, depth, dispersion, frost, light,
    intensity} bends, splits and rim-lights what is beneath (glass buttons, liquid-glass panels).
  noise: 0..1, or {mode: mono | duo | multi, amount, size, colors: [c1, c2], density} (film grain, speckle).
  texture: number or {amount, size, seed} roughens the edges (worn, stamped, torn, hand-cut looks).
  A fill list entry may carry its own blend: [gradient, {"type": "radial", ..., "blend": "overlay"}].
  shadow / glow / inner_shadow / inner_glow also accept a list for stacked effects.
""",
    "design": """\
Shapes like a design tool: boolean_elements merges / subtracts / intersects / excludes filled shapes into one
exact vector outline (strokes and shadows follow the cut; prefer it to blend "erase" for holes); add_rect
smoothing 0..1 gives Figma-style smoothed "squircle" corners; arrange_elements(wrap=true) flows items onto new
lines; set_theme(modes={...}, mode=...) switches every $token between light / dark / team / seasonal sets.
export_svg writes an editable vector SVG for Figma, Penpot, Illustrator and the web.
style.feather: px softens only the edge (soft light spots, fog, beams).
style.backdrop_blur: px blurs whatever is already drawn beneath the shape (frosted glass panels; give
  its shadow "knockout": true so the shadow does not show through the glass);
stroke.sides ["top", "bottom"...] strokes only some edges of a rect (tab underlines, dividers);
add_text max_lines + max_width truncates with "...", decoration "underline" | "strikethrough";
canvas_version saves / restores named versions of a canvas.
make_palette(base) builds a 50-950 colour scale (even perceived lightness, same hue, WCAG text contrast per
step, matching accent hues) and can add it to the theme or a mode. restyle swaps a colour or font across
every canvas and theme style at once (Figma "selection colours"), or sets props on matching elements.
path_ops: flatten (any shape -> plain path), offset (grow / shrink a shape: inner panels, even rims),
outline_stroke (a stroke or line -> filled shape that can take gradients, effects and booleans), simplify;
on text, flatten turns the glyphs into an editable path. find_elements selects matching objects (same look,
colour, font, text). restyle replace_text finds and replaces copy. canvas_version diff compares versions.
Tokens: set_theme(numbers={"space-md": 16}) then "$space-md" in any number (radius, width, gap, size,
blur...; not x / y), per mode too; set_theme(tokens=<W3C DTCG json>) imports Tokens Studio / Penpot tokens,
export_theme("dtcg") writes them. Element "note" adds a designer note (shown in specs and as a web tooltip).
Live auto layout: arrange_elements(..., container=id, live=true) keeps re-flowing on every change (a
button hugs its label, lists re-flow); children take layout_size {width / height: "fill" | number, min_*,
max_*}, span [cols, rows] in grids, absolute true. Components: add_instance variant {prop: value} (states
named "prop=value"), hide / show [ids], slots {placeholder: canvas}. vectorize_image turns a picture into
editable vector paths. Lines take start_cap / end_cap (arrow, triangle, circle, square, diamond, bar),
taper, width_profile and wiggle. Fills also take {"type": "diamond", ...}.
""",
    "layers": """\
Layers (create_layer): a canvas is a stack of layers, bottom to top; new elements go to the active layer.
A layer has its own opacity, blend mode and style - layer styles (shadow, glow, stroke, light, blur, adjust,
mask, perspective...) apply to everything on the layer as one merged shape. style.perspective
({"rotate_y": 24, "rotate_x": -8, "visor_curve": 0.18}) renders 3D diegetic panels and curved-visor HUDs.
clip=true confines a layer to the pixels of the layer below: that is how you paint shading and highlights
freely on top of a base shape (dark soft shapes on a multiply layer, light ones on a screen or overlay layer).
export_layers / export_psd give the stack back as separate images or an editable PSD.
""",
    "geometry": """\
Angles (add_arc, add_ticks, conic): degrees, 0 = 3 o'clock, clockwise. A classic gauge sweeps 135 -> 405.
Any element takes rotation (degrees clockwise) and origin [x, y] as the pivot (default: its centre) -
e.g. a needle pivoting on the gauge hub. Shapes and text take skew (degrees) for slanted, italic looks.
Any element also takes scale / scale_x / scale_y and flip_x / flip_y (mirror; lighting stays put) - set
them with update_element or as extra keys in batch add ops. Text takes arc {cx, cy, radius} to run along
a circle. Paths take fill_rule "nonzero" | "evenodd".
""",
    "text": """\
add_text: size (px, default 24), font (list_fonts; 10 bundled + system + the workspace fonts folder),
weight 100-900 or "bold"..., anchor ("top-left", "center", "middle-left", "bottom-right", "baseline-left"...;
"center" is optically centred on capital height), align for multi-line text.
max_width wraps lines; fit_width shrinks the size until the text fits; max_lines (with max_width) cuts the
text and ends it with "..."; decoration "underline" | "strikethrough"; letter_spacing (px); line_height;
uppercase true or "tr" (Turkish i -> I-dot rules); case upper | lower | title | tr-upper | small-caps;
italic; skew; stroke = outline behind the glyphs. list "bullet" | "number", paragraph_spacing, indent;
features ["tnum", "smcp", "ss01"...] (OpenType; warns when the font lacks one); axes {"wdth": 75, ...};
trim true (box hugs cap height to baseline). Colour emoji are drawn in colour.
arc {cx, cy, radius, angle, side: outer|inner} sets text on a circle; path {"d": svg path} or {"points"}
runs it along any path (Latin, Greek, Cyrillic).
lang ("ar", "he", "hi", "th", "ja", "zh-Hans", "zh-Hant", "ko", "tr"...): Arabic, Hebrew, Indic, Thai and
CJK are shaped with HarfBuzz and fall back to bundled Noto / system fonts. Always set lang for Han text.
{placeholders} in text are filled from canvas vars, template rows and string tables (set_strings; render
any export with language=...; "pseudo", "pseudo-long", "pseudo-rtl" stress-test layouts).
measure_text gives the real size before you place text; exports refuse text no font can draw.
""",
    "reuse": """\
Reuse and import: add_instance places another canvas as a live component (edit once, every copy follows);
duplicate_element with count / rotate / pivot makes linear and radial arrays; add_svg imports SVG markup
or a .svg file as editable paths (logos, icons from any set, art you write as SVG).
""",
    "review": """\
Checking: review_canvas finds clipped shadows at the canvas edge, low text contrast, tiny text, missing
glyphs, blurry half-pixel rects, broken layers and animations, and lints the design (edges that almost
line up, too many radii / stroke widths / text sizes, hard-coded colours instead of tokens). inspect_pixels reads exact colours.
view_image shows you a reference image from disk with its dominant palette. fit_canvas trims or grows the
canvas to the painted area.
""",
    "animation": """\
Animation: create_animation, then set_keyframes per (target, property). Any numeric or color property can be
keyframed (x, width, rotation, radius, end_angle, style.glow.blur, style.fill, ...) plus the helpers dx, dy
(move), scale / scale_x / scale_y (around the pivot) and opacity. Check motion with preview_animation (a
filmstrip of frames) and export with export_animation (sprite sheet, frames, GIF/APNG/WebP, Lottie JSON, or
keyframe JSON). Eases include spring ("spring-out"). Animation frames render in parallel.
property "motion" travels along a path: values 0..1, path {"d": "M 0 0 C ...", "rotate": true}.
export_animation motion_blur 4-8 averages sub-frames (camera shutter) for fast spins and swipes.
Lottie: plain shapes and text become vector shape layers; effects move as pictures; animated glow /
shape becomes one picture per frame (the result lists which).
Interactions & Data Binding:
  set_interaction(canvas, id, trigger, action, ..., sfx="ui_click") - triggers load, hover, leave, press,
  release, click, key:<Key>, end:<animation>; actions play / stop / set_state / clear_state / toggle_state /
  navigate / overlay / back / url. Runs in export_web / export_react (with arrow-key & Gamepad API focus
  navigation) and generates controller code in export_screen (Unity, Godot, Roblox).
  set_binding(canvas, data={"hp": 75, "max_hp": 100}, target="hp_bar", property="width",
  expr="clamp(hp / max_hp, 0, 1) * 240") - reactive variables & expressions for bars, colours, visibility and
  {placeholders}; test live with preview(canvas, data={"hp": 15}); exported to Web, React props & engines.
  live_preview("start") launches a local browser studio (127.0.0.1 SSE) that auto-reloads on every edit.
export_animation "mp4" / "webm" writes video (needs ffmpeg); repeat plays a loop several times.
""",
    "export": """\
Which export to use:
  export_asset   one engine-ready sprite (engine: unity | unreal | roblox | godot | generic) with 9-slice
                 borders (nine_slice: "auto") and a .uiforge.json; write_engine_helpers adds the importer.
  export_pbr_maps  real-time engine PBR texture map set (beauty, albedo, tangent normal OpenGL/DirectX,
                 roughness, metallic, ao, height, packed ORM, emissive) + Godot 4 CanvasTexture .tres.
  export_png     PNG / WebP / JPG / ICO at scales [1, 2], exact sizes, or preset "ios" | "android" | "web"
                 for whole density sets; trim, ids / group, state, language.
  export_svg     editable vector SVG for Figma, Penpot, Illustrator, web; image_scale for embedded pictures.
  export_pdf     vector PDF, one page per canvas (print, client review, kit books); text as outlines.
  export_web     a working website: HTML / CSS pages with live text, links, overlays, hover CSS,
                 CSS animations, smart-animate page transitions; layout "fit" or "responsive" (pins).
  export_layers  one image per layer or group (+ layout JSON with positions and pivots); format png | webp |
                 jpg | svg (one layered SVG). For engine-animated parts (needles, fills, glows).
  export_react   React components (JSX or TypeScript TSX via typescript=true; css="css" | "tailwind") with
                 data props, onNavigate, onSfx & gamepad navigation.
  export_psd     layered Photoshop file with PackBits RLE compression (opens in Photopea, Krita, GIMP).
  export_atlas   many canvases packed into one texture + metadata (format: json | texturepacker | godot | unity | css).
  export_animation  sprite sheet, frames, GIF / APNG / WebP, Lottie JSON, dotLottie v2 (.lottie with
                 manifest version "2", a/<id>.json animations & s/<id>.json interactive State Machine;
                 pass animation="all" to bundle all animations), MP4 / WebM video, or engine tween JSON.
  export_screen  a whole screen with native text and interactive widgets (Input, Scroll, Slider, Toggle, Dropdown):
                 Game engines: "godot" (.tscn + _controller.gd), "roblox" (LocalScript), "unity" (UXML + USS
                 + Controller.cs), "unity-ugui" (C# Canvas/InputField/ScrollRect builder), "unreal" (UE 5.5-5.8
                 UMG WidgetBlueprint Python builder script).
                 C# / .NET & C++ desktop: "wpf" (.xaml + .xaml.cs + ViewModel), "avalonia" (.axaml), "winui"
                 (WinUI 3 .xaml), "qt-qml" (C++ Qt 6 .qml), "imgui" (C++17 Dear ImGui _ui.hpp).
  add_frame      parametric AAA frame builder (9 presets: rpg_gold, royal_ornate, fantasy_parchment,
                 scifi_hud, cyber_tech, glass_card, medieval_iron, luxury_minimal, cartoon_thick) returning
                 editable vector ids + safe inner_box.
  add_icon       100+ pure-MIT built-in vector icons (HUD, RPG, controls, status, social, UI); see uiforge://icons.
  add_input / add_scroll / add_slider / add_toggle / add_dropdown
                 first-class native interactive widgets rendered on canvas and exported natively to Web/React,
                 Godot, Unity, Unreal UMG, Roblox, WPF, Avalonia, WinUI, Qt QML & ImGui.
  import_screenshot  OpenCV screenshot analyzer reconstructing an editable canvas + theme palette tokens.
  set_theme(quality=..., style_preset=..., environment=...):
                 quality: "simple" | "standard" | "advanced" | "aaa" (modulates SS, PBR shading, noise & frame detail).
                 style_preset: "kids" | "cartoon" | "stylized" | "minimal" | "web_saas" | "scifi" |
                 "dark_fantasy" | "realistic" | "photorealistic" (seeds matching palette, styles, frame & studio).
                 environment: custom Radiance .hdr & OpenEXR .exr IBL maps for the workspace or canvas.
  make_variations  2-8 alternative directions of a canvas (palette, shape, type) + a comparison sheet.
  export_theme("design.md") / set_theme(tokens="DESIGN.md"): DESIGN.md for AI design and coding agents.
  export_spec / export_theme / export_prototype / export_bitmap_font: developer spec, design tokens
                 (CSS, USS, C#, GDScript, Luau, JSON with modes), clickable HTML prototype, BMFont.
Relative paths go to the workspace exports folder; absolute paths are used as given.
""",
}
