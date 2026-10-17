import {Point} from "./Point.js";
import {Vector3} from './Vector3.js';

export class Face {

    constructor(points) {
        this.points = points;
        this.offset = 0;
        this.hover = false;
        this.select = false;
    }

    // Area 2d for an array of points
    static area2dFlat(points) {
        let area = 0;
        for (let i = 0; i < points.length; i++) {
            area += points[i].xf * points[(i + 1) % points.length].yf - points[i].yf * points[(i + 1) % points.length].xf;
        }
        return area / 2;
    }

    // All turns the same way (colinear vertices ignored)
    static isConvex2d(face) {
        const pts = face.points;
        if (pts.length < 3) return true;
        let sign = 0;
        for (let i = 0; i < pts.length; i++) {
            const z = Face.distance2dLineToPoint(pts[i], pts[(i + 1) % pts.length], pts[(i + 2) % pts.length]);
            if (Math.abs(z) < 1e-9) continue;
            const s = Math.sign(z);
            if (sign === 0) sign = s;
            else if (s !== sign) return false;
        }
        return true;
    }

    // Distance 2d from line AB to point C
    static distance2dLineToPoint(a, b, c) {
        // Cross-product AC x AB give z > 0 if C is on the right, ACB is CCW
        // AC = C-A and AB = B-A
        return (c.xf - a.xf) * (b.yf - a.yf) - (c.yf - a.yf) * (b.xf - a.xf);
    }

    // Intersection with a segment (a,b)
    static intersectionPlaneSegment(plane, a, b) {
        // (A+tAB).N = d <=> t = (d-A.N) / (AB.N) then Q=A+tAB 0<t<1
        const ab = new Vector3(b.x - a.x, b.y - a.y, b.z - a.z);
        const abn = Vector3.dot(plane.normal, ab);
        // segment parallel to the plane
        if (abn === 0) return undefined;
        // segment crossing
        const t = (Vector3.dot(plane.normal, plane.origin) - Vector3.dot(plane.normal, a)) / abn;
        if (t >= 0 && t <= 1) {
            const scaled = Vector3.scale(ab, t);
            const xf = a.xf + t * (b.xf - a.xf);
            const yf = a.yf + t * (b.yf - a.yf);
            return new Point(xf, yf, a.x + scaled.x, a.y + scaled.y, a.z + scaled.z);
        }
        return undefined;
    }

    // Signed distance in 3d
    static planeToPointSignedDistance(plane, point) {
        // Signed distance from plane(origin, normal) to point
        // (A+tAB).N = d <=> d<e front, d>e behind, else on plane
        return Vector3.dot(plane.normal, point) - Vector3.dot(plane.normal, plane.origin);
    }

    // Face contains 2d point
    static contains2d(face, xf, yf) {
        // ray-casting algorithm based on
        // https://wrf.ecse.rpi.edu/Research/Short_Notes/pnpoly.html

        let inside = false;
        const vs = face.points;
        for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
            const xi = vs[i].xf, yi = vs[i].yf;
            const xj = vs[j].xf, yj = vs[j].yf;
            // Special case where the point is part of the face.
            if (xi === xf && yi === yf) {
                return true;
            }
            const intersect = ((yi > yf) !== (yj > yf)) && (xf < (xj - xi) * (yf - yi) / (yj - yi) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    // Face contains 3d point
    static contains3d(face, xCanvas, yCanvas, view3d) {
        // ray-casting algorithm based on
        // https://wrf.ecse.rpi.edu/Research/Short_Notes/pnpoly.html

        const x = xCanvas, y = yCanvas;
        let inside = false;
        const vs = face.points;
        for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
            const pi = vs[i];
            const pj = vs[j];

            const idxI = view3d.indexMap.get(pi);
            const idxJ = view3d.indexMap.get(pj);

            if (idxI !== undefined && idxJ !== undefined) {
                const xi = pi.xCanvas, yi = pi.yCanvas;
                const xj = pj.xCanvas, yj = pj.yCanvas;

                if (xi === xCanvas && yi === yCanvas) {
                    return true;
                }

                const intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
                if (intersect) inside = !inside;
            }
        }

        return inside;
    }
}
// 102 lines of code
