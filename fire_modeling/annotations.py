"""Candidate masks, reviewable boxes and COCO/YOLO coordinate conventions."""
from __future__ import annotations

import math
import numpy as np
from scipy.ndimage import label, find_objects


def boxes_from_mask(mask: np.ndarray, min_area: int = 16) -> list[list[int]]:
    array = np.asarray(mask)
    if array.ndim != 2:
        raise ValueError("Mask must be a two-dimensional image")
    components, _ = label(array > 0)
    result=[]
    for i, region in enumerate(find_objects(components),1):
        if region is None or np.count_nonzero(components[region]==i)<min_area: continue
        y,x=region
        result.append([x.start,y.start,x.stop,y.stop])
    return result


def validate_boxes(boxes, width: int, height: int) -> None:
    for box in boxes:
        if len(box)!=4 or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in box):
            raise ValueError("Box must contain four finite numbers")
        x0,y0,x1,y1=box
        if not 0<=x0<x1<=width or not 0<=y0<y1<=height:
            raise ValueError(f"Invalid or out-of-bounds box: {box}")


def yolo_lines(boxes, width: int, height: int) -> str:
    validate_boxes(boxes,width,height)
    return "".join(f"0 {(a+c)/2/width:.8f} {(b+d)/2/height:.8f} {(c-a)/width:.8f} {(d-b)/height:.8f}\n" for a,b,c,d in boxes)


def box_iou(a,b) -> float:
    ax0,ay0,ax1,ay1=a; bx0,by0,bx1,by1=b
    intersection=max(0,min(ax1,bx1)-max(ax0,bx0))*max(0,min(ay1,by1)-max(ay0,by0))
    union=(ax1-ax0)*(ay1-ay0)+(bx1-bx0)*(by1-by0)-intersection
    return intersection/union if union>0 else 0.0
