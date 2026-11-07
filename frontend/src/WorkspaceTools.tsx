import { useMemo, useState } from "react";

type Role = "owner" | "manager" | "employee" | "customer";
type Notice = { id: number; title: string; detail: string; kind: "approval" | "info" | "warning" };

const roleLabels: Record<Role, string> = {
  owner: "مدیر کل", manager: "مدیر فروشگاه", employee: "کارمند", customer: "مشتری",
};
const searchIndex = [
  { title: "فروش و صندوق", detail: "فاکتورها، پرداخت‌ها و شیفت صندوق", roles: ["owner", "manager", "employee"] },
  { title: "موجودی و انبار", detail: "کالاها، گردش موجودی و هشدار کمبود", roles: ["owner", "manager", "employee"] },
  { title: "کاربران و دسترسی‌ها", detail: "اعضا، نقش‌ها و محدوده شعب", roles: ["owner"] },
  { title: "گزارش‌های مالی", detail: "فروش، هزینه و عملکرد شعب", roles: ["owner", "manager"] },
  { title: "باشگاه مشتریان", detail: "امتیاز، کوپن و پاداش‌ها", roles: ["owner", "manager", "customer"] },
  { title: "سوابق خرید", detail: "رسیدها و سفارش‌های قبلی", roles: ["customer"] },
  { title: "شیفت و وظایف", detail: "برنامه کاری و کارهای روزانه", roles: ["manager", "employee"] },
];

const initialNotices: Notice[] = [
  { id: 1, title: "درخواست خرید شعبه مرکزی", detail: "نیازمند بررسی مدیر مجاز · نمونه", kind: "approval" },
  { id: 2, title: "موجودی کالای پرفروش کم است", detail: "هشدار عملیاتی نمایشی · نمونه", kind: "warning" },
  { id: 3, title: "گزارش پایان روز آماده است", detail: "گزارش نمونه برای پیش‌نمایش", kind: "info" },
];

export default function WorkspaceTools({ role }: { role: Role }) {
  const [query, setQuery] = useState("");
  const [notices, setNotices] = useState(initialNotices);
  const [showAllNotices, setShowAllNotices] = useState(false);
  const [visibleWidgets, setVisibleWidgets] = useState(["metrics", "approvals", "activity"]);
  const [showCustomize, setShowCustomize] = useState(false);
  const [reviewed, setReviewed] = useState<number[]>([]);

  const results = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return [];
    return searchIndex.filter(item =>
      item.roles.includes(role) &&
      (item.title.toLocaleLowerCase().includes(normalized) || item.detail.toLocaleLowerCase().includes(normalized))
    );
  }, [query, role]);

  const approvalCount = notices.filter(item => item.kind === "approval" && !reviewed.includes(item.id)).length;
  const widgetOptions = [
    { id: "metrics", label: "کارت‌های شاخص" },
    { id: "approvals", label: "مرکز تأییدها" },
    { id: "activity", label: "اعلان‌ها و فعالیت‌ها" },
  ];

  function toggleWidget(id: string) {
    setVisibleWidgets(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]);
  }

  return <section className="workspace-tools" aria-label="ابزارهای فضای کاری">
    <div className="workspace-toolbar">
      <div className="workspace-search">
        <label htmlFor="workspace-global-search">جست‌وجوی سراسری</label>
        <span aria-hidden="true">⌕</span>
        <input id="workspace-global-search" value={query} onChange={event => setQuery(event.target.value)} placeholder="جست‌وجوی بخش‌ها و ابزارهای مجاز..." />
        {query.trim() && <button type="button" onClick={() => setQuery("")} aria-label="پاک کردن جست‌وجو">×</button>}
        {query.trim() && <div className="workspace-search-results" role="status">
          {results.length ? results.map(item => <div key={item.title}><b>{item.title}</b><small>{item.detail}</small></div>) : <p>نتیجه‌ای در بخش‌های نمایشی این نقش پیدا نشد.</p>}
        </div>}
      </div>
      <button className="workspace-customize-button" type="button" onClick={() => setShowCustomize(value => !value)} aria-expanded={showCustomize}>⚙ شخصی‌سازی داشبورد</button>
    </div>

    {showCustomize && <div className="workspace-customize-panel">
      <div><b>نمایش کارت‌های داشبورد</b><small>تنظیمات فقط در همین پیش‌نمایش و تا زمان باز بودن صفحه نگهداری می‌شود.</small></div>
      {widgetOptions.map(item => <label key={item.id}><input type="checkbox" checked={visibleWidgets.includes(item.id)} onChange={() => toggleWidget(item.id)} />{item.label}</label>)}
    </div>}

    <div className="workspace-quick-panels">
      {visibleWidgets.includes("approvals") && role !== "customer" && <article className="workspace-tool-card">
        <div className="workspace-tool-card-heading"><div><b>مرکز تأییدها</b><small>گردش بررسی نمونه، بدون اجرای عملیات واقعی</small></div><span>{approvalCount} مورد</span></div>
        {notices.filter(item => item.kind === "approval").map(item => <div className="workspace-approval" key={item.id}><span><b>{item.title}</b><small>{reviewed.includes(item.id) ? "در این پیش‌نمایش بررسی‌شده" : item.detail}</small></span><button type="button" disabled={reviewed.includes(item.id)} onClick={() => setReviewed(current => [...current, item.id])}>{reviewed.includes(item.id) ? "بررسی شد" : "علامت‌گذاری بررسی"}</button></div>)}
        {!notices.some(item => item.kind === "approval") && <p className="workspace-empty">درخواست تأیید نمونه‌ای وجود ندارد.</p>}
      </article>}

      {visibleWidgets.includes("activity") && <article className="workspace-tool-card">
        <div className="workspace-tool-card-heading"><div><b>اعلان‌ها و وضعیت‌ها</b><small>اطلاع‌رسانی نمایشی برای {roleLabels[role]}</small></div><button type="button" onClick={() => setShowAllNotices(value => !value)}>{showAllNotices ? "نمایش کمتر" : "مشاهده همه"}</button></div>
        {(showAllNotices ? notices : notices.slice(0, 2)).map(item => <div className="workspace-notice" key={item.id}><i className={item.kind} /><span><b>{item.title}</b><small>{item.detail}</small></span><button type="button" aria-label={`حذف اعلان ${item.title} از پیش‌نمایش`} onClick={() => setNotices(current => current.filter(notice => notice.id !== item.id))}>×</button></div>)}
        {!notices.length && <p className="workspace-empty">اعلانی برای نمایش وجود ندارد.</p>}
      </article>}
    </div>
    <p className="workspace-tools-footnote">جست‌وجو، اعلان‌ها، تأییدها و شخصی‌سازی در این مرحله محلی و نمایشی هستند؛ مجوز نهایی و ثبت تغییرات باید توسط API و سرور انجام شود.</p>
  </section>;
}
