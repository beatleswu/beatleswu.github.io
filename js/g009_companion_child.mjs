// Presentation child only: the shared Hero host owns all scene/node disposal.
export const COMPANION_KEYS = Object.freeze([
  "ink_drop_kelpie", "whispering_void_kit", "star_shell_hatchling",
  "starpath_antlerling", "fatty", "obsidian_bastion",
]);
const SLOT = "COMPANION";
export function stageFromServerLevel(level) {
  if (!Number.isSafeInteger(level) || level < 1) throw new Error("INVALID_PERSISTENT_PET_LEVEL");
  return level >= 25 ? "III" : level >= 10 ? "II" : "I";
}
export function createCompanionChild({
  hero, resolvePresentation = async () => null, loadPresentation,
  fetchImpl = fetch, eventTarget = window, onChange = () => {},
}) {
  let sequence = 0;
  let controller = null;
  let disposed = false;
  let listening = false;
  let descriptor = null;
  let state = Object.freeze({ status: "inactive", pet_key: null, stage: null });
  const publish = value => { state = Object.freeze(value); onChange(state); return state; };
  const resolver = id => descriptor?.presentation_id === id ? descriptor : null;
  const unregisterResolver = hero.registerHeroPresentationResolver(SLOT, resolver);
  const clear = () => {
    sequence++;
    controller?.abort();
    controller = null;
    descriptor = null;
    hero.getHeroSharedAttachmentHost()?.detach(SLOT);
  };
  function suspend() {
    clear();
    if (listening) eventTarget.removeEventListener("g009:companion-status", invalidate);
    listening = false;
    publish({ status: "inactive", pet_key: null, stage: null });
  }
  async function refresh() {
    if (disposed) return state;
    clear(); // invalidates in-flight loads immediately, before the status read
    const token = sequence;
    const host = hero.getHeroSharedAttachmentHost();
    if (!host) return publish({ status: "not_ready", pet_key: null, stage: null });
    const activeController = controller = new AbortController();
    const current = () => !disposed && token === sequence
      && hero.getHeroSharedAttachmentHost() === host && !host.diagnostics().disposed;
    publish({ status: "loading", pet_key: null, stage: null });
    try {
      const response = await fetchImpl("/api/pet/status", {
        credentials: "include", cache: "no-store", signal: activeController.signal,
      });
      if (!response.ok) throw new Error("COMPANION_STATUS_HTTP_" + response.status);
      const snapshot = await response.json();
      if (!current()) return state;
      if (!snapshot || !Object.hasOwn(snapshot, "pet")) throw new Error("COMPANION_STATUS_INVALID");
      if (snapshot.pet === null) return publish({ status: "none", pet_key: null, stage: null });
      const pet = snapshot.pet;
      if (!COMPANION_KEYS.includes(pet?.pet_key)) throw new Error("UNKNOWN_COMPANION_PET_KEY");
      const stage = stageFromServerLevel(pet.level);
      // Only the freshly fetched server key + level crosses the resolver seam.
      const resolved = await resolvePresentation(Object.freeze({pet_key: pet.pet_key, level: pet.level}), activeController.signal);
      if (!current()) return state;
      if (!resolved) throw new Error("COMPANION_PRESENTATION_UNAVAILABLE");
      if (resolved.pet_key !== pet.pet_key || resolved.stage !== stage || resolved.slot !== SLOT
        || typeof resolved.presentation_id !== "string" || !resolved.presentation_id
        || typeof resolved.asset_path !== "string" || !resolved.asset_path.startsWith("/assets/")
        || resolved.asset_path.includes("..") || resolved.asset_path.includes("\\")
        || !resolved.asset_path.endsWith(".glb")
        || !/^[a-f0-9]{64}$/i.test(resolved.asset_sha256)
        || !Number.isSafeInteger(resolved.asset_bytes) || resolved.asset_bytes <= 0) {
        throw new Error("COMPANION_DESCRIPTOR_REJECTED");
      }
      descriptor = Object.freeze({...resolved});
      if (typeof loadPresentation !== "function") throw new Error("COMPANION_LOADER_UNAVAILABLE");
      const result = await host.attach(SLOT, descriptor.presentation_id,
        entry => loadPresentation(entry, activeController.signal));
      if (!current()) return state;
      if (result.status !== "attached") throw new Error("COMPANION_ATTACH_FAILED");
      return publish({ status: "ready", pet_key: pet.pet_key, stage,
        presentation_id: descriptor.presentation_id, asset_sha256: descriptor.asset_sha256 });
    } catch (error) {
      if (!current()) return state;
      descriptor = null;
      host.detach(SLOT);
      return publish({ status: "unavailable", pet_key: null, stage: null,
        reason: error instanceof Error ? error.message : String(error) });
    }
  }
  function invalidate() { void refresh(); } // event details are never authority
  function rehydrate() {
    if (disposed) return state;
    if (!listening) eventTarget.addEventListener("g009:companion-status", invalidate);
    listening = true;
    return refresh();
  }
  const unregisterTeardown = hero.registerHeroPresentationTeardown("canonical-companion", suspend);
  const unregisterRehydrator = hero.registerHeroPresentationRehydrator("canonical-companion", rehydrate);
  return Object.freeze({
    refresh, getState: () => state,
    dispose() {
      if (disposed) return;
      disposed = true;
      suspend();
      unregisterRehydrator();
      unregisterTeardown();
      unregisterResolver();
    },
  });
}
