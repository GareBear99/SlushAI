// TripoSR in the browser — SlushAI static generation (no server).
// Pipeline: image -> DINO (fp32) -> triplane (int8 per-channel) -> decoder
// grid (128^3) -> marching cubes -> vertex colours -> GLB / OBJ.
// Proven in Node with onnxruntime-web (same library this page uses):
//   chair.png -> 12,802 verts / 25,600 faces, watertight, vol 0.0927, 140 s.
// Models are chunked (~48 MB) under triposr/models/ with sha256 in manifest.json
// (GitHub rejects single files > 100 MB on push).
(function () {
  'use strict';

  var RES = 128, RADIUS = 0.87, THRESHOLD = 25.0;
  var MODEL_DIR = 'triposr/models/';
  var sessions = {};
  var lastMesh = null; // {positions, normals, colors, faces}

  var logEl = null, barEl = null, stageEl = null;
  function log(msg) {
    var line = '[' + new Date().toISOString().substr(11, 8) + '] ' + msg;
    if (logEl) { logEl.textContent += line + '\n'; logEl.scrollTop = logEl.scrollHeight; }
    console.log(line);
  }
  function stage(text, frac) {
    if (stageEl) stageEl.textContent = text;
    if (barEl) barEl.style.width = Math.round((frac || 0) * 100) + '%';
  }

  function sha256Hex(buf) {
    return crypto.subtle.digest('SHA-256', buf).then(function (hash) {
      var bytes = new Uint8Array(hash), out = '';
      for (var i = 0; i < bytes.length; i++) out += ('0' + bytes[i].toString(16)).slice(-2);
      return out;
    });
  }

  function loadModel(name, manifest) {
    var entry = manifest.models[name];
    var parts = [];
    var chain = Promise.resolve();
    entry.chunks.forEach(function (ch, idx) {
      chain = chain.then(function () {
        return fetch(MODEL_DIR + name + '/' + ch.file).then(function (r) {
          if (!r.ok) throw new Error('fetch failed: ' + ch.file + ' (' + r.status + ')');
          return r.arrayBuffer();
        }).then(function (buf) {
          return sha256Hex(buf).then(function (hex) {
            if (hex !== ch.sha256) throw new Error('chunk sha256 mismatch: ' + ch.file);
            parts[idx] = buf;
            stage('Loading ' + name + ' model… ' + (idx + 1) + '/' + entry.chunks.length,
                  (idx + 1) / entry.chunks.length * 0.25);
          });
        });
      });
    });
    return chain.then(function () {
      var total = parts.reduce(function (s, p) { return s + p.byteLength; }, 0);
      var all = new Uint8Array(total), off = 0;
      parts.forEach(function (p) { all.set(new Uint8Array(p), off); off += p.byteLength; });
      return sha256Hex(all.buffer).then(function (hex) {
        if (hex !== entry.sha256) throw new Error('model sha256 mismatch: ' + name);
        log(name + ' model verified (' + (total / 1e6).toFixed(1) + ' MB, sha256 ok)');
        return ort.InferenceSession.create(all);
      });
    });
  }

  function loadSessions(onProgress) {
    ort.env.wasm.wasmPaths = 'triposr/ort/';
    ort.env.wasm.numThreads = Math.min(4, (navigator.hardwareConcurrency || 4));
    return fetch(MODEL_DIR + 'manifest.json').then(function (r) { return r.json(); })
      .then(function (manifest) {
        return loadModel('dino', manifest).then(function (s) {
          sessions.dino = s; log('DINO session ready');
          return loadModel('triplane', manifest);
        }).then(function (s) {
          sessions.triplane = s; log('Triplane session ready');
          return loadModel('decoder', manifest);
        }).then(function (s) {
          sessions.decoder = s; log('Decoder session ready');
        });
      });
  }

  function imageToTensor(img) {
    var canvas = document.createElement('canvas');
    canvas.width = 512; canvas.height = 512;
    var ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0, 512, 512);
    var data = ctx.getImageData(0, 0, 512, 512).data;
    var out = new Float32Array(1 * 3 * 512 * 512);
    for (var i = 0, n = 512 * 512; i < n; i++) {
      // PIL convert("RGB"): stored RGB channels, alpha ignored.
      out[i] = data[i * 4] / 255;
      out[n + i] = data[i * 4 + 1] / 255;
      out[2 * n + i] = data[i * 4 + 2] / 255;
    }
    return new ort.Tensor('float32', out, [1, 3, 512, 512]);
  }

  function decodeGrid(triplane3, onChunk) {
    var N = RES * RES * RES;
    var dens = new Float32Array(N);
    var CH = 65536, done = 0;
    function step(i) {
      var n = Math.min(CH, N - i);
      var pts = new Float32Array(n * 3);
      for (var j = 0; j < n; j++) {
        var idx = i + j;
        var gx = Math.floor(idx / (RES * RES));
        var gy = Math.floor((idx % (RES * RES)) / RES);
        var gz = idx % RES;
        pts[j * 3] = (gx / (RES - 1)) * (2 * RADIUS) - RADIUS;
        pts[j * 3 + 1] = (gy / (RES - 1)) * (2 * RADIUS) - RADIUS;
        pts[j * 3 + 2] = (gz / (RES - 1)) * (2 * RADIUS) - RADIUS;
      }
      return sessions.decoder.run({
        points: new ort.Tensor('float32', pts, [n, 3]),
        triplane: triplane3,
      }).then(function (out) {
        dens.set(out.density.data, i);
        done += n;
        if (onChunk) onChunk(done / N);
        if (i + n < N) return step(i + n);
        return dens;
      });
    }
    return step(0);
  }

  function computeNormals(pos, faces) {
    var normals = new Float32Array(pos.length);
    for (var i = 0; i < faces.length; i += 3) {
      var a = faces[i] * 3, b = faces[i + 1] * 3, c = faces[i + 2] * 3;
      var ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
      var vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
      var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      normals[a] += nx; normals[a + 1] += ny; normals[a + 2] += nz;
      normals[b] += nx; normals[b + 1] += ny; normals[b + 2] += nz;
      normals[c] += nx; normals[c + 1] += ny; normals[c + 2] += nz;
    }
    for (var j = 0; j < normals.length; j += 3) {
      var len = Math.hypot(normals[j], normals[j + 1], normals[j + 2]) || 1;
      normals[j] /= len; normals[j + 1] /= len; normals[j + 2] /= len;
    }
    return normals;
  }

  function generate(img) {
    var t0 = Date.now();
    var secs = function () { return ((Date.now() - t0) / 1000).toFixed(1); };
    stage('Encoding image…', 0.05);
    var tensor = imageToTensor(img);
    return sessions.dino.run({ image: tensor }).then(function (out) {
      log('DINO: ' + secs() + 's -> [' + out.image_tokens.dims + ']');
      stage('Triplane transformer… (the slow part, ~1–2 min)', 0.35);
      return sessions.triplane.run({ image_tokens: out.image_tokens });
    }).then(function (out) {
      log('Triplane: ' + secs() + 's -> [' + out.triplane.dims + ']');
      var triplane3 = new ort.Tensor('float32', out.triplane.data, [3, 40, 64, 64]);
      stage('Decoding density grid…', 0.55);
      return decodeGrid(triplane3, function (f) {
        stage('Decoding density grid… ' + Math.round(f * 100) + '%', 0.55 + f * 0.2);
      }).then(function (dens) { return { dens: dens, triplane3: triplane3 }; });
    }).then(function (r) {
      stage('Marching cubes…', 0.8);
      var N = RES * RES * RES;
      var level = new Float32Array(N);
      for (var i = 0; i < N; i++) level[i] = -(r.dens[i] - THRESHOLD);
      var mc = TripoSRMC.marchingCubes(level, RES, 0.0);
      log('Marching cubes: ' + secs() + 's -> ' + (mc.positions.length / 3) + ' verts / ' + (mc.faces.length / 3) + ' faces');
      var pos = new Float32Array(mc.positions.length);
      for (var i = 0; i < mc.positions.length; i += 3) {
        pos[i] = mc.positions[i + 2] / (RES - 1) * (2 * RADIUS) - RADIUS;
        pos[i + 1] = mc.positions[i + 1] / (RES - 1) * (2 * RADIUS) - RADIUS;
        pos[i + 2] = mc.positions[i] / (RES - 1) * (2 * RADIUS) - RADIUS;
      }
      stage('Vertex colours…', 0.88);
      var nV = pos.length / 3, colors = new Float32Array(nV * 3), CH = 65536;
      var chain = Promise.resolve();
      for (var s0 = 0; s0 < nV; s0 += CH) {
        (function (start) {
          chain = chain.then(function () {
            var n = Math.min(CH, nV - start);
            return sessions.decoder.run({
              points: new ort.Tensor('float32', pos.slice(start * 3, (start + n) * 3), [n, 3]),
              triplane: r.triplane3,
            }).then(function (o) { colors.set(o.color.data, start * 3); });
          });
        })(s0);
      }
      return chain.then(function () {
        var normals = computeNormals(pos, mc.faces);
        lastMesh = { positions: pos, normals: normals, colors: colors, faces: mc.faces };
        log('TOTAL: ' + secs() + 's — ' + (pos.length / 3) + ' verts / ' + (mc.faces.length / 3) + ' faces');
        stage('Done in ' + secs() + 's', 1.0);
        return lastMesh;
      });
    });
  }

  // ---- GLB export (minimal, single mesh, POSITION + NORMAL + COLOR_0 + indices) ----
  function exportGLB(mesh) {
    var pos = mesh.positions, nor = mesh.normals, col = mesh.colors, faces = mesh.faces;
    var posBytes = pos.byteLength, norBytes = nor.byteLength, colBytes = col.byteLength;
    var idx = new Uint32Array(faces);
    var idxBytes = idx.byteLength;
    function align4(n) { return (n + 3) & ~3; }
    var binLen = align4(posBytes) + align4(norBytes) + align4(colBytes) + align4(idxBytes);
    var bin = new Uint8Array(binLen), off = 0;
    function put(arr) { bin.set(new Uint8Array(arr.buffer, arr.byteOffset, arr.byteLength), off); off += align4(arr.byteLength); }
    put(pos); put(nor); put(col); put(idx);
    var min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    for (var i = 0; i < pos.length; i += 3) {
      for (var c = 0; c < 3; c++) {
        if (pos[i + c] < min[c]) min[c] = pos[i + c];
        if (pos[i + c] > max[c]) max[c] = pos[i + c];
      }
    }
    var oPos = 0, oNor = align4(posBytes), oCol = oNor + align4(norBytes), oIdx = oCol + align4(colBytes);
    var json = {
      asset: { version: '2.0', generator: 'SlushAI TripoSR (static, ONNX Runtime Web)' },
      scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }],
      meshes: [{ primitives: [{ attributes: { POSITION: 0, NORMAL: 1, COLOR_0: 2 }, indices: 3, material: 0 }] }],
      materials: [{ pbrMetallicRoughness: { baseColorFactor: [1, 1, 1, 1], metallicFactor: 0, roughnessFactor: 1 } }],
      accessors: [
        { bufferView: 0, componentType: 5126, count: pos.length / 3, type: 'VEC3', min: min, max: max },
        { bufferView: 1, componentType: 5126, count: nor.length / 3, type: 'VEC3' },
        { bufferView: 2, componentType: 5126, count: col.length / 3, type: 'VEC3' },
        { bufferView: 3, componentType: 5125, count: idx.length, type: 'SCALAR' },
      ],
      bufferViews: [
        { buffer: 0, byteOffset: oPos, byteLength: posBytes },
        { buffer: 0, byteOffset: oNor, byteLength: norBytes },
        { buffer: 0, byteOffset: oCol, byteLength: colBytes },
        { buffer: 0, byteOffset: oIdx, byteLength: idxBytes },
      ],
      buffers: [{ byteLength: binLen }],
    };
    var jsonBytes = new TextEncoder().encode(JSON.stringify(json));
    var jsonPad = align4(jsonBytes.length) - jsonBytes.length;
    var total = 12 + 8 + jsonBytes.length + jsonPad + 8 + binLen;
    var out = new Uint8Array(total);
    var dv = new DataView(out.buffer);
    dv.setUint32(0, 0x46546C67, true); // 'glTF'
    dv.setUint32(4, 2, true);
    dv.setUint32(8, total, true);
    dv.setUint32(12, jsonBytes.length + jsonPad, true);
    dv.setUint32(16, 0x4E4F534A, true); // 'JSON'
    out.set(jsonBytes, 20);
    out.fill(0x20, 20 + jsonBytes.length, 20 + jsonBytes.length + jsonPad); // space padding
    var binOff = 20 + jsonBytes.length + jsonPad;
    dv.setUint32(binOff, binLen, true);
    dv.setUint32(binOff + 4, 0x004E4942, true); // 'BIN\0'
    out.set(bin, binOff + 8);
    return new Blob([out], { type: 'model/gltf-binary' });
  }

  function exportOBJ(mesh) {
    var lines = ['# SlushAI TripoSR (static, ONNX Runtime Web)'];
    var pos = mesh.positions, col = mesh.colors, faces = mesh.faces;
    for (var i = 0; i < pos.length; i += 3) {
      lines.push('v ' + pos[i].toFixed(6) + ' ' + pos[i + 1].toFixed(6) + ' ' + pos[i + 2].toFixed(6) +
        ' ' + col[i].toFixed(4) + ' ' + col[i + 1].toFixed(4) + ' ' + col[i + 2].toFixed(4));
    }
    for (var j = 0; j < faces.length; j += 3) {
      lines.push('f ' + (faces[j] + 1) + ' ' + (faces[j + 1] + 1) + ' ' + (faces[j + 2] + 1));
    }
    return new Blob([lines.join('\n')], { type: 'text/plain' });
  }

  // ---- Canvas preview (painter's algorithm, drag to rotate) ----
  var preview = { rotX: -0.4, rotY: 0.6 };
  function drawPreview(canvas) {
    if (!lastMesh) return;
    var ctx = canvas.getContext('2d');
    var W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#0b0b10'; ctx.fillRect(0, 0, W, H);
    var pos = lastMesh.positions, col = lastMesh.colors, faces = lastMesh.faces;
    var cx = Math.cos(preview.rotX), sx = Math.sin(preview.rotX);
    var cy = Math.cos(preview.rotY), sy = Math.sin(preview.rotY);
    var scale = Math.min(W, H) * 0.42;
    var tris = [];
    for (var i = 0; i < faces.length; i += 3) {
      var pts = [], zsum = 0;
      for (var k = 0; k < 3; k++) {
        var p = faces[i + k] * 3;
        var x = pos[p], y = pos[p + 1], z = pos[p + 2];
        var x1 = x * cy + z * sy, z1 = -x * sy + z * cy;
        var y1 = y * cx - z1 * sx, z2 = y * sx + z1 * cx;
        pts.push([W / 2 + x1 * scale, H / 2 - y1 * scale]);
        zsum += z2;
      }
      var c = faces[i] * 3;
      tris.push([zsum / 3, pts, col[c], col[c + 1], col[c + 2]]);
    }
    tris.sort(function (a, b) { return a[0] - b[0]; });
    for (var t = 0; t < tris.length; t++) {
      var tri = tris[t];
      ctx.beginPath();
      ctx.moveTo(tri[1][0][0], tri[1][0][1]);
      ctx.lineTo(tri[1][1][0], tri[1][1][1]);
      ctx.lineTo(tri[1][2][0], tri[1][2][1]);
      ctx.closePath();
      var shade = 0.55 + 0.45 * Math.max(0, Math.min(1, (tri[0] + 0.87) / 1.74));
      ctx.fillStyle = 'rgb(' + Math.round(tri[2] * 255 * shade) + ',' + Math.round(tri[3] * 255 * shade) + ',' + Math.round(tri[4] * 255 * shade) + ')';
      ctx.fill();
    }
  }

  window.SlushAITripoSR = {
    loadSessions: loadSessions, generate: generate, exportGLB: exportGLB, exportOBJ: exportOBJ,
    drawPreview: drawPreview, preview: preview,
    get lastMesh() { return lastMesh; },
    bindLog: function (el, bar, stage) { logEl = el; barEl = bar; stageEl = stage; },
  };
})();
