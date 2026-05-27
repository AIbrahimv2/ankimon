// Ankimon Items — unified Mart + Bag web UI.
// Talks to Python via QWebChannel (window.bridge) for buy / reroll / use.

(function () {
    'use strict';

    const TYPE_COLORS = {
        normal: '#A8A77A', fire: '#EE8130', water: '#6390F0',
        electric: '#F7D02C', grass: '#7AC74C', ice: '#96D9D6',
        fighting: '#C22E28', poison: '#A33EA1', ground: '#E2BF65',
        flying: '#A98FF3', psychic: '#F95587', bug: '#A6B91A',
        rock: '#B6A136', ghost: '#735797', dragon: '#6F35FC',
        dark: '#705746', steel: '#B7B7CE', fairy: '#D685AD',
    };

    const CATEGORY_LABELS = {
        tm: 'TM',
        heal: 'Heal',
        pokeball: 'Ball',
        evolution: 'Evolution',
        fossil: 'Fossil',
        other: '',
    };

    const state = {
        data: null,
        filter: 'in_shop',     // in_shop | owned
        category: 'all',       // all | tm | heal | pokeball | evolution | fossil
        search: '',
        selected: null,        // item name
    };

    let bridge = null;

    function initChannel(callback) {
        if (typeof qt === 'undefined' || !qt.webChannelTransport) {
            console.warn('qt.webChannelTransport unavailable — standalone mode');
            callback(null);
            return;
        }
        new QWebChannel(qt.webChannelTransport, function (channel) {
            bridge = channel.objects.bridge;
            window.bridge = bridge;
            callback(bridge);
        });
    }

    function preloadImages(urls, callback) {
        if (!urls || urls.length === 0) {
            callback();
            return;
        }
        let loaded = 0;
        const target = urls.length;
        urls.forEach((url) => {
            const img = new Image();
            img.onload = img.onerror = () => {
                loaded++;
                if (loaded === target) {
                    callback();
                }
            };
            img.src = url;
        });
    }

    // Entry from Python
    window.initializeItems = function (data) {
        state.data = data;
        const urls = (data.items || []).map((i) => i.image_url).filter(Boolean);
        preloadImages(urls, function () {
            render();
        });
    };

    // ---------- Rendering ----------
    function render() {
        if (!state.data) return;
        const items = state.data.items || [];

        document.getElementById('currency-value').textContent =
            formatMoney(state.data.cash) + '¥';

        const rerollBtn = document.getElementById('reroll-btn');
        const rerollCost = state.data.reroll_cost || 0;
        document.getElementById('reroll-cost-label').textContent = rerollCost + '¥';
        rerollBtn.disabled = state.data.cash < rerollCost;

        const counts = countItems(items);
        document.getElementById('count-in-shop').textContent = counts.in_shop;
        document.getElementById('count-owned').textContent = counts.owned;
        document.getElementById('stat-shop').textContent = counts.in_shop;
        document.getElementById('stat-owned').textContent = counts.owned;

        const visible = items.filter(matchesFilters);
        const grid = document.getElementById('items-grid');
        const empty = document.getElementById('empty-state');

        if (visible.length === 0) {
            grid.replaceChildren();
            empty.classList.remove('hidden');
            refreshDetailPanel();
            return;
        }
        empty.classList.add('hidden');

        // Keyed DOM Reconciliation to completely eliminate visual flicker:
        // Instead of destroying and rebuilding all card DOM elements (which
        // destroys <img> instances and triggers asynchronous image-decoding layout passes),
        // we map existing cards by their item name and update/reorder them in-place.
        const existingCards = Array.from(grid.querySelectorAll('.shop-card'));
        const cardMap = new Map();
        existingCards.forEach(card => {
            const name = card.getAttribute('data-item-name');
            if (name) cardMap.set(name, card);
        });

        const itemEntries = visible.filter((i) => !i.is_tm);
        const tmEntries = visible.filter((i) => i.is_tm);
        const splitSections = state.category === 'all'
            && itemEntries.length > 0
            && tmEntries.length > 0;

        const targetElements = [];

        if (splitSections) {
            targetElements.push({type: 'header', kind: 'items', label: 'Items', count: itemEntries.length});
            itemEntries.forEach((item) => targetElements.push({type: 'card', item}));
            targetElements.push({type: 'header', kind: 'tms', label: 'TMs', count: tmEntries.length});
            tmEntries.forEach((item) => targetElements.push({type: 'card', item}));
        } else {
            visible.forEach((item) => targetElements.push({type: 'card', item}));
        }

        const elementsList = targetElements.map(target => {
            if (target.type === 'card') {
                const existing = cardMap.get(target.item.name);
                if (existing) {
                    updateCard(existing, target.item);
                    return existing;
                } else {
                    return buildCard(target.item);
                }
            } else {
                // Find existing header or create a new one
                let headerEl = grid.querySelector(`.shop-section-header .shop-section-title.${target.kind}`);
                if (headerEl) {
                    headerEl = headerEl.closest('.shop-section-header');
                    const countEl = headerEl.querySelector('.shop-section-sub');
                    if (countEl) {
                        countEl.textContent = target.count + ' ' + (target.count === 1 ? 'entry' : 'entries');
                    }
                    return headerEl;
                } else {
                    return buildSectionHeader(target.label, target.kind, target.count);
                }
            }
        });

        // Remove obsolete elements
        const activeSet = new Set(elementsList);
        Array.from(grid.childNodes).forEach(node => {
            if (!activeSet.has(node)) {
                node.remove();
            }
        });

        // Order elements in the grid in-place
        elementsList.forEach((el, index) => {
            if (grid.childNodes[index] !== el) {
                grid.insertBefore(el, grid.childNodes[index] || null);
            }
        });

        refreshDetailPanel();
    }

    function buildSectionHeader(label, kind, count) {
        const header = document.createElement('div');
        header.className = 'shop-section-header inline';
        header.innerHTML =
            '<span class="shop-section-title ' + kind + '">' + label + '</span>' +
            '<span class="shop-section-sub">' + count + ' ' +
                (count === 1 ? 'entry' : 'entries') + '</span>';
        return header;
    }

    function countItems(items) {
        const counts = {all: items.length, in_shop: 0, owned: 0};
        items.forEach((i) => {
            if (i.in_shop) counts.in_shop++;
            if ((i.owned_quantity || 0) > 0) counts.owned++;
        });
        return counts;
    }

    function matchesFilters(item) {
        if (state.filter === 'in_shop' && !item.in_shop) return false;
        if (state.filter === 'owned' && (item.owned_quantity || 0) <= 0) return false;
        if (state.category !== 'all' && item.category !== state.category) return false;
        if (state.search) {
            const q = state.search.toLowerCase();
            const hay = [
                item.ui_name, item.name, item.move_type, item.category
            ].filter(Boolean).join(' ').toLowerCase();
            if (!hay.includes(q)) return false;
        }
        return true;
    }

    function cardStateClass(item) {
        const inShop = item.in_shop;
        const owned = (item.owned_quantity || 0) > 0;
        if (inShop && owned) return 'in-shop-and-owned';
        if (inShop) return 'in-shop-only';
        if (owned) return 'owned-only';
        return '';
    }

    // Returns {label, cls} or null. Tag is suppressed when the filter context
    // already communicates everything (e.g. "OWNED" tag in the Bag filter).
    function cardTagFor(item) {
        if (item.is_tm) return {label: 'TM', cls: 'tm'};

        const owned = (item.owned_quantity || 0) > 0;
        const inShop = !!item.in_shop;

        // Build the parts that aren't already implied by the active filter.
        const parts = [];
        let cls = '';
        if (inShop && state.filter !== 'in_shop') {
            parts.push('STOCK');
            cls = owned ? 'in-shop-and-owned' : 'in-shop-only';
        }
        if (owned && state.filter !== 'owned') {
            parts.push('OWNED');
            if (!cls) cls = 'owned-only';
        }
        if (parts.length === 0) return null;  // category pill below carries it
        return {label: parts.join(' · '), cls};
    }

    function updateCard(card, item) {
        // Reset and update class list
        card.className = 'shop-card pokemon-card-equivalent';
        const stateCls = cardStateClass(item);
        if (stateCls) card.classList.add(stateCls);
        if (item.is_tm && (item.owned_quantity || 0) > 0) card.classList.add('owned');
        if (item.in_shop && state.data.cash < (item.price || 0) &&
            (!item.is_tm || (item.owned_quantity || 0) === 0)) {
            card.classList.add('unaffordable');
        }
        if (state.selected === item.name) card.classList.add('selected');

        // Update tag
        let tag = card.querySelector('.shop-card-tag');
        const tagText = cardTagFor(item);
        if (tagText) {
            if (!tag) {
                tag = document.createElement('div');
                card.insertBefore(tag, card.firstChild);
            }
            tag.className = 'shop-card-tag ' + tagText.cls;
            tag.textContent = tagText.label;
        } else if (tag) {
            tag.remove();
        }

        // Update badges
        let badges = card.querySelector('.shop-card-badges');
        if (!badges) {
            badges = document.createElement('div');
            badges.className = 'shop-card-badges';
            const refNode = card.querySelector('.shop-card-tag') ? card.querySelector('.shop-card-tag').nextSibling : card.firstChild;
            card.insertBefore(badges, refNode);
        }
        badges.innerHTML = '';
        if ((item.owned_quantity || 0) > 0) {
            if (item.is_tm) {
                if (state.filter !== 'owned') {
                    const badge = document.createElement('span');
                    badge.className = 'shop-card-badge owned';
                    badge.textContent = 'OWNED';
                    badges.appendChild(badge);
                }
            } else {
                const badge = document.createElement('span');
                badge.className = 'shop-card-badge qty';
                badge.textContent = 'x' + item.owned_quantity;
                badges.appendChild(badge);
            }
        }

        // Update sprite src if different (preserves img DOM instance to avoid flickering)
        const img = card.querySelector('.shop-card-sprite img');
        if (img && img.getAttribute('src') !== (item.image_url || '')) {
            img.src = item.image_url || '';
        }

        // Update name
        const nameEl = card.querySelector('.shop-card-name');
        if (nameEl) {
            nameEl.textContent = item.ui_name || item.name;
        }

        // Update price pill
        let priceEl = card.querySelector('.shop-card-price-pill');
        if (item.in_shop) {
            if (!priceEl) {
                priceEl = document.createElement('div');
                priceEl.className = 'shop-card-price-pill';
                card.appendChild(priceEl);
            }
            priceEl.textContent = formatMoney(item.price || 0) + '¥';
        } else if (priceEl) {
            priceEl.remove();
        }
    }

    function buildCard(item) {
        const card = document.createElement('div');
        card.className = 'shop-card pokemon-card-equivalent';
        card.setAttribute('data-item-name', item.name);
        const stateCls = cardStateClass(item);
        if (stateCls) card.classList.add(stateCls);
        if (item.is_tm && (item.owned_quantity || 0) > 0) card.classList.add('owned');
        if (item.in_shop && state.data.cash < (item.price || 0) &&
            (!item.is_tm || (item.owned_quantity || 0) === 0)) {
            card.classList.add('unaffordable');
        }
        if (state.selected === item.name) card.classList.add('selected');

        // Top-left tag — only show information the filter doesn't already imply.
        const tag = document.createElement('div');
        const tagText = cardTagFor(item);
        if (tagText) {
            tag.className = 'shop-card-tag ' + tagText.cls;
            tag.textContent = tagText.label;
            card.appendChild(tag);
        }

        // Top-right badges. TMs are binary (owned or not), so we surface a
        // word "OWNED" instead of a redundant "x1" quantity — and suppress
        // it entirely in the Bag view where every visible card is owned.
        const badges = document.createElement('div');
        badges.className = 'shop-card-badges';
        if ((item.owned_quantity || 0) > 0) {
            if (item.is_tm) {
                if (state.filter !== 'owned') {
                    const badge = document.createElement('span');
                    badge.className = 'shop-card-badge owned';
                    badge.textContent = 'OWNED';
                    badges.appendChild(badge);
                }
            } else {
                const badge = document.createElement('span');
                badge.className = 'shop-card-badge qty';
                badge.textContent = 'x' + item.owned_quantity;
                badges.appendChild(badge);
            }
        }
        card.appendChild(badges);

        // Sprite
        const spriteWrap = document.createElement('div');
        spriteWrap.className = 'shop-card-sprite';
        const img = document.createElement('img');
        img.decoding = 'sync';
        img.src = item.image_url || '';
        img.alt = item.ui_name || item.name;
        img.onerror = () => { img.style.opacity = '0.25'; };
        spriteWrap.appendChild(img);
        card.appendChild(spriteWrap);

        // Name
        const name = document.createElement('div');
        name.className = 'shop-card-name';
        name.textContent = item.ui_name || item.name;
        card.appendChild(name);

        // Tags row: TM type + category
        const tagsRow = document.createElement('div');
        tagsRow.className = 'shop-card-tags-row';
        if (item.is_tm && item.move_type) {
            const t = document.createElement('span');
            t.className = 'mini-type';
            t.textContent = item.move_type;
            t.style.background = TYPE_COLORS[item.move_type.toLowerCase()] || 'var(--border-main)';
            tagsRow.appendChild(t);
        } else if (CATEGORY_LABELS[item.category]) {
            const c = document.createElement('span');
            c.className = 'cat-pill';
            c.textContent = CATEGORY_LABELS[item.category];
            tagsRow.appendChild(c);
        }
        card.appendChild(tagsRow);

        // Price pill (only if in_shop)
        if (item.in_shop) {
            const price = document.createElement('div');
            price.className = 'shop-card-price-pill';
            price.textContent = formatMoney(item.price || 0) + '¥';
            card.appendChild(price);
        }

        card.addEventListener('click', () => selectItem(item.name));
        return card;
    }

    function formatMoney(n) {
        return (n || 0).toLocaleString();
    }

    // ---------- Detail panel ----------
    function selectItem(name) {
        state.selected = name;
        render();
    }

    function refreshDetailPanel() {
        const placeholder = document.getElementById('detail-placeholder');
        const content = document.getElementById('detail-content');
        const closeBtn = document.getElementById('close-detail');

        if (!state.selected) {
            placeholder.classList.remove('hidden');
            content.classList.add('hidden');
            closeBtn.classList.add('hidden');
            return;
        }

        const item = (state.data.items || []).find((i) => i.name === state.selected);
        if (!item) {
            state.selected = null;
            placeholder.classList.remove('hidden');
            content.classList.add('hidden');
            closeBtn.classList.add('hidden');
            return;
        }

        placeholder.classList.add('hidden');
        content.classList.remove('hidden');
        closeBtn.classList.remove('hidden');
        renderDetail(item);
    }

    function renderDetail(item) {
        document.getElementById('det-id').textContent =
            item.is_tm ? 'TM' : (CATEGORY_LABELS[item.category] || 'ITEM').toUpperCase();
        document.getElementById('det-name').textContent = item.ui_name || item.name;

        const statusRow = document.getElementById('det-status-row');
        statusRow.innerHTML = '';

        if (item.in_shop) {
            const p = document.createElement('span');
            p.className = 'det-pill price';
            p.textContent = formatMoney(item.price || 0) + '¥';
            statusRow.appendChild(p);
        }
        if ((item.owned_quantity || 0) > 0) {
            const o = document.createElement('span');
            o.className = 'det-pill owned';
            o.textContent = item.is_tm ? 'Owned' : 'Owned x' + item.owned_quantity;
            statusRow.appendChild(o);
        }
        if (item.is_tm && item.move_type) {
            const t = document.createElement('span');
            t.className = 'det-pill move-type';
            t.textContent = item.move_type;
            t.style.background = TYPE_COLORS[item.move_type.toLowerCase()] || 'var(--border-main)';
            statusRow.appendChild(t);
        }

        const sprite = document.getElementById('det-sprite');
        sprite.src = item.image_url || '';
        sprite.alt = item.ui_name || item.name;

        const glow = document.getElementById('det-glow');
        const glowColor = item.is_tm && item.move_type
            ? (TYPE_COLORS[item.move_type.toLowerCase()] || '#58a6ff')
            : (item.in_shop ? '#d29922' : '#3fb950');
        glow.style.background = `radial-gradient(circle, ${glowColor}55, transparent 70%)`;

        document.getElementById('det-description').textContent =
            item.description || 'No description available.';

        // Move stats (TMs)
        const moveSection = document.getElementById('det-move-section');
        const moveStats = document.getElementById('det-move-stats');
        moveStats.innerHTML = '';
        if (item.is_tm && (item.move_power || item.move_accuracy || item.move_pp)) {
            moveSection.classList.remove('hidden');
            const rows = [
                {label: 'Power', value: item.move_power, max: 250},
                {label: 'Accuracy', value: item.move_accuracy, max: 100},
                {label: 'PP', value: item.move_pp, max: 40},
            ];
            if (item.move_damage_class) {
                rows.push({label: 'Category', value: item.move_damage_class, max: null});
            }
            rows.forEach((row) => {
                if (row.value === null || row.value === undefined || row.value === '') return;
                moveStats.appendChild(buildStatRow(row));
            });
            setTimeout(() => {
                moveStats.querySelectorAll('.stat-bar-fill').forEach((el) => {
                    el.style.width = el.dataset.targetWidth || '0%';
                });
            }, 50);
        } else {
            moveSection.classList.add('hidden');
        }

        // Actions
        const actions = document.getElementById('det-actions');
        actions.innerHTML = '';
        const hint = document.getElementById('det-hint');
        hint.textContent = '';
        hint.className = 'affordability-hint';

        const ownedQty = item.owned_quantity || 0;
        const blockedTm = item.is_tm && ownedQty > 0;
        const unaffordable = state.data.cash < (item.price || 0);

        if (item.in_shop) {
            const buy = document.createElement('button');
            buy.className = 'det-action-btn buy';
            if (blockedTm) {
                buy.disabled = true;
                buy.innerHTML = '<span>Already Owned</span>';
            } else if (unaffordable) {
                buy.disabled = true;
                buy.innerHTML = '<span>Buy</span><span class="det-action-meta">Not Enough ¥</span>';
            } else {
                buy.innerHTML = '<span>Buy</span><span class="det-action-meta">' + formatMoney(item.price || 0) + '¥</span>';
                buy.onclick = () => onBuy(item);
            }
            actions.appendChild(buy);
        }

        if (ownedQty > 0 && !item.is_tm) {
            const use = document.createElement('button');
            use.className = 'det-action-btn use';
            const label = useLabelFor(item);
            use.innerHTML = '<span>' + label + '</span><span class="det-action-meta">x' + ownedQty + '</span>';
            use.onclick = () => onUse(item);
            actions.appendChild(use);
        }

        if (actions.childElementCount === 0) {
            hint.textContent = 'Nothing to do for this item right now.';
        } else if (item.in_shop && unaffordable && !blockedTm) {
            const shortBy = (item.price || 0) - state.data.cash;
            hint.textContent = `Need ${formatMoney(shortBy)}¥ more to buy.`;
            hint.classList.add('error');
        } else if (item.in_shop && !blockedTm) {
            const after = state.data.cash - (item.price || 0);
            hint.textContent = `Balance after buy: ${formatMoney(after)}¥`;
        }
    }

    function useLabelFor(item) {
        switch (item.category) {
            case 'heal': return 'Use on Active Pokémon';
            case 'fossil': return 'Revive Fossil';
            case 'pokeball': return 'Throw at Wild Pokémon';
            case 'evolution': return 'Evolve a Pokémon';
            default: return 'Give to a Pokémon';
        }
    }

    function buildStatRow({label, value, max}) {
        const row = document.createElement('div');
        row.className = 'stat-item';
        const labelEl = document.createElement('div');
        labelEl.className = 'stat-label';
        const lbl = document.createElement('span');
        lbl.textContent = label;
        const val = document.createElement('span');
        val.className = 'stat-val';
        val.textContent = value;
        labelEl.appendChild(lbl);
        labelEl.appendChild(val);
        row.appendChild(labelEl);

        if (max !== null) {
            const bg = document.createElement('div');
            bg.className = 'stat-bar-bg';
            const fill = document.createElement('div');
            fill.className = 'stat-bar-fill';
            const numVal = typeof value === 'number' ? value : 0;
            const pct = Math.max(0, Math.min(100, (numVal / max) * 100));
            fill.dataset.targetWidth = pct + '%';
            bg.appendChild(fill);
            row.appendChild(bg);
        }
        return row;
    }

    // ---------- Actions ----------
    function onBuy(item) {
        if (!bridge) return;
        bridge.buy(item.name, !!item.is_tm, function (result) {
            if (!result) return;
            showToast(result.message || (result.ok ? 'Purchased!' : 'Purchase failed.'), !result.ok);
        });
    }

    function onUse(item) {
        if (!bridge) return;
        bridge.useItem(item.name, function (result) {
            if (!result) return;
            if (result.message) showToast(result.message, !result.ok);
        });
    }

    function onReroll() {
        if (!bridge) return;
        bridge.reroll(function (result) {
            if (!result) return;
            showToast(result.message || (result.ok ? 'Stock rerolled!' : 'Reroll failed.'), !result.ok);
        });
    }

    function showToast(message, isError) {
        if (!message) return;
        const toast = document.getElementById('toast');
        toast.textContent = message;
        toast.classList.toggle('error', !!isError);
        toast.classList.add('visible');
        clearTimeout(toast._timer);
        toast._timer = setTimeout(() => toast.classList.remove('visible'), 2400);
    }

    // ---------- UI plumbing ----------
    function bindUI() {
        document.querySelectorAll('.nav-item[data-filter]').forEach((btn) => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.nav-item[data-filter]').forEach((b) =>
                    b.classList.remove('active'));
                btn.classList.add('active');
                state.filter = btn.dataset.filter;
                render();
            });
        });

        document.querySelectorAll('.nav-item[data-category]').forEach((btn) => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.nav-item[data-category]').forEach((b) =>
                    b.classList.remove('active'));
                btn.classList.add('active');
                state.category = btn.dataset.category;
                render();
            });
        });

        const searchInput = document.getElementById('shop-search');
        const clearBtn = document.getElementById('clear-search');
        searchInput.addEventListener('input', (e) => {
            state.search = e.target.value.trim();
            clearBtn.classList.toggle('hidden', !state.search);
            render();
        });
        clearBtn.addEventListener('click', () => {
            searchInput.value = '';
            state.search = '';
            clearBtn.classList.add('hidden');
            render();
        });

        document.getElementById('reroll-btn').addEventListener('click', openRerollConfirm);
        document.getElementById('confirm-cancel').addEventListener('click', closeConfirm);
        document.getElementById('confirm-modal').addEventListener('click', (e) => {
            if (e.target.classList.contains('confirm-backdrop')) closeConfirm();
        });
        document.getElementById('confirm-ok').addEventListener('click', () => {
            closeConfirm();
            onReroll();
        });

        document.getElementById('close-detail').addEventListener('click', () => {
            state.selected = null;
            render();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const modal = document.getElementById('confirm-modal');
                if (!modal.classList.contains('hidden')) {
                    closeConfirm();
                } else if (state.selected) {
                    state.selected = null;
                    render();
                }
            } else if (e.key === '/' && document.activeElement !== searchInput) {
                e.preventDefault();
                searchInput.focus();
            } else if (e.key === 'Enter') {
                const modal = document.getElementById('confirm-modal');
                if (!modal.classList.contains('hidden')) {
                    const ok = document.getElementById('confirm-ok');
                    if (!ok.disabled) ok.click();
                }
            }
        });
    }

    function openRerollConfirm() {
        if (!state.data) return;
        const cost = state.data.reroll_cost || 0;
        const after = (state.data.cash || 0) - cost;
        const insufficient = after < 0;

        document.getElementById('confirm-cost').textContent = formatMoney(cost) + '¥';
        const balance = document.getElementById('confirm-balance');
        document.getElementById('confirm-balance-value').textContent = formatMoney(after) + '¥';
        balance.classList.toggle('insufficient', insufficient);

        const okBtn = document.getElementById('confirm-ok');
        okBtn.disabled = insufficient;
        okBtn.textContent = insufficient ? 'Not Enough ¥' : 'Confirm Reroll';

        document.getElementById('confirm-modal').classList.remove('hidden');
    }

    function closeConfirm() {
        document.getElementById('confirm-modal').classList.add('hidden');
    }

    // Nav switcher
    function bindNavSwitcher() {
        const trigger = document.getElementById('nav-trigger');
        const menu = document.getElementById('nav-menu');

        function openMenu() {
            menu.classList.remove('hidden');
            trigger.setAttribute('aria-expanded', 'true');
        }
        function closeMenu() {
            menu.classList.add('hidden');
            trigger.setAttribute('aria-expanded', 'false');
        }

        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            menu.classList.contains('hidden') ? openMenu() : closeMenu();
        });
        document.addEventListener('click', (e) => {
            if (!menu.classList.contains('hidden') &&
                !menu.contains(e.target) && e.target !== trigger) {
                closeMenu();
            }
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !menu.classList.contains('hidden')) closeMenu();
        });
        menu.querySelectorAll('.nav-menu-item[data-screen]').forEach((item) => {
            item.addEventListener('click', () => {
                const screen = item.dataset.screen;
                closeMenu();
                if (screen === 'items') return;
                if (!bridge) return;
                if (screen === 'ankidex' && bridge.openAnkidex) bridge.openAnkidex();
            });
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        bindUI();
        bindNavSwitcher();
        initChannel(() => {});
    });
})();
