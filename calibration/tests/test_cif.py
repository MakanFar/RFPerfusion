from calib import cif

# Three residues resolved in chain A of model 1, plus decoys the count must
# ignore: a side-chain atom, a second chain, a second model, and a ligand.
CIF = """data_7ABC
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.type_symbol
_atom_site.label_atom_id
_atom_site.label_comp_id
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.pdbx_PDB_model_num
ATOM 1 N N MET A 1 1
ATOM 2 C CA MET A 1 1
ATOM 3 C CB MET A 1 1
ATOM 4 C CA GLY A 2 1
ATOM 5 C CA LYS A 3 1
ATOM 6 C CA SER B 1 1
ATOM 7 C CA MET A 1 2
HETATM 8 O O HOH C 1 1
#
"""


def test_the_count_is_resolved_residues_of_the_first_chain_and_model():
    """`query_length` is the sequence ESMFold was handed; `reference_length`
    is what the experiment actually resolved. They differ whenever a loop is
    disordered, and a reviewer needs both to see whether a high TM-score was
    earned over the whole chain or over the part that happened to be there."""
    assert cif.count_residues(CIF) == 3


def test_a_cif_without_an_atom_site_loop_reports_unknown_not_zero():
    """Zero would read as a truncated structure and quietly invite a wrong
    conclusion; None says the parse did not answer."""
    assert cif.count_residues("data_7ABC\n#\n_entry.id 7ABC\n") is None
