// View3dWebGL
// Inspired by https://developer.mozilla.org/en-US/docs/Web/API/WebGL_API/Tutorial/Lighting_in_WebGL Sample 7
// No uNormalMatrix but vLightingBack
import * as mat4 from './lib/mat4.js';
import { Vector3 } from './Vector3.js';

export class View3d {
    // Vertex shader program
    VERTEX_SHADER = `#version 300 es
    precision highp float;
    
    in vec4 aVertexPosition;
    in vec3 aVertexNormal;
    in vec2 aTexCoordsFront;
    in vec2 aTexCoordsBack;

    uniform mat4 uModelViewMatrix;
    uniform mat4 uProjectionMatrix;

    out highp vec2 vTexCoordsFront;
    out highp vec2 vTexCoordsBack;
    out highp vec3 vLighting;
    void main(void) {
        gl_Position = uProjectionMatrix * uModelViewMatrix * aVertexPosition;
        vTexCoordsFront = aTexCoordsFront;
        vTexCoordsBack  = aTexCoordsBack;
        highp vec3 directionalVector =  normalize(vec3(0.1, 0.1, 0.75)); // normalize(vec3(0.85, 0.8, 0.75));
        highp vec4 normal = normalize(uModelViewMatrix * vec4(aVertexNormal, 0.0));
        float directional = dot(normal.xyz, directionalVector);
        vLighting = vec3(0.1) + directional;
    }
    `;

    // Fragment shader program
    FRAGMENT_SHADER = `#version 300 es
        precision highp float;
        
        in highp vec2 vTexCoordsFront;
        in highp vec2 vTexCoordsBack;
        in highp vec3 vLighting;
                
        uniform sampler2D uSamplerFront;
        uniform sampler2D uSamplerBack;
        uniform bool uLine; 
        out vec4 outColor; 
        void main(void) {
            highp vec4 texelColor;
            highp vec3 lighting = vLighting;
            if (uLine) {
                texelColor = vec4(0.0, 0.0, 0.0, 1.0);
            } else if (gl_FrontFacing) {
                texelColor = texture(uSamplerFront, vTexCoordsFront);
            } else {
                texelColor = texture(uSamplerBack,  vTexCoordsBack);
                lighting = vec3(0.1) - vLighting;            
            }
            outColor = vec4(texelColor.rgb * lighting, texelColor.a);
        }
    `;

    // Current rotation angle (x-axis, y-axis degrees)
    angleX = 0;
    angleY = 0;
    angleZ = 0;
    translationX = 0;
    translationY = 0;
    scale = 1;

    // Projection and model view matrix
    projection = new Float32Array(16);
    modelView = new Float32Array(16);
    canvasView = new Float32Array(16);

    wTexFront = 1;
    hTexFront = 1;
    wTexBack = 1;
    hTexBack = 1;
    vtx = [];
    ftx = [];
    btx = [];
    fnr = [];
    lin = [];

    constructor(model, canvas3d) {
        this.model = model;
        this.canvas3d = canvas3d;
        this.overlay = this.createOverlay(canvas3d);
        this.gl = canvas3d.getContext('webgl2');

        this.initShaders();
        this.initTextures();
        this.initPerspective();
        this.initModelView();

        globalThis.addEventListener('resize', () => {
            this.initPerspective();
            this.initModelView();
            this.render();
        });
    }

    // Stack a 2D overlay canvas on top of canvas3d (same parent, same CSS box).
    createOverlay(canvas3d) {
        const doc = globalThis.document;
        if (!doc?.createElement) return null;
        const overlay = doc.createElement('canvas');
        overlay.id = 'overlay';
        if (typeof canvas3d.after === 'function') {
            canvas3d.after(overlay);
        } else {
            canvas3d.parentNode?.insertBefore(overlay, canvas3d.nextSibling);
        }
        return overlay;
    }

    // Keep both canvas buffers identical; returns the shared pixel size.
    syncCanvasSize() {
        const width = this.canvas3d.clientWidth || this.canvas3d.width || 1;
        const height = this.canvas3d.clientHeight || this.canvas3d.height || 1;
        this.canvas3d.width = width;
        this.canvas3d.height = height;
        if (this.overlay) {
            this.overlay.width = width;
            this.overlay.height = height;
        }
        return { width, height };
    }

    get context2d() {
        return this.overlay?.getContext('2d');
    }

    initShaders() {
        const gl = this.gl;
        const program = gl.createProgram();
        const shaders = [[gl.VERTEX_SHADER, this.VERTEX_SHADER], [gl.FRAGMENT_SHADER, this.FRAGMENT_SHADER]].map(([type, source]) => {
            const shader = gl.createShader(type);
            gl.shaderSource(shader, source);
            gl.compileShader(shader);
            if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) console.error(gl.getShaderInfoLog(shader));
            gl.attachShader(program, shader);
            return shader;
        });
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
            console.error(`Shader link error: ${gl.getProgramInfoLog(program)}\n${shaders.map((s) => gl.getShaderInfoLog(s)).join('\n')}`);
        }
        gl.useProgram(program);
        gl.program = program;
        this.uniforms = Object.fromEntries(['uModelViewMatrix', 'uProjectionMatrix', 'uSamplerFront', 'uSamplerBack', 'uLine']
            .map((name) => [name, gl.getUniformLocation(program, name)]));
    }
    initTextures() {
        const blue = [0x70, 0xAC, 0xF3, 0xFF], yellow = [0xFF, 0xFF, 0x00, 0xA8];
        this.texPlaceholderFront = this.createTexture(blue);
        this.texImageFront = this.loadTexture('front', blue, (w, h) => { this.wTexFront = w; this.hTexFront = h; });
        this.texPlaceholderBack = this.createTexture(yellow);
        this.texImageBack = this.loadTexture('back', yellow, (w, h) => { this.wTexBack = w; this.hTexBack = h; });
        this.gl.uniform1i(this.uniforms.uSamplerFront, 0);
        this.gl.uniform1i(this.uniforms.uSamplerBack, 1);
        this.initBuffers();
        this.render();
    }
    createTexture(rgba) {
        const gl = this.gl;
        const texture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array(rgba));
        return texture;
    }
    loadTexture(id, rgba, setSize) {
        const gl = this.gl;
        const texture = this.createTexture(rgba);
        const src = globalThis.document.getElementById(id)?.src;
        if (!src) return texture;
        const image = new Image();
        image.onload = () => {
            gl.bindTexture(gl.TEXTURE_2D, texture);
            gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, 1);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
            gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, image);
            setSize(image.width, image.height);
            this.initBuffers();
            this.render();
        };
        image.src = src;
        return texture;
    }
    initPerspective() {
        const gl = this.gl;
        gl.clearColor(0xCC / 0xFF, 0xE4 / 0xFF, 1, 1);
        gl.enable(gl.DEPTH_TEST);
        gl.depthFunc(gl.LEQUAL);
        const {width, height} = this.syncCanvasSize();
        gl.viewport(0, 0, width, height);
        this.projection = mat4.perspective(mat4.create(), 40 * Math.PI / 180, width / height, 50, 1200);
        gl.uniformMatrix4fv(this.uniforms.uProjectionMatrix, false, this.projection);
    }
    initBuffers() {
        const gl = this.gl;
        this.vao ??= gl.createVertexArray();
        gl.bindVertexArray(this.vao);
        this.vtx = [];
        this.ftx = [];
        this.btx = [];
        this.fnr = [];
        this.lin = [];
        this.indexMap = new WeakMap();
        for (const f of this.model.faces) {
            const pts = f.points;
            const n = this.normal(pts);
            const faceIndex = new Map();
            for (let i = 1; i < pts.length - 1; i++) {
                for (const p of [pts[0], pts[i], pts[i + 1]]) {
                    const index = this.vtx.length / 3;
                    if (!this.indexMap.has(p)) this.indexMap.set(p, index);
                    if (!faceIndex.has(p)) faceIndex.set(p, index);
                    this.vtx.push(p.x + f.offset * n[0], p.y + f.offset * n[1], p.z + f.offset * n[2]);
                    this.fnr.push(...n);
                    this.ftx.push((200 + p.xf) / this.wTexFront, (200 + p.yf) / this.hTexFront);
                    this.btx.push((200 + p.xf) / this.wTexBack, (200 + p.yf) / this.hTexBack);
                }
            }
            pts.forEach((p, i) => this.lin.push(faceIndex.get(p), faceIndex.get(pts[(i + 1) % pts.length])));
        }
        this.vtxBuffer = this.attribute(this.vtxBuffer, 'aVertexPosition', this.vtx, 3);
        this.fnrBuffer = this.attribute(this.fnrBuffer, 'aVertexNormal', this.fnr, 3);
        this.ftxBuffer = this.attribute(this.ftxBuffer, 'aTexCoordsFront', this.ftx, 2);
        this.btxBuffer = this.attribute(this.btxBuffer, 'aTexCoordsBack', this.btx, 2);
        this.linBuffer ??= gl.createBuffer();
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.linBuffer);
        gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint32Array(this.lin), gl.STATIC_DRAW);
        gl.uniform1i(this.uniforms.uLine, 0);
        gl.bindVertexArray(null);
    }
    attribute(buffer, name, data, size) {
        const gl = this.gl;
        buffer ??= gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(data), gl.STATIC_DRAW);
        const location = gl.getAttribLocation(gl.program, name);
        gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0);
        gl.enableVertexAttribArray(location);
        return buffer;
    }
    // Compute Face normal in [3]
    normal(pts) {
        const n = [0, 0, 0];
        for (let i = 0; i < pts.length - 2; i++) {
            // Take triangles until p2p1 x p1p3 > 0.1
            const p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2];
            const u = [p2.x - p1.x, p2.y - p1.y, p2.z - p1.z];
            const v = [p3.x - p1.x, p3.y - p1.y, p3.z - p1.z];
            n[0] = u[1] * v[2] - u[2] * v[1];
            n[1] = u[2] * v[0] - u[0] * v[2];
            n[2] = u[0] * v[1] - u[1] * v[0];
            if (Math.abs(n[0]) + Math.abs(n[1]) + Math.abs(n[2]) > 0.1) {
                break;
            }
        }
        // n.normalize();
        const sq = Math.hypot(n[0], n[1], n[2]);
        if (sq < 1e-6) return [0, 0, 1];
        n[0] /= sq;
        n[1] /= sq;
        n[2] /= sq;
        return n;
    }
    // Model view matrix
    initModelView() {
        // Rotation around X axis
        let ex = mat4.create();
        mat4.translate(ex, ex, [this.translationX, this.translationY, -700]);   // recul en view space
        ex = mat4.rotateX(ex, ex, this.angleX * Math.PI / 180);
        // Rotation around Y axis
        ex = mat4.rotateY(ex, ex, this.angleY * Math.PI / 180);
        // Rotation around Z axis
        const mv = mat4.rotateZ(ex, ex, this.angleZ * Math.PI / 180);
        // Scale ModelView
        this.modelView = mat4.scale(mv, mv, [this.scale, this.scale, this.scale]);

        this.gl.uniformMatrix4fv(this.uniforms.uModelViewMatrix, false, this.modelView);

        this.updateCanvasCoords();
    }

    // Project model points into overlay/canvas pixel space (xCanvas, yCanvas)
    updateCanvasCoords() {
        const width = this.canvas3d.width || this.canvas3d.clientWidth || 1;
        const height = this.canvas3d.height || this.canvas3d.clientHeight || 1;
        const scale = mat4.scale(mat4.create(), mat4.create(), [width / 2, -height / 2, 1]);
        const translation = mat4.fromTranslation(mat4.create(), [1, -1, 0]);
        const overlayMat = mat4.multiply(mat4.create(), scale, translation);
        const projection = mat4.multiply(mat4.create(), this.projection, this.modelView);
        this.canvasView = mat4.multiply(mat4.create(), overlayMat, projection);
        for (const p of this.model.points) {
            const eye = Vector3.transformMat4(p, this.modelView);
            p.zEye = eye.z;
            const v = Vector3.transformMat4(p, this.canvasView);
            p.xCanvas = v.x;
            p.yCanvas = v.y;
        }
    }

    // Mean eye-space z of face vertices; lower = closer to camera.
    faceDepth(face) {
        let z = 0;
        for (const p of face.points) z += p.zEye ?? p.z;
        return z / face.points.length;
    }

    // Render
    render() {
        const gl = this.gl;

        // Faces with texture shader
        gl.useProgram(gl.program);
        gl.bindVertexArray(this.vao);

        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, this.model.textures ? this.texImageFront : this.texPlaceholderFront);

        gl.activeTexture(gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, this.model.textures ? this.texImageBack : this.texPlaceholderBack);

        // Clear and draw triangles
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

        // Faces
        gl.drawArrays(gl.TRIANGLES, 0, this.vtx.length / 3);

        if (this.model.lines){
            // Segments drawElements and not drawArrays because normals imply 3 vertices per triangle
            gl.uniform1i(this.uniforms.uLine, 1);
            gl.disable(gl.DEPTH_TEST);
            gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.linBuffer);
            gl.drawElements(gl.LINES, this.lin.length, gl.UNSIGNED_INT, 0);
            gl.enable(gl.DEPTH_TEST);
            gl.uniform1i(this.uniforms.uLine, 0);
        }

        // Model projected on overlay canvas
        const context2d = this.context2d;
        if (!context2d) return;
        context2d.clearRect(0, 0, this.overlay.width, this.overlay.height);
        // Black segments are done by webgl, see this.model.lines
        // Faces first so their fill/hover outline sits under segment and point highlights.
        this.drawFaces(this.model.faces);
        this.drawSegments(this.model.segments);
        this.drawPoints(this.model.points);
        if (this.model.labels) {
            this.drawLabels(context2d);
        }
    }

    // Draw on overlay. Called from render()
    // Only selected/hovered points are drawn; selected drawn last (on top).
    drawPoints(points) {
        const context2d = this.context2d;
        const visible = points.filter(p => p.select || p.hover);
        visible.sort((a, b) => (a.select ? 1 : 0) - (b.select ? 1 : 0));
        for (const p of visible) {
            // Circle with color for selected, bigger for hovered
            context2d.beginPath();
            context2d.arc(p.xCanvas, p.yCanvas, p.hover ? 10 : 6, 0, 2 * Math.PI);
            context2d.fillStyle = p.select ? 'red' : 'blue';
            context2d.fill();
        }
    }

    // Stroke a single segment on the overlay: red/width 4 for the fold axis
    // (and its hover candidate in fold mode), blue/width 6 for a plain hover.
    strokeSegment(segment, strokeStyle, lineWidth) {
        const context2d = this.context2d;
        const x1 = segment.p1.xCanvas, y1 = segment.p1.yCanvas;
        const x2 = segment.p2.xCanvas, y2 = segment.p2.yCanvas;
        if (x1 == null || x2 == null) return;
        context2d.beginPath();
        context2d.moveTo(x1, y1);
        context2d.lineTo(x2, y2);
        context2d.strokeStyle = strokeStyle;
        context2d.lineWidth = lineWidth;
        context2d.lineCap = 'round';
        context2d.stroke();
    }

    // Draw on overlay. Called from render()
    // Only the selected (axis) or hovered segments are drawn.
    drawSegments(segments) {
        // A face being dragged is only .hover (not yet .select) until the fold
        // commits, so the axis candidate must count that too, or it renders blue.
        const foldMode = this.model.faces.some(f => f.select || f.hover);
        // Only the first selected segment is the fold axis
        const axis = segments.find(s => s.select);

        for (const s of segments) {
            if (s === axis || !s.hover) continue;
            if (foldMode) this.strokeSegment(s, 'red', 4);
            else this.strokeSegment(s, 'blue', 6);
        }
        if (axis) this.strokeSegment(axis, 'red', 4);
    }

    // Draw faces: selected = fill only (no full border — that hid the fold axis).
    // Hover without select still gets a blue outline.
    // Only selected/hovered faces are drawn; selected drawn last (on top).
    drawFaces(faces) {
        const context2d = this.context2d;
        const visible = faces.filter(f => f.select || f.hover);
        visible.sort((a, b) => (a.select ? 1 : 0) - (b.select ? 1 : 0));
        for (const f of visible) {
            const pts = f.points;
            if (!pts || pts.length === 0) continue;
            context2d.beginPath();
            context2d.moveTo(pts[0].xCanvas, pts[0].yCanvas);
            pts.forEach(p => context2d.lineTo(p.xCanvas, p.yCanvas));
            context2d.closePath();
            context2d.fillStyle = f.select ? 'rgba(255,0,0,0.35)' : 'rgba(0,102,255,0.3)';
            context2d.fill();
            if (f.hover && !f.select) {
                context2d.lineWidth = 4;
                context2d.strokeStyle = 'blue';
                context2d.stroke();
            }
        }
    }

    /**
     * Draw labels for Points and Segments; each label takes a slot on the screen.
     */
    labels = [];

    drawLabels(context2d) {
        this.labels = [];
        for (const p of this.model.points) {
            if (p.hidden || p.xCanvas == null) continue;
            this.placeLabel(
                context2d,
                p.xCanvas, p.yCanvas,
                String(this.model.points.indexOf(p)),
                p.select ? 'red' : 'skyblue',
            );
        }
        for (const s of this.model.segments) {
            if (s.p1.xCanvas == null || s.p2.xCanvas == null) continue;
            const mx = (s.p1.xCanvas + s.p2.xCanvas) / 2;
            const my = (s.p1.yCanvas + s.p2.yCanvas) / 2;
            this.placeLabel(
                context2d,
                mx, my,
                String(this.model.segments.indexOf(s)),
                s.select ? 'red' : 'white',
            );
        }
    }

    placeLabel(context2d, x, y, txt, fillStyle) {
        const oneLabel = new Label(x, y);
        this.labels.push(oneLabel);
        this.labels.forEach(label => {
            if (label !== oneLabel && label.over(oneLabel)) {
                oneLabel.moveLabel();
            }
        });
        context2d.strokeStyle = 'black';
        context2d.beginPath();
        context2d.moveTo(x, y);
        context2d.lineTo(oneLabel.getX(), oneLabel.getY());
        context2d.lineWidth = 1;
        context2d.stroke();
        const radius = 12;
        context2d.fillStyle = fillStyle;
        context2d.beginPath();
        context2d.arc(oneLabel.getX(), oneLabel.getY(), radius, 0, 2 * Math.PI);
        context2d.stroke();
        context2d.fill();
        context2d.fillStyle = 'black';
        context2d.font = '20px serif';
        context2d.fillText(txt, oneLabel.getX() - 4 * (txt.length), oneLabel.getY() + 5);
    }
}

class Label {
    static size = 20;

    constructor(x, y) {
        this.x = x;
        this.y = y;
        this.n = 0;
    }

    getX() {
        return Math.floor(this.x + Label.size * 2 * Math.cos((this.n - 1) * Math.PI / 4));
    }

    getY() {
        return Math.floor(this.y + Label.size * 2 * Math.sin((this.n - 1) * Math.PI / 4));
    }

    moveLabel() {
        this.n++;
        return this.n > 8;
    }

    over(other) {
        const dx = this.getX() - other.getX();
        const dy = this.getY() - other.getY();
        return !(Math.abs(dy) > 20 || Math.abs(dx) > 20);

    }
}
