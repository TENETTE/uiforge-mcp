"""Photorealistic 39-material library powered by Cook-Torrance GGX PBR + Perspective HDR Studio IBL + ACES.

style {"material": "gold"} or {"material": {"name": "marble", "color": "$primary", "scale": 1,
"seed": 1, "t": 0, "shine": 0.5}} expands into a domain-warped albedo+height shader paired with
physically-based surface parameters (metallic, roughness, clearcoat, anisotropy, IOR, SSS, studio IBL).
"""
from __future__ import annotations

from typing import Any

_METAL = ("w1 = fbm(x/(110*sc), y/(70*sc), 3, seed); "
          "sc_h = (noise(x*0.03/sc, y*4.2/sc, seed+7)-0.5)*grain; "
          "micro = (noise(x*0.12/sc, y*9.0/sc, seed+13)-0.5)*grain*0.45; "
          "sheen = 0.90 + 0.12*(u*0.35 + (1-v)*0.65) + (w1-0.5)*0.12; "
          "wear = (1-smoothstep(0, 4.0*sc, d))*0.06; "
          "m = clamp(sheen + sc_h*0.26 + micro*0.18 + wear, 0.48, 1.12); "
          "height = clamp(0.5 + sc_h*0.45 + micro*0.35 + (w1-0.5)*0.12); "
          "r = clamp(c_r*m); g = clamp(c_g*m); b = clamp(c_b*m)")

_CHROME = ("w1 = fbm(x/(140*sc), y/(95*sc), 2, seed); "
           "m = 0.95 + 0.06*(1-v) + (w1-0.5)*0.04; "
           "height = clamp(0.5 + (w1-0.5)*0.05); "
           "r = clamp(c_r*m); g = clamp(c_g*m); b = clamp(c_b*m)")

_RADIAL_METAL = ("dx = u-0.5; dy = v-0.5; rad = length(dx*w, dy*h); "
                 "grooves = (noise(rad*3.8/sc, seed, seed+3)-0.5)*0.22 + (noise(rad*9.5/sc, seed+2, seed+9)-0.5)*0.12; "
                 "m = clamp(0.94 + grooves*0.26, 0.55, 1.12); "
                 "height = clamp(0.5 + grooves*0.45); "
                 "r = clamp(c_r*m); g = clamp(c_g*m); b = clamp(c_b*m)")

_HAMMERED = ("c1 = voronoi(x/(19*sc), y/(19*sc), seed); c2 = voronoi(x/(10.5*sc), y/(10.5*sc), seed+5); "
             "cup = smoothstep(0.05, 0.72, c1)*0.72 + smoothstep(0.05, 0.75, c2)*0.28; "
             "ridge = pow(smoothstep(0.55, 0.92, c1), 1.6)*0.26; "
             "patina = fbm(x/(48*sc), y/(48*sc), 3, seed+2); "
             "m = 0.80 + 0.16*(1-cup) + ridge + (patina-0.5)*0.12; "
             "height = clamp(0.66 - cup*0.36 + ridge*0.48 + (patina-0.5)*0.06); "
             "r = clamp(c_r*m); g = clamp(c_g*m); b = clamp(c_b*m)")

_GEM = ("bw = max(9*sc, min(w, h)*0.24); facet = clamp(d/bw, 0, 1); "
        "step1 = smoothstep(0.0, 0.48, facet); step2 = smoothstep(0.48, 0.92, facet); "
        "table = smoothstep(0.84, 0.98, facet); "
        "band_e = pow(clamp(1 - abs(facet - 0.50)*14), 2.5)*0.24 + pow(clamp(1 - abs(facet - 0.90)*16), 2.8)*0.34; "
        "internal = 0.56 + 0.34*step1*0.6 + 0.28*v - 0.18*u + 0.12*sin((u*2.4 - v*1.9)*3.1416); "
        "depth_k = mix(0.48 + 0.42*step2 + 0.18*(1-v), internal, table); "
        "height = clamp(step1*0.58 + step2*0.42); "
        "r = clamp(c_r*depth_k + band_e); g = clamp(c_g*depth_k + band_e); b = clamp(c_b*depth_k + band_e)")

_CODE = {
    "metal": _METAL,
    "chrome": _CHROME,
    "radial_metal": _RADIAL_METAL,
    "hammered": _HAMMERED,
    "wood": ("wx = x/(160*sc); wy = y/(24*sc); "
             "warp = fbm(wx*1.5, wy*0.45, 4, seed); "
             "rings = fract(wy*1.15 + warp*3.2); "
             "ring_band = smoothstep(0.0, 0.28, rings) * smoothstep(1.0, 0.45, rings); "
             "fibers = (noise(x*0.08/sc, y*2.6/sc, seed+7)-0.5)*0.12; "
             "pores = smoothstep(0.80, 0.96, noise(x*0.25/sc, y*2.2/sc, seed+9))*0.18; "
             "tone = 0.68 + 0.26*ring_band + fibers + (warp-0.5)*0.14 - pores; "
             "height = clamp(0.48 + ring_band*0.22 + fibers*0.5 - pores*1.1); "
             "r = clamp(c_r*tone); g = clamp(c_g*tone*0.93); b = clamp(c_b*tone*0.84)"),
    "stone": ("wx = fbm(x/(44*sc), y/(44*sc), 4, seed); wy = fbm(x/(44*sc)+7, y/(44*sc)+3, 4, seed+1); "
              "n1 = fbm((x+wx*18)/(24*sc), (y+wy*18)/(24*sc), 5, seed+2); "
              "cr = ridged(x/(38*sc)+wx*0.4, y/(38*sc)+wy*0.4, 4, seed+4); "
              "speck = (rand(x*0.7, y*0.7, seed+6)-0.5)*0.08; "
              "wear = (1-smoothstep(0, 6*sc, d))*0.12; "
              "m = clamp(0.56 + 0.42*n1 - (1-cr)*0.18 + speck + wear, 0.2, 1.15); "
              "height = clamp(0.45*n1 + 0.42*cr + 0.13*(0.5+speck)); "
              "r = clamp(c_r*m); g = clamp(c_g*m); b = clamp(c_b*m)"),
    "marble": ("qx = fbm(x/(52*sc), y/(52*sc), 4, seed); qy = fbm(x/(52*sc)+5.2, y/(52*sc)+1.3, 4, seed+3); "
               "rx = fbm(x/(26*sc)+qx*2.2, y/(26*sc)+qy*2.2, 4, seed+7); "
               "cloud = fbm(x/(70*sc)+qx, y/(70*sc)+qy, 4, seed+11); "
               "v1 = pow(clamp(1 - abs(sin((x*0.6 + y)/(24*sc) + rx*5.5))), 10); "
               "v2 = pow(clamp(1 - abs(sin((x - y*0.7)/(17*sc) + qy*6.2))), 24)*0.72; "
               "vein_k = clamp(v1*0.72 + v2*0.52); "
               "base_m = 0.86 + 0.14*cloud; "
               "height = clamp(0.62 - vein_k*0.20 + cloud*0.08); "
               "r = mix(clamp(c_r*base_m), vein_r, vein_k); "
               "g = mix(clamp(c_g*base_m), vein_g, vein_k); "
               "b = mix(clamp(c_b*base_m), vein_b, vein_k)"),
    "leather": ("c = voronoi(x/(3.6*sc), y/(3.6*sc), seed); "
                "f = fbm(x/(38*sc), y/(38*sc), 4, seed+2); "
                "pebble = smoothstep(0.05, 0.85, c); "
                "st_band = smoothstep(1.5*sc, 0.35*sc, abs(d - 7.5*sc)); "
                "dash = smoothstep(0.32, 0.42, fract((x + y)/(9.0*sc))) * smoothstep(0.92, 0.82, fract((x + y)/(9.0*sc))); "
                "stitch = st_band * dash; "
                "groove = smoothstep(2.8*sc, 0.4*sc, abs(d - 7.5*sc)) * (1-stitch); "
                "m = (0.68 + 0.26*pebble + (f-0.5)*0.22) * (1 - groove*0.38); "
                "height = clamp(0.35 + 0.42*pebble + (f-0.5)*0.15 - groove*0.35 + stitch*0.48); "
                "r = mix(clamp(c_r*m), 0.90, stitch*0.9); "
                "g = mix(clamp(c_g*m), 0.78, stitch*0.9); "
                "b = mix(clamp(c_b*m), 0.58, stitch*0.9)"),
    "paper": ("n = fbm(x/(4.5*sc), y/(4.5*sc), 3, seed); f = fbm(x/(55*sc), y/(55*sc), 4, seed+1); "
              "fiber = (noise(x*0.9/sc, y*0.25/sc, seed+5)-0.5)*0.06; "
              "m = 0.88 + 0.08*n + 0.07*f + fiber; "
              "height = clamp(0.45 + 0.35*n + 0.2*f + fiber*2); "
              "r = clamp(c_r*m); g = clamp(c_g*m); b = clamp(c_b*m)"),
    "parchment": ("n = fbm(x/(5*sc), y/(5*sc), 3, seed); f = fbm(x/(42*sc), y/(42*sc), 4, seed+2); "
                  "stain = fbm(x/(24*sc), y/(24*sc), 3, seed+8); "
                  "burn = 1 - smoothstep(0, 17*sc, d + (f-0.5)*13*sc); "
                  "m = (0.86 + 0.08*n + 0.1*f - (stain-0.5)*0.14) * (1 - burn*0.42); "
                  "height = clamp(0.46 + 0.3*n + 0.2*f); "
                  "r = clamp(c_r*m - burn*0.03); g = clamp(c_g*m - burn*0.12); b = clamp(c_b*m - burn*0.22)"),
    "fabric": ("wx = 0.5+0.5*sin(x*pi/(1.8*sc)); wy = 0.5+0.5*sin(y*pi/(1.8*sc)); "
               "o = where(mod(floor(x/(3.6*sc))+floor(y/(3.6*sc)), 2) < 1, wx, wy); "
               "f = fbm(x/(32*sc), y/(32*sc), 3, seed); "
               "m = 0.72 + 0.24*o + (f-0.5)*0.14; height = clamp(0.32 + 0.56*o + (f-0.5)*0.12); "
               "r = clamp(c_r*m); g = clamp(c_g*m); b = clamp(c_b*m)"),
    "carbon_twill": ("u2 = (x + y*0.5)/(5.8*sc); v2 = (y - x*0.5)/(5.8*sc); "
                     "cell = mod(floor(u2) + floor(v2), 2); "
                     "fu = fract(u2); fv = fract(v2); "
                     "w_hi = where(cell < 1, sin(fu*pi), sin(fv*pi)); "
                     "sh = 0.26 + 0.74*pow(clamp(w_hi), 1.35); "
                     "height = clamp(0.28 + 0.65*w_hi); "
                     "r = clamp(c_r*sh); g = clamp(c_g*sh); b = clamp(c_b*sh)"),
    "rust": ("n1 = fbm(x/(32*sc), y/(32*sc), 5, seed); "
             "n2 = turbulence(x/(14*sc), y/(14*sc), 4, seed+3); "
             "pit = ridged(x/(12*sc), y/(12*sc), 3, seed+5); "
             "edge_bias = (1-smoothstep(0, 16*sc, d))*0.24; "
             "p = smoothstep(0.32, 0.66, n1*0.72 + n2*0.35 + edge_bias); "
             "dark_ox = smoothstep(0.45, 0.82, n2); "
             "gr = (noise(x*0.05/sc, y*3.2/sc, seed+4)-0.5)*0.1; ir = 0.28+gr; "
             "ox_r = clamp(c_r*(0.65 + 0.45*pit) - dark_ox*0.22); "
             "ox_g = clamp(c_g*(0.52 + 0.42*pit) - dark_ox*0.16); "
             "ox_b = clamp(c_b*(0.38 + 0.30*pit) - dark_ox*0.08); "
             "height = clamp(0.62 - p*0.28 + pit*0.28 - dark_ox*0.16); "
             "r = mix(ir*0.95, ox_r, p); "
             "g = mix(ir*0.98, ox_g, p); "
             "b = mix(ir*1.04, ox_b, p)"),
    "lava": ("wx = fbm(x/(42*sc)+t*0.5, y/(42*sc)-t*0.3, 4, seed); "
             "n = fbm(x/(38*sc)+wx*0.9+t*0.6, y/(38*sc)-wx*0.7-t*0.3, 5, seed+2); "
             "cr = ridged(x/(32*sc)+wx*0.5, y/(32*sc)-wx*0.4, 3, seed+6); "
             "magma = smoothstep(0.46, 0.68, n*0.65 + cr*0.42); "
             "core = smoothstep(0.64, 0.82, n*0.65 + cr*0.42); "
             "crust = 0.08 + 0.08*fbm(x/(10*sc), y/(10*sc), 3, seed+9); "
             "height = clamp(0.82 - magma*0.52); "
             "r = clamp(crust + magma*c_r*1.15 + core*0.45); "
             "g = clamp(crust*0.85 + magma*c_g*0.85 + core*0.58); "
             "b = clamp(crust*0.8 + magma*c_b*0.4 + core*0.22)"),
    "ice": ("wx = fbm(x/(36*sc), y/(36*sc), 4, seed); "
            "cr = pow(ridged(x/(24*sc)+wx*0.7, y/(24*sc)-wx*0.5, 4, seed+4), 5)*0.68; "
            "fr = fbm(x/(11*sc), y/(11*sc), 3, seed+2); "
            "rim = (1 - smoothstep(0, 14*sc, d))*0.32; "
            "depth = smoothstep(0, 22*sc, d); "
            "r = clamp(c_r*(0.42 + 0.38*(1-depth) + fr*0.18) + cr*0.82 + rim*0.35); "
            "g = clamp(c_g*(0.62 + 0.28*(1-depth) + fr*0.16) + cr*0.88 + rim*0.38); "
            "b = clamp(c_b*(0.80 + 0.18*(1-depth) + fr*0.12) + cr*0.92 + rim*0.35); "
            "height = clamp(0.55 + (fr-0.5)*0.22 - cr*0.42); "
            "a = clamp(0.78 + rim*0.32 + cr*0.25)"),
    "gem": _GEM,
    "obsidian": ("wx = fbm(x/(36*sc), y/(36*sc), 3, seed); "
                 "cr = ridged(x/(24*sc)+wx*0.5, y/(24*sc)-wx*0.4, 4, seed+2); "
                 "n = fbm(x/(14*sc), y/(14*sc), 3, seed+5); "
                 "m = 0.40 + 0.60*pow(cr, 2.0) + n*0.18; "
                 "height = clamp(cr*0.72 + n*0.22); "
                 "r = clamp(c_r*m); g = clamp(c_g*m); b = clamp(c_b*m + (1-smoothstep(0, 7*sc, d))*0.14)"),
    "jade": ("qx = fbm(x/(46*sc), y/(46*sc), 4, seed); "
             "n = turbulence(x/(34*sc)+qx*0.8, y/(34*sc)-qx*0.6, 4, seed+2); "
             "thick = smoothstep(0, 22*sc, d); "
             "m = (0.70 + 0.36*n) * (1.12 - thick*0.26); "
             "height = clamp(0.5 + n*0.18); "
             "r = clamp(c_r*m); g = clamp(c_g*m + (1-thick)*0.08); b = clamp(c_b*m + (1-thick)*0.05)"),
    "runic_stone": ("wx = fbm(x/(30*sc), y/(30*sc), 3, seed); "
                    "cr = ridged(x/(26*sc)+wx*0.45, y/(26*sc)-wx*0.35, 3, seed+1); "
                    "n = fbm(x/(16*sc), y/(16*sc), 4, seed+4); "
                    "crack = smoothstep(0.76, 0.90, cr); "
                    "halo = smoothstep(0.58, 0.88, cr) * 0.42; "
                    "pulse = 0.85 + 0.15*sin(t*6.2832 + n*4); "
                    "base = 0.16 + 0.18*n; "
                    "height = clamp(0.68*n + 0.32*(1-crack)); "
                    "r = clamp(mix(base*0.95 + c_r*halo, c_r*1.15*pulse + 0.25, crack)); "
                    "g = clamp(mix(base*1.0 + c_g*halo, c_g*1.15*pulse + 0.28, crack)); "
                    "b = clamp(mix(base*1.1 + c_b*halo, c_b*1.2*pulse + 0.32, crack))"),
    "energy_shield": ("px_ = x/(14*sc); py_ = y/(14*sc); r3 = 1.73205; "
                      "ax = mod(px_, 1) - 0.5; ay = mod(py_, r3) - r3*0.5; "
                      "bx = mod(px_ - 0.5, 1) - 0.5; by = mod(py_ - r3*0.5, r3) - r3*0.5; "
                      "na = (ax*ax + ay*ay) < (bx*bx + by*by); "
                      "gx = abs(where(na, ax, bx)); gy = abs(where(na, ay, by)); "
                      "hex_e = 0.5 - max(gx, gx*0.5 + gy*(r3*0.5)); "
                      "grid = smoothstep(0.08, 0.02, hex_e); "
                      "rim = 1 - smoothstep(0, 14*sc, d); "
                      "wave = 0.5 + 0.5*sin((u*4 - v*3 + t*2)*6.2832); "
                      "glow_k = clamp(0.16 + grid*0.46*(0.6+0.4*wave) + rim*0.9); "
                      "r = clamp(c_r*glow_k + rim*0.35); g = clamp(c_g*glow_k + rim*0.35); b = clamp(c_b*glow_k + rim*0.4); "
                      "a = clamp(0.28 + grid*0.48 + rim*0.68)"),
    "foil_holographic": ("n = fbm(x/(38*sc), y/(38*sc), 3, seed); "
                         "ang = (u*1.7 + v*1.2 + n*0.85 + t)*6.2832; "
                         "rr = 0.52 + 0.48*cos(ang); gg = 0.52 + 0.48*cos(ang + 2.094); bb = 0.52 + 0.48*cos(ang + 4.189); "
                         "height = clamp(0.5 + n*0.18); "
                         "r = clamp(mix(c_r, rr, 0.72)); "
                         "g = clamp(mix(c_g, gg, 0.72)); "
                         "b = clamp(mix(c_b, bb, 0.72))"),
    "plastic": "k = 1.02 - v*0.22; r = clamp(c_r*k); g = clamp(c_g*k); b = clamp(c_b*k)",
    "candy": ("k = 1.04 - v*0.26 + (1-smoothstep(0, 14*sc, d))*0.10; "
              "r = clamp(c_r*k); g = clamp(c_g*k); b = clamp(c_b*k)"),
    "clay": ("n = fbm(x/(24*sc), y/(24*sc), 3, seed)*0.05; k = 0.96 - v*0.16 + n; "
             "height = clamp(0.5 + n*2.4); "
             "r = clamp(c_r*k); g = clamp(c_g*k); b = clamp(c_b*k)"),
    "enamel": ("rim = smoothstep(7.2*sc, 5.0*sc, d); "
               "k = 0.96 - v*0.22; "
               "height = clamp(0.50 + rim*0.36); "
               "r = mix(clamp(c_r*k), 0.94, rim*0.95); "
               "g = mix(clamp(c_g*k), 0.76, rim*0.95); "
               "b = mix(clamp(c_b*k), 0.30, rim*0.95)"),
    "wax": ("n = fbm(x/(16*sc), y/(16*sc), 3, seed); "
            "lip = exp(-pow((d - 7.5*sc)/(3.6*sc), 2))*0.34; "
            "rr = length((u-0.5)*w, (v-0.5)*h); cr = min(w, h)*0.27; "
            "stamp = exp(-pow((rr - cr)/(2.8*sc), 2))*0.26; "
            "k = 0.78 + 0.14*n + lip*0.30 + stamp*0.24 - smoothstep(10*sc, 16*sc, d)*0.08; "
            "height = clamp(0.45 + lip*1.85 + stamp*1.35 + (n-0.5)*0.18); "
            "r = clamp(c_r*k); g = clamp(c_g*k); b = clamp(c_b*k)"),
    "jelly": ("k = 0.96 - v*0.24; n = fbm(x/(30*sc)+t, y/(30*sc), 3, seed)*0.07; "
              "rim = (1-smoothstep(0, 11*sc, d))*0.18; "
              "r = clamp(c_r*k+n+rim); g = clamp(c_g*k+n+rim); b = clamp(c_b*k+n+rim); a = clamp(0.82 + rim*0.28)"),
    "hologram": ("ln = 0.75+0.25*sin(y*pi/(2*sc) - t*20); n = noise(x/(40*sc)+t*3, y/(6*sc), seed)*0.3; "
                 "e = smoothstep(0, 0.12, u)*smoothstep(1, 0.88, u)*smoothstep(0, 0.12, v)*smoothstep(1, 0.88, v); "
                 "r = clamp(c_r*ln+n); g = clamp(c_g*ln+n); b = clamp(c_b*ln+n); a = clamp((0.35+0.4*ln)*(1.3-e*0.6))"),
    "neon": ("tube = exp(-pow((d - 4.5*sc)/(2.8*sc), 2)); "
             "inner = smoothstep(0, 18*sc, d); "
             "core = pow(tube, 2.2); "
             "base = 0.16 + 0.34*(1 - inner) + tube*0.75; "
             "r = clamp(c_r*base + core*0.85); g = clamp(c_g*base + core*0.85); b = clamp(c_b*base + core*0.85)"),
}

_PBR_METAL = {"metallic": 0.98, "roughness": 0.18, "bevel_size": 7.5, "bevel_depth": 1.30, "profile": "machined",
              "bump_strength": 0.10, "env": 1.38, "exposure": 1.02, "crown": 0.30, "studio": "bright"}

_MATERIALS: dict[str, dict] = {
    "gold":             {"code": "metal", "color": "#e6b038", "p": {"grain": 0.14},
                         "pbr": {**_PBR_METAL, "roughness": 0.17, "anisotropy": 0.42, "studio": "warm", "exposure": 1.08}},
    "silver":           {"code": "metal", "color": "#d4dce5", "p": {"grain": 0.12},
                         "pbr": {**_PBR_METAL, "roughness": 0.15, "anisotropy": 0.38, "env": 1.32}},
    "chrome":           {"code": "chrome", "color": "#eef2f6",
                         "pbr": {**_PBR_METAL, "metallic": 1.0, "roughness": 0.045, "bevel_size": 9.0,
                                 "bevel_depth": 1.45, "profile": "round", "bump_strength": 0.04,
                                 "crown": 0.38, "env": 1.55, "exposure": 1.04}},
    "bronze":           {"code": "metal", "color": "#b87338", "p": {"grain": 0.18},
                         "pbr": {**_PBR_METAL, "roughness": 0.24, "anisotropy": 0.46, "studio": "warm", "exposure": 1.1}},
    "copper":           {"code": "metal", "color": "#d97852", "p": {"grain": 0.16},
                         "pbr": {**_PBR_METAL, "roughness": 0.21, "anisotropy": 0.42, "studio": "warm", "exposure": 1.08}},
    "steel":            {"code": "metal", "color": "#a8b2bd", "p": {"grain": 0.48},
                         "pbr": {**_PBR_METAL, "roughness": 0.26, "anisotropy": 0.78, "bump_strength": 0.18}},
    "iron":             {"code": "metal", "color": "#646c76", "p": {"grain": 0.38},
                         "pbr": {**_PBR_METAL, "metallic": 0.90, "roughness": 0.42, "bump_strength": 0.22,
                                 "studio": "dark", "env": 1.25, "exposure": 1.12}, "noise": 0.025},
    "radial_metal":     {"code": "radial_metal", "color": "#cfd8e2",
                         "pbr": {**_PBR_METAL, "roughness": 0.20, "anisotropy": 0.78, "brush_angle": "radial",
                                 "bump_strength": 0.08, "crown": 0.24, "profile": "chamfer"}},
    "hammered_gold":    {"code": "hammered", "color": "#eab63e",
                         "pbr": {**_PBR_METAL, "roughness": 0.21, "profile": "chamfer", "bump_strength": 0.34,
                                 "crown": 0.22, "env": 1.32, "exposure": 1.05, "studio": "warm"}},
    "rust":             {"code": "rust", "color": "#b8461c",
                         "pbr": {"metallic": 0.20, "roughness": 0.78, "bevel_size": 5.0, "profile": "chamfer",
                                 "bump_strength": 0.56, "ao": 0.48, "env": 0.9, "exposure": 1.12}},
    "wood":             {"code": "wood", "color": "#874e26",
                         "pbr": {"metallic": 0.0, "roughness": 0.44, "clearcoat": 0.45, "clearcoat_roughness": 0.16,
                                 "bevel_size": 5.5, "profile": "round", "bump_strength": 0.24, "ao": 0.36,
                                 "crown": 0.16, "env": 0.95, "exposure": 1.12, "studio": "warm"}},
    "stone":            {"code": "stone", "color": "#85827b",
                         "pbr": {"metallic": 0.0, "roughness": 0.85, "bevel_size": 6.5, "profile": "chamfer",
                                 "bump_strength": 0.58, "ao": 0.52, "env": 0.8, "exposure": 1.12}},
    "runic_stone":      {"code": "runic_stone", "color": "#38bdf8", "glow": True,
                         "pbr": {"metallic": 0.05, "roughness": 0.74, "bevel_size": 6.5, "profile": "chamfer",
                                 "bump_strength": 0.58, "ao": 0.55, "emissive": 2.4, "studio": "dark",
                                 "env": 0.9, "exposure": 1.15}},
    "marble":           {"code": "marble", "color": "#ece8e1", "p": {"vein": "#4c5360"},
                         "pbr": {"metallic": 0.0, "roughness": 0.14, "clearcoat": 0.88, "clearcoat_roughness": 0.05,
                                 "bevel_size": 6.0, "profile": "chamfer", "bump_strength": 0.12, "ao": 0.22,
                                 "crown": 0.22, "env": 1.15, "exposure": 1.02}},
    "obsidian":         {"code": "obsidian", "color": "#1d1a2e",
                         "pbr": {"metallic": 0.16, "roughness": 0.12, "clearcoat": 0.92, "clearcoat_roughness": 0.045,
                                 "ior": 1.56, "bevel_size": 6.5, "profile": "chamfer", "bump_strength": 0.50,
                                 "crown": 0.22, "studio": "dark", "env": 1.35, "exposure": 1.18}},
    "jade":             {"code": "jade", "color": "#1ea86e",
                         "pbr": {"metallic": 0.0, "roughness": 0.16, "clearcoat": 0.82, "clearcoat_roughness": 0.07,
                                 "sss": 0.65, "bevel_size": 8.0, "profile": "dome", "bump_strength": 0.14,
                                 "crown": 0.30, "env": 1.08, "exposure": 1.02},
                         "inner_glow": {"color": "#a7f3d0@0.22", "blur": 10}},
    "leather":          {"code": "leather", "color": "#7a4426",
                         "pbr": {"metallic": 0.0, "roughness": 0.56, "sss": 0.18, "bevel_size": 6.0, "profile": "round",
                                 "bump_strength": 0.54, "ao": 0.45, "env": 0.92, "exposure": 1.12, "studio": "warm"}},
    "paper":            {"code": "paper", "color": "#ede3cf",
                         "pbr": {"metallic": 0.0, "roughness": 0.92, "bevel_size": 2.0, "bevel_depth": 0.35,
                                 "profile": "round", "bump_strength": 0.20, "ao": 0.15, "env": 0.72, "exposure": 1.06}},
    "aged_parchment":   {"code": "parchment", "color": "#e2cc9e",
                         "pbr": {"metallic": 0.0, "roughness": 0.88, "bevel_size": 3.0, "bevel_depth": 0.45,
                                 "profile": "round", "bump_strength": 0.28, "ao": 0.28, "env": 0.78,
                                 "exposure": 1.08, "studio": "warm"}},
    "fabric":           {"code": "fabric", "color": "#3d5a8c",
                         "pbr": {"metallic": 0.0, "roughness": 0.88, "sss": 0.16, "bevel_size": 4.0, "profile": "round",
                                 "bump_strength": 0.48, "ao": 0.42, "env": 0.8, "exposure": 1.12}},
    "carbon_twill":     {"code": "carbon_twill", "color": "#323842",
                         "pbr": {"metallic": 0.15, "roughness": 0.28, "clearcoat": 0.95, "clearcoat_roughness": 0.06,
                                 "bevel_size": 6.0, "profile": "machined", "bump_strength": 0.42, "ao": 0.45,
                                 "crown": 0.22, "studio": "dark", "env": 1.25, "exposure": 1.18}},
    "lava":             {"code": "lava", "color": "#ff5a1f", "glow": True,
                         "pbr": {"metallic": 0.0, "roughness": 0.78, "bevel_size": 5.0, "profile": "chamfer",
                                 "bump_strength": 0.52, "ao": 0.5, "emissive": 2.6, "studio": "dark",
                                 "env": 0.7, "exposure": 1.1}},
    "ice":              {"code": "ice", "color": "#6cc8f5",
                         "pbr": {"metallic": 0.0, "roughness": 0.10, "clearcoat": 0.96, "clearcoat_roughness": 0.04,
                                 "ior": 1.31, "sss": 0.45, "bevel_size": 7.5, "profile": "chamfer",
                                 "bump_strength": 0.30, "crown": 0.24, "env": 1.25, "exposure": 1.02},
                         "inner_glow": {"color": "#e0f7ff@0.35", "blur": 10}},
    "gem":              {"code": "gem", "color": "#0ea5e9",
                         "pbr": {"metallic": 0.10, "roughness": 0.05, "clearcoat": 1.0, "clearcoat_roughness": 0.035,
                                 "ior": 1.85, "sss": 0.32, "bevel_size": 10.0, "bevel_depth": 1.4, "profile": "facet",
                                 "bump_strength": 0.10, "crown": 0.16, "env": 1.38, "exposure": 1.02}},
    "ruby":             {"code": "gem", "color": "#cf1140",
                         "pbr": {"metallic": 0.10, "roughness": 0.05, "clearcoat": 1.0, "clearcoat_roughness": 0.035,
                                 "ior": 1.77, "sss": 0.36, "bevel_size": 10.0, "bevel_depth": 1.4, "profile": "facet",
                                 "bump_strength": 0.10, "crown": 0.16, "env": 1.38, "exposure": 1.04},
                         "inner_glow": {"color": "#ff88a0@0.26", "blur": 8}},
    "emerald":          {"code": "gem", "color": "#059669",
                         "pbr": {"metallic": 0.10, "roughness": 0.05, "clearcoat": 1.0, "clearcoat_roughness": 0.035,
                                 "ior": 1.60, "sss": 0.36, "bevel_size": 10.0, "bevel_depth": 1.4, "profile": "facet",
                                 "bump_strength": 0.10, "crown": 0.16, "env": 1.38, "exposure": 1.04},
                         "inner_glow": {"color": "#86efac@0.26", "blur": 8}},
    "foil_holographic": {"code": "foil_holographic", "color": "#a78bfa",
                         "pbr": {**_PBR_METAL, "metallic": 0.92, "roughness": 0.12, "clearcoat": 0.85,
                                 "anisotropy": 0.5, "crown": 0.34, "env": 1.35}},
    "energy_shield":    {"code": "energy_shield", "color": "#22d3ee", "glow": True, "light": None},
    "plastic":          {"code": "plastic", "color": "#2563eb",
                         "pbr": {"metallic": 0.0, "roughness": 0.22, "clearcoat": 0.72, "clearcoat_roughness": 0.08,
                                 "bevel_size": 7.5, "profile": "round", "crown": 0.32, "env": 1.15, "exposure": 1.02}},
    "candy_gloss":      {"code": "candy", "color": "#e11d48",
                         "pbr": {"metallic": 0.0, "roughness": 0.08, "clearcoat": 1.0, "clearcoat_roughness": 0.04,
                                 "sss": 0.55, "bevel_size": 11.5, "bevel_depth": 1.15, "profile": "dome",
                                 "crown": 0.44, "env": 1.28, "exposure": 1.00}},
    "clay_3d":          {"code": "clay", "color": "#e06834",
                         "pbr": {"metallic": 0.0, "roughness": 0.76, "sss": 0.42, "bevel_size": 13.0,
                                 "bevel_depth": 1.05, "profile": "dome", "bump_strength": 0.10,
                                 "crown": 0.42, "env": 0.85, "exposure": 0.98, "studio": "warm"}},
    "enamel":           {"code": "enamel", "color": "#1d4ed8",
                         "pbr": {"metallic": 0.05, "roughness": 0.08, "clearcoat": 1.0, "clearcoat_roughness": 0.035,
                                 "bevel_size": 6.5, "profile": "machined", "bump_strength": 0.32,
                                 "crown": 0.32, "env": 1.32, "exposure": 1.02}},
    "wax_seal":         {"code": "wax", "color": "#991236",
                         "pbr": {"metallic": 0.0, "roughness": 0.36, "sss": 0.52, "clearcoat": 0.38,
                                 "bevel_size": 7.0, "profile": "round", "bump_strength": 0.50,
                                 "ao": 0.40, "crown": 0.22, "env": 0.96, "exposure": 1.02, "studio": "warm"}},
    "rubber":           {"code": "plastic", "color": "#2b2f36",
                         "pbr": {"metallic": 0.0, "roughness": 0.84, "bevel_size": 6.0, "profile": "round",
                                 "crown": 0.16, "env": 0.75, "exposure": 1.12}, "noise": 0.035},
    "jelly":            {"code": "jelly", "color": "#16b850",
                         "pbr": {"metallic": 0.0, "roughness": 0.07, "clearcoat": 1.0, "clearcoat_roughness": 0.035,
                                 "sss": 0.68, "bevel_size": 11.5, "bevel_depth": 1.15, "profile": "dome",
                                 "crown": 0.44, "env": 1.28, "exposure": 1.00},
                         "inner_glow": {"color": "#ffffff@0.26", "blur": 10}},
    "hologram":         {"code": "hologram", "color": "#34e0ff", "glow": True, "light": None},
    "glass":            {"style": {"fill": "#ffffff@0.11", "backdrop_blur": 12,
                                   "stroke": {"color": "#ffffff@0.38", "width": 1},
                                   "inner_glow": {"color": "#ffffff@0.16", "blur": 10},
                                   "shadow": {"color": "#000000@0.35", "blur": 20, "dy": 8, "knockout": True}}},
    "liquid_glass":     {"style": {"fill": {"type": "linear", "angle": 145, "stops": ["#ffffff@0.22", "#e0f2fe@0.07", "#bae6fd@0.15"]},
                                   "glass": {"refraction": 0.92, "depth": 13, "dispersion": 0.42, "frost": 1.5,
                                             "intensity": 0.85, "fresnel": 0.75, "tint": "#e0f2fe@0.12"},
                                   "stroke": {"color": {"type": "linear", "angle": 135, "stops": ["#ffffff@0.82", "#ffffff@0.12", "#ffffff@0.50"]}, "width": 1.2},
                                   "shadow": {"color": "#000000@0.38", "blur": 22, "dy": 10, "knockout": True}}},
    "neon":             {"code": "neon", "color": "#ff3df2", "glow": True, "light": None},
}

NAMES = sorted(_MATERIALS)


def _own(name: str, spec: dict, custom: dict, theme: dict, depth: int) -> dict:
    """A theme material: any style keys, optionally built on another material ("material": "wood")."""
    out = dict(custom[name])
    base = out.pop("material", None)
    if base is not None:
        if depth > 8:
            raise ValueError(f"material '{name}' refers to itself")
        base_spec = dict(base) if isinstance(base, dict) else {"name": base}
        base_spec.update({k: out.pop(k) for k in ("color", "scale", "seed", "t", "shine") if k in out})
        out = {**expand(base_spec, theme, depth + 1), **out}
    over = {k: v for k, v in spec.items() if k != "name"}
    fill = out.get("fill")
    if over and isinstance(fill, dict) and str(fill.get("type")).lower() == "shader":
        params = dict(fill.get("params") or {})
        for key, value in over.items():
            if key == "shine":
                if isinstance(out.get("pbr"), dict):
                    out["pbr"] = {**out["pbr"], "shine": value}
                elif isinstance(out.get("light"), dict):
                    out["light"] = {**out["light"], "shine": value}
                continue
            params["c" if key == "color" else "sc" if key == "scale" else key] = value
        out["fill"] = {**fill, "params": params}
    elif "color" in over and not isinstance(fill, dict):
        out["fill"] = over["color"]
    return out


def expand(spec: Any, theme: dict | None = None, depth: int = 0) -> dict:
    """Style keys for a material reference (a name or {"name", "color", "scale", "seed", "t", "shine", ...}).
    Theme materials (set_theme(materials=...)) come first, then the built-in ones."""
    if isinstance(spec, str):
        spec = {"name": spec}
    custom = (theme or {}).get("materials") or {}
    if not isinstance(spec, dict) or not spec.get("name"):
        raise ValueError(f'material must be a name or {{"name": ...}}. Materials: {", ".join(sorted(custom) + NAMES)}')
    name = str(spec["name"])
    if name in custom:
        return _own(name, spec, custom, theme or {}, depth)
    name = name.lower()
    if name not in _MATERIALS:
        raise ValueError(f"Unknown material '{name}'. Materials: {', '.join(sorted(custom) + NAMES)}")
    m = _MATERIALS[name]
    color = spec.get("color", m.get("color"))
    if "style" in m:
        out = dict(m["style"])
        if name == "liquid_glass" and spec.get("color"):
            out["glass"] = {**out["glass"], "tint": spec["color"]}
        return out
    params = {"c": color, "sc": max(0.05, float(spec.get("scale", 1))), "seed": float(spec.get("seed", 1)),
              "t": float(spec.get("t", 0)), **m.get("p", {})}
    params.update({k: v for k, v in spec.items() if k not in ("name", "color", "scale", "seed", "t", "shine")})
    out = {"fill": {"type": "shader", "code": _CODE[m["code"]], "params": params}}
    if m.get("pbr"):
        pbr_cfg = dict(m["pbr"])
        if spec.get("shine") is not None:
            pbr_cfg["shine"] = float(spec["shine"])
        out["pbr"] = pbr_cfg
    if m.get("light"):
        light = dict(m["light"])
        if spec.get("shine") is not None:
            light["shine"] = float(spec["shine"])
        out["light"] = light
    for key in ("stroke", "inner_glow", "noise"):
        if m.get(key) is not None:
            out[key] = m[key]
    if m.get("glow"):
        out["glow"] = [{"color": f"{color}@0.85", "blur": 8}, {"color": f"{color}@0.55", "blur": 22}] if name == "neon" \
            else {"color": f"{color}@0.6", "blur": 16}
    return out
