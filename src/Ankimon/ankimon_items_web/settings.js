// Settings screen — renders the group schema, tracks dirty state, persists
// via the QWebChannel `settings` bridge object.

(function () {
    'use strict';

    const state = {
        data: null,           // raw payload from Python
        edits: {},            // key → new value (only present if dirty)
        search: '',
        activeGroup: null,    // currently scrolled-into-view group label
    };

    let bridge = null;
    let nav = null;

    function initChannel(cb) {
        if (typeof qt === 'undefined' || !qt.webChannelTransport) {
            console.warn('qt.webChannelTransport unavailable — standalone mode');
            cb(null);
            return;
        }
        new QWebChannel(qt.webChannelTransport, function (channel) {
            bridge = channel.objects && channel.objects.settings;
            nav = channel.objects && channel.objects.nav;
            window.bridge = bridge;
            window.nav = nav;
            cb(bridge);
        });
    }

    window.initializeSettings = function (data) {
        state.data = data || {groups: []};
        state.edits = {};  // fresh data resets dirty state
        renderAll();
    };

    // ---------- Rendering ----------
    function renderAll() {
        renderGroupJumps();
        renderContent();
        applySearchFilter();
        updateDirtyUI();
    }

    function renderGroupJumps() {
        const container = document.getElementById('group-jumps');
        container.innerHTML = '';
        (state.data.groups || []).forEach((g) => {
            const btn = document.createElement('button');
            btn.className = 'group-jump';
            btn.dataset.group = g.label;
            const label = document.createElement('span');
            label.textContent = g.label;
            const count = document.createElement('span');
            count.className = 'group-jump-count';
            count.textContent = countSettings(g);
            btn.appendChild(label);
            btn.appendChild(count);
            btn.addEventListener('click', () => scrollToGroup(g.label));
            container.appendChild(btn);
        });
    }

    function countSettings(group) {
        let n = (group.settings || []).length;
        (group.subgroups || []).forEach((s) => { n += (s.settings || []).length; });
        return n;
    }

    function renderContent() {
        const root = document.getElementById('settings-content');
        root.innerHTML = '';
        (state.data.groups || []).forEach((group) => {
            const groupEl = document.createElement('section');
            groupEl.className = 'settings-group';
            groupEl.dataset.group = group.label;

            const header = document.createElement('div');
            header.className = 'settings-group-header';
            const title = document.createElement('h2');
            title.className = 'settings-group-title';
            title.textContent = group.label;
            const count = document.createElement('span');
            count.className = 'settings-group-count';
            count.textContent = countSettings(group) + ' settings';
            header.appendChild(title);
            header.appendChild(count);
            groupEl.appendChild(header);

            (group.settings || []).forEach((s) => {
                groupEl.appendChild(buildSettingRow(s));
            });

            (group.subgroups || []).forEach((sub) => {
                const subEl = document.createElement('div');
                subEl.className = 'settings-subgroup';
                subEl.dataset.subgroup = sub.label;
                const subTitle = document.createElement('div');
                subTitle.className = 'settings-subgroup-title';
                subTitle.textContent = sub.label;
                subEl.appendChild(subTitle);
                (sub.settings || []).forEach((s) => {
                    subEl.appendChild(buildSettingRow(s));
                });
                groupEl.appendChild(subEl);
            });

            root.appendChild(groupEl);
        });
    }

    function buildSettingRow(setting) {
        const row = document.createElement('div');
        row.className = 'setting-row';
        row.dataset.key = setting.key;
        row.dataset.label = (setting.label || '').toLowerCase();
        row.dataset.desc = (setting.description || '').toLowerCase();

        // Info column
        const info = document.createElement('div');
        info.className = 'setting-info';
        const label = document.createElement('span');
        label.className = 'setting-label';
        label.textContent = setting.label;
        info.appendChild(label);
        // Config key only surfaces in dev mode — irrelevant noise otherwise.
        if (state.data && state.data.dev_mode) {
            const key = document.createElement('span');
            key.className = 'setting-key';
            key.textContent = setting.key;
            info.appendChild(key);
        }
        if (setting.description) {
            const desc = document.createElement('div');
            desc.className = 'setting-description';
            desc.textContent = setting.description;
            info.appendChild(desc);
        }
        row.appendChild(info);

        // Control column
        const control = document.createElement('div');
        control.className = 'setting-control';
        control.appendChild(buildControl(setting));
        row.appendChild(control);

        return row;
    }

    function buildControl(setting) {
        switch (setting.type) {
            case 'boolean':
                return buildToggle(setting);
            case 'select':
                return buildSelect(setting);
            case 'int':
            case 'float':
                return buildNumberInput(setting);
            case 'chips':
                return buildChipGroup(setting);
            default:
                return buildTextInput(setting);
        }
    }

    function buildChipGroup(setting) {
        const wrap = document.createElement('div');
        wrap.className = 'setting-chips';
        (setting.chips || []).forEach((chip) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'setting-chip';
            btn.dataset.key = chip.key;
            const current = (Object.prototype.hasOwnProperty.call(state.edits, chip.key))
                ? state.edits[chip.key] : chip.value;
            if (current) btn.classList.add('active');
            btn.textContent = chip.label;
            btn.addEventListener('click', () => {
                const now = !btn.classList.contains('active');
                // Manually track edits since chips don't go through setEdit's
                // findSetting() lookup (each chip's "setting" is a sub-entry).
                if (chip.value === now) {
                    delete state.edits[chip.key];
                } else {
                    state.edits[chip.key] = now;
                }
                btn.classList.toggle('active', now);
                updateDirtyUI();
                markChipRowDirty(setting.key);
            });
            wrap.appendChild(btn);
        });
        return wrap;
    }

    function markChipRowDirty(rowKey) {
        const row = document.querySelector(`.setting-row[data-key="${cssEscape(rowKey)}"]`);
        if (!row) return;
        const anyDirty = Array.from(row.querySelectorAll('.setting-chip')).some((c) =>
            Object.prototype.hasOwnProperty.call(state.edits, c.dataset.key));
        row.classList.toggle('dirty', anyDirty);
    }

    function buildToggle(setting) {
        const wrap = document.createElement('div');
        wrap.className = 'setting-toggle';
        const current = currentValue(setting);
        ['Enabled', 'Disabled'].forEach((label, i) => {
            const isOn = (i === 0 && current) || (i === 1 && !current);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'setting-toggle-option' + (isOn ? ' active' : '') + (i === 1 ? ' off' : '');
            btn.textContent = label;
            btn.addEventListener('click', () => {
                setEdit(setting.key, i === 0);
                renderAll();  // refresh control + dirty pip
            });
            wrap.appendChild(btn);
        });
        return wrap;
    }

    function buildSelect(setting) {
        const sel = document.createElement('select');
        sel.className = 'setting-select';
        const current = currentValue(setting);
        (setting.options || []).forEach((opt, i) => {
            const o = document.createElement('option');
            o.value = (opt.value === null || opt.value === undefined) ? '__null__' : String(opt.value);
            o.textContent = opt.label;
            if (opt.value === current) o.selected = true;
            sel.appendChild(o);
        });
        sel.addEventListener('change', () => {
            const raw = sel.value === '__null__' ? null : sel.value;
            setEdit(setting.key, raw);
            renderAll();
        });
        return sel;
    }

    function buildNumberInput(setting) {
        const input = document.createElement('input');
        input.type = 'text';  // text so range strings like "1-3" work too
        input.className = 'setting-input numeric';
        input.value = currentValue(setting);
        input.addEventListener('input', () => {
            const raw = input.value.trim();
            // Allow ranges for cards_per_round; otherwise coerce to number.
            if (setting.key === 'battle.cards_per_round' && raw.includes('-')) {
                setEdit(setting.key, raw);
            } else if (raw === '') {
                setEdit(setting.key, raw);
            } else {
                const n = Number(raw);
                setEdit(setting.key, Number.isFinite(n) ? n : raw);
            }
            updateDirtyUI();
            markRowDirty(setting.key);
        });
        return input;
    }

    function buildTextInput(setting) {
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'setting-input';
        input.value = currentValue(setting) ?? '';
        input.addEventListener('input', () => {
            setEdit(setting.key, input.value);
            updateDirtyUI();
            markRowDirty(setting.key);
        });
        return input;
    }

    function currentValue(setting) {
        if (Object.prototype.hasOwnProperty.call(state.edits, setting.key)) {
            return state.edits[setting.key];
        }
        return setting.value;
    }

    // ---------- Edit tracking ----------
    function setEdit(key, value) {
        const original = findSetting(key);
        if (!original) return;
        if (deepEqual(original.value, value)) {
            delete state.edits[key];
        } else {
            state.edits[key] = value;
        }
    }

    function findSetting(key) {
        for (const g of (state.data.groups || [])) {
            for (const s of (g.settings || [])) {
                if (s.key === key) return s;
            }
            for (const sub of (g.subgroups || [])) {
                for (const s of (sub.settings || [])) {
                    if (s.key === key) return s;
                }
            }
        }
        return null;
    }

    function deepEqual(a, b) {
        if (a === b) return true;
        if (typeof a !== typeof b) return false;
        return JSON.stringify(a) === JSON.stringify(b);
    }

    function markRowDirty(key) {
        document.querySelectorAll('.setting-row').forEach((row) => {
            if (row.dataset.key !== key) return;
            row.classList.toggle('dirty',
                Object.prototype.hasOwnProperty.call(state.edits, key));
        });
    }

    function updateDirtyUI() {
        const n = Object.keys(state.edits).length;
        const dirty = n > 0;
        const saveBtn = document.getElementById('save-btn');
        const discardBtn = document.getElementById('discard-btn');
        const pill = document.getElementById('dirty-count');
        const status = document.getElementById('save-status');
        saveBtn.disabled = !dirty;
        saveBtn.classList.toggle('dirty', dirty);
        discardBtn.classList.toggle('hidden', !dirty);
        if (dirty) {
            pill.classList.remove('hidden');
            pill.textContent = n;
            status.textContent = n + ' unsaved';
            status.style.color = 'var(--accent-gold)';
        } else {
            pill.classList.add('hidden');
            status.textContent = 'All saved';
            status.style.color = 'var(--accent-green)';
        }
        // Sync the row-level dirty markers (in case render rebuilt them)
        document.querySelectorAll('.setting-row').forEach((row) => {
            row.classList.toggle('dirty',
                Object.prototype.hasOwnProperty.call(state.edits, row.dataset.key));
        });
    }

    // ---------- Search ----------
    function applySearchFilter() {
        const q = state.search;
        const empty = document.getElementById('settings-empty');
        let visible = 0;
        document.querySelectorAll('.settings-group').forEach((groupEl) => {
            let groupVisible = 0;
            groupEl.querySelectorAll('.setting-row').forEach((row) => {
                const hit = !q || row.dataset.label.includes(q) || row.dataset.desc.includes(q);
                row.classList.toggle('hidden', !hit);
                if (hit) groupVisible++;
            });
            // Hide empty subgroups
            groupEl.querySelectorAll('.settings-subgroup').forEach((sub) => {
                const anyHit = Array.from(sub.querySelectorAll('.setting-row'))
                    .some((r) => !r.classList.contains('hidden'));
                sub.classList.toggle('hidden', !anyHit);
            });
            groupEl.classList.toggle('hidden', groupVisible === 0);
            visible += groupVisible;
        });
        empty.classList.toggle('hidden', visible > 0);
    }

    // ---------- Save ----------
    function onSave() {
        if (!bridge) return;
        const payload = {...state.edits};
        if (Object.keys(payload).length === 0) return;
        // Stringify so the bridge sees a stable `str` parameter — see the
        // SettingsBridge.saveSettings comment for why we avoid passing the
        // dict directly through QVariant.
        bridge.saveSettings(JSON.stringify(payload), function (result) {
            if (!result) return;
            if (result.ok) {
                const adj = (result.adjustments || []).join('\n');
                const msg = adj ? result.message + '\n' + adj : result.message;
                showToast(msg);
                // Re-fetch fresh data so the UI reflects what was actually
                // persisted (including any clamping).
                bridge.getSettings(function (fresh) {
                    if (fresh) window.initializeSettings(fresh);
                });
            } else {
                showToast(result.message || 'Save failed', true);
            }
        });
    }

    function onDiscard() {
        if (Object.keys(state.edits).length === 0) return;
        state.edits = {};
        renderAll();
        showToast('Changes discarded');
    }

    function showToast(message, isError) {
        if (!message) return;
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.classList.toggle('error', !!isError);
        toast.classList.add('visible');
        clearTimeout(toast._timer);
        toast._timer = setTimeout(() => toast.classList.remove('visible'), 2800);
    }

    // ---------- Scroll spy / jumps ----------
    function scrollToGroup(label) {
        // scrollIntoView in QtWebEngine sometimes targets the document
        // rather than .content-scroll. Compute the offset relative to the
        // scroll container and call scrollTo() on it directly — reliable
        // across Qt versions.
        const el = document.querySelector(`.settings-group[data-group="${cssEscape(label)}"]`);
        const scroller = document.querySelector('.content-scroll');
        if (!el || !scroller) return;
        const top = el.offsetTop - 16;  // small breathing room above the header
        scroller.scrollTo({top: Math.max(0, top), behavior: 'smooth'});
    }

    function cssEscape(s) {
        return s.replace(/"/g, '\\"');
    }

    function updateActiveJump() {
        const groups = document.querySelectorAll('.settings-group');
        const scroller = document.querySelector('.content-scroll');
        if (!scroller) return;
        const scrollTop = scroller.scrollTop;
        let active = null;
        groups.forEach((g) => {
            if (g.classList.contains('hidden')) return;
            if (g.offsetTop - 24 <= scrollTop) active = g.dataset.group;
        });
        if (active === state.activeGroup) return;
        state.activeGroup = active;
        document.querySelectorAll('.group-jump').forEach((b) => {
            b.classList.toggle('active', b.dataset.group === active);
        });
    }

    // ---------- UI plumbing ----------
    function bindUI() {
        const search = document.getElementById('settings-search');
        const clear = document.getElementById('clear-search');
        search.addEventListener('input', () => {
            state.search = search.value.trim().toLowerCase();
            clear.classList.toggle('hidden', !state.search);
            applySearchFilter();
        });
        clear.addEventListener('click', () => {
            search.value = '';
            state.search = '';
            clear.classList.add('hidden');
            applySearchFilter();
        });

        document.getElementById('save-btn').addEventListener('click', onSave);
        document.getElementById('discard-btn').addEventListener('click', onDiscard);

        const scroller = document.querySelector('.content-scroll');
        if (scroller) scroller.addEventListener('scroll', updateActiveJump);

        document.addEventListener('keydown', (e) => {
            if (e.key === '/' && document.activeElement !== search) {
                e.preventDefault();
                search.focus();
            } else if ((e.metaKey || e.ctrlKey) && e.key === 's') {
                e.preventDefault();
                onSave();
            }
        });
    }

    function bindNavSwitcher() {
        const trigger = document.getElementById('nav-trigger');
        const menu = document.getElementById('nav-menu');
        if (!trigger || !menu) return;

        const open = () => { menu.classList.remove('hidden'); trigger.setAttribute('aria-expanded', 'true'); };
        const close = () => { menu.classList.add('hidden'); trigger.setAttribute('aria-expanded', 'false'); };

        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            menu.classList.contains('hidden') ? open() : close();
        });
        document.addEventListener('click', (e) => {
            if (!menu.classList.contains('hidden') && !menu.contains(e.target) && e.target !== trigger) close();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !menu.classList.contains('hidden')) close();
        });
        menu.querySelectorAll('.nav-menu-item[data-screen]').forEach((item) => {
            item.addEventListener('click', () => {
                const screen = item.dataset.screen;
                close();
                if (item.classList.contains('active')) return;
                if (!nav) return;
                if (screen === 'items' && nav.openItems) nav.openItems();
                else if (screen === 'ankidex' && nav.openAnkidex) nav.openAnkidex();
                else if (screen === 'settings' && nav.openSettings) nav.openSettings();
            });
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        bindUI();
        initChannel(() => bindNavSwitcher());
    });
})();
