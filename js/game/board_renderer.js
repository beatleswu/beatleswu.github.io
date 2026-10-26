(function (global) {
    'use strict';

    // Read only the initial node. Values are tokenized so comments, escaped
    // brackets and variation punctuation cannot masquerade as board properties.
    function readSgfRoot(sgf) {
        if (typeof sgf !== 'string') return null;
        const start = /^\s*\(\s*;/.exec(sgf);
        if (!start) return null;
        let i = start[0].length;
        const properties = Object.create(null);
        while (i < sgf.length) {
            while (/\s/.test(sgf[i] || '') && i < sgf.length) i++;
            if (';()'.includes(sgf[i])) break;
            const name = /^[A-Z]+/.exec(sgf.slice(i));
            if (!name) return null;
            i += name[0].length;
            const values = properties[name[0]] || (properties[name[0]] = []);
            let count = 0;
            while (i < sgf.length) {
                while (/\s/.test(sgf[i] || '') && i < sgf.length) i++;
                if (sgf[i] !== '[') break;
                i++;
                let value = '', closed = false;
                while (i < sgf.length) {
                    const ch = sgf[i++];
                    if (ch === ']') { closed = true; break; }
                    if (ch === '\\') {
                        const escaped = sgf[i++];
                        if (escaped === undefined) return null;
                        if (escaped === '\r' && sgf[i] === '\n') i++;
                        if (escaped !== '\r' && escaped !== '\n') value += escaped;
                    } else value += ch;
                }
                if (!closed) return null;
                values.push(value);
                count++;
            }
            if (!count) return null;
        }
        if (i >= sgf.length) return null;
        const sizeText = (properties.SZ || ['19'])[0];
        const size = /^\d+$/.test(sizeText) ? Number(sizeText) : NaN;
        if (!Number.isInteger(size) || size < 2 || size > 25) return null;
        const point = value => {
            if (!/^[a-z]{2}$/.test(value)) return null;
            const x = value.charCodeAt(0) - 97, y = value.charCodeAt(1) - 97;
            return x < size && y < size ? { x, y } : null;
        };
        const points = value => {
            const single = point(value);
            if (single) return [single];
            const range = value.split(':');
            const a = point(range[0]), b = point(range[1]);
            if (range.length !== 2 || !a || !b || a.x > b.x || a.y > b.y) return [];
            const out = [];
            for (let x = a.x; x <= b.x; x++) for (let y = a.y; y <= b.y; y++) out.push({ x, y });
            return out;
        };
        const annotations = [];
        for (const type of ['TR', 'SQ', 'CR', 'MA', 'LB']) {
            for (const value of properties[type] || []) {
                if (type === 'LB') {
                    const colon = value.indexOf(':');
                    const p = point(value.slice(0, colon));
                    if (colon === 2 && p && value.length > 3) annotations.push({ ...p, type, text: value.slice(3) });
                } else for (const p of points(value)) annotations.push({ ...p, type });
            }
        }
        return {
            size, pl: (properties.PL || [])[0], end: i, annotations,
            black: (properties.AB || []).flatMap(points),
            white: (properties.AW || []).flatMap(points),
        };
    }

    function renderAnnotations(board, problem, crop = {}) {
        if (!board || !problem || typeof board.addObject !== 'function') return 0;
        let count = 0;
        const size = crop.displayLines || problem.size;
        for (const marker of problem.annotations || []) {
            const x = marker.x - (crop.startX || 0), y = marker.y - (crop.startY || 0);
            if (x < 0 || y < 0 || x >= size || y >= size) continue;
            board.addObject({ ...marker, x, y });
            count++;
        }
        return count;
    }

    function create(dependencies = {}) {
        if (!dependencies || typeof dependencies !== 'object') {
            throw new TypeError('BoardRenderer dependencies must be an object');
        }

        let board = null;
        let renderGeneration = 0;
        let lifecycleGeneration = 0;
        let mounted = false;
        let activeClickHandler = null;

        const getContainer = () => typeof dependencies.getContainer === 'function'
            ? dependencies.getContainer()
            : dependencies.container || null;

        function detachListener() {
            if (!board || !activeClickHandler) return;
            try {
                if (typeof board.removeEventListener === 'function') {
                    board.removeEventListener('click', activeClickHandler);
                }
            } catch (error) {}
            activeClickHandler = null;
        }

        function teardown({ removeDom = true } = {}) {
            lifecycleGeneration += 1;
            detachListener();
            const oldBoard = board;
            board = null;
            mounted = false;
            if (typeof dependencies.setBoard === 'function') {
                try { dependencies.setBoard(null); } catch (error) {}
            }
            if (typeof dependencies.onTeardown === 'function') {
                try { dependencies.onTeardown(oldBoard, lifecycleGeneration); } catch (error) {}
            }
            if (removeDom) {
                const container = getContainer();
                if (container) {
                    try { container.innerHTML = ''; } catch (error) {}
                }
            }
            return true;
        }

        function mount(options = {}) {
            const container = getContainer();
            if (!container || typeof dependencies.createBoard !== 'function') return null;
            const skipTeardown = typeof dependencies.skipTeardown === 'function'
                && dependencies.skipTeardown(options.attemptNumber);
            teardown({ removeDom: !skipTeardown });
            container.style.width = '';
            container.style.height = '';
            const result = dependencies.createBoard({
                container,
                options,
                renderGeneration: renderGeneration + 1,
            });
            const createdBoard = result && result.board ? result.board : result;
            if (!createdBoard) return null;
            board = createdBoard;
            mounted = true;
            renderGeneration += 1;
            if (typeof dependencies.setBoard === 'function') {
                try { dependencies.setBoard(board); } catch (error) {}
            }
            activeClickHandler = options.onClick || dependencies.onClick || null;
            if (activeClickHandler && typeof board.addEventListener === 'function') {
                try { board.addEventListener('click', activeClickHandler); } catch (error) {}
            }
            if (typeof dependencies.onMounted === 'function') {
                try {
                    dependencies.onMounted({
                        board,
                        renderGeneration,
                        result,
                        options,
                    });
                } catch (error) {}
            }
            return { board, renderGeneration, result };
        }

        function resize(options = {}) {
            if (!board || !mounted) return false;
            const width = Number(options.width);
            const height = Number(options.height ?? options.width);
            try {
                if (Number.isFinite(width) && typeof board.setDimensions === 'function') {
                    board.setDimensions(width, Number.isFinite(height) ? height : width);
                } else if (Number.isFinite(width) && typeof board.resize === 'function') {
                    board.resize(width, Number.isFinite(height) ? height : width);
                } else if (typeof dependencies.resizeBoard === 'function') {
                    dependencies.resizeBoard(board, options);
                } else {
                    return false;
                }
                if (typeof dependencies.onResize === 'function') {
                    dependencies.onResize({ board, renderGeneration, options });
                }
                return true;
            } catch (error) {
                if (typeof dependencies.onError === 'function') {
                    try { dependencies.onError(error, 'resize'); } catch (observerError) {}
                }
                return false;
            }
        }

        function clear() {
            if (!board) return false;
            try {
                if (typeof board.removeAllObjects === 'function') board.removeAllObjects();
                if (typeof dependencies.onClear === 'function') dependencies.onClear(board);
                return true;
            } catch (error) {
                if (typeof dependencies.onError === 'function') {
                    try { dependencies.onError(error, 'clear'); } catch (observerError) {}
                }
                return false;
            }
        }

        function render(callback, options = {}) {
            if (!board || !mounted) return false;
            if (options.generation != null && Number(options.generation) !== renderGeneration) {
                return false;
            }
            if (typeof callback !== 'function') return true;
            try {
                callback(board, renderGeneration);
                return true;
            } catch (error) {
                if (typeof dependencies.onError === 'function') {
                    try { dependencies.onError(error, 'render'); } catch (observerError) {}
                }
                return false;
            }
        }

        const addObject = (object) => board && typeof board.addObject === 'function'
            ? board.addObject(object)
            : false;
        const removeObject = (object) => board && typeof board.removeObject === 'function'
            ? board.removeObject(object)
            : false;

        return Object.freeze({
            mount,
            remount: mount,
            resize,
            clear,
            render,
            teardown,
            destroy: teardown,
            addObject,
            removeObject,
            board: () => board,
            renderGeneration: () => renderGeneration,
            isMounted: () => mounted,
        });
    }

    const api = Object.freeze({ create, readSgfRoot, renderAnnotations });
    global.GoOdysseyBoardRenderer = api;
    global.BoardRenderer = api;
})(window);
