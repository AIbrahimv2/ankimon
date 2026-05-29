// Dropdown nav switcher for the Profile shell.
//
// IMPORTANT: this does NOT create its own QWebChannel. Creating a second
// QWebChannel over the same transport overwrites the first's
// `transport.onmessage`, so one of them never finishes initializing. Instead
// the page's own script (profile.js / team.js) creates the single channel,
// reads `nav` from it, and calls window.wireNavSwitcher(nav). This matches the
// working Items shell (shop.js wires its own dropdown from its one channel).

(function () {
    'use strict';

    function methodFor(screen) {
        if (!screen) return null;
        return 'open' + screen.charAt(0).toUpperCase() + screen.slice(1);
    }

    // Wire the dropdown to a NavBridge. Safe to call with null (standalone /
    // no bridge) — it just leaves the switcher hidden via the CSS
    // body:not(.shell-mode) rule.
    window.wireNavSwitcher = function (nav) {
        if (!nav) return;
        document.body.classList.add('shell-mode');

        const trigger = document.getElementById('nav-trigger');
        const menu = document.getElementById('nav-menu');
        if (!trigger || !menu) return;

        const open = () => {
            menu.classList.remove('hidden');
            trigger.setAttribute('aria-expanded', 'true');
        };
        const close = () => {
            menu.classList.add('hidden');
            trigger.setAttribute('aria-expanded', 'false');
        };

        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            menu.classList.contains('hidden') ? open() : close();
        });
        document.addEventListener('click', (e) => {
            if (!menu.classList.contains('hidden') &&
                !menu.contains(e.target) && e.target !== trigger) {
                close();
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !menu.classList.contains('hidden')) close();
        });

        menu.querySelectorAll('.nav-menu-item[data-screen]').forEach((item) => {
            item.addEventListener('click', () => {
                const screen = item.dataset.screen;
                close();
                if (item.classList.contains('active')) return;
                const fn = methodFor(screen);
                if (fn && typeof nav[fn] === 'function') nav[fn]();
            });
        });
    };
})();
