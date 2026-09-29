/*
 * Player-character -> 3D runtime bridge.
 *
 * This module is deliberately presentation-only.  Lane B owns the player
 * identity and character-to-asset mapping; this bridge consumes that mapping
 * and never creates, persists, or mutates character/progression state.
 *
 * Accepted authority shape (aliases are supported so the bridge can sit
 * between existing read models without becoming a second authority):
 *
 * {
 *   authenticated: true,
 *   current_character: { character_id, character_asset_id },
 *   character_asset_mapping: {
 *     CHARACTER_ASSET_ID: { runtime_glb: "assets/.../character.glb" }
 *   }
 * }
 *
 * A mapping is never inferred from another catalog entry.  If the current
 * character, its mapping, or its GLB is unavailable, the result is the
 * supplied legacy fallback or FAIL_CLOSED.
 */

export const PLAYER_CHARACTER_3D_RUNTIME_BRIDGE_CONTRACT =
  "PLAYER_CHARACTER_3D_RUNTIME_BRIDGE_V1";
export const CHARACTER_RUNTIME_BRIDGE_MAX_TARGETS = 30;
export const CHARACTER_RUNTIME_BRIDGE_MAX_VISUAL_MODELS = 33;

const AUTHENTICATED_TRUE = new Set(["authenticated", "logged_in", "logged-in"]);

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function firstString(...values) {
  return values.find((value) => typeof value === "string" && value.trim())?.trim() || null;
}

function firstRecord(...values) {
  return values.find((value) => isRecord(value)) || null;
}

function authorityMapping(authority) {
  return firstRecord(
    authority?.character_asset_mapping,
    authority?.characterAssetMapping,
    authority?.asset_mapping,
    authority?.assetMapping,
    authority?.asset_mappings,
    authority?.assetMappings,
    authority?.mappings,
  );
}

function mappingEntries(mapping) {
  return Object.entries(mapping || {}).filter(([, value]) => isRecord(value));
}

function firstFiniteNumber(...values) {
  return values.find((value) => Number.isFinite(value) && value >= 0) ?? null;
}

function targetCounts(authority) {
  const mappingCount = mappingEntries(authorityMapping(authority)).length;
  const logicalCount = firstFiniteNumber(
    authority?.catalog_logical_character_count,
    authority?.catalogLogicalCharacterCount,
    authority?.future30?.logical_character_count,
    authority?.future30?.logicalCharacterCount,
    mappingCount,
  );
  const visualCount = firstFiniteNumber(
    authority?.catalog_visual_model_count,
    authority?.catalogVisualModelCount,
    authority?.future30?.visual_model_count,
    authority?.future30?.visualModelCount,
    mappingCount,
  );
  return { logicalCount, visualCount };
}

function authenticatedFrom(authority) {
  if (!isRecord(authority)) return false;
  if (authority.authenticated === true || authority.logged_in === true || authority.loggedIn === true) return true;
  const status = firstString(authority.auth_status, authority.authStatus, authority.login_status, authority.loginStatus);
  return status ? AUTHENTICATED_TRUE.has(status.toLowerCase()) : false;
}

function currentCharacterFrom(authority) {
  if (!isRecord(authority)) return null;
  return firstRecord(authority.current_character, authority.currentCharacter, authority.selected_character);
}

function currentCharacterId(current) {
  return firstString(
    current?.character_id,
    current?.characterId,
    current?.character_key,
    current?.characterKey,
    current?.id,
  );
}

function currentAssetId(current) {
  return firstString(
    current?.character_asset_id,
    current?.characterAssetId,
    current?.asset_id,
    current?.assetId,
  );
}

function runtimeGlbFromMapping(mappingEntry) {
  return firstString(
    mappingEntry?.runtime_glb,
    mappingEntry?.runtimeGlb,
    mappingEntry?.runtime_asset,
    mappingEntry?.runtimeAsset,
    mappingEntry?.glb,
  );
}

function fallbackDescriptorFrom(value) {
  if (!isRecord(value)) return null;
  const runtimeGlb = runtimeGlbFromMapping(value) || firstString(value.runtime_path, value.runtimePath);
  if (!runtimeGlb) return null;
  return {
    character_id: firstString(value.character_id, value.characterId, value.character_key, value.characterKey),
    character_asset_id: firstString(value.character_asset_id, value.characterAssetId, value.asset_id, value.assetId),
    runtime_glb: runtimeGlb,
    label: firstString(value.label, value.name),
  };
}

function baseResult(fields = {}) {
  return {
    contract_version: PLAYER_CHARACTER_3D_RUNTIME_BRIDGE_CONTRACT,
    target_capacity: CHARACTER_RUNTIME_BRIDGE_MAX_TARGETS,
    visual_model_capacity: CHARACTER_RUNTIME_BRIDGE_MAX_VISUAL_MODELS,
    ...fields,
  };
}

function failClosedResult(fields = {}) {
  return baseResult({
    ...fields,
    status: "fail_closed",
    source: "none",
    fallback: false,
    runtime_glb: null,
  });
}

/**
 * Resolve only the authority supplied by Lane B (or a test fixture).
 * This is pure and safe to use for diagnostics before any GLB is requested.
 */
export function resolvePlayerCharacterRuntime(authority, { fallback = null } = {}) {
  const mapping = authorityMapping(authority);
  const counts = targetCounts(authority);
  const targetCountValue = counts.logicalCount;
  const visualModelCountValue = counts.visualCount;
  const common = {
    authenticated: authenticatedFrom(authority),
    target_count: targetCountValue,
    visual_model_count: visualModelCountValue,
    target_catalog_capable: targetCountValue <= CHARACTER_RUNTIME_BRIDGE_MAX_TARGETS &&
      visualModelCountValue <= CHARACTER_RUNTIME_BRIDGE_MAX_VISUAL_MODELS,
  };

  if (!isRecord(authority)) {
    const legacy = fallbackDescriptorFrom(fallback);
    return legacy
      ? baseResult({
        ...common,
        status: "fallback",
        source: "legacy_fallback",
        fallback: true,
        reason: "authority_unavailable",
        failure_code: "AUTHORITY_UNAVAILABLE",
        character_id: legacy.character_id,
        character_asset_id: legacy.character_asset_id,
        runtime_glb: legacy.runtime_glb,
        label: legacy.label,
      })
      : failClosedResult({
        ...common,
        reason: "authority_unavailable",
        failure_code: "AUTHORITY_UNAVAILABLE",
      });
  }

  if (!authenticatedFrom(authority)) {
    const legacy = fallbackDescriptorFrom(fallback) || fallbackDescriptorFrom(authority.legacy_fallback || authority.legacyFallback);
    return legacy
      ? baseResult({
        ...common,
        status: "fallback",
        source: "legacy_fallback",
        fallback: true,
        reason: "not_authenticated",
        failure_code: "NOT_AUTHENTICATED",
        character_id: legacy.character_id,
        character_asset_id: legacy.character_asset_id,
        runtime_glb: legacy.runtime_glb,
        label: legacy.label,
      })
      : failClosedResult({
        ...common,
        reason: "not_authenticated",
        failure_code: "NOT_AUTHENTICATED",
      });
  }

  const current = currentCharacterFrom(authority);
  const characterId = currentCharacterId(current);
  const assetId = currentAssetId(current);
  if (!characterId || !assetId) {
    const legacy = fallbackDescriptorFrom(fallback) || fallbackDescriptorFrom(authority.legacy_fallback || authority.legacyFallback);
    return legacy
      ? baseResult({
        ...common,
        status: "fallback",
        source: "legacy_fallback",
        fallback: true,
        reason: "missing_current_character",
        failure_code: "MISSING_CURRENT_CHARACTER",
        requested_character_id: characterId,
        requested_character_asset_id: assetId,
        character_id: legacy.character_id,
        character_asset_id: legacy.character_asset_id,
        runtime_glb: legacy.runtime_glb,
        label: legacy.label,
      })
      : failClosedResult({
        ...common,
        reason: "missing_current_character",
        failure_code: "MISSING_CURRENT_CHARACTER",
        requested_character_id: characterId,
        requested_character_asset_id: assetId,
      });
  }

  // Exact asset-id lookup is the normal Lane B contract.  The character-id
  // lookup is only an adapter for an equivalent authoritative fixture; it is
  // still checked against the requested asset ID and never picks “the first”
  // or a neighboring character.
  const directEntry = isRecord(mapping[assetId]) ? mapping[assetId] : null;
  const byCharacterEntry = isRecord(mapping[characterId]) ? mapping[characterId] : null;
  const entry = directEntry || byCharacterEntry;
  const mappedAssetId = firstString(entry?.character_asset_id, entry?.characterAssetId, entry?.asset_id, entry?.assetId);
  if (!entry || (mappedAssetId && mappedAssetId !== assetId)) {
    const legacy = fallbackDescriptorFrom(fallback) || fallbackDescriptorFrom(authority.legacy_fallback || authority.legacyFallback);
    return legacy
      ? baseResult({
        ...common,
        status: "fallback",
        source: "legacy_fallback",
        fallback: true,
        reason: "missing_mapping",
        failure_code: "MISSING_CHARACTER_ASSET_MAPPING",
        requested_character_id: characterId,
        requested_character_asset_id: assetId,
        character_id: legacy.character_id,
        character_asset_id: legacy.character_asset_id,
        runtime_glb: legacy.runtime_glb,
        label: legacy.label,
      })
      : failClosedResult({
        ...common,
        reason: "missing_mapping",
        failure_code: "MISSING_CHARACTER_ASSET_MAPPING",
        requested_character_id: characterId,
        requested_character_asset_id: assetId,
      });
  }

  const runtimeGlb = runtimeGlbFromMapping(entry);
  if (!runtimeGlb) {
    const legacy = fallbackDescriptorFrom(fallback) || fallbackDescriptorFrom(authority.legacy_fallback || authority.legacyFallback);
    return legacy
      ? baseResult({
        ...common,
        status: "fallback",
        source: "legacy_fallback",
        fallback: true,
        reason: "missing_mapping_runtime_glb",
        failure_code: "MISSING_RUNTIME_GLB_MAPPING",
        requested_character_id: characterId,
        requested_character_asset_id: assetId,
        character_id: legacy.character_id,
        character_asset_id: legacy.character_asset_id,
        runtime_glb: legacy.runtime_glb,
        label: legacy.label,
      })
      : failClosedResult({
        ...common,
        reason: "missing_mapping_runtime_glb",
        failure_code: "MISSING_RUNTIME_GLB_MAPPING",
        requested_character_id: characterId,
        requested_character_asset_id: assetId,
      });
  }

  return baseResult({
    ...common,
    status: "ready",
    source: "authoritative_mapping",
    fallback: false,
    reason: null,
    failure_code: null,
    character_id: characterId,
    character_asset_id: assetId,
    runtime_glb: runtimeGlb,
    label: firstString(entry.label, entry.name),
  });
}

export function countPlayerCharacterTargets(authority) {
  return targetCounts(authority).logicalCount;
}

export function supportsThirtyTargetCatalog(authority) {
  const counts = targetCounts(authority);
  return counts.logicalCount <= CHARACTER_RUNTIME_BRIDGE_MAX_TARGETS &&
    counts.visualCount <= CHARACTER_RUNTIME_BRIDGE_MAX_VISUAL_MODELS;
}

/**
 * Stateful loader seam used by the Three.js runtime.  The loader is injected
 * so tests can exercise missing mappings/assets without network or renderer
 * side effects.  Generation tokens make refresh/remount races harmless.
 */
export class PlayerCharacter3DRuntimeBridge {
  constructor({ fallback = null, loadAsset = null, onStateChange = null } = {}) {
    this.fallback = fallbackDescriptorFrom(fallback);
    this.loadAsset = typeof loadAsset === "function" ? loadAsset : null;
    this.onStateChange = typeof onStateChange === "function" ? onStateChange : () => {};
    this.generation = 0;
    this.disposed = false;
    this.lastResult = failClosedResult({ reason: "not_loaded", failure_code: "NOT_LOADED" });
  }

  resolve(authority) {
    return resolvePlayerCharacterRuntime(authority, { fallback: this.fallback });
  }

  async load(authority, loadAsset = this.loadAsset) {
    if (this.disposed) {
      this.lastResult = failClosedResult({ reason: "disposed", failure_code: "DISPOSED" });
      return this.lastResult;
    }
    const generation = ++this.generation;
    const selection = this.resolve(authority);
    const loader = typeof loadAsset === "function" ? loadAsset : null;
    if (!selection.runtime_glb || !loader) {
      this.lastResult = baseResult({
        ...selection,
        status: "fail_closed",
        source: selection.source === "legacy_fallback" ? "legacy_fallback" : "none",
        fallback: selection.source === "legacy_fallback",
        failure_code: selection.failure_code || "RUNTIME_ASSET_LOADER_UNAVAILABLE",
        reason: selection.reason || "runtime_asset_loader_unavailable",
        generation,
      });
      this.onStateChange(this.lastResult);
      return this.lastResult;
    }

    try {
      const asset = await loader(selection.runtime_glb, selection);
      if (this.disposed || generation !== this.generation) {
        return baseResult({ ...selection, status: "stale", generation, reason: "stale_load" });
      }
      this.lastResult = baseResult({ ...selection, asset, generation });
      this.onStateChange(this.lastResult);
      return this.lastResult;
    } catch (error) {
      // An authoritative GLB failure may use the explicit legacy fallback,
      // but it may never silently switch to another mapped character.
      if (selection.source === "authoritative_mapping" && this.fallback?.runtime_glb) {
        try {
          const fallbackAsset = await loader(this.fallback.runtime_glb, {
            source: "legacy_fallback",
            reason: "missing_asset",
            failure_code: "MISSING_RUNTIME_ASSET",
            requested_character_id: selection.character_id,
            requested_character_asset_id: selection.character_asset_id,
          });
          if (this.disposed || generation !== this.generation) {
            return baseResult({ ...selection, status: "stale", generation, reason: "stale_fallback_load" });
          }
          this.lastResult = baseResult({
            ...selection,
            status: "fallback",
            source: "legacy_fallback",
            fallback: true,
            reason: "missing_asset",
            failure_code: "MISSING_RUNTIME_ASSET",
            requested_character_id: selection.character_id,
            requested_character_asset_id: selection.character_asset_id,
            character_id: this.fallback.character_id,
            character_asset_id: this.fallback.character_asset_id,
            runtime_glb: this.fallback.runtime_glb,
            label: this.fallback.label,
            asset: fallbackAsset,
            generation,
          });
          this.onStateChange(this.lastResult);
          return this.lastResult;
        } catch (fallbackError) {
          error = fallbackError;
        }
      }
      if (this.disposed || generation !== this.generation) {
        return baseResult({ ...selection, status: "stale", generation, reason: "stale_failed_load" });
      }
      this.lastResult = failClosedResult({
        ...selection,
        reason: "missing_asset",
        failure_code: "MISSING_RUNTIME_ASSET",
        generation,
        load_error: String(error?.message || error || "asset load failed"),
      });
      this.onStateChange(this.lastResult);
      return this.lastResult;
    }
  }

  refresh(authority, loadAsset = this.loadAsset) {
    return this.load(authority, loadAsset);
  }

  dispose() {
    this.generation += 1;
    this.disposed = true;
    this.lastResult = failClosedResult({ reason: "disposed", failure_code: "DISPOSED" });
  }
}

export function createPlayerCharacter3DRuntimeBridge(options = {}) {
  return new PlayerCharacter3DRuntimeBridge(options);
}
