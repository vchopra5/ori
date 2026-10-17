export class Point {

    constructor(xf, yf, x=0, y=0, z=0) {
        this.xf = Number(xf);
        this.yf = Number(yf);
        this.x = Number(x);
        this.y = Number(y);
        this.z = Number(z);
        // Helper
        this.hover = false;
        this.select = false;
        // xCanvas projected point in overlay
        this.xCanvas = null;
        this.yCanvas = null;
        // hide labels
        this.hidden = false;
    }

    // Adjust point i 2d coords on segment ab
    static align2dFrom3d(a, b, i) {
        const ab = Math.hypot((b.x - a.x), (b.y - a.y), (b.z - a.z));
        if (ab === 0) return;
        const ai = Math.hypot((i.x - a.x), (i.y - a.y), (i.z - a.z));
        const t = ai / ab;
        i.xf = a.xf + t * (b.xf - a.xf);
        i.yf = a.yf + t * (b.yf - a.yf);
    }

    // Adjust point i 3d coords on segment ab
    static align3dFrom2d(a, b, i) {
        const ab = Math.hypot((b.xf - a.xf), (b.yf - a.yf));
        if (ab === 0) return;
        const ai = Math.hypot((i.xf - a.xf), (i.yf - a.yf));
        const t = ai / ab;
        i.x = a.x + t * (b.x - a.x);
        i.y = a.y + t * (b.y - a.y);
        i.z = a.z + t * (b.z - a.z);
    }

    // Distance
    static distance2d(a, b) {
        return Math.hypot((b.xf - a.xf), (b.yf - a.yf));
    }

    // Normalize as if Vector 2d
    static normalize(a) {
        const length = Math.hypot(a.xf, a.yf);
        if (length === 0) return {xf: 0, yf: 0};
        return {xf: a.xf / length, yf: a.yf / length};
    }
}
