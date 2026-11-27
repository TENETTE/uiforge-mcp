---
name: uiforge-mcp
description: Oyun, C#/.NET (WPF, Avalonia, WinUI), C++ (Qt QML, Dear ImGui), mobil ve web/React arayüzleri (menü, HUD, buton, panel, bar, gösterge, 100+ gömülü vektör ikon, form, slider/toggle/dropdown, kaydırılabilir liste, 3D kavisli HUD, ekran görüntüsünden düzenleme) tasarlarken, canlandırırken ve teslim ederken uiforge-mcp server'ını kullanır. Seçilebilir kalite seviyeleri (simple/standard/advanced/aaa) ve 9 stil profili, Cook-Torrance PBR + HDR/EXR IBL, 9 prosedürel çerçeve, yerel Input/Scroll/Slider/Toggle/Dropdown bileşenleri, SEP-1865 MCP App Studio (`open_studio`), dotLottie v2 durum makinesi, Unreal UMG/Unity/Godot/Roblox + WPF/Avalonia/WinUI/Qt/ImGui + React TSX/Tailwind çıktıları.
---

# uiforge-mcp ile arayüz tasarlamak

`uiforge-mcp` görsel üreten bir difüzyon modeli değildir: her piksel senin çağırdığın deterministik vektör şekil, yazı, PBR materyal, widget ve keyframe'lerden çizilir. Kalite, baştan doğru **kalite seviyesi + stil profili** seçmene, `batch` ile temiz kurmana ve `preview` + `review_canvas` ile gerçekten bakıp düzeltmene bağlıdır.

Tool'lar listede yoksa (`create_canvas`, `preview` görünmüyorsa) server bağlı değildir: kullanıcıya `uiforge-mcp setup <istemci> --write` ile bağlamasını söyle, çizmiş gibi davranma. İlk turda **25 ayrı şema okumak yerine** tek çağrıda `uiforge://cheatsheet` kaynağını oku (tüm parametre imzaları, widget boşlukları, `batch` `in`/`add_stack` yerleşimi ve export kuralları orada); malzeme seçerken `uiforge://materials` içindeki `text_safe` ve `finish` alanlarına bak. Detay için `guide(topic)` oku (`fills`, `shader`, `style`, `design`, `layers`, `geometry`, `text`, `reuse`, `review`, `animation`, `export`).

## 1. Kalite ve Stil Seçimi (Zorunlu İlk Karar)

Her tasarım AAA veya aşırı süslü **olmamalıdır**! Kullanıcının hedefine göre ilk iş `set_theme(style_preset=..., quality=...)` çağır (veya tek canvas için `update_canvas(quality=..., style_preset=...)`):

| Kullanıcı İsteği | `style_preset` | `quality` | Gerçek Motor Etkisi |
| --- | --- | --- | --- |
| Çocuk oyunu, eğitim uygulaması, sade prototip | `"kids"` | `"simple"` | Düz/temiz gölgeleme, 0 gren, sade çerçeve, 2× SS, yuvarlak şeker köşeler, `Fredoka` |
| Çizgi film, arcade, mobil casual | `"cartoon"` | `"standard"` | Kalın kontur, cel gölge, dengeli bevel, 3× SS, `Bangers`/`Fredoka` |
| Stilize RPG / indie oyun | `"stylized"` | `"standard"` | Dengeli PBR/bevel, çekirdek köşe süsleri, 3× SS |
| Minimal uygulama, sade web | `"minimal"` | `"standard"` | Düz temiz yüzey, 1 px ince çizgi, geniş yumuşak gölge, `Inter` |
| Web SaaS, C# WPF / Avalonia / Qt masaüstü uygulaması | `"web_saas"` | `"standard"` | Modern yüksek okunabilirlikli kartlar, `add_input`/`add_scroll`, `Inter` + `JetBrains Mono` |
| Bilim kurgu, taktik HUD, siberpunk | `"scifi"` | `"advanced"` | Tam Cook-Torrance PBR, kesik köşeli `scifi_hud`/`cyber_tech`, 4× SS |
| Karanlık fantastik / ortaçağ RPG | `"dark_fantasy"` | `"aaa"` | Maksimum kübik Bézier filigran (`royal_ornate`/`rpg_gold`), perçin, derin pah + kenar aşınması |
| Gerçekçi yarış, simülasyon | `"realistic"` | `"advanced"` | Karbon twill, radyal fırçalı metal, `Barlow Condensed` + `JetBrains Mono` |
| Fotogerçekçi vitrin / stüdyo PBR | `"photorealistic"` | `"aaa"` | En derin mikro-pürüzlülük, belirgin kenar aşınması, HDRI IBL (`environment`) |

> **Özel HDR / EXR Ortam Haritası:** Kullanıcının kendi sahne HDRI dosyası varsa `set_theme(environment={"env_map": "yol.hdr", "rotation": 45, "intensity": 1.2})` ver (`.hdr` ve `.exr` destekli). Tüm PBR materyaller tek seferde o sahne ışığını yansıtır.

## 2. Çalışma Sırası (Gereksiz Tool Çağrısı Yapmadan)

1. **Brief & Profil:** Hedef platformu (Unity / Unreal / Godot / Roblox / WPF / Avalonia / WinUI / Qt / ImGui / Web / React), ekran boyutunu ve doğru `style_preset` + `quality` seçimini belirle. Eksikse en fazla 2 soru sor.
2. **Tema:** Tek çağrıda `set_theme(style_preset=..., quality=...)` ile palet, sayı token'ları ve isimlendirilmiş stilleri başlat (kullanıcının `DESIGN.md` veya DTCG JSON'u varsa `tokens=...`, ekran görüntüsü varsa `import_screenshot(path=...)` kullan!).
3. **Canvas & Toplu Çizim:** Tek tek `add_*` yerine mutlaka `batch` kullan ve elemanlara anlamlı `id` ver (15+ op'luk büyük `batch` otomatik kompakt özet + `frames`/`splits`/`warnings` döner). HUD mockupları için `background` boş bırakıp `preview_background` vererek hem şeffaf motor export'unu hem koyu web/önizleme arkaplanını koruyabilirsin!
   - **Sıfır-Matematik Layout (`add_split`, `add_grid`, `add_stack`, `in`):**
     - Çok sütunlu ekranlar için `add_split(sizes=["27%", "1fr", "27%"], names=["left", "center", "right"], children=...)` kullan — oranlı bölgeleri hesaplayıp adıyla kaydeder!
     - 2B kart/envanter ızgaraları için `add_grid(cols=2, gap=16, in="panel.inner_box", children=[...])` (`col_span` destekli).
     - Dikey/yatay akış için `add_stack(direction="column"|"row", gap=12, justify="space-between", in="panel.inner_box", children=[...])` kullan: etiketli widget'ların 22 px üst boşluğunu otomatik bırakır, `"height": "fill"` / `"flex": 1` ile `add_scroll` kalan yüksekliği doldurur, `{"op": "spacer"}` sonraki butonları sağa iter!
   - **Oyun UI Kompozitleri (Tema-Miraslı + WCAG ≥ 4.5:1 Hazır):**
     - `add_button` (ikon, 12px yüksek kontrast keycap, otomatik hover/pressed/focused/disabled, izole grup)
     - `add_progress_bar` (track + clip'li canlı dolgu + etiket + düşük seviye renk binding'i)
     - `add_gauge` (`radial`/`semi`/`segmented` AAA kadran + tick + konik yay + ibre + metal göbek + canlı `end_angle`/`rotation` binding'i)
     - `add_slot` (6 nadirlik rengi, yatay/kare düzen, keycap, cooldown bar/binding, eleman-kapsamlı `selected` toggle)
     - `add_tabs` (aktif sekme vurgulu, izole ekran linkli üst menü) ve `add_stat_card` (`compact=true` ile metne tam oturan hug pill)
   - İkon gerekiyorsa ham SVG uydurmak yerine önce gömülü 142 saf MIT vektör kütüphanesinden `add_icon(name=...)` kullan (`uiforge://icons`; mutlak `x/y` saklar).
   - Metin girişi, kaydırılabilir liste, sürgü, anahtar/onay kutusu veya açılır menü gerekiyorsa düz `rect` çizme; doğrudan `add_input`, `add_scroll`, `add_slider`, `add_toggle` ve `add_dropdown` kullan ki tüm motor ve masaüstü hedeflerinde gerçek yerel bileşene dönüşsün!
   - FPS/yarış/VR diegetic kavisli HUD gerekiyorsa katmana `style={"perspective": {"rotate_y": 20, "rotate_x": -6, "visor_curve": 0}}` ver (`visor_curve: 0` web/React'ta canlı CSS 3D `perspective()` olarak çıkar ve tüm binding/widget'lar canlı kalır; `review_canvas` 3D perspektifli metinlerin WCAG kontrastını doğru ölçer!).
4. **Canlı Önizleme, MCP App & Combined Mode (isteğe bağlı):** Kullanıcı tarayıcıda canlı izlemek isterse `live_preview("start", canvas=...)`, doğrudan sohbet/yan panelde etkileşimli incelemek isterse `open_studio(canvas=...)` çağır. Kullanıcı kendi de aynı anda tam stüdyo editöründe düzenleme yapmak isterse `uiforge combined` (veya ayrı `uiforge ui`) ile çalışabilir.
5. **Tek Çağrıda QA (`qa_screen`) veya Bak + Denetle:** Tek çağrıda `qa_screen(canvas, test_data={...})` ile Normal + uç veri + renk körlüğü + `pseudo-long` (+%100 taşma) + WCAG özetini tek görselde gör (veya ayrı `preview` + `review_canvas`). Riskli revizyonlardan önce `canvas_version("save", "v1")` ve sonra `visual_diff` kullan!
6. **Durumlar, Veri Bağlama & Çalışan Etkileşim:** Hover/press/selected/disabled için `set_state`, dinamik metin/bar/yay için `set_binding` (`format_num`, `concat`, `upper`, `lower`, `pct`, `where`, `clamp`, `lerp` + `$token`/`@alpha` otomatik çözülür), animasyon için `create_animation` + `set_keyframes`, çalışan buton/sıfırlama aksiyonları için `set_interaction` (`set_data`, `reset_data`, eleman-kapsamlı `toggle_state`, `navigate`, `overlay`, `back`).
7. **Doğru Çıktı ile Teslim:** Çok ekranlı teslim için tek çağrıda `export_project(canvases, engine="godot"|"unity"|"web"|"react")` (paylaşılan font/token + `UIManager.gd`/`UiScreenRouter.cs`/Vite `App.tsx`), paylaşılabilir tek dosya HTML için `export_web(..., single_file=True)` veya çalışır React starter için `export_react(..., scaffold=True)`.

## Tema ve tasarım sistemi

```json
{
  "colors": {"bg": "#0b0a12", "surface": "#1b1830", "primary": "#8b5cf6", "accent": "#22d3ee",
             "text": "#f4f1ff", "muted": "#9a93b8", "danger": "#f43f5e", "gold": "#fbbf24"},
  "styles": {
    "panel": {"fill": "$surface@0.93", "stroke": {"color": "$primary@0.55", "width": 2},
              "shadow": {"color": "#000000@0.55", "blur": 24, "dy": 10},
              "inner_glow": {"color": "$primary@0.18", "blur": 18}},
    "title": {"font": "Rajdhani", "weight": 700, "size": 30, "fill": "$text", "case": "tr-upper", "letter_spacing": 2},
    "body":  {"font": "Inter", "weight": 500, "size": 15, "fill": "$muted"}
  },
  "numbers": {"radius-sm": 6, "radius-lg": 16, "space-md": 12, "stroke": 2}
}
```

- **Palet:** 1 zemin, 1-2 yüzey tonu, 1 ana renk, 1 vurgu, yazı + soluk yazı, durum renkleri (tehlike, başarı, altın). Daha fazlası dağınık görünür. Tek bir ana renkten başlıyorsan `make_palette(base, apply=true)` 50-950 tonlarını eşit algılanan açıklıkta kurar; yazı rengini sonuçtaki `text_on` listesine göre seç (her ton için okunabilirlik oranı orada).
- **Hep token:** her yerde `$token` ve stil adı kullan, tek tek hex yazma. Böylece `restyle`, modlar ve web çıktısındaki CSS değişkenleri çalışır; `review_canvas` elle yazılmış renkleri işaretler.
- **Modlar:** açık / koyu, takım renkleri ya da sezon teması gerekecekse baştan `set_theme(modes={"light": {...}}, mode=...)`. Bir canvas'a ayrı mod: `update_canvas(mode=...)`.
- **DESIGN.md:** AI tasarım ve kodlama araçlarıyla tasarım sistemini paylaşmak için `export_theme("design.md")`; gelen DESIGN.md'yi `set_theme(tokens=yol)` okur (renkler, yazı stilleri, köşe ve boşluk değerleri).
- **Sayı token'ları:** köşe yarıçapı, boşluk, kontur kalınlığı, yazı boyu için `numbers` ve `"$radius-lg"` (x / y konumu için değil). Hazır bir token dosyası verilirse (Tokens Studio, Penpot) `set_theme(tokens=...)`; geliştiriciye `export_theme("dtcg" | "css" | "uss" | "csharp" | "gdscript" | "luau")`.
- **Referans görsel:** kullanıcı ekran görüntüsü verdiyse `view_image(path)` ile bak ve dönen baskın renklerden temayı kur; tahmin etme.
- **Fontlar** (`list_fonts`): Inter (temiz, modern), Barlow Condensed (motorsport, gerçek italiği var), Bebas Neue (uzun başlık), Michroma (geniş gösterge yazısı), JetBrains Mono (sabit genişlikli rakam), Rajdhani / Orbitron (sci-fi), Cinzel (fantastik), Fredoka (yuvarlak, casual), Bangers (çizgi roman). Bir kitte en fazla 2 aile, 4-6 yazı boyu. Orbitron'da Ğ/ğ yok; tool uyarırsa fontu değiştir.

## Canvas boyutu ve kenar payı

- Gölge ve glow canvas kenarında kesilir: şeklin etrafında en az `blur × 1.5 + |dx, dy|` boşluk bırak. Bol yerli çiz, bitince `fit_canvas(padding=2)`.
- Koordinatları tam sayı ver; yarım piksel kenarı bulanıklaştırır.
- Tipik boyutlar (1x): ikon 64 / 128, envanter slotu 96, buton 280-360 × 80-110, 9-slice panel 192-256 kare, bar 360 × 64.
- Keskinlik için `scales: [1, 2]`; uygulama için `export_png(preset="ios" | "android" | "web")`. Roblox'ta görsel 1024 px'i geçmesin.

## Stil ailesi: stilize mi, gerçekçi mi

| | Stilize (Roblox, cartoon, arcade) | Gerçekçi (yarış, simülasyon, AAA) |
| --- | --- | --- |
| Renk | canlı, çok renkli | nötr koyu zemin + tek vurgu; renk yalnızca anlam taşır (kırmızı = limit, yeşil = iyi) |
| Kenar | kalın kontur (3-5 px), büyük radius | 1-1.5 px çizgi, küçük radius (2-8) ya da keskin köşe |
| Efekt | belirgin glow, kalın gölge, parlama şeridi | çok yumuşak geniş gölge; glow yalnızca ışık yayan şeyde (LED, ibre) |
| Yazı | iri, konturlu, eğlenceli | dar grotesk; küçük aralıklı BÜYÜK HARF etiket + iri rakam |
| Yüzey | düz renk + gradient | koyu cam, karbon, fırçalı metal |
| Hareket | taşma, zıplama, squash / stretch | kısa, taşmasız; opaklık + 8-20 px kayma |

Kullanıcı bir oyunu örnek verdiyse o oyunun arayüzünü birebir kopyalama (logo, isim, aynı yerleşim olmaz); tasarım dilini al (oranlar, tipografi disiplini, renk kullanımı) ve özgün bir düzen kur.

### Gerçekçi tarz kuralları

1. **Palet:** zemin `#07080a`-`#14171c`, yazı `#f2f4f7`, soluk yazı `#8b929c`, çizgi `#ffffff@0.14`, tek vurgu (ör. `#ff3b30`). Amber, yeşil, mavi, mor yalnızca veri için.
2. **Cam panel:** koyu, %85 opak dikey gradient (`#171a20d9` → `#0b0d10d9`), 1 px gradient kontur (üstte `#ffffff@0.26`, altta `#ffffff@0.05`), gölge blur 24-28, dy 12, alfa 0.5, radius 6-8. Arkası gerçekten görünüyorsa `backdrop_blur` ya da `glass`.
3. **Tipografi:** etiket Barlow Condensed 600, 14-17 px, büyük harf, `letter_spacing` 2-3, soluk renk. Değer Barlow Condensed 700 italik, etiketin 2.5-8 katı. Süre ve skor JetBrains Mono ya da `features: ["tnum"]` (rakamlar zıplamaz).
4. **Eğim:** hız hissi için `skew` 10-14; bütün eğik parçalarda aynı açı, içindeki yazı italik.
5. **Malzeme:** karbon `{"type":"carbon","color":"#3b4048","color2":"#111317","size":4}`; fırçalı metal `{"type":"brushed","color":"#b9c0c8","color2":"#6d747d","amount":0.7}`; torna metal `{"type":"conic","stops":["#eef1f4","#646b75","#f7f9fa","#4c525a","#dfe4e9","#5c636d","#eef1f4"]}`. Dokuyu küçük alanlarda kullan.
6. **Işık:** LED, ibre ve dolu yay kendi renginde glow alır (alfa 0.5-0.75, blur 10-18). Panele ve yazıya glow verme.

### Gösterge (devir, hız, turbo, yakıt)

Açılar: 0 = saat 3 yönü, saat yönünde artar. Klasik kadran 135 → 405; değer açısı = `135 + 270 × oran`.

```json
[{"op":"add_ellipse","group":"dial","cx":220,"cy":220,"rx":206,
  "fill":{"type":"radial","stops":[[0,"#1c2026"],[0.72,"#0c0e11"],[1,"#050607"]]},
  "stroke":{"color":{"type":"linear","angle":70,"stops":["#7b838d","#1b1e23","#565d66"]},"width":6},
  "style":{"shadow":{"color":"#000000@0.65","blur":40,"dy":16},"inner_shadow":{"color":"#000000@0.9","blur":26,"dy":6}}},
 {"op":"add_arc","group":"dial","cx":220,"cy":220,"radius":186,"start_angle":135,"end_angle":405,"thickness":12,"color":"#ffffff@0.07"},
 {"op":"add_arc","group":"dial","cx":220,"cy":220,"radius":166,"start_angle":345,"end_angle":405,"thickness":5,"color":"#ff3b30"},
 {"op":"add_ticks","group":"dial","cx":220,"cy":220,"radius":176,"start_angle":135,"end_angle":405,
  "count":37,"major_every":4,"length":8,"width":1.5,"major_length":17,"major_width":3,
  "color":"#ffffff@0.42","major_color":"#f2f4f7","labels":["0","1","2","3","4","5","6","7","8","9"],
  "label_size":26,"label_font":"Barlow Condensed","label_weight":600,"label_italic":true,"label_color":"#d5dae1"},
 {"op":"add_arc","group":"value","cx":220,"cy":220,"radius":186,"start_angle":135,"end_angle":335,"thickness":12,
  "color":{"type":"conic","from":135,"to":405,"stops":[[0,"#dfe6ee"],[0.62,"#f2f4f7"],[0.76,"#ffb020"],[0.9,"#ff3b30"]]},
  "style":{"glow":{"color":"#ffb020@0.55","blur":18}}},
 {"op":"add_polygon","group":"needle","origin":[220,220],"rotation":335,
  "points":[[186,215.5],[388,218.8],[388,221.2],[186,224.5]],
  "fill":{"type":"linear","angle":90,"stops":["#ff6a60","#ff3b30","#b3170f"]},
  "style":{"glow":{"color":"#ff3b30@0.75","blur":14},"shadow":{"color":"#000000@0.7","blur":8,"dy":5}}},
 {"op":"add_ellipse","group":"hub","cx":220,"cy":220,"rx":22,
  "fill":{"type":"conic","stops":["#e6eaef","#5a616b","#f4f6f8","#474d55","#cfd5dc","#5a616b","#e6eaef"]},
  "stroke":{"color":"#000000@0.7","width":1.5}}]
```
Canvas 440 × 460. İbre sağa bakan ince bir çokgendir, `origin` göbektir, `rotation` değer açısıdır. `count` = büyük aralık × ara bölme + 1 (9 × 4 + 1 = 37). Parçalara ayrı `group` ver: motorda ibre ve yay ayrı oynar. Segmentli LED sırası için `add_arc` + `dash` + `cap: "butt"`: önce sönük tam sıra, üstüne daha kısa parlak sıra.

## Katmanlar: kat kat çalış

Bitmiş görüntüyü tek hamlede çizme; ressam gibi geçişlerle kur. Her geçiş bir katmandır (`create_layer`): opaklığı ayarlanır, gizlenip karşılaştırılır, ayrı dışa aktarılır.

Tipik yığın (alttan üste): `ground` (bulanık zemin gölgesi) → `body` (ana şekil, sade renk) → `shade` (`clip: true`, `blend: "multiply"`, koyu yumuşak şekiller) → `light` (`clip: true`, `"screen"` ya da `"overlay"`, parlaklık ve yansıma) → `detail` (çerçeve, süs; katman stiliyle tek parça) → `label` (yazı).

- `clip: true` katman yalnızca altındaki katmanın pikselleri üstünde görünür; serbest çiz, kırpma halleder.
- Katman stili katmandaki her şeyi tek şekil sayar: ortak kontur, ortak gölge. Aynı efekti eleman eleman tekrarlama.
- Yeni eleman en son oluşturulan katmana gider; başka katman için `layer: "ad"`, taşımak için `set_layer`, sıra için `update_layer(position=...)`.
- Bir geçişin işe yarayıp yaramadığını `update_layer(visible=false)` ya da `preview(layers=[...])` ile karşılaştır.

## Işık, gölge ve efektler

Önce ışık yönünü seç ve bütün kitte aynı tut (alışılmış olan sol üst: `angle: 225`; 0 = sağ, 90 = alt, 180 = sol, 270 = üst).

- **`pbr` ve `light`:** `style.pbr` gerçek lineer-HDR Cook-Torrance GGX + perspektif HDR stüdyo yansıması + ACES ton eşleme uygular (`metallic`, `roughness`, `clearcoat`, `ior`, `anisotropy`, `brush_angle`, `sss`, `emissive`, `profile: "round" | "chamfer" | "machined" | "dome" | "facet" | "engraved"`, `crown`, `studio: "bright" | "warm" | "dark"`, `shine`). Stilize hızlı kabartma için `light` (`profile`, `gloss`, `env`, `fresnel`, `shine`). `bevel` yalnızca ince üst-alt çizgidir.
- **İki kademeli gölge:** `shadow` listesi: yakın keskin (blur 3-5, dy 2-3, alfa 0.5) + uzak yumuşak (blur 18-30, dy 8-14, alfa 0.3-0.5).
- **Çoklu kontur:** `stroke` liste olabilir, `offset` boşluk bırakır. Tek kenar için `sides: ["bottom"]` (sekme alt çizgisi, ayraç).
- **Cam:** `backdrop_blur` arkadakini buzlu yapar; `glass` (refraction, depth, dispersion, frost, light) SDF mercek eğrisiyle arkadakini büker ve kenarına Fresnel parlaması verir. Hafif beyaz dolgu (`#ffffff@0.06-0.12`), ince açık kontur, gölgede `knockout: true`.
- **Bulanıklık:** `blur` bütün elemanı yumuşatır; `{"radius", "angle", "start", "end"}` ile kademeli bulanıklık (keskinden yumuşağa). `feather` yalnızca kenarı yumuşatır (yumuşak ışık lekesi, sis, ışık hüzmesi).
- **Doku ve gren:** `noise` (sayı ya da `{mode: mono | duo | multi, amount, size}`) film / baskı hissi; `texture` kenarları pürüzlendirir (yıpranmış, damga, yırtık); `clouds`, `hex`, `carbon`, `brushed` dolguları; kendi görselin `{"type":"image","path":...,"fit":"tile"}`. Dokuyu düşük alfayla, tercihen clip katmanında kullan.
- **Maske:** `mask` elemanı gradient ile söndürür (yalnızca alfa önemli); `mask_mode: "luminance"` parlaklığı kullanır. Bir elemanı başka bir şekle kırpmak için `clip`, parlaklığa göre kırpmak için `clip_mode: "luminance"`.
- **Hazır materyal (39 adet, Cook-Torrance GGX PBR):** `style: {"material": "gold"}` ya da `{"material": {"name": "wood", "color": "$primary", "scale": 1.5, "seed": 3, "shine": 0.5}}`. Metaller: gold, silver, chrome, bronze, copper, steel, iron, radial_metal, hammered_gold, rust; taş/mücevher: stone, runic_stone, marble, obsidian, jade, gem, ruby, emerald, lava, ice; organik/zanaat: wood, leather (dikişli), paper, aged_parchment, fabric, carbon_twill, wax_seal, enamel; modern/sci-fi: glass, liquid_glass, hologram, energy_shield, foil_holographic, neon, plastic, candy_gloss, clay_3d, rubber, jelly. `pbr` anahtarlarıyla parlaklık/pürüzlülük/stüdyo ışığı ezilebilir; `lava`, `jelly`, `hologram`, `runic_stone`, `energy_shield`, `foil_holographic` `style.material.t` ile, parlama şeridi `style.material.shine` ile canlanır.
- **Kendi materyalin:** kitte tekrar eden yüzeyi bir kez tanımla: `set_theme(materials={"dark_oak": {"material": "wood", "color": "#4a2c18", "scale": 2, "light": {...}}})` (hazırdan türet) ya da `{"fill": {"type": "shader", "code": "...", "params": {"c": "$primary", "t": 0}}, "light": {...}, "noise": 0.04}` (sıfırdan). Sonra her yerde `{"material": "dark_oak"}`; `{"name": ..., "color": ..., "scale": ..., "t": ...}` shader'ın `c`, `sc`, `t` parametrelerine gider. Shader yazımı için "Shader dolgusu".
- **Renk:** `adjust` yeniden çizmeden düzeltir (brightness, contrast, saturation, exposure, temperature, shadows, highlights, hue, tint). Hover `brightness: 0.08`, disabled `saturation: -0.8`. Uzak renkler arası gradient için `"space": "oklab"` (gri-çamur geçişi olmaz).
- **Dolgu yığını:** `fill` liste olabilir (alttan üste); her katmana ayrı `blend` verilebilir (gradient + `overlay` ile parlaklık).
- **Karışım modu:** gölge `multiply`, ışık `screen` (yumuşak) ya da `add` (neon, enerji), canlandırmak için `overlay` / `soft-light`.

Efektleri az kullan: bir asset'te glow ya da kalın gölgeden biri baskın olsun. Her şeye glow verince hiçbir şey öne çıkmaz.

**Örnek: cam küre** (canvas 240 × 240):
```json
[{"op":"create_layer","name":"ground"},
 {"op":"add_ellipse","cx":120,"cy":214,"rx":74,"ry":12,"fill":"#000000@0.55","style":{"blur":14}},
 {"op":"create_layer","name":"body"},
 {"op":"add_ellipse","cx":120,"cy":116,"rx":80,
  "fill":{"type":"radial","cx":0.42,"cy":0.38,"r":0.7,"space":"oklab","stops":[[0,"#ff5b6e"],[0.55,"#c81e3a"],[1,"#5c0a1c"]]}},
 {"op":"create_layer","name":"shade","clip":true,"blend":"multiply"},
 {"op":"add_ellipse","cx":120,"cy":116,"rx":82,
  "fill":{"type":"radial","cx":0.3,"cy":0.28,"r":0.98,"stops":[[0,"#3b0613@0"],[0.42,"#3b0613@0"],[1,"#22030b@0.92"]]}},
 {"op":"add_ellipse","cx":120,"cy":196,"rx":70,"ry":26,"fill":"#2a0410@0.7","style":{"blur":22}},
 {"op":"create_layer","name":"light","clip":true,"blend":"screen"},
 {"op":"add_ellipse","cx":92,"cy":84,"rx":52,"ry":40,"rotation":-28,"fill":"#ffd9de@0.55","style":{"blur":26}},
 {"op":"add_ellipse","cx":88,"cy":76,"rx":22,"ry":11,"rotation":-32,"fill":"#ffffff@0.95","style":{"blur":3}},
 {"op":"create_layer","name":"ring","style":{"light":{"angle":225,"size":5,"depth":1.4,"gloss":0.8},
  "stroke":{"color":"#2b1c05","width":1.5,"align":"outside"},"shadow":{"color":"#000000@0.6","blur":10,"dy":5}}},
 {"op":"add_arc","cx":120,"cy":116,"radius":86,"start_angle":0,"end_angle":360,"thickness":13,
  "color":{"type":"conic","from":200,"space":"oklab","stops":["#f6d98a","#a9781c","#ffe9a8","#8a5e12","#e9c463","#9a6c18","#f6d98a"]}}]
```
Biçim okunmuyorsa kontrastı artır; her yer parlıyorsa ışık lekelerini küçült.

### Derinlik veren sıra

Düz tek dikdörtgen "programcı işi" görünür. Bir yüzey alttan üste: gövde (hafif dikey gradient + gölge) → kenar (`stroke`, varsayılan içte) → iç ışık (`bevel` ya da `inner_glow`) → parlama (üst yarıda beyazdan saydama gradient, gövdeye `clip`) → isteğe bağlı doku (alfa 0.04-0.08) → içerik (ikon, yazı, hafif gölge) → vurgu (ince çizgi, köşe işareti, küçük glow).

## Yerleşim

- **Canlı otomatik yerleşim:** `arrange_elements(mode="row" | "column" | "grid", ids=[...], container="çerçeve", padding=..., gap=..., hug=true, live=true)`. Yerleşim çerçeveye kaydedilir ve her değişiklikte yeniden uygulanır: yazı uzayınca buton büyür, eleman eklenince liste yeniden dizilir. Çok parçalı bir öğeyi tek parça taşımak için `ids` içine `"group:ad"`.
- **Boyut kuralları:** çocuğa `update_element(id, {"layout_size": {"width": "fill", "min_width": 120, "max_width": 320}})`; ızgarada büyük kart için `{"span": [2, 1]}`; yerleşimden çıkarmak için `{"absolute": true}`. Sığmayan öğeler alt satıra geçsin: `wrap=true`.
- **Tek seferlik hizalama:** `align_elements(align=..., distribute=...)`; elle tahmin etme.
- **Farklı ekranlar:** parçaları ekran kenarına `set_pin` ile sabitle (sol / orta / sağ / esnet / oranla), `preview_resolutions` ile 16:9, 21:9, telefon hallerine bak, `resize_canvas` ile başka boyuta uyarla. Çentik ve TV kenarı için `update_canvas(safe_area=...)`; `review_canvas` taşanları söyler.
- **Odak sırası:** gamepad / klavye ile gezilecek ekranlarda `update_canvas(focus_order=[...])`.

## Bileşenler, durumlar ve veri

- **Bileşen:** tekrar eden parçayı (slot çerçevesi, tuş, madalya, buton) kendi canvas'ında bir kez çiz, başka yerlere `add_instance(source=...)` ile koy. Kaynak değişince bütün kopyalar değişir ve her boyutta keskin kalır.
- **Durumlar:** tek canvas bütün durumları taşır: `set_state("btn", "hover", "face", {"style": {"glow": {...}}})`. Ad olarak hover, pressed, disabled, selected, focused (gamepad) kullan; motor ve web çıktısı bunları tanır. `preview(state=...)` ile bak.
- **Varyantlar:** boyut / ton gibi seçenekler için `prop=değer` adlı durumlar (`set_state("btn", "size=large", ...)`), kullanırken `add_instance(variant={"size": "large", "tone": "danger"})`. İsteğe bağlı parçalar `hide=["icon"]` / `show=[...]`; değişen içerik için kaynakta bir yer tutucu çiz ve `slots={"icon": "gem"}` ile başka canvas'ı içine yerleştir.
- **Veri ve canlı bağlama:** yazıda `{yer_tutucu}` ve dinamik özellikler için `set_binding(canvas, data={"hp": 75, "max_hp": 100}, target="hp_bar", property="width", expr="clamp(hp / max_hp, 0, 1) * 240")`. Farklı değerleri `preview(canvas, data={"hp": 15})` ile dene; Web/React ve motor controller'larına otomatik aktarılır. Şablondan onlarca kart üretmek için `generate_from_template(template, rows)`. Dil tabloları `set_strings`; her çıktı `language` alır.
- **Canlı izleme:** Kullanıcı çizimi tarayıcıda canlı görmek isterse `live_preview("start")` yerel (`127.0.0.1`) otomatik yenilenen önizleme stüdyosu açar.

## Şekil gereçleri

- **Boolean (`boolean_elements`):** birleştir / çıkar / kesiştir / dışla; sonuç tek, gerçek bir vektör şekildir, kontur ve gölge kesilen kenarı izler. Çentikli panel, hilal, anahtar deliği, dişli için `erase` yerine bunu kullan; işlem sonradan `update_element(id, {"op": ...})` ile değişir.
- **Yol işlemleri (`path_ops`):** `offset` ile eşit iç / dış kopya (iç panel, eşit çerçeve), `outline_stroke` ile kontur ya da çizgiyi dolgulu şekle çevir, `flatten` ile her şeyi (yazı dahil) tek path yap, `simplify` ile nokta sayısını azalt.
- **Köşeler:** `radius` (tek ya da dört köşe), `corner: "cut"` (kesik, sci-fi), `smoothing: 0.6` (iOS tarzı yumuşak köşe). Çokgen ve path konturu varsayılan keskindir (`join: "miter"`); yumuşak için `"round"`.
- **Çizgiler:** `start_cap` / `end_cap` (arrow, triangle, circle, square, diamond, bar) bağlantı ve kaydırıcılar için; `taper`, `width_profile`, `wiggle` fırça ve el çizimi hissi için; `dash` kesikli.
- **Tekrar:** `duplicate_element` ile doğrusal (`count`, `dx`) ve dairesel dizi (`rotate`, `pivot`); simetrik parçanın ikinci yarısı için `flip_x` / `flip_y` (ışık yönü korunur); serpiştirme için `scatter`.
- **Görseller:** `add_image` ile `crop` (parçasını al), `cutout: true` (düz arka planı sil), `fit: "cover"` + `zoom` / `focus` (çerçeve içinde kaydır, yakınlaştır). Görseli herhangi bir şeklin içine koymak için şekle `fill: {"type": "image", "path": ..., "zoom", "focus"}` ver ya da `clip` kullan. Görseller alt-piksel hassasiyetle hareket eder.
- **Dışarıdan:** logo ya da ikon SVG'si `add_svg`; düz renkli bir çizim, logo ya da piksel sanatını düzenlenebilir vektöre `vectorize_image(path, colors=...)` çevirir (fotoğraf posterize olur).
- **Toplu değişiklik:** "maviyi mor yap", "fontu değiştir", "Play yerine Start yaz" gibi isteklerde `restyle(replace_colors=..., replace_fonts=..., replace_text=...)`; önce `dry_run=true`. Benzer elemanları bulmak için `find_elements(like=id)`.

## Tarifler

**Buton (sci-fi, kesik köşe)** — canvas 320 × 96:
```json
[{"op":"add_rect","id":"body","x":16,"y":14,"width":288,"height":60,"radius":14,"corner":"cut",
  "fill":{"type":"linear","angle":90,"stops":[[0,"#a78bfa"],[0.5,"#7c3aed"],[1,"#5b21b6"]]},
  "stroke":{"color":"#ddd6fe@0.9","width":2},
  "style":{"glow":{"color":"$primary@0.7","blur":22},"shadow":{"color":"#000@0.5","blur":10,"dy":6},"bevel":{"size":2}}},
 {"op":"add_rect","id":"shine","x":22,"y":18,"width":276,"height":24,"clip":"body",
  "fill":{"type":"linear","angle":90,"stops":[[0,"#ffffff@0.28"],[1,"#ffffff@0"]]}},
 {"op":"add_text","id":"label","text":"oyuna başla","x":160,"y":44,"anchor":"center","size":28,"color":"#ffffff",
  "style":{"use":"title","shadow":{"color":"#2e1065@0.9","blur":4,"dy":2}}}]
```
Durumlar `set_state` ile: hover gradient'i bir ton açar ve glow'u artırır; pressed gradient'i koyulaştırır, gölgeyi azaltır, gövde ve yazı 2 px aşağı iner; disabled gri-soluk dolgu, glow yok, yazı `opacity` 0.45.

**Cartoon / Roblox buton:** altta koyu "derinlik" rect'i, 10 px yukarıda açık gradient'li yüz, ikisinde kalın koyu `outside` kontur (4 px), üstte yarı saydam beyaz parlama şeridi, Bangers / Fredoka yazı + kalın koyu kontur + `shadow` blur 0, dy 4.

**Can / XP barı:** `track` (koyu, radius = yükseklik / 2, `inner_shadow`) + `fill` (aynı x, y, yükseklik; `clip: "track"`; yatay gradient; `bevel`). Yuvarlak uç clip'ten gelir, fill'e radius verme. Motorda dolgu ayrı oynayacaksa ikisini ayrı katman ya da canvas yap.

**Envanter slotu:** radial gradient'li koyu kare, ince altın ya da ana renk kontur, `inner_shadow`, ortada ikon için `slots` yer tutucusu, sağ altta `anchor: "bottom-right"` adet yazısı + koyu kontur. Nadirlik için yalnızca kontur ve glow rengi değişir (varyant).

**HUD mockup:** 1920 × 1080, koyu gradient zemin, parçalar güvenli alan içinde (kenarlardan ≥ 32 px) ve kenarlara `set_pin` ile sabit. `preview(background="game")` ile oyun sahnesi üstünde okunuyor mu bak.

## Yazı

- `anchor: "center"` büyük harf yüksekliğine göre ortalar; butonda optik olarak tam ortada durur. Butonlarda `trim: true` kutuyu harflere sıkı oturtur.
- Taşmayı önle: `max_width` satır kırar, `max_lines` "..." ile keser (oyuncu ve eşya adı), `fit_width` boyu küçültür. Kutuyu %30 fazla yazıya göre tasarla.
- Rakamlar zıplamasın: skor, süre, sayaçta `features: ["tnum"]`. Küçük büyük harf için `case: "small-caps"` (font desteklemezse uyarı gelir).
- Türkçe büyük harf için `case: "tr-upper"` (i → İ doğru). Uzun metinde `list: "bullet" | "number"`, `paragraph_spacing`, `indent`. Eski fiyat `decoration: "strikethrough"`.
- Rozet ve amblemde `arc` (çember üstünde), serbest eğri için `path: {"d": ...}`. Yazıyı şekle çevirmek (logo, efektli başlık) için `path_ops(action="flatten")`.
- **Çok dilli:** her yazıya `lang` ver; Han karakterleri için şart (Japonca, Çince, Korece farklı çizilir). Arapça, İbranice, Hint yazıları, Tayca ve CJK şekillendirilir; fontta olmayan harf yedek fonttan gelir, hiçbir fontun çizemediği harf varsa export reddedilir. RTL ekranda yerleşimi de aynala (ilerleme yönü, geri oku). Renkli emoji renkli çizilir.
- Canlı yazıyı motora verirken (`export_screen`, `export_spec`) dönen motor notlarını kullanıcıya aktar (TextMeshPro Arapçayı şekillendirmez, Unreal'da Full Shaping gerekir).

## Animasyon

Hazır animasyon yok: hangi özelliğin ne zaman, hangi değere, hangi ivmeyle gideceğini sen yazarsın. Keyframe'lenebilenler: `dx`, `dy`, `scale`, `scale_x`, `scale_y`, `rotation`, `opacity`, `motion` (yol boyunca), her sayısal özellik (`width`, `end_angle`, `dash_offset`...), stil yolları (`style.fill`, `style.glow.blur`, `style.fill.params.t`), adım adım değişenler (`text`, `visible`).

**Sıra:** statik hali bitir → `create_animation(ad, süre)` → `set_keyframes` (batch içinde) → `preview_animation` → düzelt → export. Bir canvas birden çok animasyon taşır: `appear`, `hover`, `press`, `idle`.

**Süre:** hover / press 0.10-0.18 sn; küçük parça girişi 0.2-0.3; panel / menü 0.3-0.45; ekran geçişi en fazla 0.6; boşta döngü 1.5-3 sn ve `loop: true`.

**Ease** (bir keyframe'in ease'i o keyframe'e varışı şekillendirir):
- Giren şey `-out` (`cubic-out`, `expo-out`), çıkan `-in`, yer değiştiren `-in-out`.
- Taşma `back-out`; doğal yaylanma `spring-out`. Stilize tarzda belirgin, gerçekçi tarzda yok ya da çok kısa.
- `elastic-out`, `bounce-out` yalnızca cartoon / arcade. Döngüler `sine-in-out`, sabit hızla dönen şeyler `linear`.

**Kurallar:**
- 1 ana hareket + en fazla 1-2 destek (opaklık, glow). Her şey aynı anda oynamaz.
- Sıralı giriş: grup hedefinde `stagger: 0.05-0.08`.
- Bir grubu tek parça gibi büyütmek / döndürmek için `target: "group:ad"` ve ortak `pivot`.
- Ölçek 0'dan başlamaz (0.5-0.85) ve opaklıkla birlikte gelir. Döngüde ilk ve son değer aynıdır.
- Kare kare görsel: animasyonlu GIF / APNG / WebP ya da `sheet: {"cols", "rows", "count"}` ile sprite sheet; `frame` özelliğini 0'dan kare sayısına keyframe'le (döngüye girer). Fotoğrafta yavaş kaydırma / yakınlaştırma için `zoom` ve `focus` keyframe'le.
- Yol boyunca hareket (HUD'a uçan coin, yörüngedeki ikon): `property: "motion"`, değerler 0 → 1, `path: {"d": "M 0 0 C ...", "rotate": true}`.
- Hareket canvas dışına taşıyorsa canvas'ta pay bırak.

**Film şeridini okumak:** kareler arası fark hep aynıysa hareket cansızdır; sona doğru küçülüyorsa ease-out çalışıyordur. Öğe bir karede aniden beliriyorsa keyframe zamanı ya da başlangıç değeri yanlıştır. Hızlı kısmı `times=[0, 0.05, 0.1, ...]` ile yakından örnekle; tek anı tam boy görmek için `preview(animation=..., time=...)`.

**Örnek: buton girişi + parlama geçişi** (butonun bütün parçaları `group: "btn"`; `shine` gövdeye clip'li, başlangıçta solda dışarıda):
```json
[{"op":"create_animation","name":"appear","duration":1.0},
 {"op":"set_keyframes","animation":"appear","target":"group:btn","property":"scale","pivot":[180,64],
  "keyframes":[[0,0.55],[0.28,1,"back-out"]]},
 {"op":"set_keyframes","animation":"appear","target":"group:btn","property":"opacity",
  "keyframes":[[0,0],[0.14,1,"quad-out"]]},
 {"op":"set_keyframes","animation":"appear","target":"shine","property":"dx",
  "keyframes":[[0.35,0],[0.85,400,"quad-in-out"]]}]
```

**Animasyon çıktısı:**
- Motorun kendisinin canlandırabildiği hareket (konum, ölçek, dönme, opaklık, renk): `format="json"` + parçalar için `export_layers`. JSON her ease'in Roblox ve DOTween adını verir; motor kodunu bu veriden yaz.
- Uygulama, web ve Lottie oynatıcıları: `format="lottie"`. Sade şekiller ve yazı gerçek vektör katman olur (her boyutta keskin, renk değişimi doğal animasyon); efektli parçalar resim olarak hareket eder; glow / şekil değişen parçalar kare kare gider. Sonuçtaki listelere bak; kare kare giden çoksa efekti sadeleştir.
- Motorun canlandıramadığı efektler (kırpılmış parlama, şekil değiştiren yay, dash akışı): `format="spritesheet"`, fps 12-24, kısa süre. Hızlı dönen ya da kayan şeylerde `motion_blur: 4-6`.
- Göstermek için `gif`; kalite ve saydamlık için `apng` / `webp`. Fragman, mağaza sayfası, sosyal medya için `mp4` (opak) ya da `webm` (saydam); döngüde `repeat` ile birkaç tur. ffmpeg gerekir; yoksa hata mesajı kurulumu söyler.

## Etkileşim (durum makinesi)

Animasyonlar ve durumlar tek başına sadece görünüştür; ne zaman oynayacaklarını `set_interaction(canvas, id, trigger, action, ...)` belirler. Kurallar `export_web` ve `export_react` çıktısında çalışır, `export_animation(format="json")` içinde motor kodu için listelenir.

- **id:** eleman, `"group:ad"` ya da `"canvas"` (load / key / end için).
- **trigger:** `load`, `hover`, `leave`, `press`, `release`, `click`, `key:Escape` gibi tuşlar, `end:<animasyon>` (zincirleme).
- **action:** `play` / `stop` (animasyon; bir kural oynatınca o animasyon kendiliğinden başlamaz), `set_state` / `clear_state` / `toggle_state` (`set_state` ile tanımlanmış görünüş: selected, open, muted...), `navigate` / `overlay` (başka canvas), `back`, `url`. `delay` saniye.
- **Tipik buton:** hover → play `hover_in`; leave → play `hover_out`; press → set_state `pressed`; release → clear_state `pressed`; click → navigate `settings`, delay 0.15. Sekme / onay kutusu: click → toggle_state. Açılış: canvas load → play `intro`, `end:intro` → play `idle`.
- Tarayıcıda dene: `export_web` klasöründeki index.html. Gerçek oyunda kuralları json'daki `interactions` listesinden motor koduyla kur.

## 9-slice kuralları (panel, buton, tooltip, bar)

- Esneyecek yönde gradient olmaz: dikey gradient'li gövde yalnızca yatay esner. İki yöne esneyecek panelde düz dolgu kullan; derinliği `inner_glow`, `bevel` ve konturla ver.
- Merkezde yazı, ikon, desen ya da `noise` olmaz; süsler köşe bölgesinde durur.
- `export_asset(nine_slice="auto")` kenarları kendisi bulur. Sonuçtaki `notes` "no stretchable area" diyorsa tasarımı düzelt ya da kenarları elle ver.

## Shader dolgusu

Hazır dolgular yetmiyorsa formülü kendin yaz: `{"type":"shader","code":"...","params":{...}}` (ayrıntı: `guide("shader")`). Renkleri `params` içine koy (`"c": "$primary"` → kodda `c_r, c_g, c_b`), kenarları `smoothstep` ile yumuşat, hareket için `t` parametresini `style.fill.params.t` ile canlandır. Önce küçük canvas'ta dene; fbm'de 4-5 oktav çoğu zaman yeter. Shader'ı clip katmanında `overlay` ile kullanmak (çizik, kir, parlama) çoğu zaman tek başına kullanmaktan iyi sonuç verir. SVG, PDF ve web çıktısında shader resim olarak gider.

## İkonlar

- **142 gömülü saf MIT vektör ikonu (`add_icon`, `uiforge://icons`):** Standart UI, navigasyon, medya, RPG, FPS, yarış, bilim kurgu ve mağaza ikonları için ham SVG uydurmak yerine önce `add_icon(name=...)` kullan — standart düzenlenebilir `path` olarak eklenir ve PBR materyal, kontur, glow ve animasyon destekler.
- Özel bir sembol gerekiyorsa 24 × 24 ızgarada `add_path` ile çiz ve `scale` ile büyüt; çizdikten sonra `preview(region=..., zoom=4)` ile yakından bak.
- Kullanıcının ikon SVG'si varsa `add_svg`; elinde yalnızca PNG varsa `vectorize_image`.
- Motor içinde renklendirilecek ikonları beyaz çiz (Unity `Image.color`, Roblox `ImageColor3`, Unreal `Tint`); setin tamamını tek dosyada vermek için `export_atlas`.

## Çıktı seçimi

| Hedef | Çıktı |
| --- | --- |
| Unity / Unreal / Roblox / Godot sprite | `export_asset(engine=..., nine_slice="auto")` + bir kez `write_engine_helpers` |
| Gerçek zamanlı motor ışığıyla canlı 2B/3B UI (Normal/ORM/CanvasTexture) | `export_pbr_maps(engine="godot" \| "unity" \| "unreal" \| "generic")` |
| Hızlı AAA çerçeve / panel kurulumu | `add_frame(preset="auto" \| "rpg_gold" \| "royal_ornate" \| "fantasy_parchment" \| "scifi_hud" \| "cyber_tech" \| "glass_card" \| "medieval_iron" \| "luxury_minimal" \| "cartoon_thick")` (`inner_box` döner) |
| Yerel etkileşimli bileşenler | `add_input`, `add_scroll`, `add_slider`, `add_toggle`, `add_dropdown` — Web/React, Unreal UMG, Unity, Godot, Roblox, WPF, Avalonia, WinUI, Qt QML ve ImGui'de yerel bileşen olur |
| Ekran görüntüsünden düzenlenebilir canvas | `import_screenshot(path=...)` — OpenCV kontur/palet, satır/sütun grubu + `$ss_*` token + isteğe bağlı yerel OCR |
| Bütün bir ekran motor veya masaüstü sahnesi olarak | `export_screen(engine="unreal" \| "godot" \| "roblox" \| "unity" \| "unity-ugui" \| "wpf" \| "avalonia" \| "winui" \| "qt-qml" \| "imgui")`: yazılar ve widget'lar yerel bileşendir; Unreal UMG Python / C# ViewModel / GDScript / C++ kodu üretir |
| Sprite atlası (Phaser/Pixi/Godot/Unity/CSS) | `export_atlas(format="texturepacker" | "godot" | "unity" | "css" | "json")` |
| Motorda ayrı oynayacak parçalar (ibre, dolgu) | `export_layers` (her parça + pivot'lu `layout.json`) |
| Mobil uygulama / web görseli | `export_png(preset="ios" | "android" | "web")`, ikon için `format="ico"` ya da `sizes` |
| Figma / Penpot / Illustrator'da düzenleme, sınırsız büyütme | `export_svg` (`embedded_as_image` resim olanları söyler; büyük baskıda `image_scale: 4`) |
| Baskı, müşteri sunumu, kit kitabı | `export_pdf([...])` (çok sayfa, yazı vektör) |
| React / Next.js / Vite projesi (JSX veya TypeScript TSX) | `export_react([...], css="css" | "tailwind", typescript=true)`: `<Ad>.tsx`, `data` prop'u, `onNavigate`, `onSfx` ve gamepad odağı dahil |
| Çalışan web sitesi / prototip | `export_web([...], layout="fit" | "responsive")`: linkler (`set_link`, `mode: "overlay"`), hover CSS, CSS animasyon, sayfa geçişi |
| Görsel düzenleyicide devam | `export_psd` |
| Geliştiriciye ölçü ve token | `export_spec`, `export_theme` (css, dtcg, design.md...) |
| Video / dotLottie / Animasyon | `export_animation(format="dotlottie" | "lottie" | "mp4" | "webm" | "spritesheet" | "json")` (`animation="all"` ile çoklu `.lottie`) |

**Motor ayrıntıları:**
- **Roblox:** `export_asset(engine="roblox", scales=[2])` → kullanıcı PNG'leri Studio'da yükler → `write_engine_helpers("roblox", out_dir, roblox_ids={...})` → `UiForge.apply(label, "ad")`. Boyutta `Scale` + `UIAspectRatioConstraint`, yazı `TextLabel`, hover / press `TweenService`. Arka plan bulanıklığı yoktur; camı daha opak yap.
- **Unity:** `write_engine_helpers("unity", "<Proje>/Assets/Editor")` → `export_asset(engine="unity", out_dir=...)`. uGUI'de `Image.type = Sliced`, UI Toolkit'te `-unity-slice-*`. Yazı TextMeshPro. İbre: `RectTransform.pivot` + `localEulerAngles.z = -açı`; dolan yay `Image.type = Filled`, `Radial360`.
- **Unreal:** `export_asset(engine="unreal")` → `write_engine_helpers("unreal", ...)` → editörde Python ile `import_uiforge.py`. Brush `Draw As: Box` ve margin'ler log'da. İbre `SetRenderTransformAngle`, cam için `BackgroundBlur`.
- **Godot 4:** `export_asset(engine="godot")` → `write_engine_helpers("godot", ..., godot_res_path=...)` → her 9-slice için `.stylebox.tres`; `NinePatchRect` için `.uiforge.json` içindeki `margins_LTRB`.
- Hareketli parçayı export etmeden önce dinlenme haline getir (ibre `rotation: 0`, sağa bakar); motor döndürsün. Clip'li gölge / ışık katmanları `export_layers`'ta tabana gömülür (motor multiply / screen uygulayamaz).

## Kontrol turu (her asset için)

Önce `review_canvas` ve her `warn` maddesini düzelt (bilerek yaptıysan nedenini söyle). `info` maddeleri tasarım hatalarıdır (neredeyse hizalı kenarlar, fazla çeşit radius / kontur / yazı boyu, token yerine elle renk); onları da toparla. Sonra `preview` resminde sırayla:

1. Kesilen gölge ya da glow (kenara yapışmış koyu bant) → canvas'ı büyüt ya da `fit_canvas`.
2. Yazı kutuya sığıyor ve ortada mı? Sonuçtaki `bbox_xywh`'yi gövdeyle karşılaştır.
3. Kontrast: küçük yazı 4.5:1, büyük kalın başlık 3:1. HUD için `background="game"`; gerekirse koyu kontur ya da gölge. Rengin gerçekte ne çıktığından emin değilsen `inspect_pixels`.
4. Hizalama ve boşluklar eşit mi? `align_elements`.
5. Detay: `preview(region=[x, y, w, h], zoom=4)` ile köşelere ve ince çizgilere bak; karıştıysa `show_ids=true`.
6. Yazı varsa `language="pseudo-long"` ve `"pseudo-rtl"` ile tekrar bak.
7. Erişilebilirlik: `preview(simulate="deuteranopia")` gibi renk körlüğü simülasyonlarıyla, anlam yalnızca renkle verilmiş mi?
8. Kit bitince `contact_sheet`: radius, kontur, ışık yönü ve renkler tutarlı mı?

Bir şey beklediğin gibi çıkmadıysa `get_canvas(details=true)` ile gerçek değerlere bak, `undo` ile geri al.

## Sık yapılan hatalar

- Tema kurmadan çizmek; hex'i elle yazmak (token kullan).
- Önizlemeye bakmadan ya da `review_canvas` uyarılarını okumadan export etmek.
- İçeriği değişecek parçayı canlı yerleşim yerine elle konumlamak (yazı uzayınca bozulur).
- Her duruma ayrı canvas açmak (`set_state` ve varyant var).
- 9-slice asset'in ortasına yazı ya da gradient koymak; gölge için kenar payı bırakmamak.
- Her parçaya glow vermek; yazıyı zemine yakın tonda bırakmak.
- Gerçekçi tarzda stilize alışkanlıklar: kalın kontur, her yerde glow, büyük radius, 4-5 renk.
- İbreyi kadranla aynı gruba koymak ya da `origin` vermeden döndürmek.
- Hacmi tek gradient'le geçiştirmek; ışık yönünü parçadan parçaya değiştirmek.
- Aynı konturu ve gölgeyi her elemana ayrı ayrı vermek (katman stili kullan); gölge şekillerini elle tabana sığdırmak (clip katmanı kullan).
- Delik için zemin renginde şekil koymak (`boolean_elements` subtract kullan).
- Aynı şeyi elle tekrar çizmek (`duplicate_element`, `add_instance`, `flip_x`).
- Animasyonları yapıp ne zaman oynayacaklarını bağlamamak (`set_interaction`); web / React çıktısında her şey kendiliğinden oynar.
- Animasyonu film şeridine bakmadan export etmek; her şeye bounce / elastic vermek; motorun tween'leyebileceği basit hareketi sprite sheet'e gömmek.
- Karakter portresi, illüstrasyon, fotoğraf çizmeye çalışmak: bu aracın işi değil. Yer tutucu çerçeve çiz, görsel verilirse `add_image` ile yerleştir.
