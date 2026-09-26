import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

// Review mode (?views=a,b,c) renders a multi-view sheet and measures the asset.
// View angles and the 1.80 m scale figure follow the Muster WW2 archive's review
// harness (MIT). Conventions: +Y up, +Z forward, +X is the asset's left.
const VIEWS = {
  'q-front': { yaw: 35, pitch: 18, label: 'front-left 3/4' },
  'q-front-r': { yaw: -35, pitch: 18, label: 'front-right 3/4' },
  front: { yaw: 0, pitch: 5, label: 'front' },
  left: { yaw: 90, pitch: 4, label: 'left side (+X)' },
  right: { yaw: -90, pitch: 4, label: 'right side (-X)' },
  rear: { yaw: 180, pitch: 5, label: 'rear' },
  'q-rear': { yaw: 215, pitch: 20, label: 'rear-right 3/4' },
  'q-rear-l': { yaw: 145, pitch: 20, label: 'rear-left 3/4' },
  top: { yaw: 0, pitch: 89.5, label: 'top' },
  bottom: { yaw: 0, pitch: -89.5, label: 'bottom' },
  ground: { yaw: 60, pitch: 1.2, label: 'ground contact' },
  high: { yaw: 30, pitch: 45, label: 'high 3/4' },
};

const params = new URLSearchParams(window.location.search);
const reviewViews = params.get('views') ? params.get('views').split(',') : null;
const result = { status: 'loading', mesh_count: 0, triangle_count: 0, material_count: 0, texture_count: 0 };
window.__BAF_RESULT__ = result;

function measure(root) {
  const materials = new Set();
  const textures = new Set();
  root.traverse((object) => {
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
}

function scaleFigure() {
  const material = new THREE.MeshStandardMaterial({ color: 0xb9b4ab, roughness: 0.7 });
  const figure = new THREE.Group();
  const add = (geometry, x, y) => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, 0);
    figure.add(mesh);
  };
  add(new THREE.CapsuleGeometry(0.065, 0.78, 6, 16), 0.1, 0.46);
  add(new THREE.CapsuleGeometry(0.065, 0.78, 6, 16), -0.1, 0.46);
  add(new THREE.CapsuleGeometry(0.17, 0.42, 8, 20), 0, 1.2);
  add(new THREE.CapsuleGeometry(0.045, 0.62, 6, 12), 0.25, 1.12);
  add(new THREE.CapsuleGeometry(0.045, 0.62, 6, 12), -0.25, 1.12);
  add(new THREE.SphereGeometry(0.105, 24, 16), 0, 1.69);
  figure.name = 'scale-figure-1.80m';
  return figure;
}

function frame(camera, box, yaw, pitch, aspect) {
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const radius = Math.max(sphere.radius, 0.001);
  const vertical = THREE.MathUtils.degToRad(camera.fov);
  const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * aspect);
  const distance = (radius / Math.sin(Math.min(vertical, horizontal) / 2)) * 1.05;
  const y = THREE.MathUtils.degToRad(yaw);
  const p = THREE.MathUtils.degToRad(pitch);
  const direction = new THREE.Vector3(Math.sin(y) * Math.cos(p), Math.sin(p), Math.cos(y) * Math.cos(p));
  camera.position.copy(sphere.center).addScaledVector(direction, distance);
  camera.near = Math.max(distance / 1000, 0.0001);
  camera.far = distance + radius * 4;
  camera.lookAt(sphere.center);
  camera.updateProjectionMatrix();
}

function renderReview(renderer, scene, camera, asset, bounds) {
  const unknown = reviewViews.filter((name) => !VIEWS[name]);
  if (unknown.length) throw new Error(`unknown view: ${unknown.join(', ')}`);
  const width = Number(params.get('w') || window.innerWidth);
  const height = Number(params.get('h') || window.innerHeight);
  const columns = Number(params.get('cols') || Math.min(3, reviewViews.length));
  const rows = Math.ceil(reviewViews.length / columns);
  const cellWidth = Math.floor(width / columns);
  const cellHeight = Math.floor((height - 28) / rows);
  renderer.setSize(cellWidth, cellHeight, false);
  camera.aspect = cellWidth / cellHeight;

  // Draw calls are counted with only the asset in the scene.
  frame(camera, bounds, 35, 18, camera.aspect);
  renderer.render(scene, camera);
  const drawCalls = renderer.info.render.calls;

  const size = bounds.getSize(new THREE.Vector3());
  const span = Math.max(size.x, size.z, 1) * 2;
  const grid = new THREE.GridHelper(span, Math.max(4, Math.round(span / 0.25)), 0x56606a, 0x2c3238);
  grid.position.set((bounds.min.x + bounds.max.x) / 2, 0, (bounds.min.z + bounds.max.z) / 2);
  scene.add(grid);
  const content = new THREE.Group();
  content.add(asset);
  scene.add(content);
  if (params.get('ref') === '1') {
    const figure = scaleFigure();
    figure.position.set(bounds.max.x + 0.6, 0, (bounds.min.z + bounds.max.z) / 2);
    content.add(figure);
  }
  const frameBox = new THREE.Box3().setFromObject(content, true);

  const out = document.createElement('canvas');
  out.width = width;
  out.height = height;
  document.body.appendChild(out);
  const context = out.getContext('2d');
  context.fillStyle = '#171a1d';
  context.fillRect(0, 0, width, height);
  reviewViews.forEach((name, index) => {
    const view = VIEWS[name];
    frame(camera, frameBox, view.yaw, view.pitch, camera.aspect);
    renderer.render(scene, camera);
    const x = (index % columns) * cellWidth;
    const y = Math.floor(index / columns) * cellHeight;
    context.drawImage(renderer.domElement, x, y, cellWidth, cellHeight);
    context.fillStyle = 'rgba(0,0,0,0.5)';
    context.fillRect(x, y, 170, 20);
    context.fillStyle = '#e8e2d6';
    context.font = '12px Arial, sans-serif';
    context.fillText(view.label, x + 6, y + 14);
  });
  const footer =
    `tris=${result.triangle_count.toLocaleString()}  draws=${drawCalls}  materials=${result.material_count}  ` +
    `size W${size.x.toFixed(3)} H${size.y.toFixed(3)} L${size.z.toFixed(3)} m  minY=${bounds.min.y.toFixed(4)}`;
  context.fillStyle = '#e8e2d6';
  context.font = '13px Arial, sans-serif';
  context.fillText(footer, 8, height - 9);
  result.review = { views: reviewViews, draw_calls: drawCalls, scale_figure: params.get('ref') === '1' };
}

try {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  if (!reviewViews) document.body.appendChild(renderer.domElement);

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
    try {
      measure(gltf.scene);
      const bounds = new THREE.Box3().setFromObject(gltf.scene, true);
      result.bounds = { min: bounds.min.toArray(), max: bounds.max.toArray() };
      if (reviewViews) {
        scene.add(gltf.scene);
        renderReview(renderer, scene, camera, gltf.scene, bounds);
      } else {
        scene.add(gltf.scene);
        const center = bounds.getCenter(new THREE.Vector3());
        const size = bounds.getSize(new THREE.Vector3());
        const maxDimension = Math.max(size.x, size.y, size.z, 0.001);
        camera.near = Math.max(maxDimension / 1000, 0.0001);
        camera.far = Math.max(maxDimension * 100, 100);
        camera.position.copy(center).add(new THREE.Vector3(maxDimension * 0.9, maxDimension * 0.55, maxDimension * 2.3));
        camera.lookAt(center);
        camera.updateProjectionMatrix();
        renderer.render(scene, camera);
        result.camera = { position: camera.position.toArray(), target: center.toArray() };
      }
      const gl = renderer.getContext();
      result.renderer = gl.getParameter(gl.RENDERER);
      result.vendor = gl.getParameter(gl.VENDOR);
      result.status = 'loaded';
    } catch (error) {
      result.status = 'error';
      result.error = String(error?.stack || error);
    }
  }, undefined, (error) => {
    result.status = 'error';
    result.error = String(error?.message || error);
  });
} catch (error) {
  result.status = 'error';
  result.error = String(error?.stack || error);
}
