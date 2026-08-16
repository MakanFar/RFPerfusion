"""Tiny synthetic structures for T1 tests -- no network, no real PDB/AlphaFold
files. Every structure here is built atom-by-atom with biotite and written to
a temp file, so tests exercise the real PDB/CIF readers without fetching
anything.
"""
from __future__ import annotations
import numpy as np
import biotite.structure as struc
import biotite.structure.io.pdb as pdb
import biotite.structure.io.pdbx as pdbx


def _residue(chain_id, res_id, res_name, atoms, b_factor):
    """Build a one-residue AtomArray from an {atom_name: [x,y,z]} dict."""
    n = len(atoms)
    arr = struc.AtomArray(n)
    arr.chain_id = np.array([chain_id] * n)
    arr.res_id = np.array([res_id] * n)
    arr.res_name = np.array([res_name] * n)
    arr.atom_name = np.array(list(atoms.keys()))
    arr.element = np.array(["N" if name in ("N", "NZ") else name[0] for name in atoms.keys()])
    arr.coord = np.array(list(atoms.values()), dtype=float)
    arr.hetero = np.array([False] * n)
    arr.set_annotation("b_factor", np.array([b_factor] * n, dtype=float))
    return arr


def asp_residue(chain_id, res_id, b_factor, x0=0.0):
    """ASP with a carboxylate (OD1/OD2) that can salt-bridge with a nearby amine."""
    return _residue(chain_id, res_id, "ASP", {
        "N": [x0 + 0, 0, 0], "CA": [x0 + 1, 0, 0], "C": [x0 + 2, 0, 0], "O": [x0 + 2, 1, 0],
        "CB": [x0 + 1, 1, 0], "CG": [x0 + 1, 2, 0],
        "OD1": [x0 + 0, 2.5, 0], "OD2": [x0 + 2, 2.5, 0],
    }, b_factor)


def lys_residue(chain_id, res_id, b_factor, x0=0.0):
    """LYS with an NZ amine placed ~1-2 A from the paired ASP's carboxylate."""
    return _residue(chain_id, res_id, "LYS", {
        "N": [x0 + 3, 0, 0], "CA": [x0 + 4, 0, 0], "C": [x0 + 5, 0, 0], "O": [x0 + 5, 1, 0],
        "CB": [x0 + 4, 1, 0], "CG": [x0 + 4, 2, 0], "CD": [x0 + 4, 3, 0], "CE": [x0 + 4, 4, 0],
        "NZ": [x0 + 1.5, 3.0, 0],
    }, b_factor)


def salt_bridge_pair(chain_id, b_factor, x0=0.0, res_offset=0):
    """One ASP-LYS ion pair on a single chain, well within the 4 A cutoff."""
    return asp_residue(chain_id, 1 + res_offset, b_factor, x0) + \
        lys_residue(chain_id, 2 + res_offset, b_factor, x0)


def write_pdb(atom_array, path):
    f = pdb.PDBFile()
    f.set_structure(atom_array)
    f.write(str(path))
    return str(path)


def write_cif(atom_array, path, data_block="TEST"):
    f = pdbx.CIFFile()
    pdbx.set_structure(f, atom_array, data_block=data_block)
    f.write(str(path))
    return str(path)
