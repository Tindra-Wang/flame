"""Run Blender in its own Python environment, exchanging only JSON/files."""
from pathlib import Path
import shutil
import subprocess

from .config import SceneConfig
from .io import write_json


def render(config: SceneConfig, directory: Path, executable: str, *, seed: int, angle: float, weather: str, strength: float, positive: bool, volume: Path | None = None,viewpoint: str | None = None,profile=None,controls=False):
    resolved=shutil.which(executable) or (str(Path(executable).resolve()) if Path(executable).is_file() else None)
    if not resolved:
        raise RuntimeError("Blender not found; set --blender-exe or BLENDER_EXE")
    directory.mkdir(parents=True,exist_ok=True)
    job=directory/"job.json"
    write_json(job,{"config":config.to_dict(),"seed":seed,"angle":angle,"weather":weather,"strength":strength,"positive":positive,"output":str(directory.resolve()),"volume":str(volume.resolve()) if volume else None,'viewpoint':viewpoint,'profile':profile,'controls':controls})
    script=Path(__file__).with_name("fds_volume_scene.py" if volume else "blender_scene.py")
    with (directory/"blender.log").open("w",encoding="utf-8") as log:
        proc=subprocess.run([resolved,"--background","--factory-startup","--python",str(script),"--",str(job.resolve())],stdout=log,stderr=subprocess.STDOUT,timeout=1800,check=False)
    if proc.returncode or not (directory/"render.json").is_file():
        raise RuntimeError(f"Blender rendering failed; inspect {directory/'blender.log'}")
    from PIL import Image
    with Image.open(directory/"rgb.png") as rgb,Image.open(directory/"mask.png") as mask:
        return rgb.convert("RGB").copy(),mask.convert("L").copy()
