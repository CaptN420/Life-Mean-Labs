"""Physics tools — Deterministic physics toolkit (15 tools).

Pure Python, zero LLM. Adapted from Mia_Brain (captn/tools/physics_tools.py).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List


def force(mass=None, acceleration=None, momentum=None, time=None) -> Dict[str, Any]:
    if mass is None or mass <= 0:
        return {"valid": False, "error": "mass>0"}
    if acceleration is not None:
        return {"valid": True, "force": mass * acceleration, "unit": "N"}
    if momentum is not None and time is not None and time > 0:
        return {"valid": True, "force": momentum / time, "unit": "N"}
    return {"valid": False, "error": "need acceleration or (momentum,time)"}


def work(force=0, distance=0, angle_deg=0) -> Dict[str, Any]:
    w = force * distance * math.cos(math.radians(angle_deg))
    return {"valid": True, "work": round(w, 6), "unit": "J"}


def power(work=0, time=1) -> Dict[str, Any]:
    if time <= 0:
        return {"valid": False, "error": "time>0"}
    return {"valid": True, "power": work / time, "unit": "W"}


def pressure(force=0, area=1) -> Dict[str, Any]:
    if area <= 0:
        return {"valid": False, "error": "area>0"}
    return {"valid": True, "pressure": force / area, "unit": "Pa"}


def kinetic_energy(mass=0, velocity=0) -> Dict[str, Any]:
    return {"valid": True, "kinetic_energy": 0.5 * mass * velocity ** 2, "unit": "J"}


def potential_energy(mass=0, height=0, g=9.81) -> Dict[str, Any]:
    return {"valid": True, "potential_energy": mass * g * height, "unit": "J"}


def momentum(mass=0, velocity=0) -> Dict[str, Any]:
    return {"valid": True, "momentum": mass * velocity, "unit": "kg.m/s"}


def ohms_law(voltage=None, current=None, resistance=None) -> Dict[str, Any]:
    if voltage is not None and current is not None and resistance is None:
        return {"valid": True, "resistance": voltage / current, "unit": "Ohm"}
    if voltage is not None and resistance is not None and current is None:
        return {"valid": True, "current": voltage / resistance, "unit": "A"}
    if current is not None and resistance is not None and voltage is None:
        return {"valid": True, "voltage": current * resistance, "unit": "V"}
    return {"valid": False, "error": "need 2 of (V,I,R)"}


def wave_speed(freq=None, wavelength=None, speed=None) -> Dict[str, Any]:
    if freq and wavelength and not speed:
        return {"valid": True, "speed": freq * wavelength, "unit": "m/s"}
    if speed and wavelength and not freq:
        return {"valid": True, "freq": speed / wavelength, "unit": "Hz"}
    if speed and freq and not wavelength:
        return {"valid": True, "wavelength": speed / freq, "unit": "m"}
    return {"valid": False, "error": "need 2 of (v,f,lam)"}


def density(mass=0, volume=1) -> Dict[str, Any]:
    if volume <= 0:
        return {"valid": False, "error": "volume>0"}
    return {"valid": True, "density": mass / volume, "unit": "kg/m3"}


def idealgas(P=None, V=None, n=None, T=None, R=8.314) -> Dict[str, Any]:
    known = sum(1 for x in (P, V, n, T) if x is not None)
    if known < 3:
        return {"valid": False, "error": "need 3/4 variables"}
    if P is None:
        P = n * R * T / V
        u = "Pa"
    elif V is None:
        V = n * R * T / P
        u = "m3"
    elif n is None:
        n = P * V / (R * T)
        u = "mol"
    else:
        T = P * V / (n * R)
        u = "K"
    return {"valid": True, "P": P, "V": V, "n": n, "T": T, "unit": u}


def kinematics(v0=0, a=0, t=0) -> Dict[str, Any]:
    return {"valid": True, "v": v0 + a * t, "x": v0 * t + 0.5 * a * t * t}


def coulomb(q1=0, q2=0, r=1, k=8.99e9) -> Dict[str, Any]:
    if r <= 0:
        return {"valid": False, "error": "r>0"}
    return {"valid": True, "force": k * abs(q1 * q2) / (r * r), "unit": "N"}


def specific_heat(mass=0, delta_T=0, Q=None, c=None) -> Dict[str, Any]:
    if Q is None and c is not None:
        return {"valid": True, "Q": mass * c * delta_T, "unit": "J"}
    if c is None and Q is not None:
        return {"valid": True, "c": Q / (mass * delta_T), "unit": "J/(kg.K)"}
    return {"valid": False, "error": "give (m,dT,c) or (m,dT,Q)"}


def kepler(period=None, semi_major=None, central_mass=1.989e30, G=6.674e-11) -> Dict[str, Any]:
    if period and not semi_major:
        a = ((G * central_mass * period ** 2) / (4 * math.pi ** 2)) ** (1 / 3)
        return {"valid": True, "semi_major": a, "period": period}
    if semi_major and not period:
        T = math.sqrt((4 * math.pi ** 2 * semi_major ** 3) / (G * central_mass))
        return {"valid": True, "period": T, "semi_major": semi_major}
    return {"valid": False, "error": "need period OR semi_major"}


PHYSICS_TOOLS: Dict[str, Dict[str, Any]] = {
    "force": {"fn": force, "desc": "F=ma / F=dp/dt"},
    "work": {"fn": work, "desc": "W=F.d"},
    "power": {"fn": power, "desc": "P=W/t"},
    "pressure": {"fn": pressure, "desc": "P=F/A"},
    "kinetic_energy": {"fn": kinetic_energy, "desc": "Ek=0.5mv^2"},
    "potential_energy": {"fn": potential_energy, "desc": "Ep=mgh"},
    "momentum": {"fn": momentum, "desc": "p=mv"},
    "ohms_law": {"fn": ohms_law, "desc": "V=IR"},
    "wave_speed": {"fn": wave_speed, "desc": "v=f*lam"},
    "density": {"fn": density, "desc": "rho=m/V"},
    "idealgas": {"fn": idealgas, "desc": "PV=nRT (SI)"},
    "kinematics": {"fn": kinematics, "desc": "v=v0+at, x=x0+v0t+0.5at^2"},
    "coulomb": {"fn": coulomb, "desc": "F=k.q1.q2/r^2"},
    "specific_heat": {"fn": specific_heat, "desc": "Q=mc.dT"},
    "kepler": {"fn": kepler, "desc": "3rd law: T^2 propto a^3"},
}


def list_tools() -> List[Dict[str, str]]:
    return [{"name": k, "description": v["desc"]} for k, v in PHYSICS_TOOLS.items()]


def execute(tool_name: str, **kwargs) -> Dict[str, Any]:
    """Execute a physics tool by name with kwargs."""
    if tool_name not in PHYSICS_TOOLS:
        return {"valid": False, "error": f"Unknown tool: {tool_name}"}
    fn = PHYSICS_TOOLS[tool_name]["fn"]
    try:
        result = fn(**kwargs)
        return result
    except Exception as e:
        return {"valid": False, "error": str(e)}
