"""Regression: all source-approved P048 bonus presentations require exact image GLB/texture closure."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
FILES=[
 "assets/3d_shop/p048/companion/C01/animal-bunny.glb",
 "assets/3d_shop/p048/companion/C01/Textures/colormap.png",
 "assets/3d_shop/p048/companion/C04/Corgi.glb",
]
def test_each_image_dependency_exact_copy_and_manifest():
 docker=(ROOT/"Dockerfile").read_text(encoding="utf8")
 m=json.loads((ROOT/"deploy/build-manifest.json").read_text(encoding="utf8"))
 for name in FILES:
  assert (ROOT/name).is_file()
  assert "COPY "+name+" ./"+name in docker
  assert name in m["build_inputs"]["tracked_in_canonical_branch_this_sprint"]
  assert "/app/"+name in m["post_build_verification_files"]
def test_known_external_bunny_texture_sha_exact():
 img=ROOT/FILES[1]
 assert hashlib.sha256(img.read_bytes()).hexdigest()=="2f6d0032e51c2d49b13b8e689d59eb39aa3ee6c32f2a1851213e11fc7593177d"
def test_released_only_presentation_does_not_grant_ownership():
 m=json.loads((ROOT/"docs/handoffs/G010_P048_C01_C04_IMAGE_CLOSURE_20261021.json").read_text(encoding="utf8"))
 assert len(m["files"])==3 and m["release_admission"] is False
 assert m["ownership_authority_changes"] is False
