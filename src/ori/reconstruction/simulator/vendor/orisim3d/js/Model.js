import {Point} from './Point.js';
import {Segment} from './Segment.js';
import {Face} from './Face.js';
import {Vector3} from './Vector3.js';
import {Plane} from './Plane.js';

export const State = {run: 0, anim: 1, undo: 2, pause: 3,};

// Newell's accumulated (unnormalized) normal vector; {0,0,0} when < 3 points
function newellNormal(points) {
    let nx = 0, ny = 0, nz = 0;
    if (points && points.length >= 3) {
        for (let i = 0; i < points.length; i++) {
            const a = points[i], b = points[(i + 1) % points.length];
            nx += (a.y - b.y) * (a.z + b.z);
            ny += (a.z - b.z) * (a.x + b.x);
            nz += (a.x - b.x) * (a.y + b.y);
        }
    }
    return {nx, ny, nz};
}

// Newell: magnitude of the accumulated normal (0 if degenerated or < 3 points)
function polygonArea3d(points) {
    const {nx, ny, nz} = newellNormal(points);
    return Math.hypot(nx, ny, nz) / 2;
}

// -1 left, 0 on the line, +1 right
function side2d(d, epsilon) {
    if (d < -epsilon) return -1;
    if (d > epsilon) return 1;
    return 0;
}

export class Model {

    constructor() {
        // Core
        this.points = [];
        this.segments = [];
        this.faces = [];

        // State of the model
        this.state = State.run;
        this.scale = 1;

        // Helper
        this.labels = false;
        this.textures = false;
        this.lines = true;   // render lines on 3d
        this.snap = true;     // snap nearest points
    }

    // Initialize with 2d coordinates
    init(width = 200, height = 200) {
        this.points = [];
        this.segments = [];
        this.faces = [];
        // 4 points
        const p0 = new Point(-width, -height, -width, -height, 0);
        const p1 = new Point(width, -height, width, -height, 0);
        const p2 = new Point(width, height, width, height, 0);
        const p3 = new Point(-width, height, -width, height, 0);
        this.points.push(p0, p1, p2, p3);
        // 4 segments
        this.segments.push(new Segment(p0, p1), new Segment(p1, p2), new Segment(p2, p3), new Segment(p3, p0));
        // 1 face
        this.faces.push(new Face([p0, p1, p2, p3]));
        // State run
        this.state = State.run;
        this.scale = 1;
        // Options
        this.labels = false;
        this.textures = false;
        this.lines = true;   // render lines on 3d
        this.snap = true;    // snap nearest points
        return this;
    }

    // First non-empty pick among points, then segments, then faces
    firstHit(points, segments, faces) {
        if (points.length) return points;
        if (segments.length) return segments;
        return faces;
    }

    // Update hover2d3d on points, segments, faces 2d and 3d
    hover2d3d(points, segments, faces) {
        // Clean
        this.points.forEach((p) => { p.hover = false; });
        this.segments.forEach((s) => { s.hover = false; });
        this.faces.forEach((f) => { f.hover = false; });
        // Hover
        this.firstHit(points, segments, faces).forEach((o) => { o.hover = true; });
    }

    // Handle click2d3d on points, segments, faces 2d and 3d
    click2d3d(points, segments, faces) {
        this.firstHit(points, segments, faces).forEach((o) => { o.select = !o.select; });
    }

    // Index of Point or Segment or Face
    indexOf(object) {
        if (object instanceof Point) return this.points.indexOf(object);
        if (object instanceof Segment) return this.segments.indexOf(object);
        if (object instanceof Face) return this.faces.indexOf(object);
        return -1;
    }

    // Get point on the flat crease pattern
    getPoint(xf, yf, epsilon = 0.01) {
        return this.points.find((p) => Math.abs(p.xf - xf) + Math.abs(p.yf - yf) < epsilon);
    }

    // Add a point or return an existing point
    addPoint(xf, yf, x, y, z) {
        const existing = this.getPoint(xf, yf);
        // None found, create one
        if (existing) return existing;
        const point = new Point(xf, yf, x, y, z);
        this.points.push(point);
        return point;
    }

    // Add a segment or return an existing segment
    addSegment(a, b) {
        const existing = this.getSegment(a, b);
        // None found, create one
        if (existing) return existing;
        const segment = new Segment(a, b);
        this.segments.push(segment);
        return segment;
    }

    // Get the face containing these points in this order
    getFace(points) {
        return this.faces.find((f) =>
            f.points.length === points.length && f.points.every((p, i) => p === points[i])
        );
    }

    // Add a face or return an existing face
    addFace(points) {
        const existing = this.getFace(points);
        // None found, create one
        if (existing) return existing;
        // Add segments for the face
        points.forEach((p, i, a) => this.addSegment(p, a[(i + 1) % a.length]));
        const face = new Face(points);
        this.faces.push(face);
        return face;
    }

    // Replace face polygon by left, add right as a new face, keep offset
    commitSplit(face, left, right) {
        face.points = left;
        const created = this.addFace(right);
        created.offset = face.offset;
    }

    // Reverse order to add new faces in the same pass
    forEachFaceReverse(fn) {
        for (let i = this.faces.length - 1; i >= 0; i--) fn(this.faces[i]);
    }

    // Origami
    // Split face by plane 3d
    // 9 cases: left <0, on 0, right >0
    //         Current
    // last | < | 0 | > |
    //    < | 1 | 3 | 9 |
    //    0 | 6 | 4 | 7 |
    //    > | 8 | 5 | 2 |
    // Not exactly 0 for distance but epsilon = 10
    splitFaceByPlane3d(face, plane) {
        const left = [], right = [];
        let lastInter;
        const epsilon = 10;
        const side = (d) => {
            if (Math.abs(d) <= epsilon) return 0;
            if (d < 0) return -1;
            return 1;
        };

        // Begin with the last point
        let last = face.points[face.points.length - 1];
        let dLast = Face.planeToPointSignedDistance(plane, last);
        for (const current of face.points) {
            // Segment from previous to current
            const dCurrent = Face.planeToPointSignedDistance(plane, current);
            const lastSide = side(dLast);
            const currSide = side(dCurrent);
            // last and current on the same side // 1, 2
            if (lastSide && lastSide === currSide) {
                (currSide < 0 ? left : right).push(current);
            }
            // current on plane // 3 4 5
            else if (currSide === 0) {
                left.push(current);
                right.push(current);
                lastInter = current;
            }
            // last on plane, current on left or right // 6 7
            else if (lastSide === 0) {
                (currSide < 0 ? left : right).push(current);
            }
            // last and current on different side, crossing // 8 9
            else {
                const inter = Face.intersectionPlaneSegment(plane, last, current);
                if (inter) {
                    Point.align2dFrom3d(last, current, inter);
                    lastInter = this.addIntersection3d(inter, left, right, dCurrent, current, last, lastInter);
                } else {
                    (currSide < 0 ? left : right).push(current);
                }
            }
            last = current;
            dLast = dCurrent;
        }

        // Modify initial face and add new face if not degenerated
        // Discard degenerated polygons artifacts
        if (polygonArea3d(left) && polygonArea3d(right)) {
            this.commitSplit(face, left, right);
        }
    }

    addIntersection3d(inter, left, right, dCurrent, current, last, lastInter) {
        inter = this.addPoint(inter.xf, inter.yf, inter.x, inter.y, inter.z);
        left.push(inter);
        right.push(inter);
        (dCurrent < 0 ? left : right).push(current);

        // Set Segment [last,current] to [last,inter]
        const segment = this.getSegment(last, current);
        if (segment) Model.splitSegment(segment, last, inter);
        // Add a new segment
        this.addSegment(inter, current);

        // Eventually, if last intersection was on plane,
        // add a segment from the last intersection to inter
        if (lastInter && inter !== lastInter) {
            this.addSegment(lastInter, inter);
            return undefined;
        }
        return inter;
    }

    splitFaceBySegment2d(face, a, b) {
        const left = [], right = [];
        const EPSILON = 1;
        // Segment from last to current
        let last = face.points[face.points.length - 1];
        let dLast = Face.distance2dLineToPoint(a, b, last); // Positive if on the right of the segment a,b
        // Discard if on the line but not on Segment
        if (Math.abs(dLast) < EPSILON && Segment.intersectionFlat(a, b, last, face.points[0]) === undefined) {
            return;
        }
        for (const current of face.points) {
            // Segment from previous to current
            const dCurrent = Face.distance2dLineToPoint(a, b, current);
            const lastSide = side2d(dLast, EPSILON);
            const currSide = side2d(dCurrent, EPSILON);
            if (lastSide === currSide) {
                // Last and current on the same side, or both on the line
                if (currSide < 0) left.push(current);
                else if (currSide > 0) right.push(current);
                else {
                    // Don't split face if inter is on the line but not on the segment ab
                    if (Segment.intersectionFlat(a, b, last, current) === undefined) return;
                    left.push(current);
                    right.push(current);
                }
            } else if (currSide === 0) {
                // Last off the line, current on the line
                if (Segment.intersectionFlat(a, b, last, current) === undefined) return;
                left.push(current);
                right.push(current);
            } else if (lastSide === 0) {
                // Last on the line, current on left or right
                (currSide < 0 ? left : right).push(current);
            } else {
                // Crossing: last on left, current on right, or the reverse
                const inter = Segment.intersectionFlat(a, b, last, current);
                if (inter === undefined) return;
                // Origami: lift 2d intersection onto the 3d crease
                Point.align3dFrom2d(last, current, inter);
                this.addIntersectionPoint(inter, left, right, last, current, face);
                (currSide < 0 ? left : right).push(current);
            }
            last = current;
            dLast = dCurrent;
        }
        // Discard degenerated polygons artifacts
        // Modify initial face and add new face if not degenerated
        if (Math.abs(Face.area2dFlat(left)) > EPSILON && Math.abs(Face.area2dFlat(right)) > EPSILON) {
            this.commitSplit(face, left, right);
        }
    }

    addIntersectionPoint(inter, left, right, last, current, face) {
        // Add intersection to both sides
        inter = this.addPoint(inter.xf, inter.yf, inter.x, inter.y, inter.z);
        left.push(inter);
        right.push(inter);
        // Set Segment [last,current] to [last,inter]
        const segment = this.getSegment(last, current);
        if (segment) {
            // When splitting a single face, any other face sharing this edge must also
            // gain the point, or its polygon goes out of sync with the segment we're
            // about to cut in two (a "T-junction"). Do this before splitting the
            // segment, while it still connects last directly to current.
            for (const sibling of Model.incidentFaces(this, segment)) {
                if (sibling === face || sibling.points.includes(inter)) continue;
                const pts = sibling.points;
                for (let i = 0; i < pts.length; i++) {
                    const next = pts[(i + 1) % pts.length];
                    if ((pts[i] === last && next === current) || (pts[i] === current && next === last)) {
                        pts.splice(i + 1, 0, inter);
                        break;
                    }
                }
            }
            Model.splitSegment(segment, last, inter);
            this.addSegment(inter, current);
        }
        return inter;
    }

    static splitSegment(segment, last, inter) {
        if (!segment) return;
        if (segment.p1 === last) segment.p2 = inter;
        else if (segment.p2 === last) segment.p1 = inter;
        // else Segment already cut
    }

    splitSegmentByRatio2d(s, k) {
        this.splitSegmentOnPoint2d(s, new Point(
            s.p1.xf + k * (s.p2.xf - s.p1.xf),
            s.p1.yf + k * (s.p2.yf - s.p1.yf),
        ));
    }

    splitSegmentOnPoint2d(s, p) {
        // Align Point p on segment s in 2D
        const a = s.p1, b = s.p2;
        // Add this as a new point to the model
        p = this.addPoint(p.xf, p.yf);
        Point.align3dFrom2d(a, b, p);
        // Add the point p to both faces, between a and b
        for (const face of this.searchFacesWithAB(a, b)) {
            const pts = face.points;
            if (pts.includes(p)) continue;
            for (let i = 0; i < pts.length; i++) {
                const next = pts[(i + 1) % pts.length];
                if ((pts[i] === a && next === b) || (pts[i] === b && next === a)) {
                    pts.splice(i + 1, 0, p);
                    break;
                }
            }
        }
        // Reduce segment s to [a, p]
        Model.splitSegment(s, a, p);
        // And add a new segment p,b
        this.addSegment(p, b);
        return s;
    }

    // Split all faces by a plane
    splitAllFacesByPlane3d(plane) {
        this.forEachFaceReverse((face) => this.splitFaceByPlane3d(face, plane));
    }

    // Split all faces by a segment two points on 2d crease pattern
    splitAllFacesBySegment2d(a, b) {
        this.forEachFaceReverse((face) => this.splitFaceBySegment2d(face, a, b));
    }

    // Split all faces by a line defined by two points on 2d crease pattern
    splitAllFacesByLine2d(a, b) {
        // Vector from a to b, extended
        const dx = (b.xf - a.xf) * 1000, dy = (b.yf - a.yf) * 1000;
        this.splitAllFacesBySegment2d(
            new Point(a.xf + dx, a.yf + dy),
            new Point(b.xf - dx, b.yf - dy),
        );
    }

    // Split a single face by the line through a,b, extended just far enough to clear that
    // face (unlike splitAllFacesByLine2d's fixed 1000x, which mixes huge and tiny magnitudes
    // and can lose intersections to floating-point noise when the line grazes a vertex).
    splitFaceByLine2d(face, a, b) {
        const dx = b.xf - a.xf, dy = b.yf - a.yf;
        const len = Math.hypot(dx, dy);
        if (len === 0) return;
        const reach = face.points.reduce((m, p) => Math.max(m, Point.distance2d(a, p)), 0) + 1;
        const k = reach / len;
        this.splitFaceBySegment2d(face,
            new Point(a.xf - dx * k, a.yf - dy * k),
            new Point(a.xf + dx * k, a.yf + dy * k),
        );
    }

    // Find the face where b is a vertex adjacent to both a and c (edges [b,a] and [b,c])
    faceAtVertex(a, b, c) {
        const facesA = this.searchFacesWithAB(a, b);
        const facesC = this.searchFacesWithAB(b, c);
        return facesA.find((f) => facesC.includes(f));
    }

    // Split faces across two points in 3d
    splitCross3d(p1, p2) {
        this.splitAllFacesByPlane3d(Plane.across(p1, p2));
    }

    // Split faces across two points in 2d
    splitCross2d(p1, p2) {
        const nx = p2.yf - p1.yf, ny = -(p2.xf - p1.xf); // x,y -> y,-x
        const mx = (p1.xf + p2.xf) / 2, my = (p1.yf + p2.yf) / 2;
        // Two points apart from the middle
        this.splitAllFacesByLine2d(new Point(mx + nx, my + ny), new Point(mx - nx, my - ny));
    }

    // Split faces by a plane passing by two points on xy orthogonal to z
    splitBy3d(p1, p2) {
        this.splitAllFacesByPlane3d(Plane.by(p1, p2));
    }

    // Split faces by a line passing by two points in 2d
    splitBy2d(p1, p2) {
        this.splitAllFacesBySegment2d(p1, p2);
    }

    // Split faces by a line perpendicular to [p1,p2] passing by point
    splitPerpendicular2d(s, point) {
        this.splitAllFacesBySegment2d(point, Segment.project2d(s, point));
    }

    // Split faces by a plane perpendicular to [p1,p2] passing by point
    splitPerpendicular3d(s, point) {
        this.splitAllFacesByPlane3d(Plane.orthogonal(s.p1, s.p2, point));
    }

    // Crease between segment and point: fold that brings the line onto the point
    // (perpendicular bisector of the point and its projection on the line of s).
    splitParallel2d(s, point) {
        const dx = s.p2.xf - s.p1.xf, dy = s.p2.yf - s.p1.yf;
        const l2 = dx * dx + dy * dy;
        if (l2 === 0) return;
        const t = ((point.xf - s.p1.xf) * dx + (point.yf - s.p1.yf) * dy) / l2;
        const foot = {xf: s.p1.xf + t * dx, yf: s.p1.yf + t * dy};
        if (Point.distance2d(point, foot) < 1e-9) return;
        this.splitCross2d(point, foot);
    }

    // Crease between segment and point in 3d (plane that brings the line onto the point).
    splitParallel3d(s, point) {
        const foot = Vector3.closestPoint(point, s.p1, s.p2);
        if (Vector3.length3d(Vector3.sub(point, foot)) < 1e-9) return;
        this.splitAllFacesByPlane3d(Plane.across(point, foot));
    }

    // Split faces by a plane between two lines [ab] [cd]
    bisector3d(a, b, c, d) {
        // Creases align supporting lines, even when their finite edge pieces
        // stop just short of the intersection after subdivision or rounding.
        const u = Vector3.sub(b, a), v = Vector3.sub(d, c), w = Vector3.sub(a, c);
        const dot = (x, y) => x.x*y.x + x.y*y.y + x.z*y.z;
        const aa = dot(u, u), bb = dot(u, v), cc = dot(v, v), dd = dot(u, w), ee = dot(v, w);
        if (aa < 1e-12 || cc < 1e-12) return;
        const determinant = aa*cc - bb*bb;
        const t = determinant > 1e-12*aa*cc ? (bb*ee - cc*dd)/determinant : 0;
        const s = determinant > 1e-12*aa*cc ? (aa*ee - bb*dd)/determinant : ee/cc;
        const p = new Vector3(a.x+t*u.x, a.y+t*u.y, a.z+t*u.z);
        const q = new Vector3(c.x+s*v.x, c.y+s*v.y, c.z+s*v.z);
        // The closest line is just one point
        const tolerance = 1e-9 * Math.max(1,
            Vector3.length3d(Vector3.sub(a, b)), Vector3.length3d(Vector3.sub(c, d)));
        if (Vector3.length3d(Vector3.sub(p, q)) <= tolerance) {
            // Choose points a and c far from center p (which could be a or c)
            const farther = (u, v) => Vector3.length3d(Vector3.sub(u, p)) > Vector3.length3d(Vector3.sub(v, p)) ? u : v;
            this.bisector3dPoints(farther(a, b), p, farther(c, d));
        } else {
            // Lines do not cross, parallel, there is a plane across the closest segment
            this.splitAllFacesByPlane3d(Plane.across(p, q));
        }
    }

    // Split faces by a line between two lines [ab] [cd]
    bisector2d(s1, s2) {
        const inter = Segment.intersection2dLines(s1.p1, s1.p2, s2.p1, s2.p2);
        if (inter) {
            // Farther from the intersection on each segment
            const a = Point.distance2d(inter, s1.p1) < Point.distance2d(inter, s1.p2) ? s1.p2 : s1.p1;
            const b = Point.distance2d(inter, s2.p1) < Point.distance2d(inter, s2.p2) ? s2.p2 : s2.p1;
            this.bisector2dPoints(a, inter, b);
        } else {
            // Lines do not cross, parallel: split by line from (p1+p2)/2 oriented by p1p2
            const middle = {xf: (s1.p1.xf + s2.p1.xf) / 2, yf: (s1.p1.yf + s2.p1.yf) / 2};
            const p1p2 = {xf: s1.p2.xf - s1.p1.xf, yf: s1.p2.yf - s1.p1.yf};
            this.splitAllFacesByLine2d(middle, {xf: middle.xf + p1p2.xf, yf: middle.yf + p1p2.yf});
        }
    }

    // Split faces by a plane between two segments [ap] [pc].
    bisector3dPoints(a, p, c) {
        const denom = Math.hypot(p.x - c.x, p.y - c.y, p.z - c.z);
        if (denom === 0) return;
        // Project [a] on [p c] to get a symmetric point
        const k = Math.hypot(p.x - a.x, p.y - a.y, p.z - a.z) / denom;
        // e is on pc symmetric of a
        const e = new Vector3(p.x + k * (c.x - p.x), p.y + k * (c.y - p.y), p.z + k * (c.z - p.z));
        // Define Plane across a and e
        this.splitAllFacesByPlane3d(Plane.across(a, e));
    }

    // Split the face at vertex b (adjacent to a and c) by the bisector of angle a-b-c.
    // Falls back to splitting every face crossed by the bisector line when b isn't an
    // existing vertex shared by a single face (e.g. two segments whose lines cross
    // without the crossing point being an actual model vertex).
    bisector2dPoints(a, b, c) {
        // Two unit vectors from b towards a and c
        const v1n = Point.normalize({xf: a.xf - b.xf, yf: a.yf - b.yf});
        const v2n = Point.normalize({xf: c.xf - b.xf, yf: c.yf - b.yf});
        // Bisector direction from b
        const dir = {xf: v1n.xf + v2n.xf, yf: v1n.yf + v2n.yf};
        const target = {xf: b.xf + dir.xf, yf: b.yf + dir.yf};

        const vertex = this.getPoint(b.xf, b.yf);
        const face = vertex && this.faceAtVertex(a, vertex, c);
        if (face) {
            this.splitFaceByLine2d(face, vertex, target);
        } else {
            this.splitAllFacesByLine2d(b, target);
        }
    }

    // Rotate around axis Segment, by angle, the list of Points
    rotate(s, angle, list = this.points) {
        if (!s) return;
        const angleRd = angle * Math.PI / 180;
        const ax = s.p1.x, ay = s.p1.y, az = s.p1.z;
        let nx = s.p2.x - ax, ny = s.p2.y - ay, nz = s.p2.z - az;
        const len = Math.hypot(nx, ny, nz);
        if (len === 0) return;
        const n = 1 / len;
        nx *= n;
        ny *= n;
        nz *= n;
        const sin = Math.sin(angleRd), cos = Math.cos(angleRd);
        const c1 = 1 - cos;
        const c11 = c1 * nx * nx + cos, c12 = c1 * nx * ny - nz * sin, c13 = c1 * nx * nz + ny * sin;
        const c21 = c1 * ny * nx + nz * sin, c22 = c1 * ny * ny + cos, c23 = c1 * ny * nz - nx * sin;
        const c31 = c1 * nz * nx - ny * sin, c32 = c1 * nz * ny + nx * sin, c33 = c1 * nz * nz + cos;
        list.forEach((p) => {
            const ux = p.x - ax, uy = p.y - ay, uz = p.z - az;
            p.x = ax + c11 * ux + c12 * uy + c13 * uz;
            p.y = ay + c21 * ux + c22 * uy + c23 * uz;
            p.z = az + c31 * ux + c32 * uy + c33 * uz;
        });
    }

    // Adjust one point 3d with 2d length of segments
    adjust(point) {
        // Take all segments containing point p
        const segments = this.searchSegmentsOnePoint(point);
        let max = 0.1;
        // Iterate while the length difference between 2d and 3d is > 1e-3
        for (let i = 0; max > 0.001 && i < 200; i++) {
            max = 0;
            // Pm is the medium point
            const pm = new Vector3(0, 0, 0);
            for (const s of segments) {
                const lg3d = Segment.length3d(s) / this.scale;
                if (lg3d === 0) continue;
                const lg2d = Segment.length2d(s); // Should not change
                const d = Math.abs(lg2d - lg3d);
                if (d > max) max = d;
                // Move B = A + AB * r with r = l2d / l3d
                // AB * r is based on length 3d to match length 2d
                const r = lg2d / lg3d;
                let other = null;
                if (s.p2 === point) other = s.p1;
                else if (s.p1 === point) other = s.p2;
                if (!other) continue;
                pm.x += other.x + (point.x - other.x) * r;
                pm.y += other.y + (point.y - other.y) * r;
                pm.z += other.z + (point.z - other.z) * r;
            }
            // Set Point with an average position taking all segments
            if (segments.length > 0) {
                point.x = pm.x / segments.length;
                point.y = pm.y / segments.length;
                point.z = pm.z / segments.length;
            }
        }
        return max;
    }

    // Adjust list of points 3d
    adjustList(list) {
        let max = 0.1;
        for (let i = 0; max > 0.001 && i < 200; i++) {
            max = 0;
            for (const point of list) {
                const d = Math.abs(this.adjust(point));
                if (d > max) max = d;
            }
        }
        return max;
    }

    // Checks segments and selects segments with anormal length
    checkSegments() {
        for (const s of this.segments) {
            const lg3d = Segment.length3d(s) / this.scale;
            const lg2d = Segment.length2d(s); // Should not change
            if (Math.abs(lg2d - lg3d) > 1) {
                s.select = true;
            }
        }
    }

    // Search all segments containing Point a
    searchSegmentsOnePoint(a) {
        return this.segments.filter((s) => s.p1 === a || s.p2 === a);
    }

    // Search faces containing a segment [a, b]
    searchFacesWithAB(a, b) {
        const seg = this.getSegment(a, b);
        if (seg) {
            const list = Model.incidentFaces(this, seg);
            if (list.length > 0) return list;
        }
        // Fallback: faces that contain both vertices
        return this.faces.filter((f) => f.points.includes(a) && f.points.includes(b));
    }

    // Segments that border both faceA and faceB (their shared edges)
    sharedSegments(faceA, faceB) {
        const pts = faceA.points;
        const segs = [];
        for (let i = 0; i < pts.length; i++) {
            const s = this.getSegment(pts[i], pts[(i + 1) % pts.length]);
            if (s && Model.incidentFaces(this, s).includes(faceB)) segs.push(s);
        }
        return segs;
    }

    // Move a list of points by dx,dy,dz
    movePoints(dx, dy, dz, points) {
        if (points.length === 0) points = this.points;
        points.forEach((p) => {
            p.x += dx;
            p.y += dy;
            p.z += dz;
        });
    }

    // Move on a point 'p0' all following list of points
    moveOnPoint(p0, points) {
        points.forEach((p) => {
            p.x = p0.x;
            p.y = p0.y;
            p.z = p0.z;
        });
    }

    // Move on a segment s the following points.
    moveOnSegment(s, points) {
        const A = s.p1, B = s.p2;
        const lengthAB = Math.hypot(B.xf - A.xf, B.yf - A.yf);
        points.forEach((p) => {
            const t = lengthAB === 0 ? 0 : Math.hypot(p.xf - A.xf, p.yf - A.yf) / lengthAB;
            p.x = A.x + t * (B.x - A.x);
            p.y = A.y + t * (B.y - A.y);
            p.z = A.z + t * (B.z - A.z);
        });
    }

    // snap points near each other, and round coordinates
    snapPoints() {
        this.points.forEach((p, i) => {
            if (Math.abs(p.z) <= 6) p.z = 0;
            p.x = Math.round(p.x * 100) / 100;
            p.y = Math.round(p.y * 100) / 100;
            p.z = Math.round(p.z * 100) / 100;
            this.points.slice(i + 1).forEach((q) => {
                if (Math.hypot(q.x - p.x, q.y - p.y, q.z - p.z) < 1) {
                    q.x = p.x;
                    q.y = p.y;
                    q.z = p.z;
                }
            });
        });
    }

    // Turn the model around axis by angle
    turn(axe, angle) {
        const axes = {x: {p1: {x:0, y:0, z:0}, p2: {x:1, y:0, z:0}}, y: {p1: {x:0, y:0, z:0}, p2: {x:0, y:1, z:0}}, z: {p1: {x:0, y:0, z:0}, p2: {x:0, y:0, z:1}}};
        const s = typeof axe === 'string' ? (axes[axe.toLowerCase().replace('angle', '')] || axes.x) : axe;
        this.rotate(s, angle, this.points);
    }

    // Zoom model. Scales 3D distances by `scale`, so the 2d/3d comparison in
    // adjust()/checkSegments() (which divides length3d by this.scale) must be
    // kept in sync, the same way scaleModel() does.
    zoom(scale, x = 0, y = 0) {
        this.scale *= scale;
        this.points.forEach((p) => {
            p.x = x + (p.x - x) * scale;
            p.y = y + (p.y - y) * scale;
            p.z *= scale;
        });
    }

    // Fit model in 400x400
    fit() {
        const b = this.get3DBounds();
        const s = 400 / (Math.max(b.xMax - b.xMin, b.yMax - b.yMin) || 1);
        const cx = (b.xMin + b.xMax) / 2, cy = (b.yMin + b.yMax) / 2;
        this.points.forEach((p) => {
            p.x = (p.x - cx) * s;
            p.y = (p.y - cy) * s;
            p.z *= s;
        });
    }

    // Offset faces by dz
    offset(dz, faces) {
        if (dz === 0 || faces.length === 0) {
            this.faces.forEach((face) => { face.offset = 0; });
        } else {
            faces.forEach((face) => { face.offset += dz / 10; });
        }
    }

    // Bounds helper [xMin, yMin, xMax, yMax]
    bounds(getX, getY) {
        let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
        this.points.forEach((p) => {
            xMin = Math.min(xMin, getX(p));
            xMax = Math.max(xMax, getX(p));
            yMin = Math.min(yMin, getY(p));
            yMax = Math.max(yMax, getY(p));
        });
        return {xMin, xMax, yMin, yMax};
    }

    // 2d Boundary [xMin, yMin, xMax, yMax]
    get2DBounds() {
        return this.bounds((p) => p.xf, (p) => p.yf);
    }

    // 3D Boundary View [xMin, yMin, xMax, yMax]
    get3DBounds() {
        return this.bounds((p) => p.x, (p) => p.y);
    }

    // Scale model @testOK
    scaleModel(scale) {
        this.scale *= scale;
        this.points.forEach((p) => {
            p.x *= scale;
            p.y *= scale;
            p.z *= scale;
        });
    }

    // Snapshot 3D point positions for animation frames (lightweight snapshot)
    snapshotPositions() {
        const coords = new Float64Array(this.points.length * 3);
        for (let i = 0; i < this.points.length; i++) {
            const p = this.points[i];
            const offset = i * 3;
            coords[offset] = p.x;
            coords[offset + 1] = p.y;
            coords[offset + 2] = p.z;
        }
        return coords;
    }

    // Restore 3D point positions from a lightweight snapshot
    restorePositions(coords) {
        for (let i = 0; i < this.points.length; i++) {
            const offset = i * 3;
            this.points[i].x = coords[offset];
            this.points[i].y = coords[offset + 1];
            this.points[i].z = coords[offset + 2];
        }
    }

    // Serialize the model, replace instances by indexes in JSON, and return a JSON string
    serialize() {
        // Non-serialized / UI-only fields (keep undo snapshots lean)
        const exclude = new Set(['hidden', 'hover', 'select', 'xCanvas', 'yCanvas']);
        const pointIndex = new Map(this.points.map((p, i) => [p, i]));
        // Define a replacer function to convert instances into indexes in JSON
        const replacer = (key, value) => {
            if (value instanceof Segment) return {p1: pointIndex.get(value.p1), p2: pointIndex.get(value.p2), assignment: value.assignment};
            if (value instanceof Face) return {points: value.points.map((p) => pointIndex.get(p)), offset: value.offset};
            if (exclude.has(key)) return undefined;
            return value;
        };
        return JSON.stringify(this, replacer);
    }

    // Deserialize the model, revive objects, and return a new model
    static deserialize(json) {
        const data = typeof json === 'string' ? JSON.parse(json) : json;
        const model = new Model();
        Object.assign(model, data);
        if (Array.isArray(data.points)) {
            model.points = data.points.map((p) => new Point(p.xf, p.yf, p.x, p.y, p.z));
        }
        if (Array.isArray(data.segments)) {
            model.segments = data.segments.map((segment) => {
                const newSegment = new Segment(model.points[segment.p1], model.points[segment.p2]);
                if (segment.assignment) newSegment.assignment = segment.assignment;
                return newSegment;
            });
        }
        if (Array.isArray(data.faces)) {
            model.faces = data.faces.map((face) => {
                const newFace = new Face(face.points.map((index) => model.points[index]));
                newFace.offset = face.offset;
                return newFace;
            });
        }
        return model;
    }

    // Get a segment from two points
    getSegment(p1, p2) {
        return this.segments.find((s) =>
            (s.p1 === p1 && s.p2 === p2) || (s.p1 === p2 && s.p2 === p1)
        );
    }

    // Compute 3D unit normal vector [nx, ny, nz]
    static normal(face) {
        const {nx, ny, nz} = newellNormal(face?.points || face || []);
        const len = Math.hypot(nx, ny, nz);
        if (len < 1e-6) return [0, 0, 1];
        return [nx / len, ny / len, nz / len];
    }

    // Compute dihedral angle in degrees between two faces
    static dihedralAngle(face1, face2) {
        const n1 = Model.normal(face1);
        const n2 = Model.normal(face2);
        const dot = Math.max(-1, Math.min(1, n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]));
        return Math.round(Math.acos(dot) * 180 / Math.PI);
    }

    // Signed dihedral angle in degrees between two faces sharing edge [a, b], in the
    // FOLD edges_foldAngle convention: 0 flat, negative Mountain, positive Valley.
    // The shared edge is oriented by face1's own vertex winding (n1 x n2 is parallel
    // to that edge, so its projection on the edge direction gives sin(angle) with a
    // sign consistent with which way face2 folds relative to face1).
    static signedDihedralAngle(face1, face2, a, b) {
        const edgeDir = Model.#edgeDirection(face1, a, b);
        if (!edgeDir) return 0;
        const n1 = Model.normal(face1);
        const n2 = Model.normal(face2);
        const cross = [
            n1[1] * n2[2] - n1[2] * n2[1],
            n1[2] * n2[0] - n1[0] * n2[2],
            n1[0] * n2[1] - n1[1] * n2[0],
        ];
        const sin = cross[0] * edgeDir.x + cross[1] * edgeDir.y + cross[2] * edgeDir.z;
        const cos = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2];
        return Math.round(Math.atan2(sin, cos) * 180 / Math.PI);
    }

    // Unit direction of edge [a, b] as traversed by face's own vertex loop (a, b in either order)
    static #edgeDirection(face, a, b) {
        const pts = face?.points || [];
        for (let i = 0; i < pts.length; i++) {
            const p0 = pts[i], p1 = pts[(i + 1) % pts.length];
            if ((p0 === a && p1 === b) || (p0 === b && p1 === a)) {
                return Vector3.normalize(Vector3.sub(p1, p0));
            }
        }
        return null;
    }

    /**
     * Return up to two faces incident to the given segment
     */
    static incidentFaces(model, segment) {
        if (!model || !segment) return [];
        const faces = [];
        if (!model.faces) return faces;
        for (const face of model.faces) {
            if (Model.#faceContainsSegment(face, segment)) {
                if (!faces.includes(face)) {
                    faces.push(face);
                }
                if (faces.length === 2) break;
            }
        }
        return faces;
    }

    /**
     * Check if a face contains the given segment (in any order)
     */
    static #faceContainsSegment(face, segment) {
        const pts = face.points || [];
        for (let i = 0; i < pts.length; i++) {
            const a = pts[i];
            const b = pts[(i + 1) % pts.length];
            if ((a === segment.p1 && b === segment.p2) || (a === segment.p2 && b === segment.p1)) {
                return true;
            }
        }
        return false;
    }
}
