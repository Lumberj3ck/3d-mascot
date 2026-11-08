# Roadmap: from model to premium chibi companion

## Vision

The dragon is the companion in a **streak game / web app**. Users check on it, decorate its **room**, dress it
in **clothes**, and **buy items**. It reacts with **emotions** and **animations** (for example, celebrating a kept
streak or sulking after a missed one). The bar is premium quality: soft clay look, appealing motion, and clothes
that fit with no clipping.

## Where we are

| Have | Don't have yet |
|---|---|
| Smoothed 80k-tri model with sage textures and a glowing gem (`outputs/dragon_clean.glb`) | Animation-friendly topology (current mesh is a uniform voxel-remesh triangle soup) |
| Faithful shape from the turnaround sheet | Skeleton / skin weights |
| 2D design of 6 expressions (`inputs/raw/expressions.png`) | 3D expressions. The neutral face is **painted into** the body texture |
| Image-to-3D pipeline (Pixal3D on Nebius) + clean pipeline (Blender) | Normal / AO maps, compression, web runtime |

## Key principle: lock the body first

Every clothing item is fitted to **one body**: its shape, topology, and skeleton. If any of those change later,
every item has to be refitted. So the order is fixed: **production body → rig → face → clothes**, and the
body + rig get "frozen" (versioned) before wardrobe production starts.

---

## Phase 1: Production body (retopology + bakes)

The single biggest quality jump.
- **Retopologize** to a clean, **symmetric quad mesh**, ~15–25k tris, with edge loops where things bend or
  emote: around eyes and mouth, neck, shoulders, elbows, wrists, hips, knees, wing roots, tail segments.
  Symmetry also halves the rigging and clothing work (the asymmetric fang stays a texture/decal detail).
  - Tools: Blender + Quad Remesher / Instant Meshes for a first pass, then hand cleanup. This is where a
    human 3D artist gives the most value. Scripted auto-retopo is acceptable but not premium.
- **Split parts** into separate meshes/material slots:
  - **eyes**: separate, so they can look at things and blink
  - **gem**: its own emissive material, so it can pulse on streak events
  - **horns**: rigid, and useful as hat attachment references
  - **wings**: separate for flapping, and so clothing can cut around them
- **Bake from the 1M-tri Pixal3D original:** normal map (keeps the clay surface detail on the low poly),
  AO, base colour, roughness. Use one packed **ORM** texture (AO/roughness/metal) and a proper UV layout:
  hand-placed seams, packing over 75% vs. 46% today, and the face/head at a higher texel density.
- **Paint the face out** of the body texture (eyes/mouth/brows move to the expression system, Phase 3).
- Clay feel: PBR with roughness ~0.6–0.8 plus **`KHR_materials_sheen`** (soft velvet/clay rim). Optionally a
  subtle wrap-lighting tweak in the web shader to fake subsurface scattering.

## Phase 2: Skeleton, skinning, secondary motion

- **Skeleton** (~45–60 bones):
  - root, hips, spine, chest, neck, head, jaw
  - eyes L/R
  - ears L/R (2 each)
  - crest
  - arms: upper, lower, hand, 1–2 mitten fingers
  - legs: upper, lower, foot, toe
  - **tail** chain (4–5)
  - **wings** L/R (3 each)
  - gem socket
  - **attachment sockets**: hat, face, back, hand_L/R, tail_tip
- Rig in Blender (Rigify-style controls for animators). Export a clean deform-only skeleton.
- **Skin weights:** auto weights as a start, then hand-painted at joints. Corrective shape keys where chibi
  proportions crease (shoulders under the big head, hips).
- **Secondary motion at runtime** via spring bones: ears, crest, tail, wing tips, and later scarves/capes. Cheap,
  and it makes the character feel alive.
- **Format decision: use VRM 1.0 (recommended) or plain glTF with our own conventions.**
  VRM is glTF plus a standard for humanoid bone mapping, **expressions**, **spring bones**, and **look-at**.
  `@pixiv/three-vrm` implements all of it for three.js, and the *VRM Add-on for Blender* exports it. Our chibi
  maps fine to the required humanoid bones. Extra bones (tail, wings, ears) are allowed and driven by springs.
  This gets us expressions, blinking, eye tracking, and jiggle physics with no custom runtime work.

## Phase 3: Facial expressions

The design's face is flat and graphic: dot eyes, a `:3` mouth, painted-looking brows. The best fit is a
**hybrid**:
- **Face decal atlas** (2D, matches the art exactly): eye states, mouths, brows, and extras such as blush,
  tears, sweat drop, sparkle eyes, and hearts.
  - Eye states: open, happy `^ ^`, sleepy half-lid, closed, sad, wide/excited.
  - Mouths: `:3` + fang, open smile, yawn `O`, frown, talk visemes.
  - These are drawn on a thin face-layer mesh (or a second UV set) and selected per region by an atlas index
    in the shader. Each region swaps independently, so `eyes=happy + mouth=:3 + blush` combines.
- **Shape keys** for 3D motion the decal can't do: cheek puff/squash, jaw open, eyelid squeeze, head
  squash & stretch.
- **Expression presets** = decal states + shape-key weights. Map the 6 designed ones (neutral, happy, sleepy,
  sad, excited, proud) onto VRM presets (`happy`, `sad`, `relaxed`, `surprised`, plus custom `proud`, `sleepy`).
  Add automatic **blink** and **look-at** (follows cursor/finger, looks at items).
- The source designs exist. `inputs/raw/expressions.png` gets redrawn as clean vector/2K atlas tiles.

## Phase 4: Animation set

Hand-keyed in Blender. Chibi proportions (huge head, short limbs) retarget poorly from mocap or Mixamo, and
stylized timing is what reads as "premium". The emotional states come from layering expression + body
animation.

| Group | Clips |
|---|---|
| Idle | breathe idle (tail sway, blinks), idle variants (look around, scratch, stretch), sleep loop |
| Reactions | tap/poke reaction, happy bounce, sad droop, excited jump, proud pose, yawn |
| Streak moments | streak kept (celebration, gem flare), milestone (spin + wings flap + confetti hook), streak lost (sulk), welcome back |
| Room | walk/hop cycle, sit, lie down, interact (pick up / play with / eat item), turn in place |
| Wardrobe | try-on pose ("look at me"), mirror spin |

Plus a runtime **state machine**: idle ↔ reaction ↔ locomotion, with blend trees and additive layers
(breathing/expression on top of anything).

## Phase 5: Wardrobe system (clothes that fit well)

Fit is mostly a pipeline and conventions problem:
- **Slots:** `head` (hats, which must clear horns + crest), `face` (glasses, which must clear the snout), `neck`
  (scarf/bow, which must clear the gem), `torso` (tops; wing + tail holes), `back` (backpacks, which conflict
  with wings), `feet`, `hand` (held items), `tail` (ribbons/rings). Each slot defines which slots it excludes.
- **Two item types:**
  - **Rigid accessories** (hats, glasses, held items, tail rings): parented to **sockets**. They need no
    skinning and are trivially compatible. Most of the catalogue should be this type, since it's cheap and
    always fits.
  - **Skinned garments** (tops, scarves, capes): modelled on the frozen body (shrinkwrap + offset). Weights
    are **transferred from the body**, and they ship on the same skeleton. Capes/scarves get spring bones.
- **No clipping:**
  - The body is split into **mask regions** (torso, upper arms, neck, feet…). A garment declares which
    regions it hides, so hidden body parts aren't drawn and can't poke through.
  - Garments get a small **inflate** tolerance.
  - An automated **clip test**: render every garment through every animation and flag body penetration.
- **Authoring kit** for artists or AI: the body mesh, skeleton, sockets, mask regions, a "garment template"
  `.blend`, polycount/texture budgets, and a validation script (bones, scale, slots, budgets) run in CI.
- **Scaling content:** rigid items, furniture, and room props suit the **image-to-3D pipeline we already
  have** (Pixal3D → `scripts/clean/`). Generate concept art in the same soft-clay style → 3D → clean → bake →
  validate. Skinned garments need a human or semi-manual fitting pass.

## Phase 6: Rooms & items

- The room is a diorama scene: floor/wall/window templates plus placeable furniture with a grid/snap
  system and walkable navmesh for the dragon.
- Props run through the same clean pipeline with a shared **texture/palette style guide** so everything
  matches the character: pastel, soft clay, rounded.
- Interactions: items declare an interaction point + animation (bed → sleep, ball → play, bowl → eat).

## Phase 7: Premium web runtime

- **Stack:** three.js via **React Three Fiber** (+ drei), `@pixiv/three-vrm` for the character.
- **Look:**
  - HDRI image-based lighting + a soft key light
  - contact shadows / baked AO under the character
  - **AgX/Neutral** tone mapping
  - subtle **bloom** for the gem and sparkles
  - light SSAO in rooms
  - sheen on clay materials
  - FXAA/SMAA, DPR capped on mobile
- **Performance budgets** (mobile-first):
  - Character: 15–25k tris (LOD1 ~8k), 1 draw call body + eyes/gem, 2K textures (1K on low-end).
  - Garments: 2–6k tris and 512–1K textures each.
  - Character GLB under ~3 MB.
- **Delivery:**
  - `gltfpack`/gltf-transform with **meshopt** geometry compression and **KTX2/Basis** textures
  - lazy-loaded wardrobe items
  - CDN caching
- **Character Lab** dev page: preview the body with any combination of clothes, expressions, and
  animations; lighting presets; a perf HUD. This becomes the QA and art-review tool.

---

## Suggested order & what Claude can vs. should not do alone

| # | Step | Claude (scripted Blender/web) | Human 3D artist adds |
|---|---|---|---|
| 1 | Production body: retopo, parts split, bakes, face paint-out | Auto-retopo + bakes + validation (good) | Hand topology & UVs (premium) |
| 2 | Rig + skin + springs, VRM export | Skeleton, auto weights, VRM/spring setup | Weight polish, correctives |
| 3 | Face system | Decal shader, atlas pipeline, shape keys, presets | Clean drawn atlas art |
| 4 | Animation set | Procedural idles/blinks/look-at, state machine | Hand-keyed signature clips |
| 5 | Wardrobe kit + 3–5 pilot items | Slots, sockets, masks, validator, rigid items via Pixal3D | Skinned garments |
| 6 | Rooms/props pipeline | Image-to-3D → clean → validate at scale | Art direction |
| 7 | Web runtime + Character Lab | Full implementation | — |

A good first milestone, demoable end to end: **Character Lab showing the dragon idling with blinks, look-at,
switching between the 6 expressions, spring tail/ears, wearing one hat (socket) and one scarf (skinned + spring),
rendered with the premium lighting setup.**

## Open questions (product decisions)

1. Platforms: mobile web only, desktop too, or native apps later (affects budgets)?
2. Look: soft-clay PBR (as concept) vs. toon/cel shading?
3. Catalogue scale at launch (10 items vs. 200 decides how much to automate)?
4. Budget for a human 3D artist for retopo/weights/key animations, or Claude-only first pass?
5. Adopt VRM 1.0 as the character format? (Recommended.)
