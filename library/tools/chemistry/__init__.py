"""Chemistry tools — Deterministic chemistry toolkit (14 tools).

Pure Python, zero LLM. Adapted from Mia_Brain (captn/tools/chemistry_tools.py).
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List

ATOMIC_MASS = {
    "H": 1.008, "He": 4.003, "Li": 6.941, "Be": 9.012, "B": 10.811,
    "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.086, "P": 30.974,
    "S": 32.065, "Cl": 35.453, "Ar": 39.948, "K": 39.098, "Ca": 40.078,
    "Fe": 55.845, "Cu": 63.546, "Zn": 65.380, "Br": 79.904, "Ag": 107.868,
    "I": 126.904, "Pt": 195.084, "Au": 196.967, "Hg": 200.592, "Pb": 207.200,
}


def molar_mass(formula: str) -> Dict[str, Any]:
    total = 0.0
    parts = []
    for el, cnt in re.findall(r"([A-Z][a-z]*)([0-9]*)", formula):
        if not el:
            continue
        if el not in ATOMIC_MASS:
            return {"valid": False, "error": f"Unknown {el}"}
        c = float(cnt) if cnt else 1.0
        m = ATOMIC_MASS[el] * c
        total += m
        parts.append({"el": el, "count": c, "mass": round(m, 4)})
    return {"valid": True, "formula": formula, "molar_mass": round(total, 4), "unit": "g/mol", "elements": parts}


def ph(H_conc=None, pH=None) -> Dict[str, Any]:
    if H_conc is not None:
        if H_conc <= 0:
            return {"valid": False, "error": "[H+]>0"}
        return {"valid": True, "H+": H_conc, "pH": round(-math.log10(H_conc), 4), "pOH": round(14 + math.log10(H_conc), 4)}
    if pH is not None:
        return {"valid": True, "pH": pH, "H+": f"{10**(-pH):.6e}", "pOH": round(14 - pH, 4)}
    return {"valid": False, "error": "give [H+] or pH"}


def dilution(C1=None, V1=None, C2=None, V2=None) -> Dict[str, Any]:
    if C1 is None or C1 <= 0:
        return {"valid": False, "error": "C1>0"}
    if V1 and C2 and not V2:
        return {"valid": True, "V2": C1 * V1 / C2}
    if V1 and V2 and not C2:
        return {"valid": True, "C2": C1 * V1 / V2}
    if C2 and V2 and not V1:
        return {"valid": True, "V1": C2 * V2 / C1}
    return {"valid": False, "error": "C1 + 2 others"}


def mole(mass=0, molar_mass=1) -> Dict[str, Any]:
    if molar_mass <= 0:
        return {"valid": False, "error": "M>0"}
    return {"valid": True, "mass": mass, "molar_mass": molar_mass, "moles": mass / molar_mass, "unit": "mol"}


def concentration(moles=0, volume=1) -> Dict[str, Any]:
    if volume <= 0:
        return {"valid": False, "error": "V>0"}
    return {"valid": True, "moles": moles, "volume": volume, "concentration": moles / volume, "unit": "M"}


def yield_(actual=0, theoretical=1) -> Dict[str, Any]:
    if theoretical <= 0:
        return {"valid": False, "error": "theoretical>0"}
    pct = actual / theoretical * 100
    tag = "good" if pct >= 80 else "average" if pct >= 50 else "low"
    return {"valid": True, "actual": actual, "theoretical": theoretical, "yield": round(pct, 2), "unit": "%", "rating": tag}


def arrhenius(A=0, Ea=0, T=298, R=8.314) -> Dict[str, Any]:
    k = A * math.exp(-Ea / (R * T))
    return {"valid": True, "A": A, "Ea": Ea, "T": T, "k": round(k, 6), "ln_k": round(math.log(k), 6)}


def equilibrium(K=None, Q=None) -> Dict[str, Any]:
    if K is None or Q is None:
        return {"valid": False, "error": "K and Q required"}
    return {"valid": True, "K": K, "Q": Q, "direction": "->" if Q < K else "<-" if Q > K else "<=>"}


def nernst(E0=0, n=1, Q=1, T=298.15) -> Dict[str, Any]:
    R, F = 8.314, 96485
    E = E0 - (R * T / (n * F)) * math.log(Q)
    return {"valid": True, "E0": E0, "n": n, "Q": Q, "E": round(E, 6), "unit": "V"}


def half_life(decay_const=None, t_half=None) -> Dict[str, Any]:
    if decay_const and not t_half:
        return {"valid": True, "half_life": math.log(2) / decay_const, "unit": "s"}
    if t_half and not decay_const:
        return {"valid": True, "decay_const": math.log(2) / t_half, "unit": "s^-1"}
    return {"valid": False, "error": "give lambda or t_1/2"}


def enthalpy(bonds_broken=0, bonds_formed=0) -> Dict[str, Any]:
    dh = bonds_broken - bonds_formed
    return {"valid": True, "delta_H": dh, "unit": "kJ/mol", "exothermic": dh < 0}


def entropy(Q_rev=0, T=298) -> Dict[str, Any]:
    if T <= 0:
        return {"valid": False, "error": "T>0"}
    return {"valid": True, "delta_S": Q_rev / T, "unit": "J/K"}


def gibbs(H=0, T=298, S=0) -> Dict[str, Any]:
    G = H - T * S / 1000
    return {"valid": True, "delta_G": round(G, 4), "unit": "kJ/mol", "spontaneous": G < 0}


def reaction_rate(k=0, concentrations=None, orders=None) -> Dict[str, Any]:
    if not concentrations:
        concentrations = {"A": 1.0}
    if not orders:
        orders = {"A": 1}
    rate = k
    for sp, conc in concentrations.items():
        rate *= conc ** orders.get(sp, 0)
    return {"valid": True, "rate": round(rate, 6), "k": k, "total_order": sum(orders.values())}


CHEMISTRY_TOOLS: Dict[str, Dict[str, Any]] = {
    "molar_mass": {"fn": molar_mass, "desc": "Molar mass from formula"},
    "ph": {"fn": ph, "desc": "pH <-> [H+]"},
    "dilution": {"fn": dilution, "desc": "C1V1=C2V2"},
    "mole": {"fn": mole, "desc": "n=m/M"},
    "concentration": {"fn": concentration, "desc": "C=n/V"},
    "yield": {"fn": yield_, "desc": "Yield %"},
    "arrhenius": {"fn": arrhenius, "desc": "k=A*exp(-Ea/RT)"},
    "equilibrium": {"fn": equilibrium, "desc": "K vs Q direction"},
    "nernst": {"fn": nernst, "desc": "E=E0-RT/nF.ln(Q)"},
    "half_life": {"fn": half_life, "desc": "t_1/2=ln2/lambda"},
    "enthalpy": {"fn": enthalpy, "desc": "dH=bonds_broken-bonds_formed"},
    "entropy": {"fn": entropy, "desc": "dS=Q_rev/T"},
    "gibbs": {"fn": gibbs, "desc": "dG=dH-TdS"},
    "reaction_rate": {"fn": reaction_rate, "desc": "v=k*prod([C]^order)"},
}


def list_tools() -> List[Dict[str, str]]:
    return [{"name": k, "description": v["desc"]} for k, v in CHEMISTRY_TOOLS.items()]


def execute(tool_name: str, **kwargs) -> Dict[str, Any]:
    """Execute a chemistry tool by name with kwargs."""
    if tool_name not in CHEMISTRY_TOOLS:
        return {"valid": False, "error": f"Unknown tool: {tool_name}"}
    fn = CHEMISTRY_TOOLS[tool_name]["fn"]
    try:
        result = fn(**kwargs)
        return result
    except Exception as e:
        return {"valid": False, "error": str(e)}
