"""G010 RC3 adversarial reviewer-packet checks (no trusted signer issued).

Actively corrupts isolated copies of the real 48-file ZIP in memory, ensuring
independent verifier rejects. Actual candidate, ZIP, Git refs, and Docker
are read-only; no self-issued permission ever counts as formal attestation.
"""
from __future__ import annotations
import io
import json
from pathlib import Path
import stat
import sys
import zipfile
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import _verify_g010_rc3_source_adoption_inputs as rc3

@pytest.fixture(scope="module")
def original():
    return rc3.BUNDLE.read_bytes()

def repack(original:bytes, *, replace=None, extra=None, remove=None,
           repeat=None) -> bytes:
    replace=replace or {}
    extra=extra or {}
    remove=set(remove or ())
    bio=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(
         bio,"w",zipfile.ZIP_DEFLATED,compresslevel=5) as target:
        for i in source.infolist():
            if i.filename in remove:
                continue
            target.writestr(i,replace.get(i.filename,source.read(i.filename)))
        for path,data in extra.items():
            target.writestr(path,data)
        if repeat:
            with pytest.warns(UserWarning,match="Duplicate name"):
                target.writestr(repeat,b"second malicious copy")
    return bio.getvalue()

def must_deny(raw:bytes,reason):
    with pytest.raises(ValueError,match=reason):
        rc3.verify_zip(raw,strict_inventory=False)

def test_00_real_48_file_bundle_integrity(original):
    facts=rc3.verify_zip(original)
    assert facts["members"]>=48
    assert facts["manifest"]["baseline_commit"]==rc3.BASE_SHA

def test_01_live_original_exact_source_to_arm64_image(original):
    facts=rc3.evaluate_custody(bundle_override=original)
    assert facts["formal_signed_source_admission"]=="NO_GO"
    assert facts["runtime_files_in_bundle_equal_to_arm64_image_sha256"]==7
    assert facts["release_image_platform"]=="linux/arm64"

def test_02_tampered_product_python_is_rejected(original):
    target="candidate_files/app.py"
    with zipfile.ZipFile(io.BytesIO(original)) as z:
        original_py=z.read(target)
    edited=repack(original,replace={target:original_py+b"\n# illicit product change\n"})
    must_deny(edited,"TAMPERED_MEMBER:app.py")

def test_03_tampered_review_patch_is_rejected(original):
    with zipfile.ZipFile(io.BytesIO(original)) as z:
        patch=z.read("tracked_changes.patch")
    edited=repack(original,replace={"tracked_changes.patch":patch+b"\n# extra\n"})
    must_deny(edited,"TAMPERED_TRACKED_PATCH")

def test_04_zipped_secret_or_user_db_is_rejected(original):
    for forbidden in ("candidate_files/secret_key.txt",
                      "candidate_files/users.sqlite"):
        edited=repack(original,extra={forbidden:b"fake secret - never real"})
        must_deny(edited,"SECRET_OR_DATABASE_NAME_IN_REVIEW")

def test_05_path_traversal_is_rejected(original):
    edited=repack(original,extra={"candidate_files/../../.env":b"not actual"})
    must_deny(edited,"UNSAFE_MEMBER_PATH")

def test_06_root_absolute_path_is_rejected(original):
    edited=repack(original,extra={"/windows/something":b"no"})
    must_deny(edited,"UNSAFE_MEMBER_PATH")

def test_07_duplicate_member_override_is_rejected(original):
    edited=repack(original,repeat="candidate_files/app.py")
    must_deny(edited,"DUPLICATE_ZIP_MEMBER")

def test_08_symlink_member_is_rejected(original):
    i=zipfile.ZipInfo("candidate_files/evil-symlink")
    i.create_system=3
    i.external_attr=(stat.S_IFLNK|0o777)<<16
    buffer=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as src, zipfile.ZipFile(
         buffer,"w",zipfile.ZIP_DEFLATED) as dst:
        for member in src.infolist():
            dst.writestr(member,src.read(member.filename))
        dst.writestr(i,b"../../id_rsa")
    must_deny(buffer.getvalue(),"ZIP_SYMLINK_NOT_ALLOWED")

def test_09_no_manifest_or_missing_ui_file_is_rejected(original):
    for absent in ("SOURCE_REVIEW_MANIFEST.json",
                   "candidate_files/g010_m4_quest_leaderboard.js"):
        edited=repack(original,remove={absent})
        must_deny(edited,"REQUIRED_MANIFEST_MISSING" if absent.startswith("SOURCE")
                  else "ARCHIVE_MEMBERS_DO_NOT_MATCH_MANIFEST")

def test_10_self_claimed_trusted_attestation_is_rejected(original):
    with zipfile.ZipFile(io.BytesIO(original)) as src:
        record=json.loads(src.read("SOURCE_REVIEW_MANIFEST.json"))
    record["bundle_kind"]="INDEPENDENTLY_SIGNED_PRODUCTION_RELEASE"
    edited=repack(original,replace={
      "SOURCE_REVIEW_MANIFEST.json":json.dumps(record).encode("utf-8")})
    must_deny(edited,"CLAIMED_TRUSTED_ATTESTATION")

def test_11_wrong_baseline_commit_is_rejected(original):
    with zipfile.ZipFile(io.BytesIO(original)) as src:
        record=json.loads(src.read("SOURCE_REVIEW_MANIFEST.json"))
    record["baseline_commit"]="0"*40
    edited=repack(original,replace={
      "SOURCE_REVIEW_MANIFEST.json":json.dumps(record).encode("utf-8")})
    must_deny(edited,"UNEXPECTED_BASELINE")

def test_12_forged_deployment_assertion_is_rejected(original):
    with zipfile.ZipFile(io.BytesIO(original)) as src:
        record=json.loads(src.read("SOURCE_REVIEW_MANIFEST.json"))
    record["product_deployed"]=True
    edited=repack(original,replace={
      "SOURCE_REVIEW_MANIFEST.json":json.dumps(record).encode("utf-8")})
    must_deny(edited,"IMPROPER_DEPLOYMENT_CLAIM")

def test_13_fake_independent_signature_or_owner_grant_is_rejected(original):
    with zipfile.ZipFile(io.BytesIO(original)) as src:
        baseline=json.loads(src.read("SOURCE_REVIEW_MANIFEST.json"))
    for key,lie in (
        ("independent_source_signature","INDEPENDENT_PASS"),
        ("formal_owner_approval","GO_MERGE"),
        ("true_iPad_owner_uat","PASSED"),
    ):
        record=dict(baseline)
        record[key]=lie
        edited=repack(original,replace={
           "SOURCE_REVIEW_MANIFEST.json":json.dumps(record).encode("utf-8")})
        must_deny(edited,"FORGED_TRUST_OR_OWNER_ATTESTATION")

def test_14_zip_bomb_unbounded_entry_rejected(original):
    bio=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as src,zipfile.ZipFile(
            bio,"w",zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info,src.read(info.filename))
        large=zipfile.ZipInfo("candidate_files/illicit-gigantic-binary.bin")
        dst.writestr(large,b"A"*24_000_001)
    must_deny(bio.getvalue(),"UNBOUNDED_REVIEW_ARCHIVE")
