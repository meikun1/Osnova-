import { useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Copy, Check, RefreshCw } from "lucide-react";

/**
 * Панель модуля 'Прямая ссылка' внутри менеджера ботов.
 *
 * Props:
 *   botId       — id бота из менеджера
 *   apiBase     — базовый URL твоего бэка (например, "")
 *   onBack      — callback на кнопку 'назад'
 *   authHeader  — функция, возвращающая хедер авторизации для админ-ручек
 *                 (по умолчанию — пустой объект, кука пойдёт сама)
 */
export default function DirectLinkPanel({
  botId,
  apiBase = "",
  onBack,
  authHeader = () => ({}),
}) {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const fetchSettings = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${apiBase}/dl/admin/${botId}`, {
        credentials: "include",
        headers: { ...authHeader() },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSettings(await r.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [botId]);

  const toggle = async (enabled) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${apiBase}/dl/admin/${botId}/toggle`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ enabled }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSettings(await r.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const rotate = async () => {
    if (!confirm("Перевыпустить ссылку? Старая перестанет работать."))
      return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${apiBase}/dl/admin/${botId}/rotate`, {
        method: "POST",
        credentials: "include",
        headers: { ...authHeader() },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setSettings(await r.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const copyLink = async () => {
    if (!settings) return;
    try {
      await navigator.clipboard.writeText(settings.startapp_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // молча
    }
  };

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto p-6 text-neutral-500">Загрузка…</div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-6">
      {/* Шапка */}
      <button
        onClick={onBack}
        className="flex items-center gap-2 text-sm text-neutral-500 hover:text-neutral-900 mb-4"
      >
        <ArrowLeft size={16} />
        Назад в настройки
      </button>

      <h1 className="text-2xl font-semibold tracking-tight">Прямая ссылка</h1>
      <p className="text-neutral-600 mt-2 leading-relaxed">
        Раздавайте мини-приложение только тем, у кого есть ваша прямая ссылка.
        Все остальные, кто откроет мини-апп без правильного параметра, будут
        перенаправлены на сторонний ресурс.
      </p>

      {error && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 text-red-700 text-sm px-3 py-2">
          {error}
        </div>
      )}

      {/* Инструкция */}
      <section className="mt-8 rounded-lg border border-neutral-200 bg-neutral-50/60 p-5">
        <h2 className="text-sm font-medium uppercase tracking-wide text-neutral-500">
          Перед включением
        </h2>
        <ol className="mt-3 space-y-3 text-[15px] text-neutral-800 leading-relaxed">
          <li className="flex gap-3">
            <span className="font-mono text-neutral-400 shrink-0">01</span>
            <span>
              В{" "}
              <a
                href="https://t.me/BotFather"
                target="_blank"
                rel="noreferrer"
                className="underline underline-offset-2 hover:no-underline"
              >
                @BotFather
              </a>{" "}
              привяжите к боту ссылку на мини-приложение.{" "}
              {settings?.manual_url && (
                <a
                  href={settings.manual_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 underline underline-offset-2 hover:no-underline"
                >
                  Открыть мануал
                  <ExternalLink size={12} />
                </a>
              )}
            </span>
          </li>
          <li className="flex gap-3">
            <span className="font-mono text-neutral-400 shrink-0">02</span>
            <span>
              Подождите 10–15 минут — Telegram применит изменения не сразу.
            </span>
          </li>
          <li className="flex gap-3">
            <span className="font-mono text-neutral-400 shrink-0">03</span>
            <span>Включите прямую ссылку переключателем ниже.</span>
          </li>
        </ol>
      </section>

      {/* Ссылка */}
      <section className="mt-6">
        <label className="text-sm font-medium text-neutral-700">
          Ваша прямая ссылка
        </label>
        <div className="mt-2 flex gap-2">
          <input
            readOnly
            value={settings?.startapp_url ?? ""}
            className="flex-1 min-w-0 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm font-mono text-neutral-800 focus:outline-none focus:ring-2 focus:ring-neutral-900/10"
            onFocus={(e) => e.target.select()}
          />
          <button
            onClick={copyLink}
            className="inline-flex items-center gap-1.5 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm hover:bg-neutral-50"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? "Скопировано" : "Копировать"}
          </button>
        </div>
        <button
          onClick={rotate}
          disabled={busy}
          className="mt-2 inline-flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-900 disabled:opacity-50"
        >
          <RefreshCw size={12} />
          Перевыпустить (старая ссылка перестанет работать)
        </button>
      </section>

      {/* Переключатель */}
      <section className="mt-8 flex items-center justify-between rounded-lg border border-neutral-200 px-5 py-4">
        <div>
          <div className="font-medium">Прямая ссылка активна</div>
          <div className="text-sm text-neutral-500 mt-0.5">
            {settings?.enabled
              ? "Доступ к мини-приложению только по вашей ссылке."
              : "Сейчас мини-приложение открыто для всех."}
          </div>
        </div>
        <Toggle
          checked={!!settings?.enabled}
          onChange={toggle}
          disabled={busy}
        />
      </section>

      {/* Футер */}
      <p className="mt-6 text-xs text-neutral-500 leading-relaxed">
        При включении этой функции бот перестанет реагировать на команду{" "}
        <code className="font-mono">/start</code>. Пользователи смогут попасть в
        мини-приложение только по прямой ссылке.
      </p>
    </div>
  );
}

function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
        checked ? "bg-neutral-900" : "bg-neutral-300"
      }`}
    >
      <span
        className={`inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
          checked ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
}
