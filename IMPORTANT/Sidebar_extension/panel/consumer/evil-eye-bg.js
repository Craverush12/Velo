/**
 * EvilEye WebGL background for the home/new-chat panel.
 * Self-contained — no npm, no OGL dependency. Vanilla WebGL.
 * Rendered into a canvas behind #viewHome content.
 */
(function () {
  "use strict";

  var CFG = {
    eyeColor:    [0.0, 1.0, 0.969],          // #00fff7
    bgColor:     [0.0706, 0.0588, 0.0902],   // #120F17
    intensity:   1.5,
    pupilSize:   1.05,
    irisWidth:   0.25,
    glowIntensity: 0.2,
    scale:       0.8,
    noiseScale:  2.1,
    pupilFollow: 1.0,
    flameSpeed:  1.6,
  };

  /* ── Vertex shader ─────────────────────────────────────────────── */
  var VERT = [
    "attribute vec2 aPos;",
    "varying   vec2 vUv;",
    "void main(){",
    "  vUv = aPos*0.5+0.5;",
    "  gl_Position = vec4(aPos,0.0,1.0);",
    "}"
  ].join("\n");

  /* ── Fragment shader ───────────────────────────────────────────── */
  var FRAG = [
    "precision highp float;",
    "varying vec2 vUv;",
    "uniform float uTime;",
    "uniform vec2  uMouse;",
    "uniform vec2  uRes;",
    "uniform vec3  uEye;",
    "uniform vec3  uBg;",
    "uniform float uScale;",
    "uniform float uPupilSz;",
    "uniform float uIrisW;",
    "uniform float uIntensity;",
    "uniform float uGlow;",
    "uniform float uNoiseSc;",
    "uniform float uFlameSp;",
    "uniform float uFollow;",

    /* gradient noise */
    "vec2 h2(vec2 p){",
    "  p=vec2(dot(p,vec2(127.1,311.7)),dot(p,vec2(269.5,183.3)));",
    "  return fract(sin(p)*43758.5453);",
    "}",
    "float gn(vec2 p){",
    "  vec2 i=floor(p),f=fract(p),u=f*f*(3.0-2.0*f);",
    "  return mix(",
    "    mix(dot(h2(i         )*2.0-1.0,f         ),",
    "        dot(h2(i+vec2(1,0))*2.0-1.0,f-vec2(1,0)),u.x),",
    "    mix(dot(h2(i+vec2(0,1))*2.0-1.0,f-vec2(0,1)),",
    "        dot(h2(i+vec2(1,1))*2.0-1.0,f-vec2(1,1)),u.x),u.y);",
    "}",
    "float fbm(vec2 p){",
    "  float v=0.0,a=0.5;",
    "  mat2 r=mat2(1.6,1.2,-1.2,1.6);",
    "  for(int i=0;i<4;i++){v+=a*gn(p);p=r*p;a*=0.5;}",
    "  return v;",
    "}",

    /* almond SDF: abs(y) < h*(1-x²/w²) */
    "float eyeSDF(vec2 p,float w,float h){",
    "  float k=clamp(abs(p.x)/w,0.0,1.0);",
    "  return abs(p.y)-h*(1.0-k*k);",
    "}",

    "void main(){",
    "  vec2 uv=vUv-0.5;",
    "  uv.x*=uRes.x/uRes.y;",  /* aspect-correct */
    "  uv/=uScale;",

    "  float t=uTime*uFlameSp;",

    /* eye lid shape */
    "  float W=0.28, H=0.13;",
    "  float eSDF =eyeSDF(uv,W,H);",
    "  float eBlend=1.0-smoothstep(-0.004,0.014,eSDF);",

    /* pupil center with mouse follow */
    "  vec2 pc=uMouse*0.05*uFollow;",
    "  float dp=length(uv-pc);",

    /* radii */
    "  float iR=0.115;",
    "  float pR=iR*(1.0-uIrisW)*uPupilSz*0.85;",

    /* flame noise in polar space around pupil */
    "  vec2 rel=(uv-pc)*uNoiseSc;",
    "  float ang=atan(rel.y,rel.x);",
    "  float rad=length(rel);",
    "  vec2 nu=vec2(rad,ang*0.159);",   /* 0.159 ≈ 1/(2π) */
    "  float fn=fbm(nu*2.0+vec2(0.0,-t*0.55))*0.5+0.5;",

    /* masks */
    "  float irisMask=clamp(smoothstep(pR-0.008,pR,dp)-smoothstep(iR-0.006,iR,dp),0.0,1.0);",
    "  float pupilMask=1.0-smoothstep(pR-0.008,pR,dp);",
    "  float halo=exp(-dp*7.0/iR)*uGlow*uIntensity;",

    /* build colour */
    "  vec3 col=uBg;",

    /* sclera tint inside lid */
    "  col=mix(col,uBg*1.35,eBlend*0.3);",

    /* iris with flame */
    "  vec3 iCol=uEye*mix(0.45,1.0,fn)*uIntensity;",
    "  col=mix(col,iCol,irisMask*eBlend);",
    "  col+=uEye*fn*irisMask*eBlend*0.22*uIntensity;",

    /* pupil dark core */
    "  col=mix(col,vec3(0.012,0.008,0.022),pupilMask*eBlend);",

    /* specular highlight on pupil */
    "  vec2 sv=uv-pc-vec2(-pR*0.38,pR*0.42);",
    "  float spec=(1.0-smoothstep(0.0,pR*0.28,length(sv)))*pupilMask*eBlend;",
    "  col+=vec3(0.85,1.0,1.0)*spec*0.45;",

    /* iris halo */
    "  col+=uEye*halo*eBlend*(1.0-pupilMask);",

    /* outer ambient glow */
    "  col+=uEye*exp(-length(uv)*3.2)*uGlow*0.5;",

    /* lid-edge fade back to bg */
    "  col=mix(col,uBg,smoothstep(-0.006,0.020,eSDF)*0.92);",

    "  gl_FragColor=vec4(col,1.0);",
    "}"
  ].join("\n");

  /* ── WebGL helpers ─────────────────────────────────────────────── */
  function mkShader(gl, type, src) {
    var s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      console.error("[EvilEye] shader:", gl.getShaderInfoLog(s));
      gl.deleteShader(s);
      return null;
    }
    return s;
  }

  function mkProg(gl) {
    var vs = mkShader(gl, gl.VERTEX_SHADER, VERT);
    var fs = mkShader(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return null;
    var p = gl.createProgram();
    gl.attachShader(p, vs);
    gl.attachShader(p, fs);
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      console.error("[EvilEye] link:", gl.getProgramInfoLog(p));
      return null;
    }
    return p;
  }

  /* ── Main init ─────────────────────────────────────────────────── */
  function initEvilEye(host) {
    if (host._evilEyeActive) return;
    host._evilEyeActive = true;

    var canvas = document.createElement("canvas");
    canvas.className = "evil-eye-canvas";
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText = [
      "position:absolute", "inset:0", "width:100%", "height:100%",
      "pointer-events:none", "z-index:0", "display:block", "opacity:1",
      "transition:opacity 0.4s ease",
    ].join(";");

    var gl = canvas.getContext("webgl", { antialias: false, alpha: false });
    if (!gl) {
      host._evilEyeActive = false;
      return;
    }

    var prog = mkProg(gl);
    if (!prog) {
      host._evilEyeActive = false;
      return;
    }

    /* ensure host is a positioning context */
    var hostPos = getComputedStyle(host).position;
    if (hostPos === "static") host.style.position = "relative";

    /* insert canvas first */
    host.insertBefore(canvas, host.firstChild);

    /* lift existing content above canvas */
    var children = Array.prototype.slice.call(host.children);
    children.forEach(function (ch) {
      if (ch === canvas) return;
      if (getComputedStyle(ch).position === "static") {
        ch.style.position = "relative";
      }
      if (!ch.style.zIndex) ch.style.zIndex = "1";
    });

    /* quad */
    var vbuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbuf);
    gl.bufferData(gl.ARRAY_BUFFER,
      new Float32Array([-1,-1, 1,-1, -1,1, 1,1]),
      gl.STATIC_DRAW);
    var aPos = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

    /* uniform locations */
    var U = {};
    ["uTime","uMouse","uRes","uEye","uBg",
     "uScale","uPupilSz","uIrisW","uIntensity",
     "uGlow","uNoiseSc","uFlameSp","uFollow"].forEach(function (n) {
      U[n] = gl.getUniformLocation(prog, n);
    });

    var mouse = [0, 0];
    var raf = null;
    var t0 = performance.now();

    function onMove(e) {
      var r = host.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return;
      mouse[0] =  ((e.clientX - r.left) / r.width  - 0.5) * 2;
      mouse[1] = -((e.clientY - r.top)  / r.height - 0.5) * 2;
    }
    document.addEventListener("mousemove", onMove, { passive: true });

    function resize() {
      var r = host.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {
        canvas.width  = Math.round(r.width);
        canvas.height = Math.round(r.height);
        gl.viewport(0, 0, canvas.width, canvas.height);
      }
    }
    var ro = new ResizeObserver(resize);
    ro.observe(host);
    resize();

    function draw() {
      raf = requestAnimationFrame(draw);

      /* hide canvas in light mode — eye is designed for dark */
      var isLight = document.documentElement.classList.contains("light-mode");
      canvas.style.opacity = isLight ? "0" : "1";
      if (isLight) return;

      var t = (performance.now() - t0) / 1000;
      gl.useProgram(prog);
      gl.uniform1f(U.uTime,      t);
      gl.uniform2fv(U.uMouse,    mouse);
      gl.uniform2f (U.uRes,      canvas.width, canvas.height);
      gl.uniform3fv(U.uEye,      CFG.eyeColor);
      gl.uniform3fv(U.uBg,       CFG.bgColor);
      gl.uniform1f(U.uScale,     CFG.scale);
      gl.uniform1f(U.uPupilSz,   CFG.pupilSize);
      gl.uniform1f(U.uIrisW,     CFG.irisWidth);
      gl.uniform1f(U.uIntensity, CFG.intensity);
      gl.uniform1f(U.uGlow,      CFG.glowIntensity);
      gl.uniform1f(U.uNoiseSc,   CFG.noiseScale);
      gl.uniform1f(U.uFlameSp,   CFG.flameSpeed);
      gl.uniform1f(U.uFollow,    CFG.pupilFollow);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }

    draw();

    /* cleanup if host is detached from DOM */
    function cleanup() {
      if (document.contains(host)) return;
      cancelAnimationFrame(raf);
      document.removeEventListener("mousemove", onMove);
      ro.disconnect();
      domObs.disconnect();
      host._evilEyeActive = false;
    }
    var domObs = new MutationObserver(cleanup);
    domObs.observe(document.body, { childList: true, subtree: false });
  }

  /* ── Boot: watch for viewHome becoming visible ─────────────────── */
  function setup() {
    var homeEl = document.getElementById("viewHome");
    if (!homeEl) return;

    /* init now if already visible */
    if (!homeEl.hidden) {
      initEvilEye(homeEl);
    }

    /* watch hidden attr — sidebar.js toggles it on "New Chat" click */
    var attrObs = new MutationObserver(function () {
      if (!homeEl.hidden) initEvilEye(homeEl);
    });
    attrObs.observe(homeEl, { attributes: true, attributeFilter: ["hidden"] });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
})();
