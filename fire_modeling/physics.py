"""FDS input generation and measured-HRR-to-visual-parameter mapping."""
from __future__ import annotations

import csv
import math
from pathlib import Path
import shutil
import subprocess

import numpy as np

from .config import SceneConfig
from .io import write_json


def fds_input(config: SceneConfig) -> str:
    config.validate()
    if config.editor_scene is not None:
        from .editor_contract import editor_fds_input
        return editor_fds_input(config)
    lx, ly, lz = config.room_size_m
    dx = config.cell_size_m
    nx, ny, nz = (round(x / dx) for x in config.room_size_m)
    x0, x1, y0, y1 = config.burner_bounds
    hrrpua = config.peak_hrr_kw / (config.fire_size_m[0] * config.fire_size_m[1])
    lines = [
        f"&HEAD CHID='{config.scene_id}', TITLE='AI07 parameterized burner' /",
        f"&MESH IJK={nx},{ny},{nz}, XB=0,{lx:g},0,{ly:g},0,{lz:g} /",
        f"&TIME T_END={config.duration_s:g} /",
        f"&MISC TMPA={config.ambient_temperature_c:g}, HUMIDITY={config.ambient_relative_humidity_pct:g} /",
        f"&DUMP DT_HRR=0.1, DT_SLCF=0.5, DT_SL3D={min(.5,config.duration_s/(config.output_frames-1)) if config.output_frames else .5:.8g} /",
        "&REAC ID='PROPANE_FIRE', FUEL='PROPANE', SOOT_YIELD=0.01 /",
        f"&SURF ID='BURNER', HRRPUA={hrrpua:.8g}, RAMP_Q='FIRE_RAMP' /",
        "&RAMP ID='FIRE_RAMP', T=0, F=0 /",
        f"&RAMP ID='FIRE_RAMP', T={config.ramp_up_s:g}, F=1 /",
        f"&RAMP ID='FIRE_RAMP', T={config.duration_s:g}, F=1 /",
        f"&VENT XB={x0:g},{x1:g},{y0:g},{y1:g},0,0, SURF_ID='BURNER' /",
    ]
    if config.scene_type == "indoor":
        half = max(1, round(0.4 / dx)) * dx
        center = round(lx / 2 / dx) * dx
        height = round(2 / dx) * dx
        lines.append(f"&VENT XB={center-half:g},{center+half:g},0,0,0,{height:g}, SURF_ID='OPEN' /")
    else:
        if config.wind_m_s:
            # Negative VEL is into the domain at a boundary.
            lines.append(f"&SURF ID='WIND', VEL={-abs(config.wind_m_s):g}, TMP_FRONT={config.ambient_temperature_c:g} /")
            inlet = "XMIN" if config.wind_m_s > 0 else "XMAX"
        else:
            inlet = None
        for face in ("XMIN", "XMAX", "YMIN", "YMAX", "ZMAX"):
            surf = "WIND" if face == inlet else "OPEN"
            lines.append(f"&VENT MB='{face}', SURF_ID='{surf}' /")
    from .fds_weather import rain_input
    lines += rain_input(config)
    lines += [
        f"&DEVC ID='T_CENTER', XYZ={config.fire_center_m[0]:g},{config.fire_center_m[1]:g},1.5, QUANTITY='TEMPERATURE' /",
        f"&SLCF PBY={ly/2:g}, QUANTITY='TEMPERATURE' /",
        f"&SLCF PBY={ly/2:g}, QUANTITY='DENSITY', SPEC_ID='SOOT' /",
        f"&SLCF PBY={ly/2:g}, QUANTITY='VELOCITY', VECTOR=.TRUE. /",
        f"&SLCF XB=0,{lx:g},0,{ly:g},0,{lz:g}, QUANTITY='TEMPERATURE' /",
        f"&SLCF XB=0,{lx:g},0,{ly:g},0,{lz:g}, QUANTITY='DENSITY', SPEC_ID='SOOT' /",
        f"&SLCF XB=0,{lx:g},0,{ly:g},0,{lz:g}, QUANTITY='HRRPUV' /",
        "&TAIL /", "",
    ]
    return "\n".join(lines)


def read_hrr(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.reader(Path(path).read_text(encoding="utf-8-sig").splitlines()))
    header_index = next((i for i, row in enumerate(rows) if "Time" in [x.strip() for x in row] and "HRR" in [x.strip() for x in row]), None)
    if header_index is None:
        raise ValueError("FDS CSV must contain Time and HRR columns")
    header = [x.strip() for x in rows[header_index]]
    it, iq = header.index("Time"), header.index("HRR")
    pairs = [(float(row[it]), float(row[iq])) for row in rows[header_index+1:] if row and any(x.strip() for x in row)]
    if len(pairs) < 2:
        raise ValueError("FDS HRR CSV has fewer than two observations")
    values = np.array(pairs)
    if not np.isfinite(values).all() or np.any(np.diff(values[:, 0]) <= 0) or np.any(values[:, 1] < 0):
        raise ValueError("HRR observations must be finite, nonnegative and strictly time-ordered")
    return values[:, 0], values[:, 1]


def visual_hrr(config: SceneConfig, time_s: float, hrr_csv: Path | None = None) -> dict:
    if not math.isfinite(time_s) or not 0 <= time_s <= config.duration_s:
        raise ValueError("Time is outside the configured interval")
    if hrr_csv:
        times, hrr = read_hrr(hrr_csv)
        if time_s < times[0] or time_s > times[-1] + 1e-6:
            raise ValueError("Requested time is not covered by FDS output; extrapolation is forbidden")
        value = float(np.interp(time_s, times, hrr))
        source = "fds_hrr_csv"
    else:
        value = config.requested_hrr(time_s)
        source = "configured_hrr_not_solved"
    return {
        "time_s": time_s, "hrr_kw": value, "source": source,
        "relative_strength": float(np.clip(value / 100.0, 0.0, 3.0)),
        "mapping": "clip(HRR_kW / 100, 0, 3)",
        "limitation": "Visual proxy only; temperature, soot and velocity fields are not imported into the renderer.",
    }


def run_fds(config: SceneConfig, directory: Path, executable: str, timeout: float = 1800) -> Path:
    resolved = shutil.which(executable) or (str(Path(executable).resolve()) if Path(executable).is_file() else None)
    if not resolved:
        raise RuntimeError("FDS executable not found; set --fds-exe or FDS_EXE")
    if any(directory.iterdir()):
        raise ValueError("FDS working directory must be empty to avoid stale outputs")
    input_path = directory / f"{config.scene_id}.fds"
    input_path.write_text(fds_input(config), encoding="utf-8")
    state = {"status": "running", "executable": resolved, "input": input_path.name}
    write_json(directory / "execution.json", state)
    try:
        with (directory / "solver.log").open("w", encoding="utf-8") as log:
            process = subprocess.run([resolved, input_path.name], cwd=directory, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        if process.returncode:
            raise RuntimeError(f"FDS exited {process.returncode}; inspect solver.log")
        csv_path = directory / f"{config.scene_id}_hrr.csv"
        times, _ = read_hrr(csv_path)
        if times[-1] < config.duration_s - 0.11:
            raise RuntimeError("FDS stopped before the configured end time")
    except Exception as exc:
        write_json(directory / "execution.json", {**state, "status": "failed", "error": str(exc)})
        raise
    write_json(directory / "execution.json", {**state, "status": "success", "last_time_s": float(times[-1])})
    return csv_path
