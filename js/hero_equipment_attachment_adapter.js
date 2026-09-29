/**
 * MAIN_HAND/OFF_HAND lifecycle adapter for the F-owned shared Hero host.
 *
 * This module owns no renderer, character root, catalog, item mapping,
 * ownership, or equip authority. F validates the current character snapshot;
 * callers supply an exact presentation ID and the already-validated snapshot.
 */

export const HERO_EQUIPMENT_ATTACHMENT_CONTRACT = "HERO_EQUIPMENT_ATTACHMENT_V1";
export const HERO_HAND_ATTACHMENT_SLOTS = Object.freeze(["MAIN_HAND", "OFF_HAND"]);

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  throw error;
}

function requireCharacterAuthority(snapshot) {
  const characterKey = typeof snapshot?.character_key === "string"
    ? snapshot.character_key.trim() : "";
  if (!characterKey
    || snapshot.character_key_source !== "player_appearance.character_key"
    || snapshot.character_key_authority !== "player_appearance.character_key"
    || snapshot.character_entitled !== true
    || snapshot.character_runtime?.character_key !== characterKey) {
    fail("CHARACTER_AUTHORITY_REQUIRED", "validated player_appearance.character_key context is required");
  }
  return characterKey;
}

function requireDescriptor(descriptor, allowTestOnlyDescriptors) {
  if (!isRecord(descriptor)) {
    fail("PRESENTATION_DESCRIPTOR_REQUIRED", "resolved presentation descriptor is required");
  }
  if (descriptor.test_only === true && !allowTestOnlyDescriptors) {
    fail("TEST_ONLY_DESCRIPTOR_REJECTED", "TEST ONLY presentation descriptors are disabled");
  }
  if (typeof descriptor.presentation_id !== "string" || !descriptor.presentation_id.trim()) {
    fail("PRESENTATION_ID_REQUIRED", "exact presentation_id is required");
  }
  return descriptor;
}

export class HeroEquipmentAttachmentAdapter {
  constructor({ sharedHost, loadPresentation, allowTestOnlyDescriptors = false } = {}) {
    if (!sharedHost || typeof sharedHost.attach !== "function" || typeof sharedHost.detach !== "function") {
      fail("SHARED_HOST_REQUIRED", "F-owned shared Hero slot host is required");
    }
    if (typeof loadPresentation !== "function") {
      fail("PRESENTATION_LOADER_REQUIRED", "presentation loader is required");
    }
    this.sharedHost = sharedHost;
    this.loadPresentation = loadPresentation;
    this.allowTestOnlyDescriptors = allowTestOnlyDescriptors === true;
    this.disposed = false;
  }

  async setHand(slot, descriptor, playerAppearance) {
    if (!HERO_HAND_ATTACHMENT_SLOTS.includes(slot)) {
      fail("UNSUPPORTED_ATTACHMENT_SLOT", "only MAIN_HAND and OFF_HAND are owned by this adapter");
    }
    if (descriptor == null) return this.detach(slot);
    if (this.disposed) return { status: "disposed", slot, contract_version: HERO_EQUIPMENT_ATTACHMENT_CONTRACT };

    const safeDescriptor = requireDescriptor(descriptor, this.allowTestOnlyDescriptors);
    const characterKey = requireCharacterAuthority(playerAppearance);
    const result = await this.sharedHost.attach(
      slot,
      safeDescriptor.presentation_id,
      (hostResolvedDescriptor) => this.loadPresentation(hostResolvedDescriptor, {
        slot,
        character_key: characterKey,
      }),
    );
    return { ...result, contract_version: HERO_EQUIPMENT_ATTACHMENT_CONTRACT };
  }

  detach(slot) {
    if (!HERO_HAND_ATTACHMENT_SLOTS.includes(slot)) {
      fail("UNSUPPORTED_ATTACHMENT_SLOT", "only MAIN_HAND and OFF_HAND are owned by this adapter");
    }
    if (this.disposed) return { status: "disposed", slot, contract_version: HERO_EQUIPMENT_ATTACHMENT_CONTRACT };
    return { ...this.sharedHost.detach(slot), contract_version: HERO_EQUIPMENT_ATTACHMENT_CONTRACT };
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    // The Hero renderer owns host disposal. This adapter may release only its
    // two hand slots and never destroys the shared host or another child.
    for (const slot of HERO_HAND_ATTACHMENT_SLOTS) {
      try {
        this.sharedHost.detach(slot);
      } catch (_) {
        // A host already destroyed by F has already invalidated these children.
      }
    }
  }
}

export function createHeroEquipmentAttachmentAdapter(runtime, options = {}) {
  if (!runtime || typeof runtime !== "object") {
    fail("RUNTIME_REQUIRED", "Hero shared-host runtime interface is required");
  }
  const sharedHost = options.sharedHost || runtime.getHeroSharedAttachmentHost?.() || null;
  return new HeroEquipmentAttachmentAdapter({ ...options, sharedHost });
}
