# game-ui-mcp — ayrıntılı kılavuz

Kısa tanıtım ve kurulum için [README.tr.md](../README.tr.md) (English: [README.md](../README.md)).

## `preview` mı, `live_preview` mı?

İki aracın görevi tamamen farklıdır, ikisi de gereklidir:

| Araç | Kim kullanır? | Ne yapar? |
| --- | --- | --- |
| **`preview`** (`readOnlyHint=True`) | **Yapay zekâ ajanı** | Tek bir PNG render edip doğrudan modele verir. Model çizdiğini kendi gözleriyle görüp hizalama, kontrast ve gölge hatalarını düzeltir. `state`, `data`, `animation`/`time`, `region`/`zoom`, `simulate` (renk körlüğü) ve `background="game"` parametrelerini destekler. |
| **`live_preview`** | **İnsan (sen)** | Yerel `http://127.0.0.1:<port>` adresinde SSE tabanlı canlı bir tarayıcı stüdyosu açar (`live_preview("start")`). Ajan her değişiklik yaptığında tarayıcı otomatik yenilenir; ID katmanı, güvenli alan kılavuzu, arka plan seçimi ve piksel koordinat inceleyici sunar. |

## Bütün özellikler

- **Şekiller:** dikdörtgen (yuvarlak, squircle `smoothing`, kesik köşe, eğik), elips, çokgen, yıldız, çizgi (ok ucu, incelen/dalgalı fırça, kesikli), yay, kadran çizgileri, SVG path; konturlarda keskin (`miter`), yuvarlak veya pah köşe, tek kenar konturu (`stroke.sides`); `flip_x` / `flip_y` ile aynalama (gölge ve ışık yönü korunur)
- **Fotogerçekçi Cook-Torrance GGX PBR materyaller (39 hazır + özel):** lineer-HDR Cook-Torrance GGX BRDF, perspektif kameralı 360° HDR stüdyo ışık çadırı (yumuşak softbox + negatif dolgu kontrast şeritleri), ACES filmic ton eşleme, şeffaf vernik (`clearcoat`), doğrusal ve radyal fırçalı anizotropi (`radial_metal`), yüzey altı saçılım (`sss`), mikro-kabartma (`height` bump), kenar AO ve HDR ışıma (`emissive`). `style.pbr` doğrudan özelleştirilebilir veya `set_theme(materials=...)` ile projeye özel materyaller kaydedilebilir.
- **Shader dolgusu (Fused CUDA + CPU):** hazır materyal yetmediğinde model kendi piksel formülünü yazar (`{"type": "shader", "code": "..."}`). `noise`, `fbm`, `ridged`, `turbulence`, `voronoi`, `rand`, `d` (kenar mesafesi SDF), `edge` hazır; isteğe bağlı `height` çıktısı `style.pbr` ve `style.light`'a mikro-kabartma verir. NVIDIA GPU'da AST tek bir birleşik CUDA C++ çekirdeğine derlenir; CPU ile bit-birebir aynı gürültü hash'i kullanır.
- **Sıvı cam ve efektler:** OpenCV SIMD (`cv2.remap` + `cv2.distanceTransform`) ile lens kırılmalı, renk saçılımlı, Beer-Lambert emilimli ve Fresnel kenarlı `glass` / `liquid_glass`; buzlu cam (`backdrop_blur`), kademeli bulanıklık, grenli doku (`noise`), kenar aşındırma (`texture`), parlaklık maskesi (`mask_mode`), çoklu dolgu yığını, OKLab gradient.
- **Canlı veri bağlama ve durum makinesi:** `set_binding` ile değişkenler (`data={"hp": 75, "max_hp": 100}`) ve kum havuzlu ifadelerle bar genişliği, renk, görünürlük ve `{yer_tutucu}` metinleri canlı bağlanır; `preview(canvas, data=...)` ile anında test edilir. `set_interaction` ile `load`, `hover`, `press`, `click`, `key:*`, `end:*` tetikleri ve `sfx` ses kancaları tanımlanır; Web/React'te ok tuşu + Web Gamepad API odağıyla, Unity/Godot/Roblox'ta üretilen kontrolcü betikleriyle çalışır.
- **Tasarım aracı özellikleri:** canlı otomatik yerleşim (`arrange_elements(..., live=true)`: satır, sütun, ızgara, `wrap`, `hug`, `fill`, `span`), gerçek vektör `boolean_elements` (`pyclipper`), `path_ops` (`offset`, `outline_stroke`, `flatten`, `simplify`), bileşenler (`add_instance`, varyantlar, slotlar, gizle/göster), `make_variations` (tek çağrıda 2–8 alternatif yön), `make_palette` (OKLCH + WCAG), `restyle`, `find_elements`, `vectorize_image`, `canvas_version` (kaydet / geri dön / diff), W3C DTCG ve `DESIGN.md` içe/dışa aktarma.
- **Katmanlar:** her katmanın kendi opaklığı, 13 karışım modu (`multiply`, `screen`, `overlay`, `erase`...) ve katman stili var; `clip: true` alttaki katmana kırpar.
- **Öz denetim:** `review_canvas` kesilen gölgeyi, düşük WCAG kontrastını, küçük yazıyı, eksik glifi, yarım pikseli, bozuk hizalamayı ve token dışı renkleri bulur; `inspect_pixels` tam renk okur; `view_image` referans görseli ve baskın paletini verir; `fit_canvas` kenar payını ayarlar.
- **Yazı ve yerelleştirme:** 10 gömülü OFL font + sistem/çalışma klasörü fontları, Arapça/İbranice/Hintçe/Tayca/CJK için HarfBuzz + python-bidi şekillendirme ve gömülü Noto yedeği, renkli emoji, OpenType özellikleri (`tnum`, `smcp`), değişken eksenler, çember/yol üstü yazı, `uppercase: "tr"`, `set_strings` dil tabloları ve `pseudo` / `pseudo-long` / `pseudo-rtl` stres testi.
- **Animasyon ve video:** keyframe + ease (`spring-out`, `back-out`, cubic-bezier) + yol üstü hareket (`motion`) + hareket bulanıklığı (`motion_blur`). Statik katman ön-pişirme + paralel iş parçacıklarıyla hızlı render. Çıktı: vektör Lottie JSON, doğrudan `ffmpeg` akışıyla MP4 / saydam WebM, sprite sheet, kare dizisi, GIF / APNG / WebP, DOTween ve Roblox TweenService JSON.
- **Teslim ve motor sahneleri:** Unity (9-slice + `GameUiImporter.cs`, UI Toolkit `.uxml`/`.uss` + `Controller.cs`, **uGUI C# Builder** `unity-ugui`), Godot 4 (`.tscn` + gamepad/veri/SFX'li `_controller.gd` + `.stylebox.tres`), Unreal (Box brush + Python importer), Roblox (`LocalScript` + `GameUiAssets.luau`), **React (`css="css"` veya `"tailwind"`)**, responsive Web sitesi, düzenlenebilir SVG, **PackBits RLE sıkıştırmalı katmanlı PSD**, çok sayfalı vektör PDF, iOS/Android/Web boyut setleri, ICO, BMFont, spec ve prototip.

## Dosyalar nereye gidiyor

- Proje kökünde `.gameui/` klasörü varsa server **otomatik olarak** orayı kullanır (Git dostu, anahtarları sıralı JSON).
- Yoksa varsayılan çalışma klasörü `~/GameUI` (Windows'ta `C:\Users\SEN\GameUI`) veya `GAME_UI_MCP_DIR` ortam değişkenidir.

| Klasör / Dosya | İçerik |
| --- | --- |
| `projects/` | Canvas'lar (sıralı JSON). Oturum kapansa da kalır. |
| `exports/` | Yol verilmeden yapılan dışa aktarmalar |
| `fonts/` | Buraya attığın `.ttf` / `.otf` dosyaları otomatik yüklenir |
| `theme.json` | Renk token'ları, modlar, sayı token'ları, stiller ve özel materyaller |
| `strings.json` | Dil tabloları (`set_strings`) |

## Tool'lar (89 adet + 3 MCP Kaynağı + 3 Prompt)

| Grup | Tool'lar |
| --- | --- |
| **Canvas (9)** | `create_canvas`, `list_canvases`, `get_canvas`, `update_canvas`, `duplicate_canvas`, `delete_canvas`, `fit_canvas`, `resize_canvas`, `canvas_version` |
| **Katman (4)** | `create_layer`, `update_layer`, `delete_layer`, `set_layer` |
| **Çizim ve Çerçeveler (12)** | `add_rect`, `add_ellipse`, `add_line`, `add_polygon`, `add_path`, `add_arc`, `add_ticks`, `add_text`, `add_image`, `add_instance`, `add_svg`, **`add_frame`** |
| **Düzenleme (18)** | `update_element`, `delete_elements`, `duplicate_element`, `boolean_elements`, `path_ops`, `restyle`, `find_elements`, `vectorize_image`, `move_elements`, `reorder_element`, `align_elements`, `arrange_elements`, `scatter`, `copy_elements`, `set_pin`, `batch`, `undo`, `redo` |
| **Veri, durum, dil (6)** | `set_binding`, `set_state`, `delete_state`, `generate_from_template`, `set_strings`, `get_strings` |
| **Denetim ve canlı stüdyo (5)** | `live_preview`, `review_canvas`, `inspect_pixels`, `view_image`, `preview_nine_slice` |
| **Animasyon (7)** | `create_animation`, `set_keyframes`, `delete_keyframes`, `get_animations`, `delete_animation`, `preview_animation`, `export_animation` |
| **Tema ve bilgi (6)** | `set_theme`, `get_theme`, `make_palette`, `list_fonts`, `measure_text`, `guide` |
| **Önizleme ve keşif (4)** | `preview`, `preview_resolutions`, `contact_sheet`, `make_variations` |
| **Dışa aktarma (12)** | `export_png`, `export_svg`, `export_pdf`, `export_web`, `export_react`, `export_asset`, **`export_pbr_maps`**, `export_layers`, `export_psd`, `export_atlas`, `export_bitmap_font`, `write_engine_helpers` |
| **Teslim ve motorlar (6)** | `export_spec`, `export_theme`, `set_link`, `set_interaction`, `export_prototype`, `export_screen` |

- **MCP Kaynakları:** `gameui://materials`, `gameui://workspace`, `gameui://guide/{topic}`.
- **MCP Prompt'ları:** `design_game_hud`, `design_rpg_panel`, `audit_and_polish`.
- **Yeni çıktı yetenekleri:** `export_pbr_maps` (Albedo / Tangent Normal OpenGL & DirectX / Roughness / Metallic / AO / Height / ORM + Godot 4 `CanvasTexture .tres`), `export_animation(format="dotlottie")` (`animation="all"` ile tek `.lottie` arşivi), `export_atlas(format="texturepacker" | "godot" | "unity" | "css" | "json")`, `export_react(typescript=true)` (`.tsx`).
- **Lisanslar:** Tam bağımlılık ve gömülü SIL OFL-1.1 font dökümü için [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md). HarfBuzz + yerleşik saf Python MIT UAX #9 BiDi kullanılır (LGPL `python-bidi` kaldırıldı).

## Stil ve PBR nesnesi

```json
{
  "material": {"name": "gold", "scale": 1.0, "shine": 0.45},
  "pbr": {
    "metallic": 0.98, "roughness": 0.16, "clearcoat": 0.0,
    "profile": "machined", "bevel_size": 7.5, "crown": 0.30,
    "studio": "warm", "env": 1.38, "exposure": 1.05
  },
  "stroke": {"color": "$primary@0.6", "width": 2, "align": "inside", "join": "miter"},
  "shadow": {"color": "#000000@0.5", "blur": 14, "dy": 6},
  "glow": {"color": "$accent", "blur": 16},
  "opacity": 1.0
}
```

- `material` tek başına hem prosedürel albedo + bump shader'ını hem de `pbr` ayarlarını kurar; ayrıca yazılan `pbr`, `light`, `stroke`, `shadow` anahtarları materyali ezer.
- `"pbr": null` veya `"light": null` materyalin 3B ışıklandırmasını kapatıp ham dokuyu bırakır.
- Renkler: `#rrggbb`, `#rrggbbaa`, `rgba(...)`, `hsl(...)`, CSS adları (`gold`, `crimson`...), `$token`; sonuna `@0.5` eklenince alfa olur.
- Açılar (yay, kadran çizgisi, conic gradient): derece, 0 = saat 3 yönü, saat yönünde artar. Klasik kadran 135 → 405 süpürür.

## Katmanlar

`create_layer` yeni katmanı aktif yapar; sonraki elemanlar ona gider. Katman oluşturulmadan çizilenler örtük `base` katmanında kalır.

```json
[{"op": "create_layer", "name": "body"},
 {"op": "add_ellipse", "cx": 120, "cy": 116, "rx": 80, "fill": "#c81e3a"},
 {"op": "create_layer", "name": "shade", "clip": true, "blend": "multiply"},
 {"op": "add_ellipse", "cx": 120, "cy": 196, "rx": 70, "ry": 26, "fill": "#2a0410@0.7", "style": {"blur": 22}},
 {"op": "create_layer", "name": "ring", "style": {"material": "gold"}}]
```

- `clip: true`: yalnızca altındaki katmanın pikselleri üstünde görünür.
- `export_layers` her katmanı/grubu ayrı PNG/WebP/JPG ya da katmanlı SVG olarak verir; `export_psd` PackBits RLE sıkıştırmalı katmanlı PSD kaydeder (Photoshop, Photopea, Krita, GIMP).

## Animasyon, etkileşim ve veri bağlama

```json
{"animation": "appear", "target": "group:btn", "property": "scale", "pivot": [180, 64],
 "keyframes": [[0, 0.55], [0.28, 1, "back-out"]]}
```

- **Veri bağlama:** `set_binding("hud", data={"hp": 75, "max_hp": 100}, target="hp_bar", property="width", expr="clamp(hp / max_hp, 0, 1) * 240")`. Farklı değerlerle anlık test: `preview("hud", data={"hp": 15})`.
- **Etkileşim:** `set_interaction("menu", "play_btn", "click", "navigate", target="game", sfx="ui_click")`.
- **Çıktılar:** `export_animation` (`json`, `lottie`, `spritesheet`, `frames`, `gif`, `apng`, `webp`, `mp4`, `webm`), `export_react(css="css" | "tailwind")`, `export_web`, `export_screen`.

## Motorlara aktarma

| Motor | Sahne / Sprite çıktısı | Yardımcılar ve kontrolcü |
| --- | --- | --- |
| **Unity (UI Toolkit & uGUI)** | `export_screen(engine="unity")` → `.uxml` + `.uss` + `Controller.cs`; `engine="unity-ugui"` → C# `Canvas`/`RectTransform` oluşturucu | `GameUiImporter.cs` (`.gameui.json` okur, 9-slice ayarlar), C# token'lar |
| **Godot 4** | `export_screen(engine="godot")` → `.tscn` + `_controller.gd` (veri bağlama, `sfx_requested` sinyali, gamepad `focus_neighbor_*`) | `<ad>.stylebox.tres`, GDScript token'lar |
| **Unreal Engine** | `export_asset(engine="unreal")` (normalize Box margin) | `import_game_ui.py` (Editör Python betiği) |
| **Roblox** | `export_screen(engine="roblox")` → `LocalScript` ScreenGui oluşturucu | `GameUiAssets.luau` (`SliceCenter` / `SliceScale`), Luau token'lar |

## Performans ve GPU

- **OpenCV C++ SIMD (varsayılan):** `opencv-python-headless` ile `distance_field` (`cv2.distanceTransform`, 512×512'de ~2.8 ms), Scharr normal gradyanları, `cv2.GaussianBlur`, morfolojik disk dilasyon/erozyon ve `cv2.remap` cam kırılması doğrudan AVX2/NEON SIMD ile çalışır.
- **Fused CUDA 12 (`[gpu]`):** `pip install -e ".[gpu]"` (CuPy) ile 65.536 piksel üstü shader dolguları tek bir CUDA C++ çekirdeğine derlenir (`1024×1024 fbm+voronoi` RTX 4060 Ti'da ~3–6 ms). `GAME_UI_MCP_GPU=0` GPU'yu kapatır; CPU ile aynı görsel sonuç üretilir.
- **Önbellek ve akış:** 128 MB LRU eleman render önbelleği, bounding-box kırpma, animasyonda statik katman ön-pişirme, `ffmpeg` stdin akışı ve PackBits RLE PSD sıkıştırma.

## Bilinen sınırlar

- Karakter portresi, illüstrasyon veya fotoğraf üretmez (görüntü modeli değildir); bunları `add_image` ile eklersin.
- `add_svg` metin, filtre, maske, `<use>` ve CSS sınıflarını almaz (`notes` ile bildirir).
- Instance iç içe en fazla 6 seviye olabilir.
- `export_screen` Unreal için `.uasset` UMG dosyası üretmez (binary format); parçalar + `.screen.json` + Python importer kullanılır.
- PSD'de katman adı, opaklık, karışım modu, görünürlük ve clip korunur; efektler ve vektörler piksel katmanı olarak gömülür.
- `backdrop_blur` ve `glass` aynı canvas içinde altta çizilen katmanları kırar/bulanıklaştırır; gerçek 3B oyun sahnesi için motor tarafında `BackgroundBlur` gerekir.
- Web/SVG/PDF/Lottie çıktılarında shader, PBR materyal ve cam efektleri elemanın yüksek çözünürlüklü görseli olarak gömülür; düz şekiller ve metinler gerçek vektör/HTML kalır.
- 87 tool MCP istemcisine yüklenir; uzun referanslar `INSTRUCTIONS` (~2.2k karakter) yerine talep üzerine `guide(topic)` ile verilir.

## Geliştirme ve test

```powershell
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
```

Mimari, doğrulama betikleri ve yol haritası için [DEVELOPMENT.md](DEVELOPMENT.md).

## Fontlar

`src/game_ui_mcp/assets/fonts/` altındaki fontlar SIL Open Font License ile dağıtılır (`OFL.txt`). `noto/` altında Arapça, İbranice, Devanagari, Bengalce, Tamil ve Tayca gömülüdür; CJK fontları sistemden gelir.
