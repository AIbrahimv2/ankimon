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
        // Re-run the spy after render so the active button reflects the
        // post-render scroll position (in case the DOM rebuild moved things
        // around).
        updateActiveSection();
    }

    function renderGroupJumps() {
        const container = document.getElementById('group-jumps');
        // Build into a fragment then swap atomically to avoid a brief
        // empty-state on every save refresh.
        const frag = document.createDocumentFragment();
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
            frag.appendChild(btn);
        });
        container.replaceChildren(frag);
    }

    function countSettings(group) {
        let n = (group.settings || []).length;
        (group.subgroups || []).forEach((s) => { n += (s.settings || []).length; });
        return n;
    }

    function renderContent() {
        const root = document.getElementById('settings-content');
        // Build the whole settings tree into a fragment off-DOM, then swap
        // it in atomically. Without this, every save → re-fetch cycle
        // flashes an empty form area while ~60 rows rebuild sequentially.
        const frag = document.createDocumentFragment();
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

            frag.appendChild(groupEl);
        });
        root.replaceChildren(frag);
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
    //
    // Approach (after several iterations):
    // 1. Clicking a section in the sidebar SETS the active state directly
    //    and suppresses the scroll-spy for 1.5s. This means the user's
    //    explicit choice wins even when the scroll lands at max (e.g.
    //    Generations near the bottom of a short page).
    // 2. Otherwise the spy runs on scroll. The active section is the LAST
    //    one whose top has crossed a reading line near the top of the
    //    scroller — the classic "where am I" check.
    // 3. When the user is at max scroll AND later sections couldn't reach
    //    the line, fall back to whichever section's top is closest to
    //    (just below) the line. That's how Study/Generations become
    //    select-able via manual scrolling on short content.

    let suppressSpyUntil = 0;
    const READING_LINE_PX = 80;

    function setActiveButton(label) {
        if (label === state.activeGroup) return;
        state.activeGroup = label;
        document.querySelectorAll('.group-jump').forEach((b) => {
            b.classList.toggle('active', b.dataset.group === label);
        });
    }

    function scrollToGroup(label) {
        const el = document.querySelector(`.settings-group[data-group="${cssEscape(label)}"]`);
        const scroller = document.querySelector('.content-scroll');
        if (!el || !scroller) return;
        const elTop = el.getBoundingClientRect().top;
        const scrollerTop = scroller.getBoundingClientRect().top;
        const offsetWithinScroller = elTop - scrollerTop + scroller.scrollTop;
        // 32px breathing room so the section header sits comfortably
        // below the top-bar instead of butting up against it.
        const target = Math.max(0, offsetWithinScroller - 32);
        scroller.scrollTo({top: target, behavior: 'smooth'});
        flashSection(el);
        // Win against the spy: the user's click wins even if the resulting
        // scroll position would normally activate a different section.
        setActiveButton(label);
        suppressSpyUntil = Date.now() + 1500;
    }

    function flashSection(el) {
        // Brief tint so the user sees the jump landed on the right section.
        // Re-trigger the animation if the class is already present
        // (consecutive clicks on the same nav item).
        el.classList.remove('flash-highlight');
        // Force reflow so the animation restarts on re-add.
        void el.offsetWidth;
        el.classList.add('flash-highlight');
    }

    function cssEscape(s) {
        return s.replace(/"/g, '\\"');
    }

    function updateActiveSection() {
        if (Date.now() < suppressSpyUntil) return;
        const scroller = document.querySelector('.content-scroll');
        if (!scroller) return;
        const sRect = scroller.getBoundingClientRect();
        const sections = Array.from(document.querySelectorAll('.settings-group'))
            .filter((g) => !g.classList.contains('hidden'));
        if (!sections.length) return;

        const readingLine = sRect.top + READING_LINE_PX;

        // Primary: last section whose top has crossed the reading line.
        let active = null;
        sections.forEach((g) => {
            if (g.getBoundingClientRect().top <= readingLine + 4) active = g;
        });

        // Fallback when we're at max scroll: short later sections that
        // couldn't physically be scrolled past the line still need to be
        // select-able. Pick whichever section's top is closest to (just
        // below) the line.
        const atMax = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 4;
        if (atMax) {
            let nearestBelow = null;
            let nearestDist = Infinity;
            sections.forEach((g) => {
                const dist = g.getBoundingClientRect().top - readingLine;
                if (dist > 0 && dist < nearestDist) {
                    nearestDist = dist;
                    nearestBelow = g;
                }
            });
            if (nearestBelow) active = nearestBelow;
        }

        if (!active) active = sections[0];
        setActiveButton(active.dataset.group);
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
        if (scroller) scroller.addEventListener('scroll', updateActiveSection);

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

    document.addEventListener('DOMContentLoaded', () => {
        bindUI();
        // Dropdown nav: wire from the shared switcher once the channel resolves
        // so it has the live NavBridge. See ankimon_items_web/nav-switcher.js.
        initChannel(() => {
            if (window.wireNavSwitcher) window.wireNavSwitcher(nav);
        });
    });
})();
