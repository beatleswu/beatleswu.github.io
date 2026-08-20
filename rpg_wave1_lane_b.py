"""Small, pure helpers for RPG Wave 1 Lane B.

These helpers describe player-visible level rewards and the server-owned
monster encounter profile.  They do not write XP, grant attribute points, or
accept combat values from a client.
"""


def battlefield_profile(roster, monster_idx):
    """Return the authoritative profile for one roster entry.

    The application owns the roster and persists only the current encounter
    index/state.  Keeping the lookup here makes it explicit that retaliation
    values come from the server definition rather than review payload data.
    """

    if not roster:
        raise ValueError("monster roster must not be empty")
    index = int(monster_idx or 0) % len(roster)
    entry = roster[index]
    if len(entry) < 4:
        raise ValueError("monster roster entries require type, name, HP, and attack")
    return {
        "index": index,
        "type": entry[0],
        "name": entry[1],
        "max_hp": int(entry[2]),
        "attack": int(entry[3]),
        "encounter_kind": entry[4] if len(entry) > 4 else "normal",
        "stage": index // 2 + 1,
    }


def build_level_up_rewards(
    old_lv,
    new_lv,
    old_max_hp,
    new_max_hp,
    *,
    skill_unlocks=(),
    appearance_items=(),
):
    """Build a presentation-only summary for a completed level-up.

    The helper intentionally reports eligibility and already-settled
    appearance items.  It does not mutate inventory, skills, attributes, or
    XP, so it cannot create another progression authority.
    """

    old_lv = int(old_lv)
    new_lv = int(new_lv)
    old_max_hp = int(old_max_hp)
    new_max_hp = int(new_max_hp)
    hp_gain = max(0, new_max_hp - old_max_hp)
    skills = [dict(item) for item in skill_unlocks]
    appearance = [dict(item) for item in appearance_items]

    rewards = []
    if hp_gain:
        rewards.append({
            "kind": "hp",
            "value": hp_gain,
            "max_hp": new_max_hp,
        })
    for skill in skills:
        rewards.append({
            "kind": "skill_eligibility",
            "id": skill.get("id"),
            "name": skill.get("name", skill.get("id")),
            "name_en": skill.get("name_en", skill.get("name", skill.get("id"))),
        })
    for item in appearance:
        rewards.append({
            "kind": "appearance",
            "id": item.get("id"),
            "name": item.get("name", item.get("id")),
            "name_en": item.get("name_en", item.get("name", item.get("id"))),
        })

    return {
        "from_level": old_lv,
        "to_level": new_lv,
        "max_hp_before": old_max_hp,
        "max_hp_after": new_max_hp,
        "max_hp_gain": hp_gain,
        "skill_unlocks": skills,
        "appearance_items": appearance,
        "rewards": rewards,
        "attribute_points": 0,
    }
