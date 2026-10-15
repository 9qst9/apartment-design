# Apartment design: Japandi × brutalism

Interior design for a 56 m², one-bedroom, west-facing apartment. The whole scene is a single
procedural Blender script, [`apartment.py`](apartment.py): walls, furniture, materials, lighting and cameras are all code,
so every design change is a diff.

**Brief:** Japandi warmth with brutalist concrete, as much daylight as possible, and a proper home office for a software
engineer (desk 120×80, Mac mini, one ultrawide monitor).

## Renders

|                     | Day                                               | Night                                                     |
|---------------------|---------------------------------------------------|-----------------------------------------------------------|
| Isometric cutaway   | ![isometric](renders/render_isometric.png)                 | ![isometric night](renders/render_isometric_night.png)                   |
| Plan                | ![topdown](renders/render_topdown.png)                   | ![topdown night](renders/render_topdown_night.png)                     |
| TV wall             | ![living tv](renders/render_living_tv.png)                 | ![living tv night](renders/render_living_tv_night.png)                   |
| Living room, 5.9 m  | ![living length](renders/render_living_length.png)             | ![living length night](renders/render_living_length_night.png)               |
| Dining + kitchen    | ![dining](renders/render_dining.png)                    | ![dining night](renders/render_dining_night.png)                      |
| Bedroom             | ![bedroom](renders/render_bedroom.png)                   | ![bedroom night](renders/render_bedroom_night.png)                     |
| Home office         | ![bedroom office](renders/render_bedroom_office.png)            | ![bedroom office night](renders/render_bedroom_office_night.png)              |
| Entrance            | ![entrance](renders/render_entrance.png)                  | ![entrance night](renders/render_entrance_night.png)                    |

Day renders use a late-afternoon west sun. Night renders use a blue-hour sky with every light a warm 1800–3000 K source.

## Design

### Living room
- **Sofa:** Geppetto Brisel corner sofa, 260×190, in Leo 8 bouclé. It sits in the window corner, as on the developer's
  plan, with a brutalist concrete drum coffee table.
- **TV wall:**
  - Samsung 85" QE85Q8FAAU at about 3.4 m from the seats (about a 31° viewing angle).
  - The oak slat / black felt panel is set off-centre. The bare plaster at the hall end carries three oak floating
    shelves.
  - A 3.73 m fluted-oak console stands on the floor.
  - At night an LED bias light behind the TV and a strip under the console give the glow.
- **Curtains:** sheer oat-linen curtains on a ceiling track. They stack open beside the slider so the west light stays.
- **Dining:** Ø90 oak table on a concrete pedestal with a paper pendant. A Rothko-style colour field hangs on the
  concrete wall, and an Akari-style paper floor lamp stands by the sofa.

### Kitchen
Oak fronts with concrete worktops and hood chimney. The tall fridge/oven column and the wall cupboards run up to the
ceiling, with LEDs under the cupboards.

### Bedroom + office
- **Bed:** [Rroots Kyoto King Size](https://rroots.rs/krevet-kyoto-kingsize) 160×200 in natural oak, modelled from the
  maker's AR model.
  - The head is on the solid south wall.
  - There are no nightstands: a hidden shelf behind the headboard and two wall lanterns replace them.
- **Wardrobe:** floor-to-ceiling, 230×60, with fluted-glass sliding doors in the niche by the door.
- **Office:** beside the bed at the window. The window is to the side of the screen, so there is no glare on the
  glossy panel.

  | Item    | Product |
  |---------|---------|
  | Desk    | [IKEA MITTZON](https://www.ikea.com/rs/sr/p/mittzon-radni-sto-orahov-furnir-bela-s89526103/) 120×80, walnut veneer / white |
  | Chair   | Herman Miller Mirra 2 |
  | Monitor | [ASUS ROG Swift OLED PG34WCDN](https://gigatron.rs/proizvod/asus-34-pg34wcdn-uwqhd-4711387532393), 34" ultrawide with a monitor light bar |

  The ASUS has an RGB-stripe QD-OLED panel, so macOS text stays sharp. Its USB-C input (DisplayPort alt mode plus a USB
  hub) means one cable to the Mac mini.
- **Office wall:** the oak slat panel is split around a black brick bay with a preserved-moss panel and warm LED seams.
  The bricks wrap onto the window pier, which has three oak shelves.

### Key dimensions
| Item                 | Size |
|----------------------|------|
| Ceiling              | 2.85 m |
| Living room          | 4.0 × 5.9 m |
| Bedroom              | 3.3 × 3.8 m |
| Terrace              | 3.8 × 1.4 m |
| Bedroom wall (3.8 m) | wardrobe 60 cm + walkway 29.5 cm + Kyoto bed 168.5 cm + gap 2 cm + desk 120 cm |

### Assumptions / open questions
- **Ceiling height:** 2.85 m is assumed from sales listings. Confirm it on site.
- **Wardrobe walkway:** 29.5 cm is tight. A Kyoto 140 would give 49.5 cm.
- **Radiators:** positions come from the developer's floor plan.

## Rendering

Needs Blender 5.x. Tested with Blender 5.2 on an M4 Pro, using Metal.

```sh
B=/Applications/Blender.app/Contents/MacOS/Blender
$B -b --factory-startup -P apartment.py                 # isometric cutaway (also saves apartment.blend)
$B -b --factory-startup -P apartment.py -- --top        # plan view
$B -b --factory-startup -P apartment.py -- --views      # 6 eye-level shots
$B -b --factory-startup -P apartment.py -- --night      # add to any of the above for the night variant
```

| Flag        | Effect |
|-------------|--------|
| *(none)*    | Isometric cutaway, 2400×2000. Walls are cut at 0.9 m so the furniture reads. |
| `--top`     | Plan view, oriented like the floor plan. |
| `--views`   | Eye-level perspective shots, 2400×1600, with full-height walls and a ceiling. |
| `--night`   | Blue hour, warm lamps and LEDs on. Writes `*_night.png`. |
| `--preview` | 1200 px at 48 samples, written as `renders/preview_*`. All views take about 40 s. |
| `--walk`    | Eye-level walkthrough frames plus an MP4, made with Blender's bundled FFmpeg. Takes about 4 h at 1080p. |

Finals use 384 samples with denoising. Each variant (isometric + plan + views) takes about 20 min.

The script works in metres. Its coordinates follow the floor plan:
- X points north (right on the plan).
- Y points west, toward the windows (up on the plan).
- Z points up.

## Layout
```
apartment.py   the whole scene: helpers, materials, furniture, lights, cameras, render
renders/       final images, day + night
```
