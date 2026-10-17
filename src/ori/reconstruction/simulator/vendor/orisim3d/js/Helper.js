import {Segment} from './Segment.js';
import {Face} from './Face.js';
import {Vector3} from './Vector3.js';
import {State} from './Model.js';
import * as mat4 from './lib/mat4.js';

const CLICK_PX_MOUSE = 12;
const CLICK_PX_TOUCH = 24;
// A fingertip covers far more pixels than a cursor: widen the pick radii accordingly
const PICK_FACTOR_TOUCH = 2;

export class Helper {
    constructor(model, command, view3d, view2d) {
        this.model = model;
        this.command = command;
        this.view3d = view3d;
        this.view2d = view2d;
        this.currentCanvas = undefined;
        this.orbiting = false;
        this.touchTime = 0;
        this.lastClickPoints = [];
        this.pointerType = 'mouse';
        // Mouse coordinates, first and current
        this.firstX = this.firstY = this.currentX = this.currentY = undefined;
        this.pointers = new Map();
        this.pinching = false;
        this.pinchDistance = 0;

        // To test with Deno, view3d (and its overlay) may be null
        const overlay = view3d?.overlay;
        if (overlay) {
            overlay.addEventListener('pointerdown', (event) => {
                if (event.button === 1) event.preventDefault(); // no autoscroll
                try { overlay.setPointerCapture(event.pointerId); } catch { /* ignore */ }
                if (!this.pinchDown(event)) this.down3d(event);
            });
            overlay.addEventListener('pointermove', (event) => {
                if (!this.pinchMove(event)) this.move3d(event);
            });
            overlay.addEventListener('pointerup', (event) => {
                if (!this.pinchUp(event)) this.up3d(event);
            });
            overlay.addEventListener('pointercancel', (event) => {
                this.pinchUp(event);
                this.out(event);
            });
            overlay.addEventListener('wheel', (event) => this.wheel(event), {passive: true});
            overlay.addEventListener('contextmenu', (event) => {event.preventDefault();});
            // Keyboard
            document.addEventListener('keydown', (event) => this.keydown(event));
        }
        // Flat crease-pattern view — covers mouse and touch
        const canvas2d = view2d?.canvas2d;
        if (canvas2d) {
            canvas2d.addEventListener('pointerdown', (event) => {
                try { canvas2d.setPointerCapture(event.pointerId); } catch { /* ignore */ }
                this.down2d(event);
            });
            canvas2d.addEventListener('pointermove', (event) => this.move2d(event));
            canvas2d.addEventListener('pointerup', (event) => this.up2d(event));
            canvas2d.addEventListener('pointercancel', (event) => this.out(event));
        }
        this.out();
    }

    // Pointer events report the device kind: 'mouse', 'pen' or 'touch'.
    // Recorded on each pointerdown, it classifies the whole gesture that follows.
    // A stylus is as precise as a cursor, only a finger is coarse.
    setPointerType(event) {
        this.pointerType = event?.pointerType || 'mouse';
    }

    coarsePointer() {
        return this.pointerType === 'touch';
    }

    clickThreshold() {
        return this.coarsePointer() ? CLICK_PX_TOUCH : CLICK_PX_MOUSE;
    }

    // Multiplies the pick radii so a finger tap still catches points and segments
    pickFactor() {
        return this.coarsePointer() ? PICK_FACTOR_TOUCH : 1;
    }

    isClick() {
        const dx = (this.currentX ?? 0) - (this.firstX ?? 0);
        const dy = (this.currentY ?? 0) - (this.firstY ?? 0);
        return Math.hypot(dx, dy) < this.clickThreshold();
    }

    keydown(event) {
        if (!(event.ctrlKey || event.metaKey)) return;
        const key = event.key.toLowerCase();
        if (key === 'y' || (key === 'z' && event.shiftKey)) this.command.command('redo');
        else if (key === 'z') this.command.command('undo');
    }

    // Helper method to get formatted object string id (e.g. 'p0', 's1', 'f2')
    id(obj) {
        if (!obj) return '';
        if (this.model.points.includes(obj)) return 'p' + this.model.indexOf(obj);
        if (this.model.segments.includes(obj)) return 's' + this.model.indexOf(obj);
        if (this.model.faces.includes(obj)) return 'f' + this.model.indexOf(obj);
        return '';
    }

    out() {
        this.downPoints = [];
        this.downSegments = [];
        this.downPoint = this.downSegment = this.downFace = undefined;
        this.upPoints = [];
        this.upSegments = [];
        this.upPoint = this.upSegment = this.upFace = undefined;
        this.upFaces = [];
        this.downFaces = [];
        this.label = undefined;
        this.currentSegment = undefined;
        this.moving = false;
        this.orbiting = false;
    }

    clearSelection() {
        this.model.points.forEach(p => { p.select = false; });
        this.model.segments.forEach(s => { s.select = false; });
        this.model.faces.forEach(f => { f.select = false; });
    }

    selectedAxis() {
        return this.model.segments.find(s => s.select);
    }

    static FOLD_AMBER = '#e6a817';
    static VALLEY_COLOR = 'green';

    // Draw drag preview when down on a point, segment, or face: a filled arrow
    // for creasing (green — a crease has no mountain/valley until it's
    // actually folded) or moving a selected point (orange), a hollow arrow
    // only when the drag will actually fold the face or point (willFold()) — see Arrow.svg.
    draw() {
        if (!this.downPoint && !this.downSegment && !this.downFace) {
            return;
        }
        const context = (this.currentCanvas === '2d' ? this.view2d.canvas2d : this.view3d.overlay).getContext('2d');
        if (this.willFold()) {
            this.drawHollowArrow(context, this.firstX, this.firstY, this.currentX, this.currentY);
        } else {
            const color = this.moving ? 'orange' : Helper.VALLEY_COLOR;
            this.drawFilledArrow(context, this.firstX, this.firstY, this.currentX, this.currentY, color);
        }
        if (this.label) {
            const radius = 18;
            context.fillStyle = 'skyblue';
            context.beginPath();
            context.arc(this.currentX, this.currentY - 16, radius, 0, 2 * Math.PI);
            context.stroke();
            context.fill();
            context.fillStyle = 'black';
            context.font = '20px serif';
            context.fillText(this.label, this.currentX - 10, this.currentY - 8);
        }
    }

    // Thin straight shaft + small solid triangular head, both a fixed size —
    // only the shaft stretches with the drag. Crease preview (by/across/bisector);
    // orange when dragging a selected point to move it in 3d.
    drawFilledArrow(context, x1, y1, x2, y2, color = 'green') {
        const HEAD_LEN = 24, HEAD_HALF_W = 10;
        const dx = x2 - x1, dy = y2 - y1;
        const len = Math.hypot(dx, dy) || 1;
        const ux = dx / len, uy = dy / len;
        const px = -uy, py = ux;
        const shaftLen = Math.max(len - HEAD_LEN, 0);
        const sx = x1 + ux * shaftLen, sy = y1 + uy * shaftLen;

        context.strokeStyle = context.fillStyle = color;
        context.lineWidth = 6;
        context.lineCap = 'round';
        context.beginPath();
        context.moveTo(x1, y1);
        context.lineTo(sx, sy);
        context.stroke();
        context.beginPath();
        context.moveTo(x2, y2);
        context.lineTo(sx + px * HEAD_HALF_W, sy + py * HEAD_HALF_W);
        context.lineTo(sx - px * HEAD_HALF_W, sy - py * HEAD_HALF_W);
        context.closePath();
        context.fill();
    }

    // Straight thick shaft + hollow (outlined) triangular head, both a fixed size —
    // only the shaft stretches with the drag. Fold preview (rotating a face).
    drawHollowArrow(context, x1, y1, x2, y2) {
        const HEAD_LEN = 20, HEAD_HALF_W = 14, HALF_W = 6;
        const dx = x2 - x1, dy = y2 - y1;
        const len = Math.hypot(dx, dy) || 1;
        const ux = dx / len, uy = dy / len;
        const px = -uy, py = ux;
        const shaftLen = Math.max(len - HEAD_LEN, 0);
        const sx = x1 + ux * shaftLen, sy = y1 + uy * shaftLen; // shaft end / head base

        context.fillStyle = '#fff';
        context.strokeStyle = Helper.FOLD_AMBER;
        context.lineWidth = 2;
        context.lineJoin = 'round';
        context.beginPath();
        context.moveTo(x1 + px * HALF_W, y1 + py * HALF_W);
        context.lineTo(sx + px * HALF_W, sy + py * HALF_W);
        context.lineTo(sx + px * HEAD_HALF_W, sy + py * HEAD_HALF_W);
        context.lineTo(x2, y2);
        context.lineTo(sx - px * HEAD_HALF_W, sy - py * HEAD_HALF_W);
        context.lineTo(sx - px * HALF_W, sy - py * HALF_W);
        context.lineTo(x1 - px * HALF_W, y1 - py * HALF_W);
        context.closePath();
        context.fill();
        context.stroke();
    }

    // Logic begins here
    down(points, segments, faces, x, y) {
        this.downPoints = points.length ? points : [];
        this.downPoint = this.downPoints[0];
        this.downSegments = !this.downPoint && segments.length ? segments : [];
        this.downSegment = this.downSegments[0];
        this.downFaces = !this.downPoint && !this.downSegment ? faces : [];
        this.downFace = this.downFaces[0];
        this.firstX = this.currentX = x;
        this.firstY = this.currentY = y;
        this.label = undefined;
        // 3d drag of an already-selected (hovered) point → animated move
        this.moving = !!(this.downPoint?.select && this.currentCanvas === '3d');
    }

    /** Select all stacked points, or deselect all if every one is already selected. */
    togglePointStack(points) {
        if (!points.length) return;
        const allOn = points.every(p => p.select);
        points.forEach(p => { p.select = !allOn; });
    }

    /** Select all stacked faces, or deselect all if every one is already selected. */
    toggleFaceStack(faces) {
        if (!faces.length) return;
        const allOn = faces.every(f => f.select);
        faces.forEach(f => { f.select = !allOn; });
    }

    /** Arm/disarm a segment as the sole fold axis — never a stack, only one axis at a time. */
    armAxis(segment) {
        const wasArmed = segment.select;
        this.model.segments.forEach(s => { s.select = false; });
        segment.select = !wasArmed;
        this.logSelectedSegments();
    }

    logSelectedSegments() {
        const ids = this.model.segments.filter(s => s.select).map(s => `${this.id(s)}(${Math.round(Segment.length2d(s))},${Math.round(Segment.length3d(s) / this.model.scale)})`);
        if (ids.length) {
            this.command.command(`// selectSegments ${ids.join(' ')}`);
        }
    }

    sameStack(a, b) {
        return !!a?.length && a.length === b?.length && a.every(o => b.includes(o));
    }

    isDoubleClickPoints(points) {
        return Date.now() - this.touchTime < 400
            && this.sameStack(points, this.lastClickPoints);
    }

    faceBorderSegments(face) {
        const segs = [];
        const pts = face.points;
        for (let i = 0; i < pts.length; i++) {
            const s = this.model.getSegment(pts[i], pts[(i + 1) % pts.length]);
            if (s) segs.push(s);
        }
        return segs;
    }

    // Signed rotation angle (degrees) when pulling the reference point (where
    // the drag started) toward the axis, proportional to how far it went: the
    // grabbed point reaching the axis is 90°, reaching its mirror image across
    // it is 180°; moving parallel to the axis or away from it doesn't fold.
    // Uses canvasPoint() so 2d (xf,-yf) and 3d (xCanvas,yCanvas) stay consistent.
    rotationLabel(s, refX, refY, x, y) {
        const p1 = this.canvasPoint(s.p1), p2 = this.canvasPoint(s.p2);
        const dx = p2.xf - p1.xf, dy = p2.yf - p1.yf;
        const len = Math.hypot(dx, dy);
        if (len < 1e-9) return 0;
        const distance = (px, py) => ((px - p1.xf) * dy - (py - p1.yf) * dx) / len;
        const distFirst = distance(refX, refY);
        if (Math.abs(distFirst) < 1e-6) return 0;
        const ratio = Math.max(-1, Math.min(1, distance(x, y) / distFirst));
        let angle = (1 - ratio) * 90 * Math.sign(distFirst);
        angle = Math.round(angle / 10) * 10;
        return Math.abs(angle) < 10 ? 0 : angle;
    }

    move(points, segments, faces, x, y) {
        this.model.hover2d3d(points, segments, faces);
        this.currentX = x;
        this.currentY = y;
        this.currentSegment = segments[0];
        this.label = undefined;

        if (this.downPoint) {
            this.downPoints.forEach(p => { p.hover = true; });
        } else if (this.downSegment) {
            this.downSegments.forEach(s => { s.hover = true; });
        } else if (this.downFace) {
            this.downFace.hover = true;
        }
        const axis = this.selectedAxis();
        if (axis && this.canFoldOn(axis)) {
            this.label = this.angleFor(axis);
        }
    }

    up(points, segments, faces) {
        this.upPoints = points.length ? points : [];
        this.upPoint = this.upPoints[0];
        this.upSegments = !this.upPoint && segments.length ? segments : [];
        this.upSegment = this.upSegments[0];
        this.upFaces = !this.upPoint && !this.upSegment ? faces : [];
        this.upFace = this.upFaces[0];

        if (!this.downPoint && !this.downSegment && !this.downFace) {
            if (this.isClick()) this.clearSelection();
        } else if (this.downPoint) {
            this.fromPoint();
        } else if (this.downSegment) {
            this.fromSegment();
        } else if (this.downFace) {
            this.fromFace();
        }
        this.out();
    }

    fromPoint() {
        if (!this.isClick() && this.willFold()) {
            const axis = this.selectedAxis();
            this.foldAlong(axis, this.angleFor(axis));
            return;
        }
        if (this.moving && !this.isClick()) {
            this.moveSelectedPoint();
            return;
        }

        const sameStack = this.isClick()
            && this.downPoints.length
            && this.sameStack(this.downPoints, this.upPoints);

        if (sameStack) {
            if (this.isDoubleClickPoints(this.downPoints)) {
                const ids = this.downPoints.map(p => this.id(p)).join(' ');
                this.command.command(`adjust ${ids}`);
                this.touchTime = 0;
                this.lastClickPoints = [];
                return;
            }
            this.touchTime = Date.now();
            this.lastClickPoints = [...this.downPoints];
            this.togglePointStack(this.downPoints);
            return;
        }

        if (this.model.faces.some(f => f.select)) {
            // Creases blocked while composing a fold
            return;
        }
        if (this.upPoint) {
            this.creaseTwoPoints(this.downPoint, this.upPoint);
        } else if (this.upSegment) {
            this.creaseFromPointToSegment(this.downPoint, this.upSegment);
        }
    }

    /**
     * Drag of a selected point in 3d: move only that hovered point (animated),
     * then adjust every other selected point to restore segment lengths.
     */
    moveSelectedPoint() {
        const {dx, dy, dz} = this.dragToWorld();
        if (dx === 0 && dy === 0 && dz === 0) return;
        const movedId = this.id(this.downPoint);
        const others = this.model.points
            .filter((p) => p.select && p !== this.downPoint)
            .map((p) => this.id(p));
        let cmd = `t 1000 m ${dx} ${dy} ${dz} ${movedId}`;
        if (others.length) cmd += ` adjust ${others.join(' ')}`;
        this.command.command(cmd);
    }

    dragToWorld() {
        const round = (n) => Math.round(n * 10) / 10;
        const delta = this.canvasDragToWorld3d(
            this.firstX, this.firstY, this.currentX, this.currentY, this.downPoint,
        );
        return {dx: round(delta.dx), dy: round(delta.dy), dz: round(delta.dz)};
    }

    // Unproject overlay drag at the point's projected depth (screen-parallel plane).
    canvasDragToWorld3d(x0, y0, x1, y1, point) {
        const fallback = {dx: x1 - x0, dy: -(y1 - y0), dz: 0};
        const m = this.view3d?.canvasView;
        if (!m || !point) return fallback;
        const inv = mat4.invert(mat4.create(), m);
        if (!inv) return fallback;
        const z = Vector3.transformMat4(point, m).z;
        const world0 = Vector3.transformMat4({x: x0, y: y0, z}, inv);
        const world1 = Vector3.transformMat4({x: x1, y: y1, z}, inv);
        return {
            dx: world1.x - world0.x,
            dy: world1.y - world0.y,
            dz: world1.z - world0.z,
        };
    }

    fromSegment() {
        const sameStack = this.isClick()
            && this.downSegments.length
            && this.sameStack(this.downSegments, this.upSegments);

        if (sameStack) {
            this.armAxis(this.downSegment);
            return;
        }

        if (this.model.faces.some(f => f.select)) {
            return;
        }
        if (this.upSegment) {
            this.creaseTwoSegments(this.downSegment, this.upSegment);
        } else if (this.upPoint) {
            this.creaseFromSegmentToPoint(this.downSegment, this.upPoint);
        }
    }

    fromFace() {
        if (this.isClick()) {
            this.fromFaceClick();
            return;
        }
        this.fromFaceDrag();
    }

    fromFaceClick() {
        const samePile = this.downFace && this.upFaces.includes(this.downFace);
        if (samePile) {
            this.toggleFaceStack(this.upFaces.length ? this.upFaces : this.downFaces);
        } else if (this.upFace) {
            // Different face: select Up front only; keep points/segments
            this.upFace.select = true;
        }
        const ids = this.model.faces.filter(f => f.select).map(f => `${this.id(f)}(${f.offset})`);
        if (ids.length) {
            this.command.command(`// selectFaces ${ids.join(' ')}`);
        }
    }

    /**
     * A drag on a face folds it only when a crease is already armed as the fold
     * axis (via a prior click on it — never guessed) and that crease borders this
     * face. Otherwise, the drag can only score a crease across existing paper
     * (splitting whatever it crosses into new landmark points), or — if it
     * crosses nothing — arm/select the face like a click would.
     */
    fromFaceDrag() {
        if (this.willFold()) {
            const axis = this.selectedAxis();
            this.foldAlong(axis, this.angleFor(axis));
            return;
        }
        if (this.splitSegments()) return;
        if (!this.downFace.select) this.fromFaceClick();
    }

    /** Rotation angle (degrees) if hinging the dragged face or point on `axis` right now. */
    angleFor(axis) {
        return this.rotationLabel(axis, this.firstX, this.firstY, this.currentX, this.currentY);
    }

    /** A face hinges on one of its borders, a point on any axis it isn't an end of. */
    canFoldOn(axis) {
        if (this.downFace) return this.faceBorderSegments(this.downFace).includes(axis);
        if (this.downPoint) return this.downPoint !== axis.p1 && this.downPoint !== axis.p2;
        return false;
    }

    /** Would releasing now actually rotate the dragged face or point? */
    willFold() {
        const axis = this.selectedAxis();
        if (!axis || !this.canFoldOn(axis)) return false;
        return !!this.angleFor(axis);
    }

    // Folds the dragged face plus any other already-selected faces around axis, by
    // angle. The axis stays armed afterwards, so folding the other side along the
    // same crease (a very common diagram pattern) is just a second plain drag.
    foldAlong(axis, angle) {
        this.rotatePoints(axis, angle);
        this.model.points.forEach(p => { p.select = false; });
        this.model.faces.forEach(f => { f.select = false; });
    }

    /**
     * Convert a screen-space ratio r along a projected segment (0 at p1, 1 at p2)
     * into the perspective-correct parameter t along the 3D segment.
     * w1/w2 are homogeneous clip w (≈ -zEye) at the endpoints.
     */
    static screenRatioToSegmentT(r, a =1, b =1) {
        const denominator = (1 - r) * b + r * a;
        if (Math.abs(denominator) < 1e-12) return r;
        return (r * a) / denominator;
    }

    /** Clip-space w used for the point's canvas projection (perspective weight). */
    clipW(point) {
        // Flat crease pattern is orthographic — no perspective weighting
        if (this.currentCanvas === '2d') return 1;
        const m = this.view3d?.canvasView;
        if (m) {
            const w = m[3] * point.x + m[7] * point.y + m[11] * point.z + m[15];
            if (Math.abs(w) > 1e-9) return w;
        }
        // zEye is negative in front of the camera; clip w ≈ -zEye
        const zEye = point.zEye;
        if (zEye !== undefined && zEye !== null && Math.abs(zEye) > 1e-9) {
            return -zEye;
        }
        return 1;
    }

    // A point's flat-drawing coordinates on the canvas the current gesture is on
    canvasPoint(p) {
        return this.currentCanvas === '2d'
            ? {xf: p.xf, yf: -p.yf}
            : {xf: p.xCanvas, yf: p.yCanvas};
    }

    /**
     * Segments the current drag actually cuts across, as {index, ratio} pairs.
     * Pure (no commands issued) so both splitSegments() and the live arrow
     * preview can share this without splitSegments() firing twice.
     */
    computeCrossedSegments() {
        const first = {xf: this.firstX, yf: this.firstY};
        const current = {xf: this.currentX, yf: this.currentY};
        // In 3d, layers can overlap on screen. Ignore a segment that's occluded
        // behind the face being dragged — the drag can only be scoring a line on
        // the visible surface, not a hidden layer that merely projects onto it.
        const downDepth = this.currentCanvas === '3d' && this.downFace && this.view3d.faceDepth
            ? this.view3d.faceDepth(this.downFace)
            : undefined;
        const crossings = [];
        this.model.segments.forEach((s, i) => {
            if (downDepth !== undefined) {
                const faces = this.model.searchFacesWithAB(s.p1, s.p2);
                const visible = faces.length === 0
                    || faces.some(f => this.view3d.faceDepth(f) <= downDepth + 1e-6);
                if (!visible) return;
            }
            const p1 = this.canvasPoint(s.p1);
            const p2 = this.canvasPoint(s.p2);
            const inter = Segment.intersectionFlat(first, current, p1, p2);
            if (!inter) return;
            const len = Math.hypot(p2.xf - p1.xf, p2.yf - p1.yf);
            if (len < 1e-9) return;
            const r = Math.hypot(inter.xf - p1.xf, inter.yf - p1.yf) / len;
            const t = Helper.screenRatioToSegmentT(r, this.clipW(s.p1), this.clipW(s.p2));
            const ratio = Math.round(t * 100) / 100;
            if (ratio > 0 && ratio < 1) crossings.push({index: i, ratio});
        });
        return crossings;
    }

    /** @returns {boolean} true if the drag actually cut across at least one existing segment */
    splitSegments() {
        const crossings = this.computeCrossedSegments();
        crossings.forEach(({index, ratio}) => this.command.command(`split s${index} ${ratio}`));
        return crossings.length > 0;
    }

    // command.command() only enqueues — the model applies it on the next
    // animation frame. A crease command is never animated ('t ...'), so it is
    // always fully applied by exactly one command.anim() call; running that
    // now (only when nothing else is already mid-animation) shows the result
    // immediately instead of a frame late. Also rebuilds the WebGL buffers
    // right away when something was actually applied: this bypasses the
    // render loop's own command.anim() check (the one that normally gates
    // initBuffers()/initModelView()), so without this the loop's next call
    // finds nothing left to apply and never uploads the change to canvas3d,
    // even though the model (and canvas2d, drawn straight from it) already
    // reflects it.
    runQueuedNow() {
        if (this.model.state === State.run && this.command.anim()) {
            this.view3d?.initBuffers();
            this.view3d?.initModelView();
        }
    }

    // Straight crease through both points ('by'). Just marks the crease —
    // mountain/valley is only meaningful once actually folded, so the new
    // segment is left unassigned ('U') regardless of drag direction.
    // 'by' cuts along the line through a and b: when they already share a
    // segment that line is that very segment, so 'by' would split nothing —
    // fall back to 'c' (cross), the coincidence-fold that brings a onto b.
    creaseTwoPoints(a, b) {
        const across = this.model.getSegment(a, b);
        if (this.currentCanvas === '2d') {
            if (across) this.command.command(`c2d ${this.id(a)} ${this.id(b)}`);
            else this.command.command(`by2d ${this.id(a)} ${this.id(b)}`);
        } else {
            if (across) this.command.command(`c3d ${this.id(a)} ${this.id(b)}`);
            else this.command.command(`by3d ${this.id(a)} ${this.id(b)}`);
        }
        this.runQueuedNow();
    }

    // Drag starting on the point: the crease through the point, perpendicular to the segment.
    creaseFromPointToSegment(point, segment) {
        if (this.currentCanvas === '2d') this.command.command(`p2d ${this.id(segment)} ${this.id(point)}`);
        else this.command.command(`p3d ${this.id(segment)} ${this.id(point)}`);
        this.runQueuedNow();
    }

    // Drag starting on the segment: the crease that brings the segment's line onto the point once folded.
    creaseFromSegmentToPoint(segment, point) {
        if (this.currentCanvas === '2d') this.command.command(`parallel2d ${this.id(segment)} ${this.id(point)}`);
        else this.command.command(`parallel3d ${this.id(segment)} ${this.id(point)}`);
        this.runQueuedNow();
    }

    // The only sensible crease between two segments: their bisector.
    creaseTwoSegments(a, b) {
        if (this.currentCanvas === '2d') this.command.command(`b2d ${this.id(a)} ${this.id(b)}`);
        else this.command.command(`b3d ${this.id(a)} ${this.id(b)}`);
        this.runQueuedNow();
    }

    rotatePointIds(axis) {
        const pts = new Set();
        this.model.faces.filter(f => f.select).forEach(f => {
            f.points.forEach(p => pts.add(p));
        });
        if (this.downFace) {
            this.downFace.points.forEach(p => pts.add(p));
        }
        if (this.downPoint) pts.add(this.downPoint);
        // Axis endpoints don't move when rotating around that axis; excluding them
        // keeps the command's point list honest and avoids floating-point drift
        // from rotating a point that should stay exactly put.
        pts.delete(axis.p1);
        pts.delete(axis.p2);
        return [...pts].map(p => this.id(p));
    }
    // Selected points not rotated are adjusted instead
    adjustPointIds(rotatedIds) {
        const rotated = new Set(rotatedIds);
        return this.model.points
            .filter(p => p.select)
            .map(p => this.id(p))
            .filter(id => !rotated.has(id));
    }
    rotateFaceCommentIds() {
        const faces = new Set(this.model.faces.filter(f => f.select));
        if (this.downFace) faces.add(this.downFace);
        return [...faces].map(f => this.id(f));
    }

    rotatePoints(axis, angle) {
        const pts = this.rotatePointIds(axis);
        const adjustPts = this.adjustPointIds(pts);
        const adjust = adjustPts.length ? ` a ${adjustPts.join(' ')}` : '';
        const faces = this.rotateFaceCommentIds();
        const faceComment = faces.length ? ` // ${faces.join(' ')}` : '';
        this.command.command(`t 1000 r ${this.id(axis)} ${angle} ${pts.join(' ')}${adjust}${faceComment}`);
    }

    // Canvas 2d (flat crease pattern). Overridable per-instance so tests can
    // inject already-resolved {xf, yf} without a real DOM element behind view2d.
    event2d(event) {
        const rect = this.view2d.canvas2d.getBoundingClientRect();
        const canvasX = event.clientX - rect.left;
        const canvasY = event.clientY - rect.top;
        const {scale, xOffset, yOffset} = this.view2d;
        return {
            xf: (canvasX - xOffset) / scale,
            yf: (yOffset - canvasY) / scale,
        };
    }

    // Points, then segments, then faces near xf, yf
    search2d(xf, yf) {
        const scale = this.view2d.scale || 1;
        const pick = this.pickFactor();
        const points = this.model.points.filter(p => Math.abs(p.xf - xf) + Math.abs(p.yf - yf) < pick * 10 / scale);
        const segments = this.model.segments.filter(s => Segment.distance2d(s.p1.xf, s.p1.yf, s.p2.xf, s.p2.yf, xf, yf) < pick * 6 / scale);
        const faces = this.model.faces.filter(f => Face.contains2d(f, xf, yf));
        return {points, segments, faces};
    }

    // Down on flat 2d
    down2d(event) {
        this.currentCanvas = '2d';
        this.setPointerType(event);
        const {xf, yf} = this.event2d(event);
        const {points, segments, faces} = this.search2d(xf, yf);
        this.down(points, segments, faces, xf, -yf); // Note inverse y coordinate (drawing space)
    }
    // Move on flat 2d
    move2d(event) {
        this.currentCanvas = '2d';
        const {xf, yf} = this.event2d(event);
        const {points, segments, faces} = this.search2d(xf, yf);
        this.move(points, segments, faces, xf, -yf);
    }
    // Up on flat 2d
    up2d(event) {
        const {xf, yf} = this.event2d(event);
        const {points, segments, faces} = this.search2d(xf, yf);
        this.up(points, segments, faces);
    }

    // Canvas 3d. Overridable per-instance so tests can inject already-resolved
    // {xCanvas, yCanvas} without a real DOM element behind view3d.
    eventCanvas3d(event) {
        const rect = this.view3d.overlay.getBoundingClientRect();
        return {
            xCanvas: event.clientX - rect.left,
            yCanvas: event.clientY - rect.top,
        };
    }
    // Points, then segments, then faces near xCanvas, yCanvas
    pickFaces3d(xCanvas, yCanvas, contextFace = undefined) {
        let faces = this.model.faces.filter(f =>
            Face.contains3d(f, xCanvas, yCanvas, this.view3d),
        );
        if (contextFace) {
            faces = faces.filter(f =>
                f !== contextFace &&
                this.model.sharedSegments(contextFace, f).length > 0,
            );
        }
        if (this.view3d?.faceDepth) {
            // Folding a flat model routinely stacks faces at the exact same depth
            // (e.g. two layers folded flush): faceDepth alone can't tell them apart,
            // and a stable sort would then always resolve to the same array index.
            // Break exact ties in favor of a face the user already explicitly
            // selected — a stronger signal of intent than creation order.
            faces.sort((a, b) => {
                const d = this.view3d.faceDepth(a) - this.view3d.faceDepth(b);
                if (Math.abs(d) > 1e-6) return d;
                return (b.select ? 1 : 0) - (a.select ? 1 : 0);
            });
        }
        return faces;
    }

    search3d(xCanvas, yCanvas, contextFace = undefined) {
        const pick = this.pickFactor();
        // Points near xCanvas, yCanvas
        const points = this.model.points.filter(p => Math.abs(p.xCanvas - xCanvas) + Math.abs(p.yCanvas - yCanvas) < pick * 10);
        // Segments near xCanvas, yCanvas
        const segments = this.model.segments.filter(s => Segment.distance2d(s.p1.xCanvas, s.p1.yCanvas, s.p2.xCanvas, s.p2.yCanvas, xCanvas, yCanvas) < pick * 6);
        // Faces under cursor: depth-sorted; when contextFace set, adjacent faces only
        const faces = this.pickFaces3d(xCanvas, yCanvas, contextFace);
        return {points, segments, faces};
    }
    // Down on 3d overlay
    down3d(event) {
        this.currentCanvas = '3d';
        this.setPointerType(event);
        const {xCanvas, yCanvas} = this.eventCanvas3d(event);
        const {points, segments, faces} = this.search3d(xCanvas, yCanvas);
        this.orbiting = event.button === 1 || event.shiftKey || (points.length === 0 && segments.length === 0 && faces.length === 0);
        this.down(points, segments, faces, xCanvas, yCanvas);
    }

    // Move on 3d overlay
    move3d(event) {
        this.currentCanvas = '3d';
        const {xCanvas, yCanvas} = this.eventCanvas3d(event);
        const contextFace = this.downFace || undefined;
        const {points, segments, faces} = this.search3d(xCanvas, yCanvas, contextFace);
        // Handle 3d rotation
        if (this.orbiting && event.buttons > 0) {
            // Rotation
            const target = event.target || this.view3d.overlay;
            const factor = 600 / (target.height || 600);
            const dx = factor * (xCanvas - this.currentX);
            const dy = factor * (yCanvas - this.currentY);
            this.view3d.angleX += dy;
            this.view3d.angleY += dx;
        } else if ((event.buttons & 2) > 0) {
            // Translation
            const dx = (xCanvas - this.currentX);
            const dy = (yCanvas - this.currentY);
            this.view3d.translationY -= dy;
            this.view3d.translationX += dx;
        }
        this.move(points, segments, faces, xCanvas, yCanvas);
        this.view3d.initModelView();
        this.view3d.initPerspective();
    }
    // Up on 3d overlay
    up3d(event) {
        const {xCanvas, yCanvas} = this.eventCanvas3d(event);
        const {points, segments, faces} = this.search3d(xCanvas, yCanvas);
        this.up(points, segments, faces);
        if (points.length === 0 && segments.length === 0 && faces.length === 0) {
            this.doubleClick();
        }
    }

    // Mouse wheel on 3d overlay
    wheel(event) {
        this.zoom3d(this.view3d.scale + event.deltaY / 300);
    }

    zoom3d(scale) {
        this.view3d.scale = Math.max(0.2, Math.min(3, scale));
        this.view3d.initModelView();
        this.view3d.initPerspective();
    }

    pinchSpread() {
        const [a, b] = [...this.pointers.values()];
        return Math.hypot(a.x - b.x, a.y - b.y);
    }

    pinchDown(event) {
        if (event.pointerType !== 'touch') return false;
        this.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
        if (this.pointers.size < 2) return this.pinching;
        this.pinching = true;
        this.orbiting = false;
        this.out();
        this.model.hover2d3d([], [], []);
        this.pinchDistance = this.pinchSpread();
        return true;
    }

    pinchMove(event) {
        if (!this.pointers.has(event.pointerId)) return false;
        this.pointers.set(event.pointerId, {x: event.clientX, y: event.clientY});
        if (!this.pinching) return false;
        if (this.pointers.size < 2) return true;
        const distance = this.pinchSpread();
        if (this.pinchDistance > 0 && distance > 0) this.zoom3d(this.view3d.scale * distance / this.pinchDistance);
        this.pinchDistance = distance;
        return true;
    }

    pinchUp(event) {
        if (!this.pointers.delete(event.pointerId)) return false;
        const wasPinching = this.pinching;
        if (this.pointers.size === 0) this.pinching = false;
        return wasPinching;
    }

    doubleClick() {
        if (Date.now() - this.touchTime < 400) {
            this.view3d.angleX = this.view3d.angleY = this.view3d.angleZ = 0;
            this.view3d.translationX = this.view3d.translationY = 0;
            this.view3d.scale = 1;
            this.command.command('fit');
        }
        this.touchTime = Date.now();
    }
}
