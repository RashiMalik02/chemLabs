# backend/reactions/stream_state.py

CHEMICALS = {
    "HCl":        {"type": "acid",    "label": "Hydrochloric Acid"},
    "H2SO4":      {"type": "acid",    "label": "Sulfuric Acid"},
    "HNO3":       {"type": "acid",    "label": "Nitric Acid"},
    "CitricAcid": {"type": "acid",    "label": "Citric Acid"},
    "AceticAcid": {"type": "acid",    "label": "Acetic Acid"},
    "NaOH":       {"type": "base",    "label": "Sodium Hydroxide"},
    "KOH":        {"type": "base",    "label": "Potassium Hydroxide"},
    "NH3":        {"type": "base",    "label": "Ammonia Solution"},
    "CaOH2":      {"type": "base",    "label": "Calcium Hydroxide"},
    "NaHCO3":     {"type": "base",    "label": "Baking Soda"},
    "Water":      {"type": "neutral", "label": "Distilled Water"},
    "NaClSol":    {"type": "neutral", "label": "Saline Solution"},
    "SugarSol":   {"type": "neutral", "label": "Sugar Solution"},
}

state = {
    "chemical_id":            None,
    "chemical_type":          "neutral",
    "reaction_type":          None,
    "running":                False,
    "reaction_complete_flag": False,
    "owner":                  None,   
}


def set_chemical(chemical_id):
    chem = CHEMICALS.get(chemical_id)
    if not chem:
        return False
    state["chemical_id"]   = chemical_id
    state["chemical_type"] = chem["type"]
    return True


def set_reaction(reaction_type):
    state["reaction_type"] = reaction_type