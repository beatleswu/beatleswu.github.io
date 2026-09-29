const HAND_SLOTS = Object.freeze(["MAIN_HAND", "OFF_HAND"]);

function record(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function serverSlot(value) {
  const slot = String(value || "").trim().toLowerCase().replace(/[ -]+/g, "_");
  if (["weapon", "main_hand", "mainhand"].includes(slot)) return "MAIN_HAND";
  if (["off_hand", "offhand", "shield"].includes(slot)) return "OFF_HAND";
  return null;
}

function serverItemId(row) {
  for (const value of [row?.item_id, row?.id]) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

/**
 * Project only the authenticated inventory's equipped rows through an
 * authority-supplied exact server-item resolver. Unknown/duplicate rows block
 * their slot. Names, filenames, asset IDs, and display similarity are ignored.
 */
export function projectServerEquippedHandItems(inventory, resolveServerItem) {
  if (!Array.isArray(inventory) || typeof resolveServerItem !== "function") {
    return Object.freeze({
      status: "failed_closed",
      slots: Object.freeze(HAND_SLOTS.map((slot) => Object.freeze({
        slot, status: "failed_closed", reason: "inventory_projection_input_invalid",
      }))),
    });
  }

  const candidates = new Map(HAND_SLOTS.map((slot) => [slot, []]));
  for (const row of inventory) {
    if (!record(row) || row.equipped !== true) continue;
    const slot = serverSlot(row.slot);
    if (!slot) continue;
    const itemId = serverItemId(row);
    let descriptor = null;
    if (itemId) {
      try {
        descriptor = resolveServerItem(itemId, slot) || null;
      } catch (_) {
        descriptor = null;
      }
    }
    candidates.get(slot).push({ row, itemId, descriptor });
  }

  const slots = HAND_SLOTS.map((slot) => {
    const rows = candidates.get(slot);
    if (rows.length === 0) return Object.freeze({ slot, status: "empty" });
    if (rows.length !== 1) {
      return Object.freeze({ slot, status: "failed_closed", reason: "duplicate_equipped_slot" });
    }
    const [{ row, itemId, descriptor }] = rows;
    if (!itemId || !record(descriptor) || descriptor.slot !== slot
      || descriptor.server_item_id !== itemId
      || typeof descriptor.presentation_id !== "string" || !descriptor.presentation_id.trim()) {
      return Object.freeze({ slot, status: "failed_closed", reason: "equipped_item_unmapped" });
    }
    return Object.freeze({ slot, status: "resolved", item_id: itemId, descriptor, row });
  });

  return Object.freeze({
    status: slots.some((result) => result.status === "failed_closed") ? "failed_closed" : "projected",
    slots: Object.freeze(slots),
  });
}
