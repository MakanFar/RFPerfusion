"""Counting the residues an experimental structure actually resolved.

Lives here rather than in `runner/run_chain.py` for the same reason the
TM-score selection does: the runner cannot be exercised offline, so anything
in it that could be silently wrong is uncatchable. This is pure text in,
integer out, so it is testable and tested.

The figure is recorded, never gated on. `query_length` is the sequence
ESMFold was handed; `reference_length` is what the crystal actually showed.
They differ whenever a loop is disordered, and a reviewer needs both to tell
whether a high TM-score was earned over the whole chain.
"""

_ATOM_SITE = "_atom_site."


def count_residues(cif_text):
    """CA atoms in the first chain of the first model, or None.

    None rather than 0 when the loop is absent or unrecognised: 0 would read
    as a truncated structure and invite a wrong conclusion, where None says
    the parse did not answer.
    """
    columns = {}
    counted = set()
    asym = model = None
    for line in cif_text.splitlines():
        line = line.strip()
        if line.startswith(_ATOM_SITE):
            columns[line[len(_ATOM_SITE):].split()[0]] = len(columns)
            continue
        if not columns or not line.startswith(("ATOM ", "HETATM ")):
            continue
        fields = line.split()
        if len(fields) < len(columns):
            continue

        def at(name):
            i = columns.get(name)
            return fields[i] if i is not None else None

        if at("label_atom_id") != "CA":
            continue
        if asym is None:
            asym, model = at("label_asym_id"), at("pdbx_PDB_model_num")
        if (at("label_asym_id"), at("pdbx_PDB_model_num")) != (asym, model):
            continue
        counted.add(at("label_seq_id") or at("auth_seq_id") or len(counted))
    return len(counted) if counted else None
