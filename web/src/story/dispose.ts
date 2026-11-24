import type * as THREE from "three";

/** Frees a scene and its renderer, and gives the WebGL context back to the browser. */
export function disposeScene(renderer: THREE.WebGLRenderer, scene: THREE.Scene): void {
  scene.traverse((object) => {
    const mesh = object as THREE.Mesh;
    mesh.geometry?.dispose();
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const material of materials) {
      if (!material) continue;
      for (const value of Object.values(material)) {
        if (value && typeof value === "object" && "isTexture" in value)
          (value as THREE.Texture).dispose();
      }
      const uniforms = (material as THREE.ShaderMaterial).uniforms;
      for (const uniform of Object.values(uniforms ?? {})) {
        const value = uniform?.value as THREE.Texture | undefined;
        if (value && typeof value === "object" && "isTexture" in value) value.dispose();
      }
      material.dispose();
    }
  });
  renderer.dispose();
  renderer.forceContextLoss();
}
