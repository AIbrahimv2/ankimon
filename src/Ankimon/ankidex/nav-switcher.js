// Cross-screen navigation switcher logic.
//
// Tries to connect to the shell's QWebChannel. If a bridge is available we
// flip body.shell-mode (which makes the dropdown affordances visible per
// nav-switcher.css), wire the trigger click, and route menu clicks through
// window.nav.openItems() / openAnkidex(). Standalone (no bridge) is a no-op.

(function () {
    'use strict';

    function bindSwitcher(nav) {
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
                if (screen === 'items' && nav.openItems) nav.openItems();
                else if (screen === 'ankidex' && nav.openAnkidex) nav.openAnkidex();
            });
        });
    }

    function init() {
        if (typeof qt === 'undefined' || !qt.webChannelTransport) return;
        new QWebChannel(qt.webChannelTransport, function (channel) {
            const nav = channel.objects && channel.objects.nav;
            if (nav) bindSwitcher(nav);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
