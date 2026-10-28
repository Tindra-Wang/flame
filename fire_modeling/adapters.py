"""Rendering port and infrastructure factories, independent of pipeline rules."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from .config import SceneConfig


@dataclass(frozen=True)
class RenderRequest:
    config: SceneConfig
    directory: Path
    seed: int
    angle: float
    weather: str
    strength: float
    positive: bool
    volume: Path | None = None
    viewpoint: str | None = None
    profile: dict | None = None
    controls: bool = False


@dataclass
class RenderResult:
    image: Image.Image
    mask: Image.Image
    source: str


class Renderer(Protocol):
    def render(self, request: RenderRequest) -> RenderResult: ...


class PreviewRenderer:
    def render(self, request: RenderRequest) -> RenderResult:
        from .procedural import render
        image,mask=render(request.config,request.seed,request.angle,request.weather,request.strength,request.positive)
        return RenderResult(image,mask,"procedural_preview_not_cfd")


class BlenderRenderer:
    def __init__(self, executable: str): self.executable=executable

    def render(self, request: RenderRequest) -> RenderResult:
        from .blender_adapter import render
        image,mask=render(request.config,request.directory,self.executable,seed=request.seed,angle=request.angle,weather=request.weather,strength=request.strength,positive=request.positive,volume=request.volume,viewpoint=request.viewpoint,profile=request.profile,controls=request.controls)
        return RenderResult(image,mask,"fds_openvdb_volume" if request.volume else "mantaflow_visual_simulation")


def create_renderer(name: str, blender_exe="blender") -> Renderer:
    factories={"preview":PreviewRenderer,"blender":lambda:BlenderRenderer(blender_exe)}
    if name not in factories: raise ValueError(f"Unknown renderer: {name}")
    return factories[name]()
