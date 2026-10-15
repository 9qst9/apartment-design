"""56 m2 west-facing one-bedroom apartment - Japandi x brutalism isometric cutaway.

Run:  blender -b -P apartment.py            (final, 2400x2000)
      blender -b -P apartment.py -- --preview
      blender -b -P apartment.py -- --top      (plan view, oriented like the floor plan)
      blender -b -P apartment.py -- --views    (eye-level: TV wall, living length, bedroom, office, dining, entrance)
      blender -b -P apartment.py -- --walk     (eye-level walkthrough -> walk/ frames -> walkthrough.mp4)
      add --night to any of these: blue hour, warm lamps + LEDs on, writes *_night.png
      add --bed=140 for a Kyoto 140 x 200 instead of the 160 (writes *_bed140.png); --only=bedroom renders a subset
Images go to renders/ (preview_* with --preview); the default run also saves apartment.blend.
Coords in metres from the floor plan: X = north (plan right), Y = west (plan up,
windows), Z = up. Far walls (west facade + north wall) are full height, the rest
are cut at C so the furniture reads, Sims-style.
"""
import bpy, bmesh, math, os, random, sys
from mathutils import Vector, noise

PREVIEW = "--preview" in sys.argv
TOP = "--top" in sys.argv
WALK = "--walk" in sys.argv
VIEWS = "--views" in sys.argv or WALK  # full-height walls + ceiling
NIGHT = "--night" in sys.argv
OPT = dict(a[2:].split("=", 1) for a in sys.argv if a.startswith("--") and "=" in a)   # --bed=140, --only=bedroom
BED = int(OPT.get("bed", 160))  # Kyoto mattress width, cm
SUF = (f"_bed{BED}" if BED != 160 else "") + ("_night" if NIGHT else "")   # output name suffix
OUT = os.path.dirname(os.path.abspath(__file__))
REN = os.path.join(OUT, "renders")
os.makedirs(REN, exist_ok=True)
H = 2.85  # from the sales listings; the photos agree (2.7 read too low)
C = H if VIEWS else 0.9  # cutaway height; eye-level views keep walls whole
rnd = random.Random(7)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
PARENT = None


# ---------- helpers ----------
def obj(me, mat, loc, rot=(0, 0, 0), bevel=0.0, smooth=False):
    o = bpy.data.objects.new(mat.name, me)
    scene.collection.objects.link(o)
    o.location, o.rotation_euler, o.parent = loc, rot, PARENT
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = smooth
    if bevel:
        m = o.modifiers.new("bevel", "BEVEL")
        m.width, m.segments = bevel, 3
    return o


def B(x0, x1, y0, y1, z0, z1, mat, bevel=0.0, smooth=False, rot=(0, 0, 0)):
    sx, sy, sz = (x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2
    me = bpy.data.meshes.new("box")
    me.from_pydata([(x, y, z) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)], [],
                   [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    return obj(me, mat, (x0 + sx, y0 + sy, z0 + sz), rot, bevel, smooth)


def CYL(x, y, z0, z1, r, mat, r2=None, seg=40):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r,
                          radius2=r if r2 is None else r2, depth=z1 - z0)
    me = bpy.data.meshes.new("cyl")
    bm.to_mesh(me)
    bm.free()
    o = obj(me, mat, (x, y, (z0 + z1) / 2))
    for p in me.polygons:
        p.use_smooth = abs(p.normal.z) < 0.5
    return o


def SPH(x, y, z, r, mat, sz=1.0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=r)
    me = bpy.data.meshes.new("sph")
    bm.to_mesh(me)
    bm.free()
    o = obj(me, mat, (x, y, z), smooth=True)
    o.scale.z = sz
    return o


def group(x, y, rz=0.0):
    """Following parts use local coords around (x, y), rotated by rz. Nestable."""
    global PARENT
    e = bpy.data.objects.new("group", None)
    scene.collection.objects.link(e)
    e.location, e.rotation_euler.z, e.parent = (x, y, 0), rz, PARENT
    PARENT = e


def ungroup():
    global PARENT
    PARENT = PARENT.parent


def M(name, col, rough=0.6, ins=None, noise=None):
    """Principled material; noise = (colour2, mapping scale, bump strength)."""
    m = bpy.data.materials.new(name)
    N, L = m.node_tree.nodes, m.node_tree.links
    b = N["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*col, 1)
    b.inputs["Roughness"].default_value = rough
    for k, v in (ins or {}).items():
        b.inputs[k].default_value = v
    if noise:
        col2, scale, bump = noise
        tc, mp, nz, cr = (N.new(t) for t in ("ShaderNodeTexCoord", "ShaderNodeMapping",
                                             "ShaderNodeTexNoise", "ShaderNodeValToRGB"))
        mp.inputs["Scale"].default_value = scale
        nz.inputs["Detail"].default_value = 8
        L.new(tc.outputs["Object"], mp.inputs["Vector"])
        L.new(mp.outputs["Vector"], nz.inputs["Vector"])
        L.new(nz.outputs["Fac"], cr.inputs["Fac"])
        e0, e1 = cr.color_ramp.elements
        e0.position, e1.position, e0.color, e1.color = 0.3, 0.7, (*col, 1), (*col2, 1)
        L.new(cr.outputs["Color"], b.inputs["Base Color"])
        if bump:
            bp = N.new("ShaderNodeBump")
            bp.inputs["Strength"].default_value = bump
            L.new(nz.outputs["Fac"], bp.inputs["Height"])
            L.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def flutes(m, axis, period, depth):
    """Vertical reeding via a wave-texture bump (fluted glass, fluted oak)."""
    N, L = m.node_tree.nodes, m.node_tree.links
    tc, wv, bp = N.new("ShaderNodeTexCoord"), N.new("ShaderNodeTexWave"), N.new("ShaderNodeBump")
    wv.wave_type, wv.bands_direction = "BANDS", axis
    wv.inputs["Scale"].default_value = 0.314 / period
    bp.inputs["Distance"].default_value = depth
    L.new(tc.outputs["Object"], wv.inputs["Vector"])
    L.new(wv.outputs["Fac"], bp.inputs["Height"])
    L.new(bp.outputs["Normal"], N["Principled BSDF"].inputs["Normal"])
    return m


caps = []  # section caps on cut built-ins (hidden in --top, where they read as walls)


def Bc(x0, x1, y0, y1, z0, z1, mat, bevel=0.0):
    """Tall built-in part: clipped at the cutaway height, dark section cap where cut."""
    if z0 >= C:
        return
    if z1 > C:
        z1 = C
        caps.append(B(x0, x1, y0, y1, C, C + 0.004, dark))
    B(x0, x1, y0, y1, z0, z1, mat, bevel)


def light(loc, kind, watts, k, radius=0.0, aim=None, cone=60):
    """Night lamp: POINT/SPOT at loc (spots aimed at aim), blackbody colour at k kelvin, unseen by the camera."""
    ld = bpy.data.lights.new(kind.lower(), kind)
    ld.energy, ld.use_temperature, ld.temperature, ld.shadow_soft_size = watts, True, k, radius
    if kind == "SPOT":
        ld.spot_size, ld.spot_blend = math.radians(cone), 0.7
    o = bpy.data.objects.new(ld.name, ld)
    scene.collection.objects.link(o)
    o.location, o.parent, o.visible_camera = loc, PARENT, False
    if aim:
        o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    if kind == "SPOT" and VIEWS and loc[2] > H - 0.1:
        CYL(loc[0], loc[1], H - 0.003, H, 0.03, glow)              # recessed downlight's lens in the ceiling
    return o


def kelvin(m, k, strength):
    """Emission from a blackbody at k kelvin (night)."""
    N, L = m.node_tree.nodes, m.node_tree.links
    bb, b = N.new("ShaderNodeBlackbody"), N["Principled BSDF"]
    bb.inputs["Temperature"].default_value = k
    L.new(bb.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = strength
    return m


# ---------- materials ----------
plaster = M("lime_plaster", (0.87, 0.85, 0.81), 0.9)
concrete = M("concrete", (0.50, 0.49, 0.47), 0.85, noise=((0.66, 0.65, 0.62), (1, 1, 1), 0.06))
oak = M("oak", (0.60, 0.43, 0.27), 0.5, noise=((0.73, 0.56, 0.37), (40, 1.5, 1.5), 0))
linen = M("linen_oat", (0.78, 0.73, 0.64), 1.0, {"Sheen Weight": 0.4})
linen_w = M("linen_white", (0.93, 0.91, 0.86), 1.0, {"Sheen Weight": 0.4})
sheer = M("sheer_linen", (0.92, 0.89, 0.82), 0.9, {"Alpha": 0.55, "Sheen Weight": 0.3})
clay = M("clay", (0.60, 0.37, 0.25), 1.0)
sage = M("sage", (0.50, 0.55, 0.44), 1.0)
leo8 = M("boucle_leo8", (0.212, 0.262, 0.235), 1.0, {"Sheen Weight": 0.5},  # swatch avg sRGB 127,140,133
        noise=((0.29, 0.35, 0.32), (40, 40, 40), 0.25))
black = M("black_metal", (0.025, 0.025, 0.025), 0.35, {"Metallic": 0.5})
alu = M("aluminium", (0.78, 0.78, 0.80), 0.3, {"Metallic": 1.0})
screen = M("screen", (0.01, 0.012, 0.02), 0.5, {"Emission Strength": 1.2, "Specular IOR Level": 0.1})
N, L = screen.node_tree.nodes, screen.node_tree.links
tc, sep, comb, brk = (N.new(t) for t in ("ShaderNodeTexCoord", "ShaderNodeSeparateXYZ",
                                         "ShaderNodeCombineXYZ", "ShaderNodeTexBrick"))
L.new(tc.outputs["Object"], sep.inputs[0])
L.new(sep.outputs["Y"], comb.inputs["X"])
L.new(sep.outputs["Z"], comb.inputs["Y"])
L.new(comb.outputs[0], brk.inputs["Vector"])
for k, v in {"Scale": 1, "Brick Width": 0.05, "Row Height": 0.018, "Mortar Size": 0.011,
             "Color1": (0.4, 0.6, 1, 1), "Color2": (1, 0.65, 0.35, 1), "Mortar": (0.02, 0.025, 0.04, 1)}.items():
    brk.inputs[k].default_value = v  # ponytail: brick texture = fake code lines
L.new(brk.outputs["Color"], N["Principled BSDF"].inputs["Emission Color"])
glass = M("glass", (0.9, 0.95, 1.0), 0.02, {"Alpha": 0.08})
paper = M("paper_lantern", (0.97, 0.93, 0.85), 0.9, {"Emission Color": (1.0, 0.78, 0.5, 1), "Emission Strength": 3.0})
leaf = M("leaf", (0.12, 0.25, 0.09), 0.6, noise=((0.22, 0.36, 0.14), (3, 3, 3), 0))
olive = M("olive_leaf", (0.34, 0.40, 0.28), 0.8, noise=((0.48, 0.52, 0.40), (4, 4, 4), 0))
bark = M("bark", (0.22, 0.17, 0.12), 0.9)
terracotta = M("terracotta", (0.60, 0.35, 0.23), 0.8)
ceramic = M("ceramic", (0.92, 0.91, 0.88), 0.15)
wool = M("wool_rug", (0.82, 0.77, 0.68), 1.0, noise=((0.74, 0.68, 0.58), (8, 8, 8), 0))
jute = M("jute", (0.60, 0.49, 0.33), 1.0, noise=((0.50, 0.40, 0.26), (30, 30, 30), 0))
felt = M("felt", (0.10, 0.10, 0.10), 1.0)
fabric = M("chair_fabric", (0.28, 0.28, 0.29), 0.9)
micro = M("microcement", (0.70, 0.68, 0.64), 0.6, noise=((0.80, 0.78, 0.74), (1, 1, 1), 0))
tile = M("terrace_tile", (0.68, 0.68, 0.66), 0.7)
dark = M("dark", (0.035, 0.035, 0.035), 0.8)
white = M("white_appliance", (0.9, 0.9, 0.9), 0.3)
ground = M("ground", (0.80, 0.79, 0.76), 1.0)
cord = M("paper_cord", (0.78, 0.66, 0.46), 1.0)
books = [M(f"book{i}", c, 0.8) for i, c in enumerate(
    [(0.75, 0.70, 0.60), (0.30, 0.33, 0.30), (0.55, 0.35, 0.25), (0.85, 0.83, 0.78)])]
denim = M("denim", (0.16, 0.2, 0.3), 0.9)
tv_black = M("tv_black", (0.02, 0.02, 0.022), 0.45)
tv_screen = M("tv_screen", (0.004, 0.004, 0.005), 0.03, {"Specular IOR Level": 0.6})
led = M("led_strip", (1, 1, 1), 0.5, {"Emission Color": (1.0, 0.78, 0.5, 1), "Emission Strength": 12.0})
mirror = M("mirror", (0.9, 0.9, 0.9), 0.02, {"Metallic": 1.0})
fluted_glass = flutes(M("fluted_glass", (0.94, 0.96, 0.94), 0.04, {"Transmission Weight": 1.0}), "X", 0.02, 0.002)
oak_fluted = flutes(M("oak_fluted", (0.60, 0.43, 0.27), 0.5, noise=((0.73, 0.56, 0.37), (40, 1.5, 1.5), 0)),
                    "Y", 0.03, 0.004)
walnut = M("walnut_veneer", (0.20, 0.085, 0.035), 0.45, noise=((0.12, 0.045, 0.018), (40, 1.5, 1.5), 0))
graphite = M("graphite", (0.03, 0.032, 0.035), 0.45)
aireweave = M("mirra_seat", (0.045, 0.047, 0.05), 0.9)
triflex = M("triflex", (0.03, 0.032, 0.035), 0.4)  # perforated polymer back: brick-texture holes on UVs -> alpha
N, L = triflex.node_tree.nodes, triflex.node_tree.links
tc, brk = N.new("ShaderNodeTexCoord"), N.new("ShaderNodeTexBrick")
brk.inputs["Scale"].default_value, brk.inputs["Mortar Size"].default_value = 24, 0.12
L.new(tc.outputs["UV"], brk.inputs["Vector"])
L.new(brk.outputs["Fac"], N["Principled BSDF"].inputs["Alpha"])
# black-painted gypsum brick slips, 250 x 65 with 10 mm joints. Brick texture on (X + Y, Z) in world space, so one
# material runs along either wall; joints sunk by an inverted bump, faces roughened by noise.
brick = M("black_brick", (0.03, 0.03, 0.03), 0.9)
N, L = brick.node_tree.nodes, brick.node_tree.links
geo, sep, u, comb, bt, nz, h, bp = (N.new(t) for t in (
    "ShaderNodeNewGeometry", "ShaderNodeSeparateXYZ", "ShaderNodeMath", "ShaderNodeCombineXYZ",
    "ShaderNodeTexBrick", "ShaderNodeTexNoise", "ShaderNodeMath", "ShaderNodeBump"))
L.new(geo.outputs["Position"], sep.inputs[0])
L.new(sep.outputs["X"], u.inputs[0])
L.new(sep.outputs["Y"], u.inputs[1])
L.new(u.outputs[0], comb.inputs["X"])
L.new(sep.outputs["Z"], comb.inputs["Y"])
L.new(comb.outputs[0], bt.inputs["Vector"])
for k, v in {"Scale": 1, "Brick Width": 0.26, "Row Height": 0.075, "Mortar Size": 0.005, "Mortar Smooth": 0.2,
             "Color1": (0.036, 0.036, 0.038, 1), "Color2": (0.022, 0.022, 0.024, 1),
             "Mortar": (0.012, 0.012, 0.013, 1)}.items():
    bt.inputs[k].default_value = v
L.new(bt.outputs["Color"], N["Principled BSDF"].inputs["Base Color"])
nz.inputs["Scale"].default_value = 80
L.new(geo.outputs["Position"], nz.inputs["Vector"])
h.operation, h.inputs[1].default_value = "MULTIPLY_ADD", 0.3   # noise * 0.3 + mortar mask
L.new(nz.outputs["Fac"], h.inputs[0])
L.new(bt.outputs["Fac"], h.inputs[2])
bp.invert, bp.inputs["Distance"].default_value = True, 0.004
L.new(h.outputs[0], bp.inputs["Height"])
L.new(bp.outputs["Normal"], N["Principled BSDF"].inputs["Normal"])
moss = M("preserved_moss", (0.035, 0.12, 0.015), 1.0, {"Sheen Weight": 1.0, "Sheen Tint": (0.6, 0.8, 0.35, 1)},
         noise=((0.17, 0.38, 0.035), (90, 90, 90), 0.8))
N, L = moss.node_tree.nodes, moss.node_tree.links
cr = next(n for n in N if n.type == "VALTORGB")
vo, sc, ad, ao = (N.new(t) for t in ("ShaderNodeTexVoronoi", "ShaderNodeSeparateColor", "ShaderNodeMath",
                                     "ShaderNodeAmbientOcclusion"))
vo.feature, vo.inputs["Scale"].default_value = "SMOOTH_F1", 24   # each cushion its own shade, blended
L.new(next(n for n in N if n.type == "TEX_COORD").outputs["Object"], vo.inputs["Vector"])
L.new(vo.outputs["Color"], sc.inputs["Color"])
ad.operation, ad.inputs[1].default_value = "MULTIPLY_ADD", 0.5
L.new(sc.outputs["Red"], ad.inputs[0])
L.new(next(n for n in N if n.type == "TEX_NOISE").outputs["Fac"], ad.inputs[2])
L.new(ad.outputs[0], cr.inputs["Fac"])
cr.color_ramp.elements[0].position, cr.color_ramp.elements[1].position = 0.45, 1.05
ao.inputs["Distance"].default_value = 0.03                     # dark crevices between the cushions
L.new(cr.outputs["Color"], ao.inputs["Color"])
L.new(ao.outputs["Color"], N["Principled BSDF"].inputs["Base Color"])

# oak floor: planks along Y (as in the photos) with per-plank tone + grain
floor = M("oak_floor", (0.66, 0.46, 0.27), 0.42)
N, L = floor.node_tree.nodes, floor.node_tree.links
tc, mp, gm = N.new("ShaderNodeTexCoord"), N.new("ShaderNodeMapping"), N.new("ShaderNodeMapping")
mp.inputs["Rotation"].default_value = (0, 0, math.pi / 2)
gm.inputs["Scale"].default_value = (60, 1.5, 1)
nz, br = N.new("ShaderNodeTexNoise"), N.new("ShaderNodeTexBrick")
L.new(tc.outputs["Object"], mp.inputs["Vector"])
L.new(tc.outputs["Object"], gm.inputs["Vector"])
L.new(gm.outputs["Vector"], nz.inputs["Vector"])
L.new(mp.outputs["Vector"], br.inputs["Vector"])
br.offset = 0.37
for k, v in {"Scale": 1, "Brick Width": 1.6, "Row Height": 0.19, "Mortar Size": 0.0015,
             "Mortar": (0.3, 0.2, 0.12, 1)}.items():
    br.inputs[k].default_value = v
for sock, (a, c) in zip(("Color1", "Color2"), (((0.72, 0.52, 0.32), (0.60, 0.41, 0.24)),
                                               ((0.66, 0.47, 0.28), (0.56, 0.38, 0.22)))):
    r = N.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color, r.color_ramp.elements[1].color = (*a, 1), (*c, 1)
    L.new(nz.outputs["Fac"], r.inputs["Fac"])
    L.new(r.outputs["Color"], br.inputs[sock])
L.new(br.outputs["Color"], N["Principled BSDF"].inputs["Base Color"])
glow = M("warm_led", (1, 1, 1), 0.5)  # night-only fixtures: console wash, kitchen, TV bias light
wax = M("wax", (0.93, 0.90, 0.83), 0.45, {"Subsurface Weight": 0.4})
if NIGHT:  # every lamp a warm blackbody: 1800-2000 K bulbs in the paper lamps, 2400-2700 K LEDs, 3000 K art spots
    N, L = paper.node_tree.nodes, paper.node_tree.links           # washi lit from inside by its bulb: translucent
    b, tr, mx = N["Principled BSDF"], N.new("ShaderNodeBsdfTranslucent"), N.new("ShaderNodeMixShader")
    b.inputs["Emission Strength"].default_value = 0
    tr.inputs["Color"].default_value, mx.inputs["Fac"].default_value = (1.0, 0.58, 0.28, 1), 0.5
    L.new(b.outputs["BSDF"], mx.inputs[1])
    L.new(tr.outputs["BSDF"], mx.inputs[2])
    L.new(mx.outputs["Shader"], N["Material Output"].inputs["Surface"])
    kelvin(led, 2400, 5.0)
    kelvin(glow, 2700, 6.0)
    bias = kelvin(M("bias_led", (1, 1, 1), 0.5), 2200, 45.0)
    flame = kelvin(M("flame", (1, 1, 1), 0.5), 1800, 40.0)
    screen.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 0.6


# ---------- reusable pieces ----------
def plant(x, y, h, spread, zmin, pot_r=0.2, pot=concrete, leaves=leaf, trunk=False, n=9):
    pot_h = pot_r * 1.7
    CYL(x, y, 0, pot_h, pot_r, pot, r2=pot_r * 0.8)
    if trunk:
        CYL(x, y, pot_h, h - spread * 0.5, 0.025, bark, seg=10)
    for _ in range(n * 2):
        a, r = rnd.uniform(0, 6.283), spread * rnd.uniform(0.1, 0.95)
        SPH(x + r * math.cos(a), y + r * math.sin(a), rnd.uniform(zmin, h),
            spread * rnd.uniform(0.22, 0.38), leaves, 0.7)


def lantern(x, y, z, r, cord_to=None, sz=1.0, watts=0, k=2000):
    obs = [SPH(x, y, z, r, paper, sz)]
    obs[0].modifiers.new("smooth", "SUBSURF")                  # round silhouette when it glows
    if NIGHT and watts:  # bulb inside; the paper casts no shadow, so the bulb lights the room through it
        obs[0].visible_shadow = False
        obs.append(light((x, y, z), "POINT", watts, k, r * 0.5))
    if cord_to:
        obs.append(CYL(x, y, z + r * sz, cord_to, 0.004, black, seg=6))
    return obs


def radiator(x0, n, north=False, z0=0.15, h=2.0):
    """Vertical aluminium column radiator (80 mm columns) on the west wall, or the north wall (x0 runs along Y)."""
    for i in range(n):
        a, b = x0 + i * 0.08 + 0.006, x0 + i * 0.08 + 0.074
        B(*((7.34, 7.42, a, b) if north else (a, b, 7.69, 7.77)), z0, z0 + h, white, 0.01)
    e = x0 + n * 0.08 - 0.04                                     # valve tail into the floor, corner end
    CYL(*((7.38, e) if north else (e, 7.73)), 0, z0, 0.011, alu, seg=8)


def window(x0, x1, z0, z1, f, y=7.93):
    m = (x0 + x1) / 2
    for a in ((x0, x0 + f, z0, z1), (x1 - f, x1, z0, z1), (x0, x1, z0, z0 + f),
              (x0, x1, z1 - f, z1), (m - f / 2, m + f / 2, z0, z1)):
        B(a[0], a[1], y - 0.04, y + 0.04, a[2], a[3], black)
    B(x0, x1, y - 0.003, y + 0.003, z0, z1, glass)


def curtain(x0, x1, y, folds, amp=0.045):
    """Sheer wave-fold curtain along X at depth y, floor to the ceiling track."""
    bm, n = bmesh.new(), folds * 8
    vs = [[bm.verts.new((x0 + (x1 - x0) * i / n, y + amp * math.sin(2 * math.pi * i / 8), z)) for z in (0.01, H - 0.02)]
          for i in range(n + 1)]
    for i in range(n):
        bm.faces.new((vs[i][0], vs[i + 1][0], vs[i + 1][1], vs[i][1]))
    me = bpy.data.meshes.new("curtain")
    bm.to_mesh(me)
    bm.free()
    obj(me, sheer, (0, 0, 0), smooth=True)


def moss_panel(x, y0, y1, z0, z1):
    """Preserved ball-moss panel on a wall facing +X: voronoi cushions off a 7 mm grid, tapering into a dark board."""
    B(x, x + 0.012, y0, y1, z0, z1, dark)
    bm, s, vs = bmesh.new(), 0.007, []
    nu, nv = round((y1 - y0) / s), round((z1 - z0) / s)
    for i in range(nu + 1):
        vs.append([])
        for j in range(nv + 1):
            y, z = y0 + (y1 - y0) * i / nu, z0 + (z1 - z0) * j / nv
            p = Vector((y, z, 0.37)) * 24                                  # ~4 cm cushions, 1.5 cm balls on top
            dome = lambda q, r: math.sqrt(max(0.0, 1 - (noise.voronoi(q)[0][0] / r) ** 2))
            e = min(1.0, min(i, j, nu - i, nv - j) * s / 0.02) ** 0.5
            h = 0.026 * dome(p, 0.65) + 0.010 * dome(p * 2.6 + Vector((5, 0, 0)), 0.6) + 0.003 * noise.noise(p * 3)
            vs[i].append(bm.verts.new((x + 0.012 + max(h, 0.002) * e, y, z)))
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    me = bpy.data.meshes.new("moss")
    bm.to_mesh(me)
    bm.free()
    obj(me, moss, (0, 0, 0), smooth=True)


def dining_chair(x, y, rz):  # wishbone-style: oak frame, paper-cord seat; faces local +X
    group(x, y, rz)
    for lx in (-0.19, 0.19):
        for ly in (-0.19, 0.19):
            B(lx - 0.016, lx + 0.016, ly - 0.016, ly + 0.016, 0, 0.72 if lx < 0 else 0.43, oak)
    B(-0.21, 0.21, -0.21, 0.21, 0.43, 0.47, cord, 0.01)
    B(-0.23, -0.17, -0.25, 0.25, 0.66, 0.72, oak, 0.02, True)
    ungroup()


def lounge_chair(x, y, rz):  # slab-sided oak lounge chair; faces local +X
    group(x, y, rz)
    for s in (-1, 1):
        B(-0.36, 0.36, s * 0.34 - 0.03, s * 0.34 + 0.03, 0, 0.55, oak, 0.01)
    B(-0.33, 0.33, -0.31, 0.31, 0.12, 0.2, oak, 0.005)
    B(-0.28, 0.33, -0.31, 0.31, 0.2, 0.36, linen_w, 0.04, True)
    B(-0.36, -0.2, -0.31, 0.31, 0.25, 0.8, linen_w, 0.05, True, (0, -0.2, 0))
    B(-0.05, 0.25, -0.15, 0.15, 0.36, 0.42, clay, 0.02, True)
    ungroup()


def mirra2(x, y, rz):  # Herman Miller Mirra 2, graphite, TriFlex back; faces local +X
    group(x, y, rz)
    for k in range(5):                                             # 5-star base on casters
        t = k * 2 * math.pi / 5 + math.pi
        cx, cy = 0.16 * math.cos(t), 0.16 * math.sin(t)
        B(cx - 0.16, cx + 0.16, cy - 0.022, cy + 0.022, 0.06, 0.095, graphite, 0.01, rot=(0, 0, t))
        SPH(0.31 * math.cos(t), 0.31 * math.sin(t), 0.03, 0.03, graphite)
    CYL(0, 0, 0.05, 0.11, 0.05, graphite)
    CYL(0, 0, 0.11, 0.37, 0.022, graphite, seg=16)                 # gas cylinder
    B(-0.13, 0.12, -0.12, 0.12, 0.36, 0.43, graphite, 0.02)        # tilt mechanism
    B(-0.2, 0.25, -0.245, 0.245, 0.43, 0.49, aireweave, 0.03, True)   # seat with FlexFront edge
    B(-0.33, -0.1, -0.03, 0.03, 0.37, 0.42, graphite, 0.012)       # spine: back under the seat...
    B(-0.36, -0.31, -0.035, 0.035, 0.4, 0.8, graphite, 0.015, rot=(0, -0.22, 0))   # ...and up behind the back
    for s in (-1, 1):                                              # height-adjustable T-arms
        B(-0.05, 0.03, s * 0.25 - 0.02, s * 0.25 + 0.02, 0.4, 0.45, graphite)
        B(-0.04, 0.0, s * 0.27 - 0.018, s * 0.27 + 0.018, 0.42, 0.66, graphite, 0.01)
        B(-0.14, 0.12, s * 0.275 - 0.045, s * 0.275 + 0.045, 0.66, 0.69, graphite, 0.015, True)
    bm, nu, nv, g, uvs = bmesh.new(), 16, 12, {}, {}               # curved TriFlex back, solid rim
    for i in range(nu + 1):
        for j in range(nv + 1):
            u, v = i / nu * 2 - 1, j / nv
            hw = 0.205 + 0.03 * v + 0.012 * math.sin(math.pi * v)  # butterfly outline, wider at the shoulders
            bx = -0.27 - 0.12 * v + 0.05 * u * u + 0.022 * math.sin(math.pi * min(v / 0.6, 1))   # recline, wrap, lumbar
            g[i, j] = bm.verts.new((bx, hw * u, 0.56 + 0.46 * v))
            uvs[g[i, j]] = (u * 0.25, v * 0.46)
    for i in range(nu):
        for j in range(nv):
            f = bm.faces.new((g[i, j], g[i + 1, j], g[i + 1, j + 1], g[i, j + 1]))
            f.material_index = int(i in (0, nu - 1) or j in (0, nv - 1))
    uvl = bm.loops.layers.uv.new()
    for f in bm.faces:
        for lp in f.loops:
            lp[uvl].uv = uvs[lp.vert]
    me = bpy.data.meshes.new("triflex")
    bm.to_mesh(me)
    bm.free()
    obj(me, triflex, (0, 0, 0), smooth=True).modifiers.new("solid", "SOLIDIFY").thickness = 0.012
    me.materials.append(graphite)
    ungroup()


def ultrawide(x, y, rz):  # ASUS ROG Swift OLED PG34WCDN: 34" 21:9, 1800R, 81.3 x 37.3 cm, tripod stand; faces local -X
    group(x, y, rz)
    for w, z0, z1, dx, mat in ((0.8128, 0.865, 1.238, 0.0, graphite), (0.797, 0.887, 1.23, -0.001, screen)):
        bm, n, vs = bmesh.new(), 24, []
        for i in range(n + 1):                                     # arc on R 1.8 m: the ends come 4.6 cm toward you
            a = (i / n - 0.5) * w / 1.8
            vs.append([bm.verts.new((1.8 * math.cos(a) - 1.8 + dx, 1.8 * math.sin(a), z)) for z in (z0, z1)])
        for i in range(n):
            bm.faces.new((vs[i][0], vs[i + 1][0], vs[i + 1][1], vs[i][1]))
        me = bpy.data.meshes.new("ultrawide")
        bm.to_mesh(me)
        bm.free()
        o = obj(me, mat, (0, 0, 0), smooth=True)
        if mat is graphite:                                        # 9 mm panel, grown backwards (normals face +X)
            sm = o.modifiers.new("solid", "SOLIDIFY")
            sm.thickness, sm.offset = 0.009, 1
    B(0.0, 0.05, -0.2, 0.2, 0.92, 1.17, graphite, 0.02)            # rear electronics housing
    B(0.045, 0.095, -0.035, 0.035, 0.765, 1.07, graphite, 0.01)    # height-adjustable neck
    B(0.03, 0.11, -0.045, 0.045, 0.75, 0.785, graphite, 0.01)      # hub
    for ex, ey in ((-0.12, 0.27), (-0.12, -0.27), (0.15, 0.0)):    # tripod feet, 27.6 cm deep overall
        dx, L = ex - 0.07, math.hypot(ex - 0.07, ey)
        B(0.07 + dx / 2 - L / 2, 0.07 + dx / 2 + L / 2, ey / 2 - 0.012, ey / 2 + 0.012, 0.75, 0.768, graphite, 0.005,
          rot=(0, 0, math.atan2(ey, dx)))
    ungroup()


# ---------- shell ----------
poly = [(0, 1.27), (1.84, 1.27), (1.84, 0), (7.44, 0), (7.44, 7.8), (0, 7.8)]
me = bpy.data.meshes.new("floor")
me.from_pydata([(x, y, 0.002) for x, y in poly], [], [list(range(len(poly)))])
obj(me, floor, (0, 0, 0))
B(-40, 40, -40, 40, -0.32, -0.3, ground)
for a in ((-0.3, 7.74, 0.9, 8.15), (1.84, 7.74, -0.3, 0.9)):
    B(*a, -0.3, 0, concrete)

walls = [
    # west facade - full height, bedroom window + terrace slider
    (-0.3, 0.83, 7.8, 8.15, 0, H), (0.83, 2.57, 7.8, 8.15, 0, 0.37), (0.83, 2.57, 7.8, 8.15, 2.48, H),
    (2.57, 4.03, 7.8, 8.15, 0, H), (4.03, 6.82, 7.8, 8.15, 2.55, H), (6.82, 7.44, 7.8, 8.15, 0, H),
    # cut walls
    (-0.3, 0, 0.9, 7.8, 0, C),                                   # south facade
    (3.1, 3.2, -0.3, 0, 0, C), (4.2, 7.44, -0.3, 0, 0, C),       # east facade + entrance door
    (1.84, 3.1, -0.3, 0.9, 0, C), (-0.3, 1.84, 0.9, 1.27, 0, C),
    (3.3, 3.45, 3.85, 7.8, 0, C),                                # bedroom | living
    (0, 2.35, 3.85, 4.0, 0, C), (3.2, 3.3, 3.85, 4.0, 0, C),     # bedroom door
    (1.69, 1.84, 1.27, 3.05, 0, C),                              # bathroom door above
    (1.84, 3.1, 2.8, 2.95, 0, C), (2.95, 3.1, 0.85, 1.0, 0, C), (2.95, 3.1, 2.6, 2.95, 0, C),
]
for w in walls:
    B(*w, plaster)
    if w[5] == C < H:
        B(*w[:4], C, C + 0.004, dark)  # section poche
B(7.44, 7.74, -0.3, 8.15, 0, H, concrete)  # north wall: brutalist concrete feature wall
if VIEWS:
    B(-0.3, 7.74, -0.3, 8.15, H, H + 0.25, plaster)  # ceiling + closed front door, eye-level views only
    B(3.2, 4.2, -0.3, -0.25, 2.1, H, plaster)
    B(3.2, 4.2, -0.25, -0.2, 0, 2.1, dark)

window(0.83, 2.57, 0.37, 2.48, 0.06)   # sill/head heights read off the bedroom photo
window(4.03, 6.82, 0.0, 2.55, 0.08)    # slider head read off the living-room photo
radiator(2.66, 7)               # bedroom: pier between the partition and the window (developer plan)
radiator(7.14, 7, north=True)   # living: concrete north wall, in the window corner (developer plan)

# terrace 3.8 x 1.4
B(3.62, 7.74, 8.15, 9.5, -0.3, -0.02, tile)
B(3.62, 7.74, 9.44, 9.46, -0.02, 1.05, glass)
B(7.72, 7.74, 8.15, 9.44, -0.02, 1.05, glass)
B(3.62, 7.74, 9.42, 9.5, -0.02, 0.05, black)
B(5.9, 7.6, 9.05, 9.38, -0.02, 0.42, concrete, 0.01)
for i in range(8):
    SPH(6.0 + i * 0.2, 9.2, 0.62, 0.17, olive, 1.5)
lounge_chair(4.6, 8.8, -0.4)
plant(6.35, 8.6, 1.5, 0.32, 0.9, pot_r=0.22, leaves=olive, trunk=True, n=22)   # olive tree behind the fixed glass

# ---------- living: lounge ----------
LS = 1.24  # sofa in the window corner as on the developer plan: chaise end 41 cm from the glass
group(-0.14, LS)  # everything up to ungroup() is offset; 14 cm off the north wall so the radiator behind the chaise breathes
B(4.85, 7.0, 3.8, 5.95, 0, 0.012, wool)
# Geppetto Brisel corner sofa 260 x 190, Leo 8 boucle, natural feet (dims from the maker's drawing).
# Back toward the north wall, chaise on the window side.
SX, SY = 7.42, 3.55  # back outer face, east end; depth runs -X, length +Y


def S(d0, d1, l0, l1, z0, z1, mat=leo8, bevel=0.035):
    B(SX - d1 / 100, SX - d0 / 100, SY + l0 / 100, SY + l1 / 100, z0, z1, mat, bevel, True)


S(0, 23, 0, 260, 0.04, 0.78)                                  # back
for l0, l1 in ((29, 92), (95, 158), (163, 230)):
    S(1, 21, l0, l1, 0.78, 0.9, bevel=0.04)                   # headrests
S(0, 103, 0, 27, 0.04, 0.62)                                  # arm, kitchen end
S(23, 103, 27, 160, 0.04, 0.3, bevel=0.02)                    # seat base
S(23, 104, 27, 93.5, 0.3, 0.47, bevel=0.05)                   # seat cushions
S(23, 104, 93.5, 160, 0.3, 0.47, bevel=0.05)
S(23, 190, 160, 260, 0.04, 0.3, bevel=0.02)                   # chaise base
S(23, 191, 160, 260, 0.3, 0.47, bevel=0.05)                   # chaise cushion
S(0, 96, 233, 260, 0.04, 0.62)                                # chaise arm (stops short, as on the Brisel)
for d, l in ((8, 4), (95, 4), (8, 252), (88, 252), (182, 165), (182, 252)):
    S(d - 4, d + 4, l - 3, l + 3, 0, 0.04, oak, 0.003)        # natural wood feet
B(6.98, 7.16, 3.9, 4.35, 0.47, 0.87, clay, 0.07, True, (0, 0.25, 0.2))
B(6.98, 7.16, 4.68, 5.1, 0.47, 0.85, linen_w, 0.07, True, (0, 0.25, -0.2))
B(5.62, 5.98, 5.17, 6.12, 0.47, 0.5, linen, 0.01, True)       # folded throw on the chaise
CYL(5.69, 4.62, 0, 0.32, 0.35, concrete)                       # brutalist drum coffee table
B(5.47, 5.75, 4.42, 4.65, 0.32, 0.36, books[0], rot=(0, 0, 0.2))
B(5.49, 5.73, 4.44, 4.63, 0.36, 0.39, books[2], rot=(0, 0, 0.3))
CYL(5.84, 4.82, 0.32, 0.55, 0.06, ceramic, r2=0.035)
for x, y, h, r in ((5.53, 4.80, 0.10, 0.035), (5.61, 4.86, 0.15, 0.035), (5.53, 4.88, 0.07, 0.03)):
    CYL(x, y, 0.32, 0.32 + h, r, wax)                          # pillar candles
    CYL(x, y, 0.32 + h, 0.33 + h, 0.0015, black, seg=6)
    if NIGHT:
        SPH(x, y, 0.345 + h, 0.006, flame, 2.2).visible_shadow = False
        light((x, y, 0.345 + h), "POINT", 0.6, 1800, 0.005)
ungroup()
# TV wall: the oak slat / felt panel set off-centre, from the curtain past the TV to 67 cm beyond its left edge, so the
# hall end keeps 90 cm of bare plaster for open shelves. Console and TV stand on the slats' face (X 3.47).
Bc(3.45, 3.46, 4.72, 7.64, 0, H, felt)
for i in range(73):
    y = 4.73 + i * 0.04
    Bc(3.46, 3.47, y, y + 0.026, 0, H, oak)
# fluted-oak console standing on the floor, 3.73 m (stops 22 cm short of the glass so the curtain falls clear),
# TV wall-mounted, centred on the seats
CT = 0.34                                                      # console top
B(3.49, 3.86, 3.87, 7.56, 0, 0.03, dark)                       # recessed plinth
B(3.47, 3.88, 3.85, 7.58, 0.03, CT, oak, 0.004)
for i in range(4):
    y0 = 3.85 + i * 0.9325
    B(3.88, 3.90, y0 + 0.002, y0 + 0.9305, 0.035, CT - 0.005, oak_fluted, 0.002)   # push-open doors
TY = 5.1 + LS  # centred on the sofa's seat/chaise seam
B(3.47, 3.495, TY - 0.33, TY + 0.33, 0.92, 1.37, black)          # VESA 600x400 bracket
B(3.495, 3.522, TY - 0.9505, TY + 0.9505, 0.6, 1.686, tv_black, 0.004)   # Samsung QE85Q8FAAU 190.1x108.6x2.7
B(3.522, 3.5225, TY - 0.945, TY + 0.945, 0.606, 1.68, tv_screen)
# decoration grouped left of the TV (as seen from the sofa): turntable, books, vase, Akari-style lamp
B(3.54, 3.84, 4.86, 5.28, CT, CT + 0.07, oak, 0.005)            # turntable
CYL(3.69, 5.07, CT + 0.07, CT + 0.076, 0.15, dark)
for i, mat in enumerate((books[1], books[3], books[0])):
    B(3.57, 3.84, 4.50, 4.73, CT + i * 0.03, CT + 0.03 + i * 0.03, mat)
CYL(3.68, 4.32, CT, CT + 0.32, 0.07, ceramic, r2=0.045)        # vase
CYL(3.68, 4.10, CT, CT + 0.01, 0.06, black)                    # Akari-style table lamp
CYL(3.68, 4.10, CT + 0.01, CT + 0.16, 0.006, black, seg=6)
lantern(3.68, 4.10, CT + 0.32, 0.12, sz=1.4, watts=15, k=1800)
if NIGHT:
    if VIEWS:  # bias-light strip round the back of the TV, 2 cm in from its edges: a warm halo on the slats
        for a in ((TY - 0.93, TY + 0.93, 1.656, 1.666), (TY - 0.93, TY + 0.93, 0.62, 0.63),
                  (TY - 0.935, TY - 0.925, 0.63, 1.656), (TY + 0.925, TY + 0.935, 0.63, 1.656)):
            B(3.478, 3.494, *a, bias).visible_camera = False
    B(3.861, 3.877, 3.87, 7.56, 0.026, 0.03, glow).visible_camera = False   # strip under the console, washing the floor
if VIEWS:  # three oak shelves on the bare end, top one level with the TV's top edge (wall is cut away in iso)
    for z in (1.0, 1.33, 1.656):
        B(3.45, 3.67, 3.96, 4.62, z, z + 0.03, oak, 0.003)
    for i, (mat, bh) in enumerate(zip((books[3], books[1], books[0], books[2]), (0.24, 0.21, 0.23, 0.19))):
        B(3.48, 3.64, 4.01 + i * 0.034, 4.04 + i * 0.034, 1.03, 1.03 + bh, mat)      # books on end
    CYL(3.56, 4.44, 1.03, 1.09, 0.075, ceramic, r2=0.085)                         # bowl
    CYL(3.56, 4.13, 1.36, 1.58, 0.05, clay, r2=0.03)                              # bud vase
    group(3.56, 4.45)
    PARENT.location.z = 1.36
    plant(0, 0, 0.22, 0.1, 0.1, pot_r=0.055, pot=ceramic, n=6)
    ungroup()
    for i, mat in enumerate((books[0], books[3])):
        B(3.48, 3.65, 4.06, 4.32, 1.686 + i * 0.035, 1.721 + i * 0.035, mat)     # stacked books
    SPH(3.56, 4.47, 1.746, 0.06, concrete)                                        # concrete sphere
# sheer oat-linen curtains on a ceiling track, stacked open beside the slider so the light stays
curtain(3.48, 4.12, 7.72, 8)
curtain(6.72, 7.30, 7.72, 7)                                   # stops short of the corner radiator
if VIEWS:
    B(3.47, 7.32, 7.70, 7.74, H - 0.02, H, white)               # ceiling track
B(7.35, 7.40, 4.31 + LS, 5.51 + LS, 1.15, 1.95, linen_w, 0.005)  # ink "enso" print over sofa
bpy.ops.mesh.primitive_torus_add(major_radius=0.26, minor_radius=0.018, location=(7.345, 4.91 + LS, 1.55),
                                 rotation=(0, math.pi / 2, 0))
bpy.context.active_object.data.materials.append(dark)
# Akari-style paper floor lamp at the sofa's kitchen end, against the concrete: the reading light on the sofa
# (shade 19 cm off the arm, 14 off the wall, 47 cm clear of the painting's frame).
CYL(7.12, 4.42, 0, 0.012, 0.13, black)
CYL(7.12, 4.42, 0.012, 0.98, 0.006, black, seg=8)
lantern(7.12, 4.42, 1.22, 0.18, sz=1.4, watts=30)

# ---------- dining ----------
# Ø90 table 13 cm from the developer plan's spot (5.73, 3.28): 89 cm to the entrance unit, 77 cm past
# the fridge, 95 cm to the sofa, 1.5 m to the coffee table, 1.17 m to the TV-wall console corner.
DX, DY, ROT = 5.6, 3.3, 30
CYL(DX, DY, 0, 0.7, 0.16, concrete)                            # concrete pedestal
CYL(DX, DY, 0.71, 0.745, 0.45, oak)
for k in range(4):  # tucked in at r = 0.45, layout turned ROT degrees (CCW in plan)
    t = math.radians(ROT + 90 * k)
    dining_chair(DX + 0.45 * math.cos(t), DY + 0.45 * math.sin(t), t + math.pi)
CYL(DX, DY, 0.745, 0.76, 0.18, ceramic, r2=0.12)               # fruit bowl
pendant = lantern(DX, DY, 1.78, 0.3, cord_to=H, sz=0.9, watts=25)
# Rothko-style colour field on the concrete wall, centred on the table: rust over ochre on umber, 90 x 120 canvas in
# an oak floater frame. Anchors the dining zone (the TV wall already has its focal point) and greets you from the hall.
art = M("colour_field", (0.075, 0.045, 0.032), 0.9)
N, L = art.node_tree.nodes, art.node_tree.links
tc, sep, nz = N.new("ShaderNodeTexCoord"), N.new("ShaderNodeSeparateXYZ"), N.new("ShaderNodeTexNoise")
nz.inputs["Scale"].default_value, nz.inputs["Detail"].default_value = 6, 8
L.new(tc.outputs["Generated"], sep.inputs[0])
L.new(tc.outputs["Generated"], nz.inputs["Vector"])
UMB, OCH, RUST = (0.075, 0.045, 0.032), (0.52, 0.33, 0.11), (0.38, 0.105, 0.05)


def bands(axis, stops):  # soft-edged bands along one canvas axis, edges wobbled by the noise
    w, r = N.new("ShaderNodeMath"), N.new("ShaderNodeValToRGB")
    w.operation, w.inputs[1].default_value = "MULTIPLY_ADD", 0.035
    L.new(nz.outputs["Fac"], w.inputs[0])
    L.new(sep.outputs[axis], w.inputs[2])
    L.new(w.outputs[0], r.inputs["Fac"])
    for i, (pos, c) in enumerate(stops):
        el = r.color_ramp.elements[i] if i < 2 else r.color_ramp.elements.new(pos)
        el.position, el.color = pos, (*c, 1)
    return r


v = bands("Z", [(0, UMB), (0.06, UMB), (0.085, OCH), (0.35, OCH), (0.38, UMB), (0.42, UMB), (0.45, RUST), (0.91, RUST),
                (0.94, UMB), (1, UMB)])
u = bands("Y", [(0, (0, 0, 0)), (0.06, (0, 0, 0)), (0.09, (1, 1, 1)), (0.91, (1, 1, 1)), (0.94, (0, 0, 0)), (1, (0, 0, 0))])
mx = N.new("ShaderNodeMix")
mx.data_type = "RGBA"
ins = {sk.identifier: sk for sk in mx.inputs}
ins["A_Color"].default_value = (*UMB, 1)
L.new(u.outputs["Color"], ins["Factor_Float"])
L.new(v.outputs["Color"], ins["B_Color"])
L.new(next(o for o in mx.outputs if o.identifier == "Result_Color"), N["Principled BSDF"].inputs["Base Color"])
cv, bp = N.new("ShaderNodeTexNoise"), N.new("ShaderNodeBump")                # canvas tooth
cv.inputs["Scale"].default_value, bp.inputs["Strength"].default_value = 260, 0.12
L.new(tc.outputs["Generated"], cv.inputs["Vector"])
L.new(cv.outputs["Fac"], bp.inputs["Height"])
L.new(bp.outputs["Normal"], N["Principled BSDF"].inputs["Normal"])
PX = 7.44                                                      # concrete wall face
B(PX - 0.02, PX, DY - 0.462, DY + 0.462, 0.938, 2.162, dark)   # shadow-gap backer
for a in ((DY - 0.472, DY - 0.462, 0.928, 2.172), (DY + 0.462, DY + 0.472, 0.928, 2.172),
          (DY - 0.462, DY + 0.462, 0.928, 0.938), (DY - 0.462, DY + 0.462, 2.162, 2.172)):
    B(PX - 0.045, PX, *a, oak, 0.002)                          # oak floater frame
B(PX - 0.04, PX - 0.002, DY - 0.45, DY + 0.45, 0.95, 2.15, art, 0.003)   # canvas, centre at 1.55 m
if NIGHT:  # recessed 3000 K spots 49 cm off the concrete, grazing it: the colour field and the enso print
    for y in (DY, 4.91 + LS):
        light((6.95, y, H - 0.02), "SPOT", 45, 3000, 0.03, aim=(7.44, y, 1.40), cone=42)

# ---------- kitchen ----------
B(5.14, 7.44, 0, 0.6, 0.1, 0.88, oak, 0.003)
B(6.84, 7.44, 0.6, 1.8, 0.1, 0.88, oak, 0.003)
B(5.16, 7.44, 0, 0.55, 0, 0.1, dark); B(6.89, 7.44, 0.6, 1.8, 0, 0.1, dark)
B(5.14, 7.44, 0, 0.62, 0.88, 0.92, concrete, 0.003)           # concrete worktops
B(6.82, 7.44, 0.62, 1.8, 0.88, 0.92, concrete, 0.003)
B(6.84, 7.44, 1.8, 2.45, 0, H, oak, 0.003)                     # tall fridge/oven column, up to the ceiling
for z in (0.88, 1.5, 2.3):                                     # seams line up with the wall cupboards
    B(6.835, 6.84, 1.8, 2.45, z, z + 0.006, dark)
for y in (1.2,):
    B(6.835, 6.84, y, y + 0.006, 0.1, 0.88, dark)
B(6.9, 7.36, 0.8, 1.4, 0.92, 0.926, dark, 0.003)               # induction hob
B(6.95, 7.44, 0.8, 1.4, 1.65, H, concrete, 0.003)              # concrete hood chimney
B(5.75, 6.25, 0.1, 0.5, 0.905, 0.921, alu)                     # sink
CYL(6.0, 0.06, 0.92, 1.2, 0.012, black, seg=8)
B(5.99, 6.01, 0.06, 0.24, 1.17, 1.19, black)
B(6.9, 7.3, 1.45, 1.75, 0.92, 0.94, oak, 0.005)
CYL(7.2, 0.3, 0.92, 1.12, 0.07, black)                         # kettle
CYL(5.45, 0.3, 0.92, 1.02, 0.12, ceramic, r2=0.08)
plant(7.25, 1.62, 1.18, 0.08, 1.05, pot_r=0.06, pot=terracotta, n=5)
# wall cupboards to the ceiling, 35 deep, flat push-open oak doors: coat wardrobe, cupboards, concrete hood and column
# read as one built-in wall. Underside at 1.50 (58 cm over the worktop), split at 2.30 like the column.
Bc(5.14, 7.44, 0, 0.35, 1.5, H, oak, 0.003)                    # east wall, blind corner at the far end
for x in (5.79, 6.44):                                         # 3 x 65 cm doors, the middle one (dish rack) over the sink
    Bc(x - 0.003, x + 0.003, 0.35, 0.354, 1.5, H, dark)
Bc(5.14, 7.09, 0.35, 0.354, 2.3, 2.306, dark)
if not TOP:  # north wall, either side of the hood (left out of the plan so the worktop reads)
    for y0, y1 in ((0.35, 0.8), (1.4, 1.8)):
        B(7.09, 7.44, y0, y1, 1.5, H, oak, 0.003)
        B(7.086, 7.09, y0, y1, 2.3, 2.306, dark)
if NIGHT:
    B(7.0, 7.40, 0.85, 1.35, 1.644, 1.65, glow)                # hood light over the hob
    Bc(5.16, 7.07, 0.31, 0.33, 1.494, 1.5, glow)               # LEDs under the wall cupboards
    if not TOP:
        for y0, y1 in ((0.37, 0.78), (1.42, 1.78)):
            B(7.11, 7.13, y0, y1, 1.494, 1.5, glow)
    light((3.70, 1.20, H - 0.02), "SPOT", 30, 2700, 0.03, aim=(3.70, 1.20, 0), cone=100)   # hall downlight

# ---------- entrance + servis ----------
# entrance built-in on the floor-plan footprint: coat wardrobe + open shoe-rack bench niche
# (old shoe bench removed: it blocked the servis door)
Bc(4.4, 5.13, 0.0, 0.95, 0, H, oak, 0.003)                     # coat wardrobe, 2 push-open doors
Bc(4.397, 4.4, 0.473, 0.477, 0, H, dark)                       # door seam
Bc(4.78, 5.13, 0.95, 1.85, 0, H, oak, 0.003)                   # closed storage behind the niche
Bc(4.4, 4.78, 1.83, 1.85, 0, H, oak)                           # niche side
Bc(4.4, 4.78, 0.95, 1.83, 2.05, H, oak, 0.003)                 # top cupboard
Bc(4.42, 4.76, 0.97, 1.81, 2.03, 2.04, led)                    # LED under the cupboard
Bc(4.765, 4.78, 1.1, 1.68, 0.95, 1.95, mirror)                 # mirror
B(4.4, 4.78, 0.95, 1.83, 0.42, 0.46, oak, 0.003)               # bench seat
B(4.42, 4.78, 0.95, 1.83, 0.2, 0.22, oak)                      # shoe shelf
for row, z in enumerate((0, 0.22)):
    for k in range(3):
        m = (dark, linen_w, clay, black, sage, linen)[row * 3 + k]
        for dy in (0, 0.1):
            B(4.45, 4.73, 1.0 + k * 0.27 + dy, 1.09 + k * 0.27 + dy, z, z + 0.09, m, 0.02)
B(3.25, 4.15, 0.05, 0.6, 0, 0.012, jute)
B(1.84, 2.95, 0.85, 2.8, 0, 0.006, micro)
B(1.9, 2.5, 0.95, 1.55, 0, 0.85, white, 0.02)                  # washer + dryer
B(1.9, 2.5, 1.6, 2.2, 0, 0.85, white, 0.02)
B(1.9, 2.55, 0.92, 2.25, 0.85, 0.88, oak, 0.003)

# ---------- bathroom: microcement + oak ----------
B(0, 1.69, 1.27, 3.85, 0, 0.006, micro)
for a in ((0, 1.69, 1.27, 1.97, 0, 0.1), (0, 0.08, 1.27, 1.97, 0.1, 0.55), (1.61, 1.69, 1.27, 1.97, 0.1, 0.55),
          (0, 1.69, 1.27, 1.35, 0.1, 0.55), (0, 1.69, 1.89, 1.97, 0.1, 0.55)):
    B(*a, ceramic, 0.01)
B(0, 0.5, 2.4, 2.76, 0.22, 0.42, ceramic, 0.06, True)          # wall-hung WC
B(0, 0.48, 3.0, 3.75, 0.45, 0.85, oak, 0.004)                  # vanity
B(0.08, 0.42, 3.15, 3.6, 0.85, 0.96, ceramic, 0.03)
B(0.8, 1.4, 2.05, 2.5, 0.006, 0.02, linen_w, 0.01)
plant(1.45, 3.6, 0.6, 0.12, 0.35, pot_r=0.09, n=5)

# ---------- bedroom ----------
# Original orientation, no nightstands: bed head + desk side by side on the solid south wall, desk at the window.
# 3.8 m = wardrobe 60 + walkway + Kyoto (mattress + 8.5) + gap 2 + desk 120: the walkway is 29.5 cm with the 160
# (sliding doors; drawers still pull out 82%), 49.5 cm with --bed=140 (drawers pull out fully).
# The chair sits in the 1.2 m strip between the bed and the window, so the 80 cm MITTZON fits without a squeeze.
B(0.8, 2.6, 4.70, 6.85, 0, 0.012, wool)
# floor-to-ceiling wardrobe 230 x 60: oak carcass, 3 sliding fluted-glass doors in black frames, LED-lit
for x0, x1, y1 in ((0, 0.02, 4.6), (0.78, 0.8, 4.53), (1.52, 1.54, 4.53), (2.28, 2.3, 4.6)):
    Bc(x0, x1, 4.0, y1, 0, H, oak)                               # sides + dividers
Bc(0, 2.3, 4.0, 4.02, 0, H, oak)                                 # back
Bc(0, 2.3, 4.02, 4.6, H - 0.06, H, oak)                         # top fascia
B(0.02, 2.28, 4.02, 4.6, 0, 0.06, oak)                          # plinth
for i in range(4):
    B(0.81, 1.51, 4.04, 4.51, 0.08 + i * 0.2, 0.265 + i * 0.2, oak, 0.003)   # drawers
g = random.Random(3)
cols = (linen_w, linen, dark, sage, denim, clay, fabric)
for z in (1.15, 1.55, 1.95, 2.3):                                # shelves + folded stacks
    Bc(0.8, 1.52, 4.02, 4.5, z, z + 0.02, oak)
    for j in range(2):
        Bc(0.84 + j * 0.34, 1.14 + j * 0.34, 4.12, 4.45, z + 0.02, z + g.uniform(0.1, 0.24), g.choice(cols), 0.02)
for x0, x1 in ((0.04, 0.76), (1.56, 2.26)):                      # rails, hanging clothes, shoes
    Bc(x0, x1, 4.29, 4.31, 1.99, 2.01, alu)
    x = x0 + 0.02
    while x < x1 - 0.1:
        w = g.uniform(0.04, 0.08)
        Bc(x, x + w, 4.08, 4.5, g.uniform(1.0, 1.45), 1.97, g.choice(cols), 0.01)
        x += w + 0.012
    for k in range(2):
        m, sx = g.choice((dark, linen_w, clay)), x0 + 0.06 + k * 0.33
        for dx in (0, 0.1):
            B(sx + dx, sx + dx + 0.09, 4.16, 4.46, 0.06, 0.15, m, 0.02)
Bc(0.02, 2.28, 4.44, 4.48, H - 0.08, H - 0.07, led)              # LED strip glows through the glass
for x0, yd in ((0.02, 4.57), (0.765, 4.545), (1.51, 4.57)):      # doors on two tracks
    x1 = x0 + 0.77
    for a in ((x0, x0 + 0.02, 0.07, H - 0.07), (x1 - 0.02, x1, 0.07, H - 0.07),
              (x0, x1, 0.07, 0.09), (x0, x1, H - 0.09, H - 0.07)):
        Bc(a[0], a[1], yd, yd + 0.02, a[2], a[3], black)
    Bc(x0 + 0.02, x1 - 0.02, yd + 0.007, yd + 0.013, 0.09, H - 0.09, fluted_glass)
# Rroots Kyoto King Size, natural oak, measured off the maker's AR model of the 160 x 200: 168.5 x 221 cm overall, i.e.
# a 4 cm solid-oak frame round a 160.5 cm opening (other sizes assumed built the same). The frame (19.5-33 cm high)
# floats on recessed legs, slats at 29 cm, 115 cm headboard leaning back 4.6° on two side boards, with a 7 cm shelf
# hidden behind its top edge (phone, book, glass of water: no nightstands).
KW = BED / 200 + 0.0425                                        # half the frame's outside width
KY1 = 6.58                                                     # 2 cm off the desk end
KY0 = KY1 - 2 * KW
yc = (KY0 + KY1) / 2
for y0 in (KY0, KY1 - 0.04):
    B(0.137, 2.223, y0, y0 + 0.04, 0.195, 0.328, oak, 0.01)    # long sides of the frame, rounded corners
for x0 in (0.137, 2.183):
    B(x0, x0 + 0.04, KY0 + 0.04, KY1 - 0.04, 0.195, 0.328, oak, 0.01)   # head + foot ends
B(0.177, 2.183, KY0 + 0.04, KY1 - 0.04, 0.27, 0.289, oak)      # slats
for x, y, h in ((0.498, yc - KW + 0.26, 0.04), (0.498, yc + KW - 0.26, 0.04), (1.864, yc - KW + 0.26, 0.04),
                (1.864, yc + KW - 0.26, 0.04), (0.659, yc, 0.02), (1.141, yc, 0.02), (1.703, yc, 0.02)):
    B(x - h, x + h, y - h, y + h, 0, 0.195, oak, 0.004)        # recessed legs
B(0.1027, 0.1217, KY0, KY1, 0.329, 1.149, oak, 0.004, rot=(0, -0.0803, 0))   # leaning headboard, top at 115
for y0 in (yc - KW + 0.099, yc + KW - 0.117):                  # side boards carrying it, 18 mm
    B(0.01, 0.131, y0, y0 + 0.018, 0, 0.33, oak)
    B(0.01, 0.076, y0, y0 + 0.018, 0.33, 1.07, oak)
B(0.01, 0.079, yc - KW + 0.04, yc + KW - 0.04, 1.07, 1.089, oak, 0.003)   # hidden shelf, 6 cm below the top edge
B(0.18, 2.18, KY0 + 0.045, KY1 - 0.045, 0.289, 0.54, linen_w, 0.04, True)   # 25 cm mattress
B(0.75, 2.20, KY0 + 0.04, KY1 - 0.04, 0.50, 0.60, linen, 0.05, True)        # duvet
B(1.80, 2.22, KY0 + 0.03, KY1 - 0.03, 0.58, 0.62, clay, 0.02, True)         # throw
pw = BED / 200 - 0.1                                           # 70 cm pillows on the 160, 60 on the 140
for y0 in (yc - 0.05 - pw, yc + 0.05):
    B(0.19, 0.63, y0, y0 + pw, 0.54, 0.69, linen_w, 0.06, True)   # pillows
B(0.48, 0.65, yc - 0.25, yc + 0.25, 0.57, 0.80, sage, 0.06, True, (0, 0.3, 0))
for y in (yc - KW + 0.1425, yc + KW - 0.1425):                 # reading lanterns, 30 cm above the headboard
    B(0.0, 0.05, y - 0.012, y + 0.012, 1.43, 1.47, black)
    lantern(0.12, y, 1.45, 0.07, watts=5, k=1800)
# office: IKEA MITTZON 120 x 80 (walnut veneer, white frame, top at 75 cm) + Herman Miller Mirra 2, beside the bed
# against the south wall; the window starts right past the desk's front edge, on your right.
# Wall after the inspiration shot: the slat panel splits round a black brick bay (painted gypsum slips) with a
# preserved-moss panel over the screen and a warm LED line in each seam; the bricks turn the corner onto the window
# pier above the desk (desktop up, so the desk still butts the wall), with three oak shelves in reach.
for y0, y1 in ((6.62, 6.88), (7.54, 7.79)):
    Bc(0.0, 0.01, y0, y1, 0, H, felt)                          # oak slat / felt acoustic panel, now in two parts
for i in (*range(6), *range(23, 29)):
    y = 6.64 + i * 0.04
    Bc(0.01, 0.02, y, y + 0.026, 0, H, oak)
Bc(0.0, 0.015, 6.89, 7.53, 0, H, brick)                        # brick bay, centred on the screen
for y in (6.88, 7.53):
    Bc(0.0, 0.012, y, y + 0.01, 0, H, led)                     # LED profiles in the seams
B(0.02, 0.83, 7.785, 7.8, 0.75, H, brick)                      # window pier
B(0.12, 0.82, 6.60, 7.80, 0.725, 0.75, walnut, 0.003)          # walnut veneer top
B(0.02, 0.12, 6.60, 7.80, 0.725, 0.75, white, 0.003)           # white cable/accessory strip
B(0.047, 0.097, 7.00, 7.25, 0.75, 0.752, dark)                 # cable lid
B(0.04, 0.10, 7.36, 7.60, 0.744, 0.751, felt)                  # pen tray
for ly in (6.67, 7.73):                                        # height-adjustable T-legs
    B(0.08, 0.78, ly - 0.03, ly + 0.03, 0, 0.035, white, 0.006)
    B(0.30, 0.36, ly - 0.025, ly + 0.025, 0.035, 0.45, white, 0.004)
    B(0.305, 0.355, ly - 0.02, ly + 0.02, 0.45, 0.69, white, 0.004)
    B(0.08, 0.76, ly - 0.022, ly + 0.022, 0.69, 0.725, white, 0.004)
B(0.16, 0.20, 6.67, 7.73, 0.665, 0.705, white)                 # underframe beam
B(0.08, 0.28, 7.05, 7.45, 0.56, 0.665, felt, 0.01)             # cable basket
B(0.46, 0.76, 6.80, 7.60, 0.75, 0.753, felt)                   # desk mat
B(0.58, 0.72, 7.03, 7.37, 0.753, 0.765, white, 0.003)          # keyboard, centred on the screen
B(0.56, 0.70, 7.42, 7.56, 0.753, 0.758, white, 0.002)          # trackpad
B(0.13, 0.26, 7.64, 7.77, 0.75, 0.80, alu, 0.01)               # Mac mini, window end
# one 34" ultrawide instead of the two 27s, centred on the desk and the brick bay. The window is beside you,
# not behind you, so the glossy panel doesn't mirror it.
ultrawide(0.30, 7.20, math.pi)
# light bar on the screen's top edge (curved-screen kind): asymmetric beam onto the desk, so no glare on the gloss
B(0.30, 0.33, 6.95, 7.45, 1.245, 1.27, graphite, 0.008)
B(0.27, 0.31, 7.17, 7.23, 1.20, 1.25, graphite, 0.005)         # clip + counterweight behind the panel
if NIGHT:
    light((0.335, 7.20, 1.24), "SPOT", 10, 2700, 0.01, aim=(0.65, 7.20, 0.75), cone=70)
CYL(0.70, 6.70, 0.75, 0.85, 0.04, ceramic)
if VIEWS:  # moss only where the wall isn't cut away
    moss_panel(0.015, 6.96, 7.46, 1.38, 2.02)
if not TOP:  # pier shelves hidden in plan so the desk reads
    for z in (1.40, 1.76, 2.12):
        B(0.04, 0.78, 7.585, 7.785, z, z + 0.03, oak, 0.003)
    for i, mat in enumerate(books):
        B(0.07 + i * 0.035, 0.10 + i * 0.035, 7.60, 7.77, 1.43, 1.65 - i * 0.015, mat)   # books on end
    CYL(0.62, 7.68, 1.43, 1.58, 0.05, ceramic, r2=0.035)
    for i, mat in enumerate((books[2], books[0])):
        B(0.42, 0.68, 7.61, 7.77, 1.79 + i * 0.03, 1.82 + i * 0.03, mat)               # stacked books
    CYL(0.22, 7.68, 1.79, 1.95, 0.045, clay, r2=0.03)
    group(0.40, 7.68)
    PARENT.location.z = 2.15
    plant(0, 0, 0.26, 0.11, 0.06, pot_r=0.06, pot=ceramic, n=6)
    ungroup()
    if NIGHT:  # LED tucked under each shelf at the back, grazing the bricks
        for z in (1.40, 1.76, 2.12):
            B(0.06, 0.76, 7.765, 7.78, z - 0.005, z, glow)
if NIGHT:  # recessed spot over the desk, aimed at the moss: grazes the bricks, spills onto the desk
    light((0.35, 7.21, H - 0.03), "SPOT", 40, 2700, 0.02, aim=(0.02, 7.21, 1.3), cone=55)
plant(0.10, 6.69, 0.98, 0.09, 0.85, pot_r=0.05, n=5)          # left of the screen
mirra2(1.12, 7.20, math.pi)                                    # centred on the screen: 28 cm off the bed, 26 off the wall

# ---------- light: west sun, late afternoon ----------
el, az = math.radians(24), math.radians(255)  # azimuth from north, clockwise
to_sun = Vector((math.cos(el) * math.cos(az), -math.cos(el) * math.sin(az), math.sin(el)))
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
scene.collection.objects.link(sun)
sun.data.energy, sun.data.color, sun.data.angle = 5.5, (1.0, 0.83, 0.65), math.radians(1.5)
sun.rotation_euler = to_sun.to_track_quat("Z", "Y").to_euler()

world = bpy.data.worlds.new("sky")
scene.world = world
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value, bg.inputs["Strength"].default_value = (0.62, 0.74, 0.95, 1), 0.5
if NIGHT:  # blue hour: deep-blue sky, a faint cool moon on the same bearing
    sun.data.energy, sun.data.color = 0.05, (0.65, 0.75, 1.0)
    bg.inputs["Color"].default_value, bg.inputs["Strength"].default_value = (0.03, 0.05, 0.12, 1), 0.35

# ---------- camera: orthographic iso from south-east ----------
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.type, cam.data.ortho_scale = "ORTHO", 13.2
cam.data.shift_x, cam.data.shift_y = 0.025, 0.035
e = math.radians(40)
view = Vector((math.cos(e) / math.sqrt(2), math.cos(e) / math.sqrt(2), -math.sin(e)))
target = Vector((3.75, 4.55, 0.6))
cam.location = target - view * 40
cam.rotation_euler = view.to_track_quat("-Z", "Y").to_euler()
cam.data.clip_end = 200
if TOP:  # terrace up, north right; pendant hidden so the dining table reads
    cam.location, cam.rotation_euler = (3.72, 4.6, 30), (0, 0, 0)
    cam.data.ortho_scale, cam.data.shift_x, cam.data.shift_y = 10.6, 0, 0
    for o in pendant + caps:
        o.hide_render = o.type != "LIGHT"                          # its bulb stays on at night
if VIEWS:
    cam.data.type, cam.data.lens, cam.data.clip_start = "PERSP", 20 if WALK else 18, 0.05
    cam.data.shift_x = cam.data.shift_y = 0

FPS = 24
KEYS = [  # walkthrough stops (time s, eye, look-at), timed for <= 0.75 m/s and <= 36°/s turns
    (0.0, (3.70, 0.40, 1.62), (3.80, 3.60, 1.40)),   # front door, down the hall
    (3.2, (3.75, 2.15, 1.62), (5.40, 4.50, 1.20)),   # hall opens up on the right: dining, sofa, terrace light
    (5.5, (3.25, 3.30, 1.62), (2.00, 6.60, 1.20)),   # bear left to the bedroom (a dead end, so it comes first)
    (6.9, (2.80, 3.75, 1.62), (0.60, 6.40, 1.00)),   # doorway: bed, desk + window beyond
    (8.7, (2.70, 4.75, 1.62), (0.05, 5.75, 0.80)),   # bed + oak headboard
    (11.9, (2.62, 6.50, 1.62), (0.30, 7.35, 0.95)),  # along the bed's foot: desk at the window
    (16.8, (2.62, 6.50, 1.62), (3.25, 4.40, 1.40)),  # turn right: slat panel wall, toward the door
    (19.9, (2.62, 5.70, 1.62), (1.00, 4.30, 1.30)),  # wardrobe across the bed, 3/4
    (22.0, (2.72, 4.75, 1.62), (2.95, 2.20, 1.40)),  # out the door
    (24.5, (2.85, 3.45, 1.62), (6.80, 2.00, 1.10)),  # lobby: kitchen + dining ahead
    (28.4, (4.25, 3.40, 1.62), (4.90, 7.80, 1.15)),  # long view: TV wall left, sofa right, terrace ahead
    (31.8, (4.55, 5.25, 1.62), (6.90, 6.40, 0.95)),  # sofa, chaise, corner radiator
    (33.9, (4.95, 6.35, 1.62), (5.45, 9.60, 1.15)),  # terrace, whole slider in frame
    (35.5, (4.95, 6.35, 1.62), (5.45, 9.60, 1.15)),  # hold
]


def walk(t):
    """Eye + look-at at time t: Catmull-Rom/Hermite through KEYS on (eye, heading, pitch), so turns stay even."""
    ks, h0 = [], 0.0
    for tk, e, l in KEYS:
        d = Vector(l) - Vector(e)
        h = math.atan2(d.y, d.x)
        h0 = h + 2 * math.pi * round((h0 - h) / (2 * math.pi))  # unwrap: always the shortest turn
        ks.append((tk, (*e, h0, math.atan2(d.z, d.xy.length))))
    i = max(j for j in range(len(ks) - 1) if ks[j][0] <= t)
    h, s = ks[i + 1][0] - ks[i][0], (t - ks[i][0]) / (ks[i + 1][0] - ks[i][0])

    def m(j):  # finite-difference tangent, zero at the ends = ease in/out
        if j in (0, len(ks) - 1):
            return (0,) * 5
        return [(a - b) / (ks[j + 1][0] - ks[j - 1][0]) for a, b in zip(ks[j + 1][1], ks[j - 1][1])]
    w = (2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s, 3 * s**2 - 2 * s**3, s**3 - s**2)
    x, y, z, hd, p = (w[0] * a + w[1] * h * b + w[2] * c + w[3] * h * d
                      for a, b, c, d in zip(ks[i][1], m(i), ks[i + 1][1], m(i + 1)))
    return (x, y, z), (x + math.cos(hd) * math.cos(p), y + math.sin(hd) * math.cos(p), z + math.sin(p))


assert all((Vector(walk(k[0])[0]) - Vector(k[1])).length < 1e-9 for k in KEYS)  # path hits every stop

# ---------- render ----------
r = scene.render
r.engine = "CYCLES"
r.resolution_x, r.resolution_y = (1200, 1000) if PREVIEW else (2400, 2000)
if TOP:
    r.resolution_x, r.resolution_y = r.resolution_y, r.resolution_x
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "METAL"
prefs.get_devices()
for d in prefs.devices:
    d.use = d.type == "METAL"
scene.cycles.device = "GPU"
scene.cycles.samples = 48 if PREVIEW else 384
scene.cycles.use_denoising = True
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
r.image_settings.file_format = "PNG"
r.use_stamp_filename = False  # keep the .blend path (and the user's home folder) out of the PNG metadata
shots = {"render_topdown" if TOP else "render_isometric": None}
if VIEWS:
    scene.view_settings.exposure = 1.0
    r.resolution_y = r.resolution_x * 2 // 3
if NIGHT:  # camera white-balanced to 3500 K like a night interior shot: 2700 K reads warm white, the sky deep blue
    vs = scene.view_settings
    vs.use_white_balance, vs.white_balance_temperature, vs.exposure = True, 3500, -1.0 if VIEWS else -0.4
if VIEWS:
    shots = {"render_living_tv": ((7.2, TY - 0.05, 1.35), (3.45, TY + 0.1, 1.0)),
             "render_living_length": ((3.95, 2.3, 1.55), (4.55, 7.8, 1.3)),   # the 5.9 m run, like the living-room photo
             "render_bedroom": ((3.0, 5.2, 1.5), (0.2, 6.4, 0.85)),
             "render_bedroom_office": ((2.55, 6.35, 1.45), (0.3, 7.25, 0.95)),
             "render_dining": ((4.45, 4.9, 1.5), (7.44, 2.95, 1.3)),   # table + painting on the concrete wall
             "render_entrance": ((3.25, 2.8, 1.55), (4.45, 0.7, 1.0))}
    if WALK:  # frames go to walk/; existing ones are skipped so a killed run resumes (delete walk/ after path edits)
        r.resolution_x, r.resolution_y = (640, 360) if PREVIEW else (1920, 1080)
        scene.cycles.samples = 16 if PREVIEW else 64
        r.use_persistent_data = True  # only the camera moves between frames
        step = FPS if PREVIEW else 1
        shots = {f"walk/{f:04d}": walk(f / FPS) for f in range(0, round(KEYS[-1][0] * FPS) + 1, step)}
elif not (PREVIEW or TOP or NIGHT or BED != 160):
    bpy.context.preferences.filepaths.save_version = 0  # no apartment.blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "apartment.blend"))
if "only" in OPT:  # e.g. --only=bedroom renders render_bedroom + render_bedroom_office
    shots = {k: v for k, v in shots.items() if any(s in k for s in OPT["only"].split(","))}
for name, pose in shots.items():
    if pose:
        cam.location = pose[0]
        cam.rotation_euler = (Vector(pose[1]) - Vector(pose[0])).to_track_quat("-Z", "Y").to_euler()
    r.filepath = os.path.join(REN, ("preview_" if PREVIEW else "") + name + SUF + ".png")
    if WALK and os.path.exists(r.filepath):
        continue
    bpy.ops.render.render(write_still=True)
    print("saved", r.filepath)
if WALK:  # encode with Blender's bundled FFmpeg (no system ffmpeg on this Mac)
    wd = os.path.join(REN, ("preview_" if PREVIEW else "") + "walk")
    frames = sorted(f for f in os.listdir(wd) if f[4:] == SUF + ".png")   # 0123.png, 0123_night.png, 0123_bed140.png
    ed = bpy.data.scenes.new("edit")
    ed.view_settings.view_transform = "Standard"  # frames are already AgX-graded
    st = ed.sequence_editor_create().strips.new_image("walk", os.path.join(wd, frames[0]), 1, 1)
    for f in frames[1:]:
        st.elements.append(f)
    er = ed.render
    ed.frame_end, er.fps, er.resolution_x, er.resolution_y = len(frames), FPS // step, r.resolution_x, r.resolution_y
    er.image_settings.media_type, er.image_settings.file_format = "VIDEO", "FFMPEG"
    er.ffmpeg.format, er.ffmpeg.codec, er.ffmpeg.constant_rate_factor = "MPEG4", "H264", "HIGH"
    er.filepath = os.path.join(REN, ("preview_" if PREVIEW else "") + "walkthrough" + SUF + ".mp4")
    bpy.ops.render.render(animation=True, scene=ed.name)
    print("saved", er.filepath)
