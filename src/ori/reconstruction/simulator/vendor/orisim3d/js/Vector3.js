export class Vector3 {

    constructor(x = 0, y = 0, z = 0) {
        this.x = x;
        this.y = y;
        this.z = z;
    }

    // The closest point to C on line (A, B) (unclamped: not restricted to the [A, B] segment)
    static closestPoint(C, A, B) {
        // Vector AB and AC
        const AB = new Vector3(B.x - A.x, B.y - A.y, B.z - A.z);
        const AC = new Vector3(C.x - A.x, C.y - A.y, C.z - A.z);
        // Project C on AB d(t) = A + t * AB
        const ab = Vector3.dot(AB, AB);
        const t = ab === 0 ? 0 : Vector3.dot(AC, AB) / ab;
        // P = a+t*(b-a)
        return new Vector3(A.x + AB.x * t, A.y + AB.y * t, A.z + AB.z * t);
    }

    // Distance between point C and line [A, B] return number
    static pointLineDistance(C, A, B) {
        return Vector3.distance(C, Vector3.closestPoint(C, A, B));
    }

    // Euclidean distance between two points
    static distance(a, b) {
        return Vector3.length3d(Vector3.sub(a, b));
    }

    static dot(u, v) {
        return u.x * v.x + u.y * v.y + u.z * v.z;
    }

    static scale(v, scalar) {
        return new Vector3(v.x * scalar, v.y * scalar, v.z * scalar);
    }

    static length3d(v) {
        return Math.hypot(v.x, v.y, v.z);
    }

    static normalize(v) {
        const length = Vector3.length3d(v);
        return length === 0 ? new Vector3(v.x, v.y, v.z) : Vector3.scale(v, 1 / length);
    }

    static add(u, v) {
        const x = u.x + v.x;
        const y = u.y + v.y;
        const z = u.z + v.z;
        return new Vector3(x, y, z);
    }

    static sub(a, b) {
        return new Vector3(a.x - b.x, a.y - b.y, a.z - b.z);
    }

    static cross(a, b) {
        const ax = a.x, ay = a.y, az = a.z;
        const bx = b.x, by = b.y, bz = b.z;
        const x = ay * bz - az * by;
        const y = az * bx - ax * bz;
        const z = ax * by - ay * bx;
        return new Vector3(x, y, z);
    }

    static transformMat4(v, m) {
        const x = v.x, y = v.y, z = v.z;
        let w = m[3] * x + m[7] * y + m[11] * z + m[15];
        // w = w || 1;
        if (!Number.isFinite(w) || w === 0) w = 1;
        return new Vector3(
            (m[0] * x + m[4] * y + m[8] * z + m[12]) / w,
            (m[1] * x + m[5] * y + m[9] * z + m[13]) / w,
            (m[2] * x + m[6] * y + m[10] * z + m[14]) / w
        );
    }
}

// 70
