"""Units and validation for the parameterized physical/visual scene."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math
import re
from typing import Any


@dataclass(frozen=True)
class SceneConfig:
    scene_id: str = "room_demo"
    scene_type: str = "indoor"
    room_size_m: tuple[float, float, float] = (4.0, 4.0, 3.0)
    cell_size_m: float = 0.2
    fire_center_m: tuple[float, float] = (2.0, 2.0)
    fire_size_m: tuple[float, float] = (0.8, 0.8)
    peak_hrr_kw: float = 100.0
    duration_s: float = 5.0
    ramp_up_s: float = 2.0
    ambient_temperature_c: float = 20.0
    wind_m_s: float = 0.0
    ambient_relative_humidity_pct: float = 40.0
    physical_weather: str = "晴"
    rain_mm_h: float = 0.0
    rain_diameter_um: float = 1000.0
    seed: int = 42
    width: int = 384
    height: int = 384
    render_samples: int = 48
    camera_angles_deg: tuple[float, ...] = (25.0, 65.0)
    weather: tuple[str, ...] = ("clear", "fog")
    plume_steps: int = 45
    particles_per_step: int = 10
    editor_scene: dict | None = None
    output_frames: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SceneConfig":
        unknown = set(raw) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown configuration fields: {sorted(unknown)}")
        converted = dict(raw)
        for key in ("room_size_m", "fire_center_m", "fire_size_m", "camera_angles_deg", "weather"):
            if key in converted:
                converted[key] = tuple(converted[key])
        result = cls(**converted)
        result.validate()
        return result

    def validate(self) -> None:
        from .fds_weather import validate_weather
        validate_weather(self)
        if self.output_frames is not None and (type(self.output_frames)!=int or not 2<=self.output_frames<=48):raise ValueError('FDS输出帧数应为2至48')
        if self.editor_scene is not None:
            from .editor_contract import normalize_scene
            normalize_scene(self.editor_scene)
        if not isinstance(self.scene_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", self.scene_id):
            raise ValueError("scene_id must be a safe ASCII identifier")
        if self.scene_type not in {"indoor", "outdoor"}:
            raise ValueError("scene_type must be indoor or outdoor")
        for key, length in (("room_size_m", 3), ("fire_center_m", 2), ("fire_size_m", 2)):
            value = getattr(self, key)
            if len(value) != length or any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in value):
                raise ValueError(f"Invalid {key}")
        for key in ("cell_size_m", "peak_hrr_kw", "duration_s", "ramp_up_s", "ambient_temperature_c", "wind_m_s"):
            value = getattr(self, key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"Invalid finite numeric value for {key}")
        if min(self.room_size_m + self.fire_size_m) <= 0 or self.cell_size_m <= 0:
            raise ValueError("Room, fire and cell dimensions must be positive")
        if self.peak_hrr_kw <= 0 or not 0 < self.ramp_up_s < self.duration_s <= 3600:
            raise ValueError("Require positive HRR and 0 < ramp_up_s < duration_s <= 3600")
        if not -30 <= self.ambient_temperature_c <= 60 or abs(self.wind_m_s) > 15:
            raise ValueError("Ambient temperature or wind exceeds supported range")
        if self.scene_type == "indoor" and self.wind_m_s != 0:
            raise ValueError("Indoor imposed wind is unsupported; use ventilation boundaries")
        if any(x / self.cell_size_m < 4 or abs(x / self.cell_size_m - round(x / self.cell_size_m)) > 1e-6 for x in self.room_size_m):
            raise ValueError("Room dimensions must be integer multiples of cell size, at least four cells each")
        for center, size, limit in zip(self.fire_center_m, self.fire_size_m, self.room_size_m):
            for edge in (center - size / 2, center + size / 2):
                if not 0 < edge < limit or abs(edge / self.cell_size_m - round(edge / self.cell_size_m)) > 1e-6:
                    raise ValueError("Burner edges must lie inside the room and align with the FDS grid")
        if self.scene_type == "indoor" and (min(self.room_size_m[:2]) < 2 or self.room_size_m[2] < 2.4):
            raise ValueError("Indoor template requires at least 2x2x2.4 m for its doorway")
        for key in ("seed", "width", "height", "render_samples", "plume_steps", "particles_per_step"):
            if not isinstance(getattr(self, key), int) or isinstance(getattr(self, key), bool):
                raise ValueError(f"{key} must be an integer")
        if not 64 <= self.width <= 2048 or not 64 <= self.height <= 2048:
            raise ValueError("Image dimensions must be between 64 and 2048")
        if not 16 <= self.render_samples <= 128:
            raise ValueError('Render samples must be between 16 and 128')
        if not 0 <= self.seed < 2**31:
            raise ValueError("seed must be in [0, 2**31)")
        if not 1 <= self.plume_steps <= 500 or not 1 <= self.particles_per_step <= 100:
            raise ValueError("Plume step/particle budget exceeded")
        if not self.camera_angles_deg or any(not isinstance(x, (int, float)) or not math.isfinite(x) or not 5 <= x <= 175 for x in self.camera_angles_deg):
            raise ValueError("Provide camera angles between 5 and 175 degrees")
        if not self.weather or any(x not in {"clear", "fog"} for x in self.weather):
            raise ValueError("Supported visual conditions: clear, fog")

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def burner_bounds(self) -> tuple[float, float, float, float]:
        x, y = self.fire_center_m
        w, d = self.fire_size_m
        return x - w / 2, x + w / 2, y - d / 2, y + d / 2

    def requested_hrr(self, time_s: float) -> float:
        return self.peak_hrr_kw * min(1.0, max(0.0, time_s / self.ramp_up_s))
