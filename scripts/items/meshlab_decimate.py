"""Robust decimation of a raw Pixal3D item with MeshLab (pymeshlab): merge close verts, drop debris, close holes,
quadric edge collapse, light smoothing. Geometry only (colours are baked from the raw mesh afterwards).
Used for items whose raw surface is open / non-manifold, where Blender's collapse decimation shatters and a voxel
remesh punches holes (bootie, food bowl).
Usage: python scripts/items/meshlab_decimate.py <raw.glb> <out.glb> <target_faces> [max_hole_edges=300]
"""
import sys
import numpy as np, trimesh, pymeshlab

src, dst, target = sys.argv[1], sys.argv[2], int(sys.argv[3])
max_hole = int(sys.argv[4]) if len(sys.argv) > 4 else 300
m = trimesh.load(src).to_geometry()
ms = pymeshlab.MeshSet()
ms.add_mesh(pymeshlab.Mesh(np.asarray(m.vertices, np.float64), np.asarray(m.faces, np.int32)))
ms.meshing_merge_close_vertices(threshold=pymeshlab.PercentageValue(0.01))
ms.meshing_remove_duplicate_faces(); ms.meshing_remove_null_faces()
ms.meshing_remove_connected_component_by_face_number(mincomponentsize=60)
ms.meshing_repair_non_manifold_edges(method=0)
try:
    ms.meshing_close_holes(maxholesize=max_hole, newfaceselected=False)
except pymeshlab.PyMeshLabException as e:
    print("close_holes skipped:", e)
ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target, preservenormal=True, preservetopology=False,
                                            qualitythr=0.5, planarquadric=True, optimalplacement=True)
ms.apply_coord_laplacian_smoothing(stepsmoothnum=2, cotangentweight=False)
# raw Pixal3D meshes have inconsistently wound regions; make orientation coherent (dark flipped faces otherwise)
try:
    ms.meshing_re_orient_faces_coherently()
except pymeshlab.PyMeshLabException as e:
    print("re-orient skipped:", e)
out = ms.current_mesh()
trimesh.Trimesh(out.vertex_matrix(), out.face_matrix(), process=False).export(dst)
print(f"meshlab: {out.face_number()} faces")
