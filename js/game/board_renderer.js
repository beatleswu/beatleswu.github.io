(function (global) {
    'use strict';

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

    const api = Object.freeze({ create });
    global.GoOdysseyBoardRenderer = api;
    global.BoardRenderer = api;
})(window);
