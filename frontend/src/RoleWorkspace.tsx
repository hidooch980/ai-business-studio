import { useState } from "react";

type Role = "owner" | "manager" | "employee" | "customer";
type RoleConfig = {
  label: string;
  workspace: string;
  nav: string[];
  metrics: [string, string, string, string][];
  actions: string[];
  activityTitle: string;
  activity: [string, string][];
  focusTitle: string;
  focus: string;
};

const roleConfig: Record<Role, RoleConfig> = {
  owner: {
    label: "مدیر کل",
    workspace: "فضای کاری مدیر کل",
    nav: ["نمای کلی", "شعب و عملکرد", "مدیریت کاربران", "مالی و گزارش‌ها", "تأییدها"],
    metrics: [["فروش امروز", "۱۲,۸۵۰,۰۰۰", "تومان", "نمونه نمایشی"], ["شعب فعال", "۴", "شعبه", "نمونه نمایشی"], ["کاربران", "۲۸", "نفر", "نمونه نمایشی"], ["در انتظار تأیید", "۳", "مورد", "نمونه نمایشی"]],
    actions: ["بررسی عملکرد شعب", "دعوت کاربر جدید", "بررسی درخواست‌های تأیید", "مشاهده گزارش مالی"],
    activityTitle: "رویدادهای مدیریتی",
    activity: [["درخواست خرید شعبه مرکزی", "در انتظار بررسی"], ["افزودن کاربر جدید", "نیازمند دعوت"], ["گزارش پایان روز", "ثبت نمونه"]],
    focusTitle: "نمای کلی کسب‌وکار",
    focus: "مقایسه شعب، روند فروش، وضعیت نقدینگی و تصمیم‌های نیازمند تأیید در یک نمای مرکزی.",
  },
  manager: {
    label: "مدیر فروشگاه",
    workspace: "فضای کاری مدیر فروشگاه",
    nav: ["نمای کلی شعبه", "فروش و صندوق", "موجودی انبار", "کارکنان و شیفت", "خرید و تأییدها"],
    metrics: [["فروش امروز", "۴,۲۵۰,۰۰۰", "تومان", "نمونه نمایشی"], ["صندوق‌های باز", "۲", "صندوق", "نمونه نمایشی"], ["کالای کم‌موجود", "۶", "قلم", "نمونه نمایشی"], ["شیفت فعال", "۵", "نفر", "نمونه نمایشی"]],
    actions: ["مشاهده وضعیت صندوق‌ها", "ثبت درخواست خرید", "برنامه‌ریزی شیفت", "شمارش موجودی"],
    activityTitle: "کارهای نیازمند پیگیری",
    activity: [["تأیید دریافت کالا", "در انتظار بررسی"], ["مغایرت صندوق", "نیازمند بررسی"], ["شیفت عصر", "در حال برنامه‌ریزی"]],
    focusTitle: "کنترل عملیات شعبه",
    focus: "فروش روزانه، موجودی، شیفت کارکنان و درخواست‌های خرید شعبه را از یکجا مدیریت کنید.",
  },
  employee: {
    label: "کارمند",
    workspace: "فضای کاری کارمند",
    nav: ["کارهای من", "صندوق فروش", "جست‌وجوی کالا", "مشتریان", "شیفت من"],
    metrics: [["وظایف امروز", "۵", "وظیفه", "نمونه نمایشی"], ["فروش ثبت‌شده", "۱۸", "فاکتور", "نمونه نمایشی"], ["شیفت امروز", "۸", "ساعت", "نمونه نمایشی"], ["درخواست من", "۱", "مورد", "نمونه نمایشی"]],
    actions: ["شروع فروش جدید", "جست‌وجوی بارکد کالا", "ثبت وظیفه انجام‌شده", "مشاهده برنامه شیفت"],
    activityTitle: "برنامه و وظایف",
    activity: [["چیدمان قفسه نوشیدنی", "تا ساعت ۱۲"], ["کنترل موجودی بخش لبنیات", "تا ساعت ۱۵"], ["تحویل صندوق", "پایان شیفت"]],
    focusTitle: "شروع سریع کارهای روزانه",
    focus: "فروش، جست‌وجوی کالا، وظایف و اطلاعات شیفت در دسترس کارمند قرار می‌گیرد.",
  },
  customer: {
    label: "مشتری",
    workspace: "باشگاه مشتریان",
    nav: ["خانه", "کارت عضویت", "امتیازها و پاداش‌ها", "کوپن‌های من", "سوابق خرید"],
    metrics: [["امتیاز قابل استفاده", "۲,۴۵۰", "امتیاز", "نمونه نمایشی"], ["سطح عضویت", "طلایی", "", "نمونه نمایشی"], ["کوپن فعال", "۳", "کوپن", "نمونه نمایشی"], ["خریدهای ثبت‌شده", "۱۲", "خرید", "نمونه نمایشی"]],
    actions: ["نمایش کارت عضویت", "مشاهده پاداش‌ها", "بررسی کوپن‌های فعال", "پیگیری رسید خرید"],
    activityTitle: "آخرین فعالیت‌های حساب",
    activity: [["دریافت امتیاز خرید", "+۱۸۰ امتیاز"], ["کوپن وفاداری", "تا پایان ماه معتبر"], ["ارتقای سطح عضویت", "سطح طلایی"]],
    focusTitle: "مزایای عضویت شما",
    focus: "کارت دیجیتال، امتیازها، پاداش‌ها، کوپن‌ها و سوابق خرید را در یک فضای ساده ببینید.",
  },
};

const roleOptions: { id: Role; icon: string }[] = [
  { id: "owner", icon: "⌂" },
  { id: "manager", icon: "▦" },
  { id: "employee", icon: "▣" },
  { id: "customer", icon: "♡" },
];

export default function RoleWorkspace({ onHome }: { onHome: () => void }) {
  const [role, setRole] = useState<Role>("owner");
  const [active, setActive] = useState(roleConfig.owner.nav[0]);
  const config = roleConfig[role];
  const pageTitle = active === config.nav[0] ? config.focusTitle : active;

  function changeRole(next: Role) {
    setRole(next);
    setActive(roleConfig[next].nav[0]);
  }

  return <div className="dashboard role-dashboard">
    <aside className="app-sidebar">
      <div className="brand"><span className="brand-mark">✦</span><span>AI Business <b>Studio</b></span></div>
      <div className="workspace-label">{config.workspace}</div>
      <nav>{config.nav.map((item, index) => <button key={item} className={active === item ? "active" : ""} onClick={() => setActive(item)}><span>{["▦", "▣", "▤", "♙", "⌁"][index]}</span>{item}</button>)}</nav>
      <div className="sidebar-bottom"><span className="avatar">{config.label.slice(0, 1)}</span><div><b>{config.label} نمونه</b><small>حساب نمایشی</small></div><button onClick={onHome} aria-label="بازگشت به صفحه اصلی">↪</button></div>
    </aside>
    <main className="dashboard-main">
      <header className="dash-header role-header"><div><small>{config.workspace} / پیش‌نمایش</small><h1>{pageTitle}</h1></div><div className="dash-header-actions"><span className="demo-tag">● محیط نمایشی</span><button className="icon-button" aria-label="اعلان‌ها">♧</button></div></header>
      <div className="role-switcher" aria-label="انتخاب پیش‌نمایش نقش">{roleOptions.map(option => <button key={option.id} className={role === option.id ? "selected" : ""} aria-pressed={role === option.id} onClick={() => changeRole(option.id)}><span>{option.icon}</span>{roleConfig[option.id].label}</button>)}</div>
      <div className="demo-warning">این محیط فقط برای نمایش طراحی نقش‌هاست؛ انتخاب نقش در اینجا ورود یا تغییر سطح دسترسی واقعی ایجاد نمی‌کند و اطلاعات آن نمونه هستند.</div>
      <section className="metric-grid">{config.metrics.map((metric, index) => <article className="metric-card" key={metric[0]}><div className="metric-top"><span>{metric[0]}</span><i>{["↗", "▣", "♙", "!"][index]}</i></div><b className="metric-value">{metric[1]} <small>{metric[2]}</small></b><span className="metric-positive">{metric[3]}</span></article>)}</section>
      <section className="role-content-grid">
        <article className="panel role-focus"><div className="panel-heading"><div><h2>{config.focusTitle}</h2><p>نمای متناسب با نقش انتخاب‌شده</p></div><span className="count-pill">AI</span></div><p className="role-focus-copy">{config.focus}</p><div className="role-action-list">{config.actions.map((action, index) => <button key={action} onClick={() => setActive(config.nav[Math.min(index + 1, config.nav.length - 1)])}><span>{["↗", "＋", "⌕", "✓"][index]}</span>{action}<b>←</b></button>)}</div></article>
        <article className="panel"><div className="panel-heading"><div><h2>{config.activityTitle}</h2><p>موارد نمونه برای پیش‌نمایش</p></div><span className="count-pill">{config.activity.length}</span></div><div className="alert-list role-activity">{config.activity.map((item, index) => <div key={item[0]}><i className={`alert-dot ${["amber", "blue", "red"][index]}`} /><span><b>{item[0]}</b><small>{item[1]}</small></span></div>)}</div></article>
      </section>
      <section className="panel role-bottom-panel"><div className="panel-heading"><div><h2>دسترسی و تجربه کاربری</h2><p>نمایش اصول طراحی در این فضای کاری</p></div></div><div className="role-principles"><span>✓ منوی متناسب با نقش</span><span>✓ نمایش اطلاعات ضروری</span><span>✓ مناسب موبایل و تبلت</span><span>✓ کنترل نهایی دسترسی در سرور</span></div></section>
    </main>
  </div>;
}
