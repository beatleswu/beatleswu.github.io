/*
 * Go Odyssey bounded true 2D skeletal runtime.
 *
 * This module is presentation-only.  It owns no inventory, equipment,
 * account, combat, or progression state.  The skeleton is authored in a
 * fixed design space and rendered into a responsive Canvas2D surface.
 *
 * Unlike the legacy wearable renderer, this path does not position a stack of
 * viewport-sized images.  Every body/equipment region is a slot attachment
 * whose transform is composed from its parent bone and local transform.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.GoOdysseyHeroSkeletalRig = api;
})(typeof window !== 'undefined' ? window :
  (typeof globalThis !== 'undefined' ? globalThis : this), function () {
  'use strict';

  const DEG_TO_RAD = Math.PI / 180;
  const IDLE_ANIMATION = 'idle';

  function numberOr(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function scalePair(value) {
    if (Array.isArray(value)) {
      return [numberOr(value[0], 1), numberOr(value[1], numberOr(value[0], 1))];
    }
    const scale = numberOr(value, 1);
    return [scale, scale];
  }

  function matrix(a, b, c, d, tx, ty) {
    return { a, b, c, d, tx, ty };
  }

  function identityMatrix() {
    return matrix(1, 0, 0, 1, 0, 0);
  }

  function multiply(parent, child) {
    return matrix(
      parent.a * child.a + parent.c * child.b,
      parent.b * child.a + parent.d * child.b,
      parent.a * child.c + parent.c * child.d,
      parent.b * child.c + parent.d * child.d,
      parent.a * child.tx + parent.c * child.ty + parent.tx,
      parent.b * child.tx + parent.d * child.ty + parent.ty,
    );
  }

  function composeTransform(x, y, rotationDeg, scale) {
    const radians = numberOr(rotationDeg, 0) * DEG_TO_RAD;
    const [scaleX, scaleY] = scalePair(scale);
    const cosine = Math.cos(radians);
    const sine = Math.sin(radians);
    return matrix(
      cosine * scaleX,
      sine * scaleX,
      -sine * scaleY,
      cosine * scaleY,
      numberOr(x, 0),
      numberOr(y, 0),
    );
  }

  function interpolateKeyframes(keyframes, timeMs, fallback) {
    if (!Array.isArray(keyframes) || keyframes.length === 0) return fallback;
    if (timeMs <= Number(keyframes[0][0])) return numberOr(keyframes[0][1], fallback);
    for (let index = 1; index < keyframes.length; index += 1) {
      const previous = keyframes[index - 1];
      const next = keyframes[index];
      const previousTime = numberOr(previous[0], 0);
      const nextTime = numberOr(next[0], previousTime);
      if (timeMs <= nextTime) {
        const span = Math.max(1, nextTime - previousTime);
        const progress = Math.max(0, Math.min(1, (timeMs - previousTime) / span));
        return numberOr(previous[1], fallback) +
          (numberOr(next[1], fallback) - numberOr(previous[1], fallback)) * progress;
      }
    }
    return numberOr(keyframes[keyframes.length - 1][1], fallback);
  }

  function applyCanvasMatrix(context, transform) {
    context.transform(
      transform.a,
      transform.b,
      transform.c,
      transform.d,
      transform.tx,
      transform.ty,
    );
  }

  class Bone {
    constructor(definition, parent) {
      this.id = definition.id;
      this.parent = parent || null;
      this.setup = {
        x: numberOr(definition.x, 0),
        y: numberOr(definition.y, 0),
        rotation_deg: numberOr(definition.rotation_deg, 0),
        scale: definition.scale === undefined ? 1 : definition.scale,
      };
      this.x = this.setup.x;
      this.y = this.setup.y;
      this.rotation_deg = this.setup.rotation_deg;
      this.scale = this.setup.scale;
      this.world = identityMatrix();
    }

    reset() {
      this.x = this.setup.x;
      this.y = this.setup.y;
      this.rotation_deg = this.setup.rotation_deg;
      this.scale = this.setup.scale;
    }

    localMatrix() {
      return composeTransform(this.x, this.y, this.rotation_deg, this.scale);
    }

    updateWorld(parentWorld) {
      this.world = multiply(parentWorld || identityMatrix(), this.localMatrix());
      return this.world;
    }
  }

  class Slot {
    constructor(definition) {
      this.id = definition.id;
      this.bone = definition.bone;
      this.draw_order = numberOr(definition.draw_order, 0);
    }
  }

  class Attachment {
    constructor(definition) {
      this.id = definition.id;
      this.item_id = definition.item_id || null;
      this.slot = definition.slot;
      this.asset = definition.asset;
      this.attachment_type = definition.attachment_type || 'region';
      this.source_rect = Array.isArray(definition.source_rect)
        ? definition.source_rect.map(value => numberOr(value, 0)) : [0, 0, 0, 0];
      this.pivot = Array.isArray(definition.pivot)
        ? definition.pivot.map(value => numberOr(value, 0)) : [0, 0];
      const local = definition.local_transform || {};
      this.local_transform = {
        x: numberOr(local.x, 0),
        y: numberOr(local.y, 0),
        rotation_deg: numberOr(local.rotation_deg, 0),
        scale: local.scale === undefined ? 1 : local.scale,
      };
      this.clip_polygon = Array.isArray(definition.clip_polygon)
        ? definition.clip_polygon.map(point => [numberOr(point[0], 0), numberOr(point[1], 0)])
        : null;
      this.draw_order = numberOr(definition.draw_order, 0);
    }

    localMatrix() {
      return composeTransform(
        this.local_transform.x,
        this.local_transform.y,
        this.local_transform.rotation_deg,
        this.local_transform.scale,
      );
    }
  }

  class SkeletalRig {
    constructor(manifest) {
      if (!manifest || manifest.schema !== 'go-odyssey.hero-true-2d-skeletal-rig.v1') {
        throw new Error('unsupported skeletal rig manifest');
      }
      if (manifest.hero_id !== 'apprentice_p1') {
        throw new Error('vertical slice is limited to apprentice_p1');
      }
      this.manifest = manifest;
      this.bones = new Map();
      (manifest.bones || []).forEach(definition => {
        const parent = definition.parent ? this.bones.get(definition.parent) : null;
        if (definition.parent && !parent) throw new Error(`missing parent bone ${definition.parent}`);
        this.bones.set(definition.id, new Bone(definition, parent));
      });
      this.slots = new Map();
      (manifest.slots || []).forEach(definition => {
        if (!this.bones.has(definition.bone)) throw new Error(`slot ${definition.id} has unknown bone`);
        this.slots.set(definition.id, new Slot(definition));
      });
      this.attachments = new Map();
      (manifest.attachments || []).forEach(definition => {
        if (!this.slots.has(definition.slot)) throw new Error(`attachment ${definition.id} has unknown slot`);
        if (!this.manifest.assets?.[definition.asset]) throw new Error(`attachment ${definition.id} has unknown asset`);
        this.attachments.set(definition.id, new Attachment(definition));
      });
      this.items = manifest.items || {};
      this.selectedItemIds = [];
      this.clockMs = 0;
      this.playing = false;
      this.canvas = null;
      this.context = null;
      this.assets = null;
      this.resizeObserver = null;
      this.resizeHandler = null;
      this.rafId = null;
      this.usesTimeout = false;
      this.lastFrameAt = null;
      this.lifecycle = {
        mount_count: 0,
        destroy_count: 0,
        active_raf: 0,
        active_timers: 0,
        active_listeners: 0,
        active_animation_instances: 0,
      };
      this.resetPose();
      this.updateWorldTransforms();
    }

    resetPose() {
      this.bones.forEach(bone => bone.reset());
      return this;
    }

    setEquipment(itemIds) {
      const values = Array.isArray(itemIds) ? itemIds : [];
      this.selectedItemIds = [...new Set(values.filter(itemId => Boolean(this.items[itemId])))];
      return this.getEquipment();
    }

    getEquipment() {
      return [...this.selectedItemIds];
    }

    applyTrack(bone, track, timeMs) {
      if (!track || !bone) return;
      if (track.x) bone.x = interpolateKeyframes(track.x, timeMs, bone.setup.x);
      if (track.y) bone.y = interpolateKeyframes(track.y, timeMs, bone.setup.y);
      if (track.rotation_deg) {
        bone.rotation_deg = interpolateKeyframes(track.rotation_deg, timeMs, bone.setup.rotation_deg);
      }
      if (track.scale) bone.scale = interpolateKeyframes(track.scale, timeMs, bone.setup.scale);
    }

    applyAnimation(timeMs) {
      const animation = this.manifest.animation;
      if (!animation || animation.id !== IDLE_ANIMATION) return;
      const duration = Math.max(1, numberOr(animation.duration_ms, 1));
      const localTime = animation.loop ? ((timeMs % duration) + duration) % duration :
        Math.max(0, Math.min(duration, timeMs));
      this.resetPose();
      Object.entries(animation.tracks || {}).forEach(([boneId, track]) => {
        this.applyTrack(this.bones.get(boneId), track, localTime);
      });
      this.updateWorldTransforms();
    }

    setTime(timeMs) {
      this.clockMs = numberOr(timeMs, 0);
      this.applyAnimation(this.clockMs);
      return this;
    }

    update(deltaMs) {
      this.clockMs += Math.max(0, numberOr(deltaMs, 0));
      this.applyAnimation(this.clockMs);
      return this;
    }

    updateWorldTransforms() {
      this.bones.forEach(bone => {
        bone.updateWorld(bone.parent ? bone.parent.world : identityMatrix());
      });
      return this;
    }

    attachmentWorldTransform(attachment) {
      const slot = this.slots.get(attachment.slot);
      const bone = this.bones.get(slot.bone);
      return multiply(bone.world, attachment.localMatrix());
    }

    getDrawList() {
      const selected = new Set(this.selectedItemIds);
      return [...this.attachments.values()]
        .filter(attachment => !attachment.item_id || selected.has(attachment.item_id))
        .map(attachment => {
          const slot = this.slots.get(attachment.slot);
          return {
            attachment,
            slot,
            bone: this.bones.get(slot.bone),
            transform: this.attachmentWorldTransform(attachment),
          };
        })
        .sort((left, right) =>
          left.slot.draw_order - right.slot.draw_order ||
          left.attachment.draw_order - right.attachment.draw_order ||
          left.attachment.id.localeCompare(right.attachment.id));
    }

    getAttachmentWorldTransform(attachmentId) {
      const attachment = this.attachments.get(attachmentId);
      if (!attachment) throw new Error(`unknown attachment ${attachmentId}`);
      return this.attachmentWorldTransform(attachment);
    }

    layoutFor(width, height) {
      const design = this.manifest.design_space;
      const canvasWidth = Math.max(1, numberOr(width, design.width));
      const canvasHeight = Math.max(1, numberOr(height, design.height));
      const scale = Math.min(canvasWidth / design.width, canvasHeight / design.height);
      return {
        scale,
        offset_x: (canvasWidth - design.width * scale) / 2,
        offset_y: (canvasHeight - design.height * scale) / 2,
        design_width: design.width,
        design_height: design.height,
      };
    }

    draw(context, assets, options) {
      if (!context) throw new Error('Canvas2D context is required');
      const opts = options || {};
      const width = numberOr(opts.width, context.canvas?.width || this.manifest.design_space.width);
      const height = numberOr(opts.height, context.canvas?.height || this.manifest.design_space.height);
      const layout = this.layoutFor(width, height);
      const drawList = this.getDrawList();
      const missingAssets = [];
      context.save();
      context.clearRect(0, 0, width, height);
      context.translate(layout.offset_x, layout.offset_y);
      context.scale(layout.scale, layout.scale);
      drawList.forEach(entry => {
        const image = assets?.[entry.attachment.asset];
        if (!image) {
          missingAssets.push(entry.attachment.asset);
          return;
        }
        const [sourceX, sourceY, sourceWidth, sourceHeight] = entry.attachment.source_rect;
        const [pivotX, pivotY] = entry.attachment.pivot;
        context.save();
        applyCanvasMatrix(context, entry.transform);
        if (entry.attachment.clip_polygon?.length >= 3) {
          context.beginPath();
          entry.attachment.clip_polygon.forEach((point, index) => {
            const x = point[0];
            const y = point[1];
            if (index === 0) context.moveTo(x, y);
            else context.lineTo(x, y);
          });
          context.closePath();
          context.clip();
        }
        context.drawImage(
          image,
          sourceX,
          sourceY,
          sourceWidth,
          sourceHeight,
          -pivotX,
          -pivotY,
          sourceWidth,
          sourceHeight,
        );
        context.restore();
      });
      context.restore();
      return {
        layout,
        drawn_attachment_count: drawList.length - missingAssets.length,
        missing_assets: [...new Set(missingAssets)],
        equipment: this.getEquipment(),
        clock_ms: this.clockMs,
      };
    }

    resize() {
      if (!this.canvas) return null;
      const width = Math.max(1, Math.floor(this.canvas.clientWidth || this.canvas.width || this.manifest.design_space.width));
      const height = Math.max(1, Math.floor(this.canvas.clientHeight || this.canvas.height || this.manifest.design_space.height));
      const devicePixelRatio = numberOr((typeof window !== 'undefined' && window.devicePixelRatio) || 1, 1);
      this.canvas.width = Math.floor(width * devicePixelRatio);
      this.canvas.height = Math.floor(height * devicePixelRatio);
      return {width: this.canvas.width, height: this.canvas.height, device_pixel_ratio: devicePixelRatio};
    }

    mount(target, assets) {
      if (this.canvas) throw new Error('skeletal rig is already mounted');
      const hasCanvasApi = target && typeof target.getContext === 'function';
      if (hasCanvasApi) {
        this.canvas = target;
      } else {
        if (typeof document === 'undefined' || !target || typeof target.appendChild !== 'function') {
          throw new Error('mount target must be a canvas or DOM element');
        }
        this.canvas = document.createElement('canvas');
        this.canvas.dataset.heroSkeletalRig = this.manifest.hero_id;
        target.appendChild(this.canvas);
      }
      this.context = this.canvas.getContext('2d');
      if (!this.context) throw new Error('Canvas2D is unavailable');
      this.assets = assets || {};
      this.resize();
      this.lifecycle.mount_count += 1;
      this.resizeHandler = () => this.resize();
      if (typeof window !== 'undefined' && window.addEventListener) {
        window.addEventListener('resize', this.resizeHandler, {passive: true});
        this.lifecycle.active_listeners += 1;
      }
      if (typeof ResizeObserver !== 'undefined') {
        this.resizeObserver = new ResizeObserver(this.resizeHandler);
        this.resizeObserver.observe(this.canvas);
      }
      this.lifecycle.active_animation_instances = 1;
      this.draw(this.context, this.assets);
      return this;
    }

    schedule(callback) {
      if (typeof requestAnimationFrame === 'function') {
        this.usesTimeout = false;
        this.lifecycle.active_raf = 1;
        return requestAnimationFrame(callback);
      }
      this.usesTimeout = true;
      this.lifecycle.active_timers = 1;
      return setTimeout(() => callback(Date.now()), 16);
    }

    cancelScheduled() {
      if (this.rafId === null) return;
      if (this.usesTimeout) clearTimeout(this.rafId);
      else if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(this.rafId);
      this.rafId = null;
      this.lifecycle.active_raf = 0;
      this.lifecycle.active_timers = 0;
    }

    play() {
      if (!this.canvas || !this.context) throw new Error('mount the skeletal rig before play');
      if (this.playing) return this;
      this.playing = true;
      this.lastFrameAt = null;
      const frame = now => {
        if (!this.playing) return;
        const current = numberOr(now, Date.now());
        const delta = this.lastFrameAt === null ? 0 : Math.min(100, Math.max(0, current - this.lastFrameAt));
        this.lastFrameAt = current;
        this.update(delta);
        this.resize();
        this.draw(this.context, this.assets);
        this.rafId = this.schedule(frame);
      };
      this.rafId = this.schedule(frame);
      return this;
    }

    pause() {
      this.playing = false;
      this.lastFrameAt = null;
      this.cancelScheduled();
      return this;
    }

    remount(target, assets) {
      this.destroy();
      return this.mount(target, assets);
    }

    destroy() {
      this.pause();
      if (this.resizeObserver) {
        this.resizeObserver.disconnect();
        this.resizeObserver = null;
      }
      if (this.resizeHandler && typeof window !== 'undefined' && window.removeEventListener) {
        window.removeEventListener('resize', this.resizeHandler);
        this.lifecycle.active_listeners = Math.max(0, this.lifecycle.active_listeners - 1);
      }
      this.resizeHandler = null;
      this.context = null;
      this.canvas = null;
      this.assets = null;
      this.lifecycle.active_animation_instances = 0;
      this.lifecycle.destroy_count += 1;
      return this;
    }

    lifecycleSnapshot() {
      return {...this.lifecycle};
    }
  }

  async function loadManifest(url) {
    if (typeof fetch !== 'function') throw new Error('fetch is unavailable');
    const response = await fetch(url, {cache: 'no-store'});
    if (!response.ok) throw new Error(`skeletal manifest HTTP ${response.status}`);
    return response.json();
  }

  function loadImage(url) {
    if (typeof Image === 'undefined') return Promise.reject(new Error('Image is unavailable'));
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.decoding = 'async';
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error(`skeletal asset failed to load: ${url}`));
      image.src = url;
    });
  }

  async function loadAssets(manifest) {
    const entries = Object.entries(manifest.assets || {});
    const pairs = await Promise.all(entries.map(async ([key, asset]) => [key, await loadImage(asset.path)]));
    return Object.fromEntries(pairs);
  }

  return Object.freeze({
    Bone,
    Slot,
    Attachment,
    SkeletalRig,
    composeTransform,
    identityMatrix,
    multiply,
    interpolateKeyframes,
    loadManifest,
    loadAssets,
  });
});
