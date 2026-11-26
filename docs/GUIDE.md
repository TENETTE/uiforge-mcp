# UIForge (`uiforge-mcp`) — Ayrıntılı Teknik Kılavuz

Kısa tanıtım ve görseller için [README.tr.md](../README.tr.md) (English: [README.md](../README.md)). Çoklu IDE kurulum şablonları için [configs/README.md](../configs/README.md).

---

## 1. Üç Çalışma Modu ve Ortak Çekirdek

UIForge v0.15.0 itibarıyla tek bir **MCP'den bağımsız çekirdek motor** (`core.py`, `store.py`, `render.py`, `pbr.py`, `widgets.py`, `export.py`, `desktop_export.py`, `tools_delivery.py`) üzerinde üç çalışma modu sunar:

| Mod | Komut | Açıklama |
| --- | --- | --- |
| **Human Mode (UI Mode)** | `uiforge` / `uiforge ui` (`--app` ile yerel pencere) | Bağımsız Studio UI (`http://127.0.0.1:8766`). Çalışma zamanında `mcp` paketi veya AI IDE gerekmez. |
| **MCP Mode** | `uiforge-mcp` / `uiforge mcp` | Yalnızca MCP sunucusu (`stdio` veya `streamable-http`). Herhangi bir MCP uyumlu AI istemcisiyle çalışır. |
| **Combined Mode (MCP + UI)** | `uiforge combined` / `uiforge serve --mode combined` | Hem Studio UI hem MCP sunucusu aynı çalışma alanında canlı çalışır. |

### Eş Zamanlılık ve Tutarlılık

- `Store` (`store.py`) tüm değiştirme işlemlerini `threading.RLock()` ile korur ve JSON dosyalarını her çağrıya özel `tempfile.mkstemp` + `os.fsync` + yeniden denemeli `os.replace` ile atomik yazar.
- `Store.sync_from_disk()` her dosya için `(mtime_ns, size)` damgasını takip eder; böylece tek süreçli `uiforge combined` kadar, ayrı terminalde açılmış `uiforge ui` + IDE tarafından başlatılmış `uiforge-mcp` ikilisi de çakışmasız eşzamanlı çalışır.
- Studio UI'daki **Activity Log** paneli hem `[UI]` hem `[MCP]` işlemlerini gerçek zamanlı süreleriyle gösterir.

---

## 2. `preview`, `live_preview`, `open_studio` ve Human Studio UI

| Araç / Arayüz | Kim Kullanır? | Ne Yapar? |
| --- | --- | --- |
| **`preview`** (`readOnlyHint=True`) | **AI Ajanı** | Tek bir PNG render edip doğrudan modele verir (`state`, `data`, `animation`/`time`, `region`/`zoom`, `simulate`, `background="game"`). |
| **`live_preview`** | **İnsan (izleyici)** | MCP oturumu sırasında hafif `127.0.0.1` SSE tarayıcı izleyicisi açar; ID, kılavuz, katman gizleme, canlı veri ve zaman çizelgesi sunar. |
| **`open_studio`** (SEP-1865 MCP App) | **Sohbet / Yan Panel** | Destekleyen MCP istemcilerinde `ui://uiforge/studio.html` etkileşimli stüdyoyu doğrudan sohbet veya yardımcı panelde açar (0 model token'lı `studio_app_state` / `studio_app_render`). |
| **Human Studio UI (`uiforge ui`)** | **İnsan (tam editör)** | MCP olmadan tek başına çalışan tam özellikli görsel stüdyo: proje/canvas yönetimi, sürükle-taşı, 39 canlı PBR örneği, 142 ikon seçici, 9 AAA çerçeve, 5 yerel bileşen, 3D perspektif, OKLCH palet, canlı veri, WCAG denetimi, piksel görsel farkı ve dahili kod önizlemeli dışa aktarma. |

---

## 3. Tüm Yetenekler

- **Şekiller ve Geometri:** Dikdörtgen (yuvarlak, squircle `smoothing`, kesik köşe, eğik), elips, çokgen, yıldız, çizgi (ok ucu, incelen/dalgalı fırça, kesikli), yay, kadran çizgileri, SVG path; kontur köşeleri (`miter`/`round`/`bevel`), tek kenar konturu (`stroke.sides`), `flip_x` / `flip_y`, `boolean_elements` (`pyclipper`), `path_ops` (`offset`, `outline_stroke`, `flatten`, `simplify`).
- **142 Saf MIT Gömülü Vektör İkon (`add_icon`, `uiforge://icons`):** UI, navigasyon, medya, RPG, FPS, yarış, bilim kurgu ve mağaza kategorilerinde 24×24 düzenlenebilir vektör yolları; PBR materyal, kontur, glow, gradyan ve animasyon destekler.
- **9 Parametrik AAA Çerçeve (`add_frame`):** `rpg_gold`, `royal_ornate`, `fantasy_parchment`, `scifi_hud`, `cyber_tech`, `glass_card`, `medieval_iron`, `luxury_minimal`, `cartoon_thick` (`preset="auto"` aktif stile göre seçer) ve güvenli içerik `inner_box` döndürür.
- **5 Birinci Sınıf Yerel Etkileşimli Bileşen:** `add_input`, `add_scroll`, `add_slider`, `add_toggle` (switch/checkbox), `add_dropdown` — canvas üzerinde gerçekçi çizilir, `set_binding` ile senkronize olur ve Web/React, Unreal UMG, Unity (UITK & uGUI), Godot 4, Roblox, WPF, Avalonia, WinUI 3, Qt 6 QML ve Dear ImGui'de gerçek yerel kontrollere dönüşür.
- **39 Cook-Torrance GGX PBR Materyal + Özel `.hdr`/`.exr` IBL:** Lineer-HDR çift loblu GGX BRDF, kenar aşınması (`wear`), 5 HDR stüdyo çadırı (`bright`, `warm`, `dark`, `sunset`, `cyberpunk`), saf Python Radiance `.hdr` ve OpenEXR `.exr` yükleyici (`set_theme(environment=...)`), ACES ton eşleme, `clearcoat`, doğrusal/radyal anizotropi, `sss`, `emissive` ve `export_pbr_maps` (Albedo, Tangent Normal OpenGL/DirectX, Roughness, Metallic, AO, Height, ORM, Godot 4 `CanvasTexture .tres`).
- **4 Kalite Seviyesi & 9 Stil Profili:** `quality` (`simple`, `standard`, `advanced`, `aaa`) ve `style_preset` (`kids`, `cartoon`, `stylized`, `minimal`, `web_saas`, `scifi`, `dark_fantasy`, `realistic`, `photorealistic`) `set_theme` veya `update_canvas` ile ayarlanır.
- **3D Diegetic Perspektif & Kavisli Visor HUD:** Herhangi bir eleman veya katmanda `style={"perspective": {"rotate_x": -6, "rotate_y": 20, "rotate_z": 0, "fov": 60, "visor_curve": 0.16}}` ile OpenCV ön-çarpımlı RGBA 3B homografi ve kask/kokpit kavisi.
- **Ekran Görüntüsünden Düzenlenebilir Canvas (`import_screenshot`):** OpenCV SIMD K-means palet çıkarımı, `RETR_TREE` kart/buton/daire ve hap-anahtar tespiti, satır/sütun yerleşim grubu çıkarımı, otomatik `$ss_*` tema token'ı bağlama ve isteğe bağlı yerel OCR (`[ocr]` -> `rapidocr-onnxruntime`).
- **Tipografi ve Çoklu Dil:** 11 gömülü SIL OFL-1.1 font ailesi (`Bangers`, `Barlow Condensed`, `Bebas Neue`, `Cinzel`, `Fredoka`, `Inter`, `JetBrains Mono`, `Michroma`, `Noto Sans`, `Orbitron`, `Rajdhani`) + sistem ve çalışma alanı fontları; Arapça/İbranice/Hintçe/Tayca/CJK için HarfBuzz + yerleşik saf Python MIT Unicode UAX #9 BiDi (LGPL `python-bidi` tamamen kaldırıldı), renkli emoji, OpenType (`tnum`, `smcp`), değişken eksenler, `set_strings` ve `pseudo` / `pseudo-long` / `pseudo-rtl`.
- **Öz Denetim & Sürüm Görsel Farkı:** `review_canvas` metin + `input`/`dropdown` WCAG kontrast özeti, kesilen gölge, yarım piksel, hizalama ve sabit hex kontrolü; `canvas_version("visual_diff", "v1")` ile `Önce | Sonra | Isı Haritası` PNG ve `changed_pct` / MAE metrikleri.
- **Animasyon, Durum Makinesi ve Video:** Keyframe, ease (`spring-out`, `back-out`, cubic-bezier), yol hareketi (`motion`), `motion_blur`; çıktılar: **dotLottie v2 (`.lottie` çoklu animasyon + etkileşimli durum makinesi)**, vektör Lottie JSON, akışlı `ffmpeg` MP4 / saydam WebM, sprite sheet, GIF / APNG / WebP, DOTween ve Roblox TweenService JSON.

---

## 4. Dosyalar Nereye Kaydedilir?

- Proje kökünde `.uiforge/` klasörü varsa UIForge **otomatik olarak** orayı kullanır (Git diff dostu, sıralı JSON).
- Yoksa varsayılan çalışma klasörü `~/UIForge` veya `UIFORGE_MCP_DIR` ortam değişkeni / `--workspace` parametresidir.

| Klasör / Dosya | İçerik |
| --- | --- |
| `projects/` | Canvas'lar (atomik yazılan sıralı JSON) ve `versions/` anlık görüntüleri |
| `exports/` | Yol belirtilmeden yapılan tüm dışa aktarmalar (ve `--sandbox-exports` sınırı) |
| `fonts/` | Buraya bırakılan `.ttf` / `.otf` fontları otomatik yüklenir |
| `theme.json` | Renk token'ları, modlar, sayı token'ları, stiller, kalite/stil profili, ortam HDRI ve özel materyaller |
| `strings.json` | Dil tabloları (`set_strings`) |

---

## 5. Araç Kataloğu (97 Modele Açık + 2 Uygulama İçi Araç)

| Grup | Araçlar |
| --- | --- |
| **Canvas (9)** | `create_canvas`, `list_canvases`, `get_canvas`, `update_canvas`, `duplicate_canvas`, `delete_canvas`, `fit_canvas`, `resize_canvas`, `canvas_version` |
| **Katman (4)** | `create_layer`, `update_layer`, `delete_layer`, `set_layer` |
| **Çizim, Çerçeve, İkon & Bileşen (19)** | `add_rect`, `add_ellipse`, `add_line`, `add_polygon`, `add_path`, `add_arc`, `add_ticks`, `add_text`, `add_image`, `add_instance`, `add_svg`, `add_frame`, `add_icon`, `add_input`, `add_scroll`, `add_slider`, `add_toggle`, `add_dropdown`, `import_screenshot` |
| **Düzenleme ve Yerleşim (18)** | `update_element`, `delete_elements`, `duplicate_element`, `boolean_elements`, `path_ops`, `restyle`, `find_elements`, `vectorize_image`, `move_elements`, `reorder_element`, `align_elements`, `arrange_elements`, `scatter`, `copy_elements`, `set_pin`, `batch`, `undo`, `redo` |
| **Veri, Durum ve Dil (6)** | `set_binding`, `set_state`, `delete_state`, `generate_from_template`, `set_strings`, `get_strings` |
| **Denetim, Canlı Stüdyo & MCP App (6)** | `live_preview`, `open_studio`, `review_canvas`, `inspect_pixels`, `view_image`, `preview_nine_slice` |
| **Animasyon (7)** | `create_animation`, `set_keyframes`, `delete_keyframes`, `get_animations`, `delete_animation`, `preview_animation`, `export_animation` |
| **Tema ve Bilgi (6)** | `set_theme`, `get_theme`, `make_palette`, `list_fonts`, `measure_text`, `guide` |
| **Önizleme ve Keşif (4)** | `preview`, `preview_resolutions`, `contact_sheet`, `make_variations` |
| **Dışa Aktarma (12)** | `export_png`, `export_svg`, `export_pdf`, `export_web`, `export_react`, `export_asset`, `export_pbr_maps`, `export_layers`, `export_psd`, `export_atlas`, `export_bitmap_font`, `write_engine_helpers` |
| **Teslim ve Motorlar (6)** | `export_spec`, `export_theme`, `set_link`, `set_interaction`, `export_prototype`, `export_screen` |

- **Uygulama içi SEP-1865 araçları (`visibility: ["app"]`):** `studio_app_state`, `studio_app_render`.
- **MCP Kaynakları:** `uiforge://materials`, `uiforge://icons`, `uiforge://workspace`, `ui://uiforge/studio.html`, `uiforge://guide/{topic}`.
- **MCP Prompt'ları:** `design_game_hud`, `design_rpg_panel`, `audit_and_polish`.
- **Token Tasarrufu:** `--toolset full|core|game|desktop|web` ve `--compact` ile bağlam maliyeti %77'ye kadar düşürülebilir.

---

## 6. Stil ve PBR Nesnesi

```json
{
  "material": {"name": "gold", "scale": 1.0, "shine": 0.45},
  "pbr": {
    "metallic": 0.98, "roughness": 0.16, "clearcoat": 0.0,
    "profile": "machined", "bevel_size": 7.5, "crown": 0.30,
    "studio": "warm", "env": 1.38, "exposure": 1.05
  },
  "perspective": {"rotate_y": 14, "rotate_x": -4, "fov": 60, "visor_curve": 0.12},
  "stroke": {"color": "$primary@0.6", "width": 2, "align": "inside", "join": "miter"},
  "shadow": {"color": "#000000@0.5", "blur": 14, "dy": 6},
  "glow": {"color": "$accent", "blur": 16},
  "opacity": 1.0
}
```

- `material` tek başına prosedürel albedo + bump shader'ını ve `pbr` profilini kurar; yanında yazılan `pbr`, `light`, `stroke`, `shadow` anahtarları materyali ezer.
- `"pbr": null` veya `"light": null` materyalin 3B ışıklandırmasını kapatıp ham dokuyu bırakır.
- Renkler: `#rrggbb`, `#rrggbbaa`, `rgba(...)`, `hsl(...)`, CSS adları (`gold`, `crimson`...), `$token`; sonuna `@0.5` eklenince alfa olur.

---

## 7. Oyun Motorları ve Masaüstü Hedefleri

| Hedef | Sahne / Uygulama Çıktısı (`export_screen`) | Yardımcılar & PBR Haritalar |
| --- | --- | --- |
| **Unreal Engine 5.5–5.8** | `engine="unreal"` → `WBP_<Ad>_build_umg.py` (UMG `WidgetBlueprint`, 9-slice `SlateBrush`, `CanvasPanel`, `Image`, `TextBlock`, `EditableTextBox`, `ScrollBox`, `Slider`, `CheckBox`, `ComboBoxString`) | `export_asset(engine="unreal")`, `export_pbr_maps(engine="unreal")`, `write_engine_helpers("unreal", ...)` |
| **Unity 6** | `engine="unity"` (UI Toolkit `.uxml` + `.uss` + `Controller.cs`), `engine="unity-ugui"` (C# Canvas/RectTransform oluşturucu) | `UiForgeImporter.cs`, `export_pbr_maps(engine="unity")`, C# token'lar |
| **Godot 4** | `engine="godot"` → `.tscn` + `_controller.gd` (veri bağlama, `sfx_requested`, gamepad `focus_neighbor_*`, yerel bileşenler) | `<ad>.stylebox.tres`, `export_pbr_maps(engine="godot")` (`CanvasTexture .tres`), GDScript token'lar |
| **Roblox Studio** | `engine="roblox"` → `LocalScript` ScreenGui oluşturucu | `UiForgeAssets.luau` (`SliceCenter` / `SliceScale`), Luau token'lar |
| **C# / .NET Desktop** | `engine="wpf"` (`.xaml` + `.xaml.cs` + `INotifyPropertyChanged` ViewModel), `engine="avalonia"` (`.axaml`), `engine="winui"` (`.xaml`) | Sıfır harici NuGet bağımlılığı |
| **C++ Desktop** | `engine="qt-qml"` (Qt 6 Quick `.qml`), `engine="imgui"` (tek başlıklı C++17 `_ui.hpp`) | Doğrudan derlenebilir kontroller |
| **Web & React** | `export_web`, `export_react(css="css" \| "tailwind", typescript=true)` | Canlı `data` prop, `window.uiforgeSetData()`, Web Gamepad API |

Doğrulama durumu ve sürüm ayrıntıları için [COMPATIBILITY.md](COMPATIBILITY.md).

---

## 8. Performans, GPU ve Güvenlik

- **OpenCV C++ SIMD (varsayılan):** `distance_field` (`cv2.distanceTransform`, 512×512'de ~2.8 ms), Scharr normal gradyanları, `GaussianBlur`, morfoloji, `remap` cam kırılması ve 3B perspektif homografi yerel AVX2/NEON C++ ile çalışır.
- **WebGPU WGSL (`[wgpu]` / `[amd]` / `[intel]` / `[apple]`):** `wgpu-py` üzerinden Vulkan / DirectX 12 / Metal için `@compute` shader ve Cook-Torrance PBR hızlandırma (`UIFORGE_MCP_GPU=wgpu`).
- **Fused CUDA 12 (`[nvidia]` / `[gpu]`):** CuPy ile 65.536 piksel üstü shader dolgularını tek bir CUDA C++ çekirdeğine derler (`UIFORGE_MCP_GPU=cuda`). `UIFORGE_MCP_GPU=cpu` veya `0` ile CPU'ya sabitlenebilir.
- **HTTP Güvenliği:** `uiforge-mcp serve --transport http` otomatik olarak `--sandbox-exports` etkinleştirir ve yerel dışı (`0.0.0.0`) bağlamalarda `--auth-token` (`UIFORGE_MCP_AUTH_TOKEN`) zorunlu kılar.

---

## 9. Bilinen Sınırlar

- Karakter portresi, illüstrasyon veya fotoğraf üretmez (difüzyon modeli değildir); bunları `add_image` ile eklersin.
- `add_svg` metin, filtre, maske, `<use>` ve CSS sınıflarını içe almaz (`notes` ile bildirir).
- Bileşen (`instance`) iç içe en fazla 6 seviye olabilir.
- Unreal Engine `.uasset` dosyaları ikili (binary) format olduğu için `export_screen(engine="unreal")` editörde çalıştırılan `WBP_<Ad>_build_umg.py` Python oluşturucusu üretir (Unreal Editor veya `UnrealEditor-Cmd.exe` ile gerçek `.uasset` oluşturur).
- PSD çıktısında katman adı, opaklık, karışım modu, görünürlük ve clip korunur; efektler ve vektörler piksel katmanı olarak gömülür.
- `backdrop_blur` ve `glass` aynı canvas içindeki alt katmanları kırar/bulanıklaştırır; gerçek 3B oyun sahnesi için oyun motorunda `BackgroundBlur` gerekir.
- Web/SVG/PDF/Lottie çıktılarında shader, PBR materyal ve cam efektleri yüksek çözünürlüklü görsel olarak gömülür; düz şekiller, widget'lar ve metinler yerel vektör/HTML kalır.

---

## 10. Geliştirme ve Test

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest -q
```

Katkı kuralları için [CONTRIBUTING.md](../CONTRIBUTING.md), üçüncü parti lisans ve gömülü SIL OFL-1.1 font listesi için [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md).
