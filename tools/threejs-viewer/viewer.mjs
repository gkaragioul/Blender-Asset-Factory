import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const result = { status: 'loading', mesh_count: 0, triangle_count: 0, material_count: 0, texture_count: 0 };
window.__BAF_RESULT__ = result;

try {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  document.body.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x171a1d);
  const camera = new THREE.PerspectiveCamera(35, window.innerWidth / window.innerHeight, 0.001, 10000);
  scene.add(new THREE.HemisphereLight(0xdde8ff, 0x302a22, 2.1));
  const key = new THREE.DirectionalLight(0xfff1dc, 3.0);
  key.position.set(4, 6, 5);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x99b7ff, 1.1);
  fill.position.set(-4, 2, -3);
  scene.add(fill);

  const loader = new GLTFLoader();
  loader.setMeshoptDecoder(MeshoptDecoder);
  loader.load('./asset.glb', (gltf) => {
    scene.add(gltf.scene);
    const materials = new Set();
    const textures = new Set();
    gltf.scene.traverse((object) => {
      if (!object.isMesh) return;
      result.mesh_count += 1;
      const geometry = object.geometry;
      result.triangle_count += geometry.index ? geometry.index.count / 3 : geometry.attributes.position.count / 3;
      const objectMaterials = Array.isArray(object.material) ? object.material : [object.material];
      for (const material of objectMaterials) {
        if (!material) continue;
        materials.add(material.uuid);
        for (const value of Object.values(material)) {
          if (value?.isTexture) textures.add(value.uuid);
        }
      }
    });
    result.material_count = materials.size;
    result.texture_count = textures.size;

    const bounds = new THREE.Box3().setFromObject(gltf.scene);
    const center = bounds.getCenter(new THREE.Vector3());
    const size = bounds.getSize(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z, 0.001);
    camera.near = Math.max(maxDimension / 1000, 0.0001);
    camera.far = Math.max(maxDimension * 100, 100);
    camera.position.copy(center).add(new THREE.Vector3(maxDimension * 0.9, maxDimension * 0.55, maxDimension * 2.3));
    camera.lookAt(center);
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
    const gl = renderer.getContext();
    result.renderer = gl.getParameter(gl.RENDERER);
    result.vendor = gl.getParameter(gl.VENDOR);
    result.bounds = { min: bounds.min.toArray(), max: bounds.max.toArray() };
    result.camera = { position: camera.position.toArray(), target: center.toArray() };
    result.status = 'loaded';
  }, undefined, (error) => {
    result.status = 'error';
    result.error = String(error?.message || error);
  });
} catch (error) {
  result.status = 'error';
  result.error = String(error?.stack || error);
}
