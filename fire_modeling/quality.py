"""Structural quality gates; appearance statistics are not realism scores."""
from pathlib import Path
import numpy as np
from PIL import Image

from .annotations import validate_boxes
from .io import resolve_artifact, sha256


def inspect_sample(root: Path, sample: dict, expected_hash: bool = True) -> dict:
    errors=[]
    try:
        path=resolve_artifact(root,sample["image"])
        with Image.open(path) as im:
            im.load()
            if im.size!=(sample["width"],sample["height"]): errors.append("size_mismatch")
            gray=np.asarray(im.convert("L"),dtype=float)
        validate_boxes(sample["boxes"],sample["width"],sample["height"])
        if expected_hash and sha256(path)!=sample["sha256"]: errors.append("content_changed")
        lap=-4*gray[1:-1,1:-1]+gray[:-2,1:-1]+gray[2:,1:-1]+gray[1:-1,:-2]+gray[1:-1,2:]
        stats={"mean_luminance":float(gray.mean()),"laplacian_variance":float(lap.var()) if lap.size else 0}
    except (OSError,ValueError,KeyError,TypeError) as exc:
        errors.append(str(exc)); stats={}
    warnings=['expected_fire_without_candidate'] if sample.get('expected_fire') and not sample.get('boxes') else []
    return {"sample_id":sample.get("sample_id"),"structural_pass":not errors,"auto_screen_pass":not errors and not warnings,"warnings":warnings,"errors":errors,"statistics":stats}


def inspect_run(root: Path, manifest: dict) -> dict:
    seen={}; reports=[]
    for sample in manifest["samples"]:
        result=inspect_sample(root,sample)
        digest=sample["sha256"]
        if digest in seen:
            result["errors"].append(f"exact_duplicate_of:{seen[digest]}"); result["structural_pass"]=False
            result['auto_screen_pass']=False
        seen[digest]=sample["sample_id"]; reports.append(result)
    return {"count":len(reports),"structural_pass_count":sum(x["structural_pass"] for x in reports),"samples":reports,"note":"Structural validity and image statistics do not establish physical realism or label accuracy."}
