/**
 * Post-processing for the 3D stage, with pmndrs/postprocessing: the scene is drawn once into
 * half-float buffers, then optional passes (ambient occlusion) and one merged pass of effects
 * (bloom, depth of field, tilt-shift, vignette, tone mapping) run on it.
 */

import { type Effect, EffectComposer, EffectPass, type Pass, RenderPass } from "postprocessing";
import * as THREE from "three";
import type { Stage } from "./stage";

export interface PostOptions {
  lite: boolean;
  /** Passes between the scene and the effects, such as ambient occlusion. */
  passes?: Pass[];
  effects: Effect[];
}

export function postprocess(stage: Stage, o: PostOptions) {
  const { renderer, scene, camera } = stage;
  // Tone mapping is an effect at the end of the chain; the renderer keeps linear colour.
  renderer.toneMapping = THREE.NoToneMapping;
  const composer = new EffectComposer(renderer, {
    frameBufferType: THREE.HalfFloatType,
    multisampling: o.lite ? 0 : 4,
  });
  composer.addPass(new RenderPass(scene, camera));
  for (const pass of o.passes ?? []) composer.addPass(pass);
  composer.addPass(new EffectPass(camera, ...o.effects));
  stage.use({
    render: () => composer.render(),
    resize: (width, height) => composer.setSize(width, height, false),
    dispose: () => composer.dispose(),
  });
  return composer;
}
