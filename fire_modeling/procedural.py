"""CPU smoke-test renderer: buoyant particles, NOT a validated CFD solver."""
from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageDraw

from .config import SceneConfig


def simulate_plume(config: SceneConfig, seed: int, strength: float) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    position = np.empty((0, 3))
    velocity = np.empty((0, 3))
    heat = np.empty(0)
    dt = 0.05
    for _ in range(config.plume_steps):
        n = config.particles_per_step
        fresh = np.column_stack([
            rng.normal(config.fire_center_m[0], config.fire_size_m[0]/5, n),
            rng.normal(config.fire_center_m[1], config.fire_size_m[1]/5, n),
            rng.uniform(0.02, 0.12, n),
        ])
        position = np.concatenate((position, fresh))
        velocity = np.concatenate((velocity, np.tile([config.wind_m_s, 0, 0.3], (n, 1))))
        heat = np.concatenate((heat, rng.uniform(750, 1200, n) * min(strength, 2)))
        # Reduced buoyancy + drag + turbulent random walk, not Navier-Stokes.
        velocity[:, 2] += 9.81 * heat / (273.15 + config.ambient_temperature_c + heat) * dt
        velocity[:, :2] += rng.normal(0, 0.12, (len(heat), 2)) * math.sqrt(dt)
        velocity *= 0.97
        position += velocity * dt
        heat *= math.exp(-0.9 * dt)
        inside = (position[:, 2] < config.room_size_m[2]) & (heat > 180)
        position, velocity, heat = position[inside], velocity[inside], heat[inside]
    return {"position_m": position, "velocity_m_s": velocity, "temperature_excess_k": heat}


def camera_basis(config: SceneConfig, angle: float):
    target = np.array([*config.fire_center_m, 0.75])
    theta = math.radians(angle)
    radius=.4*min(config.room_size_m[:2])
    camera = target + np.array([radius * math.cos(theta), -radius * math.sin(theta), 0.8])
    forward = target - camera
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 0, 1])
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return camera, forward, right, up


def project(points: np.ndarray, config: SceneConfig, angle: float):
    camera, forward, right, up = camera_basis(config, angle)
    relative = points - camera
    depth = relative @ forward
    focal = config.width * 0.85
    xy = np.column_stack([
        config.width / 2 + focal * (relative @ right) / np.maximum(depth, 0.01),
        config.height / 2 - focal * (relative @ up) / np.maximum(depth, 0.01),
    ])
    return xy, depth, focal


def render(config: SceneConfig, seed: int, angle: float, weather: str, strength: float, positive: bool):
    rng = np.random.default_rng(seed)
    h, w = config.height, config.width
    background = Image.new("RGB", (w, h), (77, 83, 91) if config.scene_type == "indoor" else (133, 163, 172))
    draw = ImageDraw.Draw(background)
    if config.scene_type == "indoor":
        draw.polygon([(0, h*.62), (w*.28, h*.42), (w*.75, h*.42), (w, h*.62), (w,h), (0,h)], fill=(83, 79, 73))
        draw.line([(w*.28,0),(w*.28,h*.42),(0,h*.62)], fill=(42,46,51), width=2)
        draw.line([(w*.75,0),(w*.75,h*.42),(w,h*.62)], fill=(42,46,51), width=2)
    else:
        draw.rectangle((0, h*.5, w, h), fill=(78, 91, 65))
        for _ in range(15):
            x = rng.integers(0,w); y = rng.integers(h//3,h//2)
            draw.polygon([(x-12,y+45),(x,y-25),(x+12,y+45)], fill=(45,75,53))
    # Warm light distractor exists in both positive and negative samples.
    draw.ellipse((w*.1,h*.15,w*.2,h*.25),fill=(205,139,68))
    base = np.asarray(background, dtype=float)/255
    alpha = np.zeros((h,w), dtype=float)
    emission = np.zeros((h,w,3),dtype=float)
    if positive:
        particles = simulate_plume(config, seed, strength)
        xy, depth, focal = project(particles["position_m"],config,angle)
        for (cx,cy),z,temp in zip(xy,depth,particles["temperature_excess_k"]):
            if z <= .05: continue
            radius = float(np.clip(focal * (.04 + .045*temp/1200)/z,2,22))
            x0,x1 = max(0,int(cx-3*radius)),min(w,int(cx+3*radius)+1)
            y0,y1 = max(0,int(cy-3*radius)),min(h,int(cy+3*radius)+1)
            if x1<=x0 or y1<=y0: continue
            yy,xx = np.mgrid[y0:y1,x0:x1]
            a = np.exp(-((xx-cx)**2+(yy-cy)**2)/(2*radius**2)) * min(.5,temp/2200)
            hot = float(np.clip((temp-250)/950,0,1))
            color = np.array([1,.2+.65*hot,.025+.5*hot**3])
            emission[y0:y1,x0:x1] += a[:,:,None]*color
            alpha[y0:y1,x0:x1] = 1-(1-alpha[y0:y1,x0:x1])*(1-a)
    mask = alpha > .25
    image = base*(1-alpha[:,:,None]*.6)+np.clip(emission,0,1)
    if weather == "fog": image = .75*image+.25*np.array([.65,.68,.7])
    image += rng.normal(0,.006,image.shape)
    return Image.fromarray(np.uint8(np.clip(image,0,1)*255)), Image.fromarray(mask.astype("uint8")*255)
