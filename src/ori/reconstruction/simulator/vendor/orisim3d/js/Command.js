// Interprets a list of commands and apply them on Model
import {Interpolator} from './Interpolator.js';
import {Model, State} from './Model.js';
import {ReadWrite} from './ReadWrite.js';

export class Command {
    model; // Current model
    // Tokenized commands
    tokenTodo = [];
    iToken = 0;
    instructions = [];
    snapshots = [];
    paths = [];
    cursor = 0;
    path = null;
    transition = null;
    changed = false;
    // Time interpolated at an instant 'p' preceding and at instant 'n' now
    tpi = 0;
    tni = 1;
    // Rotation axes of the current animated line, frozen at its start (Segment -> {p1, p2})
    frozenAxes = new Map();
    // Interpolator used in anim() to map tn (time normalized) to tni (time interpolated)
    interpolator = Interpolator.LinearInterpolator;
    // Animation
    duration = 0;
    tStart = 0;
    // Eventual CommandArea
    commandArea;
    autoplay = false;
    halt = false;
    // Optional 3D view (for svg export and other view-dependent commands)
    /** @type {{ modelView?: Float32Array, updateCanvasCoords?: () => void } | null} */
    view3d;

    /**
     * @param {import('./Model.js').Model} model
     * @param {{ modelView?: Float32Array, updateCanvasCoords?: () => void } | null} [view3d]
     */
    constructor(model, view3d = null) {
        this.model = model;
        this.view3d = view3d;
        this.reset();
    }
    reset() {
        this.tokenTodo = [];
        this.iToken = 0;
        this.instructions = [];
        this.snapshots = [this.model.serialize()];
        this.paths = [null];
        this.cursor = 0;
        this.path = null;
        this.transition = null;
        this.tpi = 0;
        this.tni = 1;
        this.frozenAxes.clear();
        this.model.state = State.run;
    }
    get first() {
        return /^(d|define)\b/.test(this.instructions[0] ?? '') ? 1 : 0;
    }
    get busy() {
        return this.model.state === State.anim || this.iToken < this.tokenTodo.length;
    }
    steps() {
        return this.snapshots.slice(1, this.cursor + 1).map((json) => Model.deserialize(json));
    }

    // The main entry point executes a string of commands
    command(cde) {
        this.commandArea?.addLine(cde);
        const tokens = this.tokenize(cde);
        if (tokens.length) {
            this.settle();
            this.autoplay = false;
        }
        if (tokens.length === 1 && tokens[0] === 'pause') {
            this.pause();
            return this;
        }
        if (tokens[0] === 'd' || tokens[0] === 'define') {
            this.reset();
        } else if (tokens[0] === 'u' || tokens[0] === 'undo') {
            this.goTo(this.model.state === State.anim ? this.cursor : this.cursor - 1, true);
            return this;
        } else if (tokens[0] === 'redo') {
            this.goTo(this.cursor + 1, true);
            return this;
        } else if (tokens[0] === 'run') {
            this.play();
            return this;
        } else if (tokens[0] === 'stop') {
            this.tokenTodo.length = this.iToken;
            return this;
        }
        if (tokens.length && this.iToken < this.tokenTodo.length && this.tokenTodo.at(-1) !== '\n') {
            this.tokenTodo.push('\n');
        }
        this.tokenTodo.push(...tokens);
        return this;
    }
    get animating() {
        return this.model.state === State.anim || this.model.state === State.undo;
    }
    get playing() {
        return this.autoplay || (this.busy && this.model.state !== State.pause && !this.halt);
    }
    play() {
        this.halt = false;
        if (this.model.state === State.pause) this.model.state = State.run;
        this.autoplay = !this.busy && this.cursor < this.instructions.length;
    }
    pause() {
        this.autoplay = false;
        this.halt = this.busy;
    }
    autoStep() {
        if (!this.autoplay) return false;
        this.goTo(this.cursor + 1, true);
        this.autoplay = this.cursor < this.instructions.length && this.instructions[this.cursor - 1] !== 'pause';
        return true;
    }
    settle() {
        if (this.model.state !== State.undo) return;
        Object.assign(this.model, Model.deserialize(this.snapshots[this.cursor]));
        this.transition = null;
        this.model.state = State.run;
        this.changed = true;
    }
    goTo(k, animate = false) {
        this.settle();
        this.autoplay = false;
        this.halt = false;
        this.tokenTodo.length = this.iToken;
        this.frozenAxes.clear();
        this.path = null;
        this.tpi = 0;
        this.tni = 1;
        const target = Math.max(this.first, Math.min(k, this.instructions.length));
        const path = animate && Math.abs(target - this.cursor) === 1 ? this.paths[Math.max(target, this.cursor)] : null;
        const forward = target > this.cursor;
        this.cursor = target;
        Object.assign(this.model, Model.deserialize(this.snapshots[target]));
        this.model.state = State.run;
        this.changed = true;
        if (path?.frames.every((frame) => frame.coords.length === this.model.points.length * 3)) {
            this.transition = {path, forward, start: performance.now()};
            this.model.state = State.undo;
            this.runTransition();
        }
    }
    runTransition() {
        const {path, forward, start} = this.transition;
        const tn = path.duration > 0 ? Math.min((performance.now() - start) / path.duration, 1) : 1;
        const u = forward ? tn : 1 - tn;
        const frames = path.frames;
        let i = 0;
        while (i < frames.length - 2 && frames[i + 1].tn < u) i++;
        const a = frames[i], b = frames[i + 1];
        const r = b.tn > a.tn ? Math.max(0, Math.min(1, (u - a.tn) / (b.tn - a.tn))) : 1;
        this.model.restorePositions(a.coords.map((c, j) => c + (b.coords[j] - c) * r));
        if (tn >= 1) this.settle();
        return true;
    }

    // Tokenize, split the input String in Array of String
    tokenize(input) {
        const cleaned = input
            .replaceAll(/(:?\/\/|<!--)[^\r\n]*/g, '') // Remove comments
            .replaceAll(/^\s*$/gm, '')   // Remove spaces only lines
            .replaceAll(/\n{2,}/g, '\n') // Remove empty lines
            .trim();                  // Remove leading/trailing whitespace
        return cleaned.match(/\S+|\n/g) || [];
    }

    isNumber(token) {
        return token !== '\n' && !Number.isNaN(Number(token));
    }

    peek() {
        return this.tokenTodo[this.iToken];
    }

    next() {
        return this.tokenTodo[this.iToken++];
    }

    // Optional number with default
    num(fallback) {
        return this.isNumber(this.peek()) ? Number.parseFloat(this.next()) : fallback;
    }

    // Consume one token (always advances, like the previous idx++)
    token(prefix) {
        const token = this.listTokens(this.tokenTodo, this.iToken, prefix)[0];
        this.iToken++;
        return token;
    }

    // Consume a run of tokens with the same prefix (p0 p1 p2...)
    tokens(prefix) {
        const list = this.listTokens(this.tokenTodo, this.iToken, prefix);
        this.iToken += list.length;
        return list;
    }

    // Animation delta between previous and current interpolated time
    get dt() {
        return this.tni - this.tpi;
    }

    // State machine returns true if the model needs redrawing
    // Only 4 states: run, anim, undo, pause
    // Called by requestAnimationFrame(loop)
    anim() {
        const changed = this.changed;
        this.changed = false;
        return this.advance() || changed;
    }
    advance() {
        switch (this.model.state) {
            case State.pause:
                return false;
            case State.run:
                return this.runNext() || this.autoStep();
            case State.undo:
                return this.runTransition();
            case State.anim:
                return this.runAnim();
            default:
                console.log('unhandled state', Object.keys(State)[this.model.state]);
                return false;
        }
    }

    runNext() {
        if (this.iToken >= this.tokenTodo.length) {
            this.halt = false;
            return false;
        }
        if (this.halt) {
            this.halt = false;
            this.model.state = State.pause;
            return false;
        }
        this.idxBefore = this.iToken;
        // Handle time command to start animation and switch to Anim
        if (this.peek() === 't' || this.peek() === 'time') {
            this.iToken++;
            this.duration = Number.parseFloat(this.next());
            this.tStart = performance.now();
            this.tpi = 0;
            this.model.state = State.anim;
            return true;
        }
        this.execute(this.iToken);
        this.record(this.idxBefore, this.iToken);
        return true;
    }

    runAnim() {
        const tn = Math.min((performance.now() - this.tStart) / this.duration, 1);
        const targetTni = this.interpolator(tn);
        // Execute commands after t xxx up to end of line
        const iBeginAnim = this.iToken;
        if (this.tpi === 0) this.freezeRotateAxes(iBeginAnim);
        this.path ??= {duration: this.duration, frames: [{tn: 0, coords: this.model.snapshotPositions()}]};
        const maxStep = 0.01;
        const steps = Math.max(1, Math.ceil(Math.abs(targetTni - this.tpi) / maxStep));
        for (let i = 1; i <= steps; i++) {
            this.tni = this.tpi + (targetTni - this.tpi) * i / steps;
            this.iToken = iBeginAnim;
            while (this.iToken < this.tokenTodo.length && this.peek() !== '\n') {
                this.execute(this.iToken);
            }
            this.tpi = this.tni;
        }
        if (tn >= 1) {
            this.tni = 1;
            this.tpi = 0;
            this.frozenAxes.clear();
            if (this.model.snap) {
                this.model.snapPoints();
            }
            this.path.frames.push({tn: 1, coords: this.model.snapshotPositions()});
            this.record(this.idxBefore, this.iToken, this.path);
            this.path = null;
            this.model.state = State.run;
            return true;
        }
        if (tn >= this.path.frames.at(-1).tn + 1 / 16) this.path.frames.push({tn, coords: this.model.snapshotPositions()});
        this.iToken = iBeginAnim;
        return true;
    }

    // A rotated point can itself be another simultaneous rotation's axis endpoint
    // Snapshot the axis of every `r` of the line before any of them has run, so the
    // last rotation does not see an axis already moved by the earlier ones.
    freezeRotateAxes(iBegin) {
        this.frozenAxes.clear();
        for (let i = iBegin; i < this.tokenTodo.length && this.tokenTodo[i] !== '\n'; i++) {
            if (this.tokenTodo[i] !== 'r' && this.tokenTodo[i] !== 'rotate') continue;
            const s = this.listTokens(this.tokenTodo, i + 1, 's')[0];
            if (s && !this.frozenAxes.has(s)) {
                this.frozenAxes.set(s, {
                    p1: {x: s.p1.x, y: s.p1.y, z: s.p1.z},
                    p2: {x: s.p2.x, y: s.p2.y, z: s.p2.z},
                });
            }
        }
    }

    record(idxBefore, idxAfter, path = null) {
        const line = this.tokenTodo.slice(idxBefore, idxAfter).join(' ');
        if (line === '' || line === '\n') return;
        if (this.instructions[this.cursor] !== line) {
            this.instructions.length = this.cursor;
            this.snapshots.length = this.paths.length = this.cursor + 1;
        }
        this.instructions[this.cursor++] = line;
        this.snapshots[this.cursor] = this.model.serialize();
        this.paths[this.cursor] = path;
    }

    // Execute one instruction from tokenTodo starting at idx on the model.
    execute(idx) {
        this.iToken = idx;
        const token = this.next();
        const command = COMMANDS[token];
        if (command) {
            command(this);
        } else if (token !== '\n') {
            this.skipUnexpected();
        }
    }

    skipUnexpected() {
        const idx = this.iToken - 1;
        console.log('Unexpected end of command', this.tokenTodo.slice(idx, idx + 3).join(' '));
        this.iToken = idx;
        while (this.peek() !== '\n' && this.iToken < this.tokenTodo.length) {
            this.iToken++;
        }
        if (this.iToken < this.tokenTodo.length) {
            this.iToken++;
        }
    }

    listTokens(tokenList, iStart, prefix) {
        const list = [];
        prefix = prefix.toLowerCase();
        const collections = {p: this.model.points, s: this.model.segments, f: this.model.faces};
        const collection = collections[prefix];
        while (iStart < tokenList.length) {
            const token = tokenList[iStart];
            if (token === '\n' || !token || token[0].toLowerCase() !== prefix) break;
            if (token.length < 2) break;
            const n = Number(token.slice(1));        // '' → 0
            if (Number.isNaN(n) || !collection?.[n]) break;   // 0 n'est pas NaN, collection[0] existe
            list.push(collection[n]);
            iStart++;
        }
        return list;
    }

}

function reportError(cmd, message) {
    cmd.commandArea?.addLine(`// ${message}`);
}

function take(cmd, prefix, n, label, apply) {
    const list = cmd.tokens(prefix);
    if (list.length !== n) {
        const got = cmd.tokenTodo.slice(cmd.iToken, cmd.iToken + n + 1).join(' ');
        reportError(cmd, `${label} (got ${list.length}: ${got})`);
        return;
    }
    apply(...list);
}

// Consume one token per given prefix (e.g. one segment then one point), reporting a
// commandArea error if any of them is missing, wrong type, or out of order.
function takeOne(cmd, prefixes, label, apply) {
    const start = cmd.iToken;
    const list = prefixes.map((prefix) => cmd.token(prefix));
    if (list.some((o) => o === undefined)) {
        const got = cmd.tokenTodo.slice(start, cmd.iToken).join(' ');
        reportError(cmd, `${label} (got: ${got})`);
        return;
    }
    apply(...list);
}

function select(cmd, prefix, collection) {
    const selected = cmd.tokens(prefix);
    collection.forEach((o) => {
        o.select = selected.includes(o) && !o.select;
    });
}

function turn(axis) {
    return (cmd) => {
        const angle = Number(cmd.next()) * cmd.dt;
        cmd.model.turn(axis, angle);
    };
}

function define(cmd) {
    cmd.model.init(cmd.num(200), cmd.num(200));
}

function splitSegment(cmd) {
    const s = cmd.token('s');
    const k = Number.parseFloat(cmd.next());
    if (k >= 0 && k <= 1) {
        cmd.model.splitSegmentByRatio2d(s, k);
    }
}

// Uses the axis frozen at the start of the animated line (see freezeRotateAxes),
// or the live segment for a plain non-animated 'r'.
function rotate(cmd) {
    const s = cmd.token('s');
    const angle = Number(cmd.next()) * cmd.dt;
    const axis = cmd.model.state === State.anim ? cmd.frozenAxes.get(s) : undefined;
    cmd.model.rotate(axis ?? s, angle, cmd.tokens('p'));
}

function move(cmd) {
    const d = cmd.dt;
    const dx = Number(cmd.next()) * d;
    const dy = Number(cmd.next()) * d;
    const dz = Number(cmd.next()) * d;
    cmd.model.movePoints(dx, dy, dz, cmd.tokens('p'));
    cmd.model.checkSegments();
}

function zoom(cmd) {
    const scale = Number.parseFloat(cmd.next());
    const a = (1 + cmd.tni * (scale - 1)) / (1 + cmd.tpi * (scale - 1));
    cmd.model.zoom(a, cmd.num(0), cmd.num(0));
}

function fit(cmd) {
    if (cmd.tpi === 0) {
        const b = cmd.model.get3DBounds();
        cmd.fitScale = 400 / (Math.max(b.xMax - b.xMin, b.yMax - b.yMin) || 1);
        cmd.fitCx = (b.xMin + b.xMax) / 2;
        cmd.fitCy = (b.yMin + b.yMax) / 2;
    }
    const s = cmd.fitScale;
    const a = (1 + cmd.tni * (s - 1)) / (1 + cmd.tpi * (s - 1));
    cmd.model.zoom(a, 0, 0);
    const k = s * (a * cmd.tpi - cmd.tni);
    cmd.model.movePoints(cmd.fitCx * k, cmd.fitCy * k, 0, cmd.model.points);
    if (cmd.tni ===1) {
        cmd.commandArea?.addLine(`// Fit: zoom ${Math.round(a * 100) / 100} 0 0 move ${Math.round(cmd.fitCx)} ${Math.round(cmd.fitCy)} 0`);
    }
}

// Order faces front-to-back: the first face is set nearest the viewer, each
// following one progressively behind it.
function order(cmd) {
    const faces = cmd.tokens('f');
    faces.forEach((face, i) => {
        const rank = faces.length - 1 - i;
        const nz = Model.normal(face)[2];
        face.offset = rank === 0 ? 0 : Math.sign(nz) * rank;
    });
}

const COMMANDS = {};
function on(names, command) {
    for (const name of names.split(/\s+/)) {
        COMMANDS[name] = command;
    }
}

function help(cmd) {
    // Group names that were registered together (on('by by3d', fn)) as aliases
    // of the same command, so each line lists synonyms together.
    const byFn = new Map();
    for (const [name, fn] of Object.entries(COMMANDS)) {
        if (!byFn.has(fn)) byFn.set(fn, []);
        byFn.get(fn).push(name);
    }
    const groups = [...byFn.values()];
    cmd.commandArea?.addLine(`Commandes (${groups.length}) :\n${groups.map((g) => g.join('/')).join('\n')}`);
}

on('d define', define);
on('pause', (cmd) => { cmd.model.state = State.pause; });
// Breakpoint: when a script (loaded as one block, e.g. from a template) reaches this
// token, discard everything still queued after it — the rest of that script never runs
// — so lines typed next in the command area take over from here instead of after it.
on('stop', (cmd) => { cmd.tokenTodo.length = cmd.iToken; });

on('by by3d', (cmd) => take(cmd, 'p', 2, 'by3d needs 2 points', (a, b) => cmd.model.splitBy3d(a, b)));
on('by2d', (cmd) => take(cmd, 'p', 2, 'by2d needs 2 points', (a, b) => cmd.model.splitBy2d(a, b)));
on('c3d across3d', (cmd) => take(cmd, 'p', 2, 'c3d needs 2 points', (a, b) => cmd.model.splitCross3d(a, b)));
on('c2d across2d', (cmd) => take(cmd, 'p', 2, 'c2d needs 2 points', (a, b) => cmd.model.splitCross2d(a, b)));
on('p2d perpendicular2d', (cmd) => takeOne(cmd, ['s', 'p'], 'p2d needs 1 segment and 1 point', (s, p) => cmd.model.splitPerpendicular2d(s, p)));
on('p3d perpendicular3d', (cmd) => takeOne(cmd, ['s', 'p'], 'p3d needs 1 segment and 1 point', (s, p) => cmd.model.splitPerpendicular3d(s, p)));
on('parallel2d', (cmd) => takeOne(cmd, ['s', 'p'], 'parallel2d needs 1 segment and 1 point', (s, p) => cmd.model.splitParallel2d(s, p)));
on('parallel3d', (cmd) => takeOne(cmd, ['s', 'p'], 'parallel3d needs 1 segment and 1 point', (s, p) => cmd.model.splitParallel3d(s, p)));
on('bisector2d b2d', (cmd) => take(cmd, 's', 2, 'bisector2d needs 2 segments', (a, b) => cmd.model.bisector2d(a, b)));
on('bisector3d b3d', (cmd) => take(cmd, 's', 2, 'bisector3d needs 2 segments', (s1, s2) => cmd.model.bisector3d(s1.p1, s1.p2, s2.p1, s2.p2)));
on('bisector2dPoints', (cmd) => take(cmd, 'p', 3, 'bisector2dPoints needs 3 points', (a, b, c) => cmd.model.bisector2dPoints(a, b, c)));
on('bisector3dPoints', (cmd) => take(cmd, 'p', 3, 'bisector3dPoints needs 3 points', (a, b, c) => cmd.model.bisector3dPoints(a, b, c)));
on('split splitSegment2d', splitSegment);

on('r rotate', rotate);
on('m move', move);
on('mop moveOnPoint', (cmd) => {const pts = cmd.tokens('p');cmd.model.moveOnPoint(pts[0], pts);});
on('mos moveOnSegment', (cmd) => cmd.model.moveOnSegment(cmd.token('s'), cmd.tokens('p')));
on('a adjust', (cmd) => {
    const pts = cmd.tokens('p');
    cmd.model.adjustList(pts.length === 0 ? cmd.model.points : pts);
});
on('check', (cmd) => {
    cmd.model.points.forEach((p) => { p.select = false; });
    cmd.model.segments.forEach((s) => { s.select = false; });
    cmd.model.checkSegments();
});
on('o offset', (cmd) => cmd.model.offset(Number.parseFloat(cmd.next()) / 10, cmd.tokens('f')));
on('order', order);
on('mountain mv', (cmd) => cmd.tokens('s').forEach((s) => { s.assignment = 'M'; }));
on('valley', (cmd) => cmd.tokens('s').forEach((s) => { s.assignment = 'V'; }));

on('tx', turn('x'));
on('ty', turn('y'));
on('tz', turn('z'));
on('z zoom', zoom);
on('fit', fit);

on('selectPoints sp', (cmd) => select(cmd, 'p', cmd.model.points));
on('selectSegments ss', (cmd) => select(cmd, 's', cmd.model.segments));
on('selectFaces sf', (cmd) => select(cmd, 'f', cmd.model.faces));

function io(names, action) {
    on(names, (cmd) => {
        const token = cmd.peek();
        const filename = token && token !== '\n' && !COMMANDS[token] ? cmd.next() : undefined;
        action(cmd, filename);
    });
}
io('read', (cmd, filename) => ReadWrite.readFileAsText(filename).then((text) => {
    if (text != null) ReadWrite.loadText(cmd, text);
}));
io('write instructions', (cmd, filename) => ReadWrite.writeFile(cmd.instructions.slice(0, cmd.cursor).join('\n'), filename).catch(console.error));
io('writeSvg svg', (cmd, filename) => {
    cmd.view3d?.updateCanvasCoords?.();
    ReadWrite.writeSVG(cmd.model, filename).catch(console.error);
});
io('writeFold fold', (cmd, filename) => ReadWrite.writeFold(cmd.model, filename).catch(console.error));
io('writeDiagrams diagrams', (cmd, filename) => ReadWrite.writeDiagrams(cmd.steps(), filename).catch(console.error));

// Toggles
on('labels', (cmd) => { cmd.model.labels = !cmd.model.labels; });
on('textures', (cmd) => { cmd.model.textures = !cmd.model.textures; });
on('lines', (cmd) => { cmd.model.lines = !cmd.model.lines; });
on('snap', (cmd) => { cmd.model.snap = !cmd.model.snap; });

// Interpolator
on('il', (cmd) => { cmd.interpolator = Interpolator.LinearInterpolator });
on('ib', (cmd) => { cmd.interpolator = Interpolator.BounceInterpolator });
on('io', (cmd) => { cmd.interpolator = Interpolator.OvershootInterpolator });
on('ia', (cmd) => { cmd.interpolator = Interpolator.AnticipateInterpolator });
on('iao', (cmd) => { cmd.interpolator = Interpolator.AnticipateOvershootInterpolator });
on('iad', (cmd) => { cmd.interpolator = Interpolator.AccelerateDecelerateInterpolator });
on('iso', (cmd) => { cmd.interpolator = Interpolator.SpringOvershootInterpolator });
on('isb', (cmd) => { cmd.interpolator = Interpolator.SpringBounceInterpolator });
on('igb', (cmd) => { cmd.interpolator = Interpolator.GravityBounceInterpolator });

on('? help', help);


