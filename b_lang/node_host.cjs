// Trusted installed packages run in one worker. Its stdout and stderr are
// separate from the parent thread's JSON replies to B.
'use strict';
const { Worker, isMainThread, workerData, parentPort } = require('node:worker_threads');

function serialize(value, type) {
    const [kind, inner, itemType] = type;
    if (kind === 'Option') return value === null ? null : serialize(value, inner);
    if (kind === 'Any') {
        // Plain JSON data only: B checks the shape where the value is used.
        if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
        if (Number.isSafeInteger(value)) return value;
        if (Array.isArray(value)) return value.map((item) => serialize(item, ['Any']));
        throw Error('Export did not return plain JSON data for Any');
    }
    if (kind === 'Int' && Number.isSafeInteger(value)) return value;
    if (kind === 'Float' && Number.isFinite(value)) return Object.is(value, -0) ? '-0' : String(value);
    if (kind === 'Bool' && typeof value === 'boolean') return value;
    if (kind === 'Text' && typeof value === 'string') return value;
    if (kind === 'List' && Array.isArray(value)) {
        if (Reflect.ownKeys(value).length !== value.length + 1) throw Error('Expected a dense plain array');
        const result = [];
        for (let i = 0; i < value.length; i++) {
            const d = Object.getOwnPropertyDescriptor(value, String(i));
            if (!d || !Object.hasOwn(d, 'value')) throw Error('Expected an array of data values');
            result.push(serialize(d.value, inner));
        }
        return result;
    }
    if (kind === 'Dict' && value !== null && typeof value === 'object' &&
            [null, Object.prototype].includes(Object.getPrototypeOf(value))) {
        const result = Object.create(null);
        for (const key of Reflect.ownKeys(value)) {
            const d = Object.getOwnPropertyDescriptor(value, key);
            if (typeof key !== 'string' || !d.enumerable || !Object.hasOwn(d, 'value')) {
                throw Error('Expected an object with enumerable string data keys');
            }
            result[key] = serialize(d.value, itemType);
        }
        return result;
    }
    throw Error('Export did not return the declared ' + kind + ' value');
}

function runPackageWorker() {
    const { createRequire, isBuiltin } = require('node:module');
    const requireAtSource = createRequire(workerData);
    const modules = new Map();
    parentPort.on('message', req => {
        try {
            if (req.op === 'load') {
                if (req.target !== 'node:path/posix' && isBuiltin(req.target)) {
                    throw Error('Unregistered Node builtin ' + req.target);
                }
                if (req.target === 'semver') {
                    const version = requireAtSource('semver/package.json').version;
                    if (typeof version !== 'string' || !version.startsWith('7.')) {
                        throw Error('The curated semver catalog requires version 7; found ' + version);
                    }
                }
                modules.set(req.target, requireAtSource(req.target));
                parentPort.postMessage({ok: true});
                return;
            }
            const mod = modules.get(req.target);
            const fn = mod && Object.hasOwn(mod, req.member) ? mod[req.member] : undefined;
            if (typeof fn !== 'function') {
                throw Error('Missing named export ' + req.target + '.' + req.member);
            }
            const value = Reflect.apply(fn, mod, req.args);
            if (require('node:util').types.isPromise(value)) {
                value.catch(() => {});
                throw Error('Async Node exports are unsupported');
            }
            parentPort.postMessage({ok: true, value: serialize(value, req.result)});
        } catch (err) {
            parentPort.postMessage({ok: false, error: String(err?.message ?? err)});
        }
    });
}

function serve() {
    const worker = new Worker(__filename, {workerData: process.argv[2], stdout: true, stderr: true});
    worker.stdout.pipe(process.stderr);
    worker.stderr.pipe(process.stderr);
    const input = require('node:readline').createInterface({input: process.stdin});
    let timer;
    input.on('line', line => {
        // The B client serializes requests. A timeout ends this session, so a
        // later call cannot silently start a fresh copy of a stateful module.
        timer = setTimeout(() => {
            process.stdout.write(JSON.stringify({ok: false, error: 'Node request timed out'}) + '\n');
            process.exitCode = 1;
            input.close();
        }, 10000);
        worker.postMessage(JSON.parse(line));
    });
    worker.on('message', reply => {
        clearTimeout(timer);
        process.stdout.write(JSON.stringify(reply) + '\n');
    });
    worker.on('exit', () => {
        clearTimeout(timer);
        // A library can terminate its own worker. Wake the Python reader.
        process.exit(1);
    });
    worker.on('error', err => { process.stderr.write(String(err) + '\n'); });
    input.on('close', () => { worker.terminate(); });
}

if (isMainThread) serve();
else runPackageWorker();
