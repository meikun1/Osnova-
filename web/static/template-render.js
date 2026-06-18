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

  /** Найти стикер по ref в массивах main/top. */
  function findSticker(ref, stickers) {
    if (!ref) return null;
    const list = (stickers && stickers.main) || stickers || [];
    let s = list.find((x) => x.ref === ref);
    if (s) return s;
    if (stickers && stickers.top) {
      s = stickers.top.find((x) => x.ref === ref);
      if (s) return s;
    }
    return null;
  }

  function renderSticker(ref, stickers, sizePx) {
    const sticker = findSticker(ref, stickers);
    const size = sizePx || 64;
    if (!sticker) {
      const def = el('div', { style: { fontSize: size + 'px', lineHeight: '1' } }, '🦆');
      return def;
    }
    if (sticker.type === 'lottie' && sticker.url) {
      // lottie-player должен быть подключён в panel.html (CDN @lottiefiles)
      const lp = document.createElement('lottie-player');
      lp.setAttribute('src', sticker.url);
      lp.setAttribute('background', 'transparent');
      lp.setAttribute('speed', '1');
      lp.setAttribute('loop', '');
      lp.setAttribute('autoplay', '');
      lp.style.width = size + 'px';
      lp.style.height = size + 'px';
      return lp;
    }
    if (sticker.type === 'image' && sticker.url) {
      const img = el('img', { src: sticker.url, alt: '' });
      img.style.width = size + 'px';
      img.style.height = size + 'px';
      img.style.objectFit = 'contain';
      return img;
    }
    // emoji по умолчанию
    return el('div', { style: { fontSize: size + 'px', lineHeight: '1' } }, sticker.emoji || '🦆');
  }

  function renderImage(image, stickers) {
    if (!image || !image.type) return null;
    const anim = ANIM_KEYS.has(image.anim) ? image.anim : 'none';
    const node = el('div', {
      class: 'tr-image',
      style: {
        animation: anim === 'none' ? 'none' : `${anim} 1.8s ease-out infinite`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      },
    });
    if (image.type === 'sticker') {
      node.appendChild(renderSticker(image.ref, stickers, 80));
    } else if (image.type === 'upload' && image.url) {
      const img = el('img', { src: image.url, alt: '' });
      img.style.maxWidth = '160px';
      img.style.maxHeight = '160px';
      img.style.objectFit = 'contain';
      node.appendChild(img);
    } else {
      node.appendChild(el('div', { style: { fontSize: '64px' } }, '🦆'));
    }
    return node;
  }

  function renderTopSticker(topSticker, stickers) {
    if (!topSticker || !topSticker.ref) return null;
    const anim = ANIM_KEYS.has(topSticker.anim) ? topSticker.anim : 'float';
    const wrap = el('div', {
      class: 'tr-top',
      style: {
        position: 'absolute', top: '8px', right: '12px', zIndex: '3',
        pointerEvents: 'none',
        animation: anim === 'none' ? 'none' : `${anim} 2.4s ease-in-out infinite`,
      },
    });
    wrap.appendChild(renderSticker(topSticker.ref, stickers, 40));
    return wrap;
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
        position: 'relative',
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

    const top = renderTopSticker(step.topSticker, opts.stickers);
    if (top) root.appendChild(top);

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
