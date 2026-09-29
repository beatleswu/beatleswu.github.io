"""Deterministic candidate normalization (Blender 5.2, background mode).

For every source model:
  1. import the ORIGINAL source file (GLB for Kenney, glTF for KayKit),
  2. join meshes, apply transforms,
  3. orient: longest axis -> Blender +Z (glTF +Y), blade tip up (handle end = end nearest the widest cross-section),
  4. origin: grip point on the blade axis (between pommel end and guard),
  5. uniform scale to the role length used by the retired D007 formal assets
     (sword 2.25 units, knife/dagger 1.58 units),
  6. export web-safe GLB (no cameras/lights, +Y up, embedded textures).

No artistic changes (no remodel, no recolor, no retexture).
Outputs candidates/<cid>.glb and evidence/normalize_report.json.
"""
import bpy, bmesh, json, math, os, sys
from mathutils import Vector, Matrix

ROOT = r"D:\go-website-g009-formal9-weapon-candidates-002"
EX = os.path.join(ROOT, "extracted")
KK = os.path.join(EX, "kaykit_fantasy_weapons_bits", "KayKit_FantasyWeaponsBits_1.0_FREE", "Assets", "gltf")

SOURCES = [
    # cid, provider, pack, path, role length
    ("KN_MINIDUNGEON_SWORD", "Kenney", "Mini Dungeon", os.path.join(EX, "kenney_mini-dungeon", "Models", "GLB format", "weapon-sword.glb"), 2.25),
    ("KN_MINIARENA_SWORD", "Kenney", "Mini Arena", os.path.join(EX, "kenney_mini-arena", "Models", "GLB format", "weapon-sword.glb"), 2.25),
    ("KN_PROTOTYPE_SWORD", "Kenney", "Prototype Kit", os.path.join(EX, "kenney_prototype-kit", "Models", "GLB format", "weapon-sword.glb"), 2.25),
    ("KK_SWORD_A", "KayKit", "Fantasy Weapons Bits", os.path.join(KK, "sword_A.gltf"), 2.25),
    ("KK_SWORD_B", "KayKit", "Fantasy Weapons Bits", os.path.join(KK, "sword_B.gltf"), 2.25),
    ("KK_SWORD_C", "KayKit", "Fantasy Weapons Bits", os.path.join(KK, "sword_C.gltf"), 2.25),
    ("KK_SWORD_D", "KayKit", "Fantasy Weapons Bits", os.path.join(KK, "sword_D.gltf"), 2.25),
    ("KK_SWORD_E", "KayKit", "Fantasy Weapons Bits", os.path.join(KK, "sword_E.gltf"), 2.25),
    ("KK_DAGGER_A", "KayKit", "Fantasy Weapons Bits", os.path.join(KK, "dagger_A.gltf"), 1.58),
    ("KK_DAGGER_B", "KayKit", "Fantasy Weapons Bits", os.path.join(KK, "dagger_B.gltf"), 1.58),
]

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def import_source(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]

def join_meshes(objs):
    meshes = [o for o in objs if o.type == "MESH"]
    for o in objs:
        if o.type != "MESH":
            o.select_set(False)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    # bake parent transforms
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    for o in list(bpy.data.objects):
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    return obj

def verts_world(obj):
    return [obj.matrix_world @ v.co for v in obj.data.vertices]

def width_profile(pts, axis, bins=40):
    other = [i for i in range(3) if i != axis]
    lo = min(p[axis] for p in pts); hi = max(p[axis] for p in pts)
    span = hi - lo or 1e-6
    prof = [0.0] * bins
    for p in pts:
        b = min(bins - 1, int((p[axis] - lo) / span * bins))
        w = max(abs(p[other[0]]), abs(p[other[1]]))
        prof[b] = max(prof[b], w)
    return lo, hi, prof

def main():
    report = []
    os.makedirs(os.path.join(ROOT, "candidates"), exist_ok=True)
    for cid, provider, pack, path, target in SOURCES:
        reset()
        objs = import_source(path)
        obj = join_meshes(objs)
        pts = verts_world(obj)
        mn = Vector([min(p[i] for p in pts) for i in range(3)])
        mx = Vector([max(p[i] for p in pts) for i in range(3)])
        size = mx - mn
        axis = max(range(3), key=lambda i: size[i])
        # center the two short axes on the blade axis
        c = (mn + mx) / 2
        obj.data.transform(Matrix.Translation(Vector([-c[0] if axis != 0 else 0, -c[1] if axis != 1 else 0, -c[2] if axis != 2 else 0])))
        # rotate the long axis onto Blender +Z (exported as glTF +Y with export_yup)
        if axis == 0:
            obj.data.transform(Matrix.Rotation(math.radians(-90), 4, "Y"))
        elif axis == 1:
            obj.data.transform(Matrix.Rotation(math.radians(90), 4, "X"))
        pts = verts_world(obj)
        lo, hi, prof = width_profile(pts, 2)
        n = len(prof)
        guard_bin = max(range(n), key=lambda b: prof[b])
        flipped = False
        if guard_bin > n / 2:  # widest section in upper half -> handle is at top -> flip
            obj.data.transform(Matrix.Rotation(math.radians(180), 4, "X"))
            flipped = True
            pts = verts_world(obj)
            lo, hi, prof = width_profile(pts, 2)
            guard_bin = max(range(n), key=lambda b: prof[b])
        span = hi - lo
        guard_y = lo + (guard_bin + 0.5) / n * span
        grip_y = guard_y - 0.35 * (guard_y - lo)
        obj.data.transform(Matrix.Translation(Vector((0, 0, -grip_y))))
        s = target / span
        obj.data.transform(Matrix.Scale(s, 4))
        obj.name = cid
        pts = verts_world(obj)
        mn = [min(p[i] for p in pts) for i in range(3)]
        mx = [max(p[i] for p in pts) for i in range(3)]
        out = os.path.join(ROOT, "candidates", cid + ".glb")
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.ops.export_scene.gltf(
            filepath=out, export_format="GLB", use_selection=True, export_yup=True,
            export_apply=True, export_cameras=False, export_lights=False,
            export_animations=False, export_skins=False, export_morph=False,
            export_image_format="AUTO", export_texcoords=True, export_normals=True,
            export_materials="EXPORT", export_extras=False,
        )
        me = obj.data
        report.append({
            "candidate_id": cid, "provider": provider, "pack": pack, "source_model_file": path,
            "long_axis_in_source": "XYZ"[axis], "flipped_blade_up": flipped,
            "uniform_scale_factor": s, "target_length_units": target,
            "grip_origin_rule": "origin = guard - 0.35*(guard - pommel) on blade axis; blade axis = Blender +Z = glTF +Y",
            "vertices": len(me.vertices), "triangles": sum(len(p.vertices) - 2 for p in me.polygons),
            "materials": len(me.materials), "bbox_min": mn, "bbox_max": mx,
            "output_glb": out,
        })
        print("NORMALIZED", cid, report[-1]["triangles"], mn, mx)
    with open(os.path.join(ROOT, "evidence", "normalize_report.json"), "w", encoding="utf-8") as f:
        json.dump({"blender_version": bpy.app.version_string, "items": report}, f, indent=2)

main()
