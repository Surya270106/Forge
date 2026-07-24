"use client";

import { useEffect, useRef } from "react";

type Vertex = {
  x: number;
  y: number;
  z: number;
  sx: number;
  sy: number;
};

const simplexNoise = `
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 10.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
  const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(
    i.z + vec4(0.0, i1.z, i2.z, 1.0))
    + i.y + vec4(0.0, i1.y, i2.y, 1.0))
    + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(
    dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)
  ));
  p0 *= norm.x;
  p1 *= norm.y;
  p2 *= norm.z;
  p3 *= norm.w;
  vec4 m = max(0.6 - vec4(
    dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)
  ), 0.0);
  m = m * m;
  return 42.0 * dot(m * m, vec4(
    dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)
  ));
}
`;

const vertexShader = `
uniform float uTime;
varying vec3 vNormal;
varying vec3 vWorldPosition;
varying float vDisplacement;
${simplexNoise}

void main() {
  vec3 direction = normalize(position);
  vec3 drift = vec3(uTime * 0.055, -uTime * 0.035, uTime * 0.045);
  float broad = snoise(direction * 1.72 + drift);
  float medium = snoise(direction * 3.45 - drift * 1.35);
  float detail = snoise(direction * 6.8 + drift * 0.62);
  float displacement = broad * 0.20 + medium * 0.135 + detail * 0.024;
  float breath = sin(uTime * 0.62) * 0.018;
  vec3 transformed = position * (1.0 + displacement + breath);
  vec4 worldPosition = modelMatrix * vec4(transformed, 1.0);
  vWorldPosition = worldPosition.xyz;
  vDisplacement = displacement;
  vNormal = normalize(normalMatrix * direction);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(transformed, 1.0);
}
`;

const surfaceFragmentShader = `
varying vec3 vNormal;
varying vec3 vWorldPosition;
varying float vDisplacement;

void main() {
  vec3 normal = normalize(vNormal);
  vec3 viewDirection = normalize(cameraPosition - vWorldPosition);
  float fresnel = pow(1.0 - max(dot(normal, viewDirection), 0.0), 2.2);
  float topLight = max(dot(normal, normalize(vec3(-0.38, 0.72, 0.58))), 0.0);
  float contour = smoothstep(-0.2, 0.28, vDisplacement);
  vec3 deepBlue = vec3(0.004, 0.025, 0.067);
  vec3 electricBlue = vec3(0.018, 0.145, 0.34);
  vec3 color = mix(deepBlue, electricBlue, topLight * 0.72 + contour * 0.2);
  color += vec3(0.015, 0.11, 0.28) * fresnel;
  float alpha = 0.82 + fresnel * 0.12;
  gl_FragColor = vec4(color, alpha);
}
`;

const wireFragmentShader = `
varying vec3 vNormal;
varying vec3 vWorldPosition;
varying float vDisplacement;

void main() {
  vec3 normal = normalize(vNormal);
  vec3 viewDirection = normalize(cameraPosition - vWorldPosition);
  float facing = abs(dot(normal, viewDirection));
  float edge = pow(1.0 - facing, 0.75);
  float highlight = smoothstep(-0.12, 0.32, vDisplacement);
  vec3 color = mix(
    vec3(0.014, 0.17, 0.41),
    vec3(0.04, 0.38, 0.82),
    edge * 0.58 + highlight * 0.2
  );
  gl_FragColor = vec4(color, 0.34 + edge * 0.22);
}
`;

export default function BlobScene() {
  const mountRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    const canvas = canvasRef.current;
    if (!mount || !canvas) return;

    let disposed = false;
    let cleanup: (() => void) | undefined;

    const initialize = async () => {
      const THREE = await import("three");
      if (disposed) return;

      const contextOptions = {
        alpha: true,
        antialias: true,
        depth: true,
        powerPreference: "high-performance" as WebGLPowerPreference,
      };
      const gl =
        (canvas.getContext("webgl2", contextOptions) as WebGL2RenderingContext) ||
        (canvas.getContext("webgl", contextOptions) as WebGLRenderingContext);

      if (!gl) {
        cleanup = startCanvasFallback(mount, canvas, THREE);
        return;
      }

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 50);
      camera.position.set(0, 0.03, 5.15);

      const renderer = new THREE.WebGLRenderer({
        canvas,
        context: gl,
        alpha: true,
        antialias: true,
        powerPreference: "high-performance",
      });
      renderer.setClearColor(0x000000, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));

      const geometry = new THREE.IcosahedronGeometry(1.22, 30);
      const uniforms = { uTime: { value: 0 } };
      const surfaceMaterial = new THREE.ShaderMaterial({
        uniforms,
        vertexShader,
        fragmentShader: surfaceFragmentShader,
        transparent: true,
        depthWrite: true,
        side: THREE.DoubleSide,
      });
      const wireMaterial = new THREE.ShaderMaterial({
        uniforms,
        vertexShader,
        fragmentShader: wireFragmentShader,
        transparent: true,
        wireframe: true,
        depthWrite: false,
        depthTest: true,
        blending: THREE.AdditiveBlending,
      });

      const group = new THREE.Group();
      const surface = new THREE.Mesh(geometry, surfaceMaterial);
      const wire = new THREE.Mesh(geometry, wireMaterial);
      wire.scale.setScalar(1.003);
      group.add(surface, wire);
      group.rotation.set(-0.1, -0.25, 0.02);
      scene.add(group);

      const target = { x: 0, y: 0 };
      const pointer = { x: 0, y: 0 };
      const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      const clock = new THREE.Clock();
      let animation = 0;

      const onPointerMove = (event: PointerEvent) => {
        target.x = (event.clientX / window.innerWidth - 0.5) * 0.28;
        target.y = (event.clientY / window.innerHeight - 0.5) * 0.18;
      };
      const onPointerLeave = () => {
        target.x = 0;
        target.y = 0;
      };
      const resize = () => {
        const width = mount.clientWidth;
        const height = mount.clientHeight;
        renderer.setSize(width, height, false);
        camera.aspect = width / Math.max(height, 1);
        camera.updateProjectionMatrix();
        if (reducedMotion) renderer.render(scene, camera);
      };

      const observer = new ResizeObserver(resize);
      observer.observe(mount);
      window.addEventListener("pointermove", onPointerMove, { passive: true });
      document.documentElement.addEventListener("pointerleave", onPointerLeave);
      resize();

      const render = () => {
        const elapsed = reducedMotion ? 3.25 : clock.getElapsedTime();
        uniforms.uTime.value = elapsed;
        pointer.x += (target.x - pointer.x) * 0.032;
        pointer.y += (target.y - pointer.y) * 0.032;
        group.rotation.y = -0.25 + elapsed * 0.025 + pointer.x;
        group.rotation.x =
          -0.1 + Math.sin(elapsed * 0.17) * 0.025 + pointer.y;
        group.rotation.z = Math.sin(elapsed * 0.12) * 0.018;
        renderer.render(scene, camera);
        if (!reducedMotion) animation = window.requestAnimationFrame(render);
      };
      render();

      cleanup = () => {
        window.cancelAnimationFrame(animation);
        observer.disconnect();
        window.removeEventListener("pointermove", onPointerMove);
        document.documentElement.removeEventListener(
          "pointerleave",
          onPointerLeave,
        );
        geometry.dispose();
        surfaceMaterial.dispose();
        wireMaterial.dispose();
        renderer.dispose();
      };
    };

    void initialize();

    return () => {
      disposed = true;
      cleanup?.();
    };
  }, []);

  return (
    <div className="blob-stage" ref={mountRef} aria-hidden="true">
      <div className="blob-glow" />
      <canvas ref={canvasRef} />
    </div>
  );
}

function startCanvasFallback(
  mount: HTMLDivElement,
  canvas: HTMLCanvasElement,
  THREE: typeof import("three"),
) {
  const context = canvas.getContext("2d");
  if (!context) return;

  let width = 1;
  let height = 1;
  let animation = 0;
  const startedAt = performance.now();
  const pointer = { x: 0, y: 0 };
  const target = { x: 0, y: 0 };
  const fallbackGeometry = new THREE.IcosahedronGeometry(1, 16);
  const source = fallbackGeometry.attributes.position.array;
  const triangleIndices = fallbackGeometry.index?.array;
  const reducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;

  const resize = () => {
    const density = Math.min(window.devicePixelRatio || 1, 1.5);
    width = mount.clientWidth;
    height = mount.clientHeight;
    canvas.width = Math.floor(width * density);
    canvas.height = Math.floor(height * density);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(density, 0, 0, density, 0, 0);
  };
  const onPointerMove = (event: PointerEvent) => {
    target.x = (event.clientX / window.innerWidth - 0.5) * 0.28;
    target.y = (event.clientY / window.innerHeight - 0.5) * 0.17;
  };
  const rotate = (
    x: number,
    y: number,
    z: number,
    angleX: number,
    angleY: number,
  ) => {
    const cosY = Math.cos(angleY);
    const sinY = Math.sin(angleY);
    const x1 = x * cosY - z * sinY;
    const z1 = x * sinY + z * cosY;
    const cosX = Math.cos(angleX);
    const sinX = Math.sin(angleX);
    return {
      x: x1,
      y: y * cosX - z1 * sinX,
      z: y * sinX + z1 * cosX,
    };
  };

  let previousDraw = 0;
  const draw = (now: number) => {
    if (!reducedMotion && now - previousDraw < 28) {
      animation = window.requestAnimationFrame(draw);
      return;
    }
    previousDraw = now;
    const time = reducedMotion ? 2.8 : (now - startedAt) / 3200;
    pointer.x += (target.x - pointer.x) * 0.04;
    pointer.y += (target.y - pointer.y) * 0.04;
    context.clearRect(0, 0, width, height);

    const size = Math.min(width, height) * 0.35;
    const centerX = width / 2;
    const centerY = height * 0.51;
    const triangles: {
      points: [Vertex, Vertex, Vertex];
      depth: number;
    }[] = [];

    const triangleCount = triangleIndices
      ? triangleIndices.length / 3
      : source.length / 9;
    for (let triangle = 0; triangle < triangleCount; triangle += 1) {
      const points: Vertex[] = [];
      for (let corner = 0; corner < 3; corner += 1) {
        const sourceIndex = triangleIndices
          ? Number(triangleIndices[triangle * 3 + corner])
          : triangle * 3 + corner;
        const offset = sourceIndex * 3;
        const nx = source[offset];
        const ny = source[offset + 1];
        const nz = source[offset + 2];
        const broad =
          Math.sin(nx * 3.15 + time * 0.31) *
          Math.cos(ny * 3.4 - time * 0.24) *
          Math.sin(nz * 3.05 + time * 0.2);
        const lobes =
          Math.sin((nx + ny) * 5.6 - time * 0.28) *
          Math.cos((ny - nz) * 4.9 + time * 0.22);
        const detail =
          Math.cos((nx - nz) * 8.2 + time * 0.19) *
          Math.sin((ny + nz) * 7.4 - time * 0.17);
        const radius =
          1 + broad * 0.165 + lobes * 0.165 + detail * 0.032;
        const rotated = rotate(
          nx * radius,
          ny * radius,
          nz * radius,
          -0.1 + pointer.y,
          -0.25 + time * 0.075 + pointer.x,
        );
        const perspective = 1 / (1.08 - rotated.z * 0.15);
        points.push({
          ...rotated,
          sx: centerX + rotated.x * size * perspective,
          sy: centerY + rotated.y * size * perspective,
        });
      }
      const typedPoints = points as [Vertex, Vertex, Vertex];
      triangles.push({
        points: typedPoints,
        depth: typedPoints.reduce((sum, point) => sum + point.z, 0) / 3,
      });
    }
    triangles.sort((a, b) => a.depth - b.depth);

    for (const triangle of triangles) {
      const front = Math.max(0, Math.min(1, (triangle.depth + 1.15) / 2.3));
      const [a, b, c] = triangle.points;
      context.beginPath();
      context.moveTo(a.sx, a.sy);
      context.lineTo(b.sx, b.sy);
      context.lineTo(c.sx, c.sy);
      context.closePath();
      context.fillStyle = `rgba(2, 21, 57, ${0.2 + front * 0.46})`;
      context.fill();
      context.strokeStyle = `rgba(13, 91, 202, ${0.11 + front * 0.43})`;
      context.lineWidth = front > 0.72 ? 0.52 : 0.28;
      context.stroke();
    }
    if (!reducedMotion) animation = window.requestAnimationFrame(draw);
  };

  const observer = new ResizeObserver(() => {
    resize();
    if (reducedMotion) draw(startedAt);
  });
  observer.observe(mount);
  window.addEventListener("pointermove", onPointerMove, { passive: true });
  resize();
  draw(startedAt);

  return () => {
    window.cancelAnimationFrame(animation);
    observer.disconnect();
    window.removeEventListener("pointermove", onPointerMove);
    fallbackGeometry.dispose();
  };
}
