/* template-render.js — общий модуль рендера шага шаблона.
 * Используется и в превью конструктора (web/panel.html → screenBuilder),
 * и (в будущем) в рантайме дочернего бота на /app/<bot_id>.
 *
 * Контракт:
 *   renderStep(step, opts) → HTMLElement
 *     step: { key, title, description, icon, image:{type,ref,anim},
 *             button:{text,action,color,style}, theme:{background,text} }
 *     opts: { onAction?: (action) => void, stickers?: [{ref, emoji}] }
 *
 * Никаких внешних зависимостей. Vanilla DOM.
 */
(function () {
  'use strict';

  const ANIM_KEYS = new Set(['none', 'fade', 'pop', 'float', 'spin', 'slide']);

  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      if (k === 'style' && typeof attrs[k] === 'object') {
        Object.assign(e.style, attrs[k]);
      } else if (k === 'class') {
        e.className = attrs[k];
      } else if (k.startsWith('on') && typeof attrs[k] === 'function') {
        e.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
      } else {
        e.setAttribute(k, attrs[k]);
      }
    }
    if (children) {
      (Array.isArray(children) ? children : [children]).forEach((c) => {
        if (c == null) return;
        if (typeof c === 'string') e.appendChild(document.createTextNode(c));
        else e.appendChild(c);
      });
    }
    return e;
  }

  /** Превратить ссылку на стикер в Emoji (пока заглушка — будут .tgs). */
  function stickerEmoji(ref, stickers) {
    if (!stickers) return '🦆';
    const s = stickers.find((x) => x.ref === ref);
    return s ? s.emoji : '🦆';
  }

  function renderImage(image, stickers) {
    if (!image || !image.type) return null;
    const anim = ANIM_KEYS.has(image.anim) ? image.anim : 'none';
    const node = el('div', {
      class: 'tr-image',
      style: {
        animation: anim === 'none' ? 'none' : `${anim} 1.8s ease-out infinite`,
      },
    });
    if (image.type === 'sticker') {
      node.textContent = stickerEmoji(image.ref, stickers);
      node.style.fontSize = '64px';
      node.style.lineHeight = '1';
    } else if (image.type === 'upload' && image.ref) {
      // Загруженные картинки лежат под /static/uploads/.../<ref>.webp
      const img = el('img', { src: image.ref, alt: '' });
      img.style.maxWidth = '160px';
      img.style.maxHeight = '160px';
      img.style.objectFit = 'contain';
      node.appendChild(img);
    } else {
      node.textContent = '🦆';
      node.style.fontSize = '64px';
    }
    return node;
  }

  function renderButton(btn, onAction) {
    if (!btn || !btn.text) return null;
    const style = btn.style || 'filled';
    const bg = style === 'filled' ? (btn.color || '#2ea6ff') : 'transparent';
    const fg = style === 'filled' ? '#fff' : (btn.color || '#2ea6ff');
    const border = style === 'outline'
      ? `1px solid ${btn.color || '#2ea6ff'}`
      : 'none';
    return el('button', {
      class: 'tr-btn',
      style: {
        background: bg, color: fg, border: border,
        padding: '13px 18px', borderRadius: '12px',
        fontWeight: '700', fontSize: '15px',
        width: '100%', cursor: 'pointer',
        marginTop: 'auto',
      },
      onclick: () => onAction && onAction(btn.action || 'close'),
    }, btn.text);
  }

  /** Главный экспорт. */
  function renderStep(step, opts) {
    opts = opts || {};
    const theme = step.theme || {};
    const root = el('div', {
      class: 'tr-step',
      style: {
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', textAlign: 'center',
        padding: '24px 20px',
        background: theme.background || '#0e161e',
        color: theme.text || '#fff',
        borderRadius: '14px',
        minHeight: '220px',
        gap: '14px',
        fontFamily: '-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
      },
    });

    const img = renderImage(step.image, opts.stickers);
    if (img) root.appendChild(img);

    if (step.icon) {
      const ic = el('div', { class: 'tr-icon', style: {fontSize:'28px',lineHeight:'1'}}, step.icon);
      root.appendChild(ic);
    }
    if (step.title) {
      root.appendChild(el('div', {
        class: 'tr-title',
        style: { fontSize: '20px', fontWeight: '800', lineHeight: '1.2' },
      }, step.title));
    }
    if (step.description) {
      root.appendChild(el('div', {
        class: 'tr-desc',
        style: { fontSize: '13.5px', opacity: '0.85', lineHeight: '1.45',
                 maxWidth: '320px' },
      }, step.description));
    }
    const btn = renderButton(step.button, opts.onAction);
    if (btn) root.appendChild(btn);
    return root;
  }

  // CSS-keyframes для анимаций (вставляется один раз).
  function injectKeyframes() {
    if (document.getElementById('tr-keyframes')) return;
    const style = document.createElement('style');
    style.id = 'tr-keyframes';
    style.textContent = `
      @keyframes fade  { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }
      @keyframes pop   { 0%{transform:scale(.6);opacity:0} 60%{transform:scale(1.1);opacity:1} 100%{transform:scale(1)} }
      @keyframes float { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)} }
      @keyframes spin  { to { transform: rotate(360deg) } }
      @keyframes slide { from{transform:translateX(-16px);opacity:0} to{transform:none;opacity:1} }
    `;
    document.head.appendChild(style);
  }
  injectKeyframes();

  window.TemplateRender = { renderStep };
})();
