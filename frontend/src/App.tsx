import { useState, type FormEvent } from "react";
import RoleWorkspace from "./RoleWorkspace";

type Screen = "home" | "login" | "dashboard";
function Brand() {
  return <div className="brand"><span className="brand-mark">✦</span><span>AI Business <b>Studio</b></span></div>;
}

function Header({ onLogin }: { onLogin: () => void }) {
  return <header className="site-header"><Brand /><nav className="top-links"><a href="#features">امکانات</a><a href="#solutions">راهکارها</a><a href="#security">امنیت</a></nav><div className="header-actions"><span className="language" aria-label="زبان فعلی: فارسی">فارسی</span><button className="button button-ghost" onClick={onLogin}>ورود کاربران</button><button className="button button-primary" onClick={onLogin}>شروع کنید <span>←</span></button></div></header>;
}

function Home({ onLogin, onPreview }: { onLogin: () => void; onPreview: () => void }) {
  return <div className="public-page"><Header onLogin={onLogin} />
    <main>
      <section className="hero container">
        <div className="hero-copy"><div className="eyebrow"><span className="pulse" /> مدیریت یکپارچه، تصمیم‌گیری هوشمند</div><h1>کسب‌وکار خود را<br /><span>هوشمندانه</span> مدیریت کنید.</h1><p className="hero-lead">از فروش و انبار تا مشتریان و گزارش‌های مدیریتی؛ همه‌چیز در یک فضای کاری یکپارچه و ساده.</p><div className="hero-actions"><button className="button button-primary button-large" onClick={onLogin}>ورود به فضای کاری <span>←</span></button><a className="text-link" href="#features">آشنایی با امکانات <span>↓</span></a><button className="text-link preview-link" onClick={onPreview}>پیش‌نمایش داشبورد ↗</button></div><div className="trust-row"><span>✓ چندشعبه‌ای</span><span>✓ نقش‌محور</span><span>✓ آماده کار آفلاین</span></div></div>
        <div className="hero-visual"><div className="visual-glow" /><div className="mock-window"><div className="mock-top"><div className="mock-dots"><i/><i/><i/></div><span>پیش‌نمایش داشبورد</span><span className="mock-live">نمونه نمایشی</span></div><div className="mock-body"><aside className="mock-side"><div className="mini-brand">✦</div><i className="selected">▦</i><i>▤</i><i>◫</i><i>♙</i><i>◷</i></aside><div className="mock-content"><div className="mock-heading"><b>نمای کلی کسب‌وکار</b><small>گزارش نمونه</small></div><div className="mock-kpis"><div><small>فروش امروز</small><b>۱۲,۸۵۰,۰۰۰</b><em>+۱۲٪</em></div><div><small>سفارش‌ها</small><b>۱۲۸</b><em>+۸٪</em></div><div><small>مشتریان</small><b>۸۴۲</b><em>+۵٪</em></div></div><div className="mock-chart"><div className="chart-label"><b>روند فروش</b><small>۷ روز اخیر · نمونه</small></div><div className="bars">{[34,54,43,72,48,86,66,94,58,76,48,88].map((h,i)=><i key={i} style={{height:h+"%"}} />)}</div></div><div className="mock-bottom"><div><b>وضعیت موجودی</b><span className="fake-line"/><span className="fake-line short"/></div><div><b>عملکرد شعب</b><span className="fake-line"/><span className="fake-line short"/></div></div></div></div></div></div>
      </section>
      <section className="feature-section" id="features"><div className="container"><div className="section-heading"><div className="eyebrow">یک پلتفرم، تمام عملیات</div><h2>کنترل کامل فروشگاه، از یکجا</h2><p>ابزارهای موردنیاز تیم شما در یک تجربه منسجم و قابل توسعه.</p></div><div className="feature-grid">{[{icon:"▣",title:"صندوق فروشگاهی",desc:"ثبت سریع فروش، بارکد، پرداخت و مرجوعی."},{icon:"▤",title:"انبار و خرید",desc:"گردش کالا، تأمین‌کنندگان و هشدار موجودی."},{icon:"◈",title:"مالی و حساب‌ها",desc:"صندوق، هزینه‌ها و گزارش‌های مالی."},{icon:"♙",title:"مدیریت مشتریان",desc:"پروفایل، سوابق خرید و ارتباط با مشتری."},{icon:"✧",title:"باشگاه وفاداری",desc:"امتیاز، سطح عضویت، کوپن و کمپین."},{icon:"⌁",title:"هوش تجاری",desc:"تحلیل عملکرد و پیشنهادهای قابل بررسی."}].map(item=><article className="feature-card" key={item.title}><span className="feature-icon">{item.icon}</span><h3>{item.title}</h3><p>{item.desc}</p><span className="card-arrow">←</span></article>)}</div></div></section>
      <section className="roles-section" id="solutions"><div className="container roles-layout"><div><div className="eyebrow">تجربه متناسب با هر نقش</div><h2>هرکس، فضای کاری خودش</h2><p>مدیر کل، مدیر شعبه، کارمند و مشتری؛ هرکدام فقط ابزارها و اطلاعات متناسب با دسترسی خود را می‌بینند.</p></div><div className="role-list">{[["01","مدیر کل","دید جامع بر کسب‌وکار، شعب و عملکرد"],["02","مدیر فروشگاه","کنترل عملیات روزانه و کارکنان"],["03","کارمند","فروش، شیفت و وظایف روزانه"],["04","مشتری","عضویت، امتیازها و رسیدهای خرید"]].map(x=><div className="role-row" key={x[0]}><span>{x[0]}</span><div><b>{x[1]}</b><small>{x[2]}</small></div><i>↙</i></div>)}</div></div></section>
      <section className="security-section" id="security"><div className="container security-card"><div><div className="eyebrow">امنیت از ابتدا</div><h2>دسترسی درست، برای هر کاربر</h2><p>ورود OTP، سطح دسترسی نقش‌محور، محدوده شعب و ثبت رویدادهای حساس در طراحی محصول لحاظ شده‌اند.</p></div><div className="security-points"><span>✓ ورود با شماره موبایل و کد یک‌بارمصرف</span><span>✓ کنترل دسترسی در سمت سرور</span><span>✓ ثبت سوابق عملیات حساس</span></div></div></section>
    </main><footer className="site-footer container"><Brand /><span>© AI Business Studio · مدیریت هوشمند خرده‌فروشی</span><button className="text-link" onClick={onLogin}>ورود کاربران ←</button></footer>
  </div>;
}

function Login({ onBack, onPreview }: { onBack: () => void; onPreview: () => void }) {
  const [phone,setPhone]=useState("");
  const [notice,setNotice]=useState("");
  function submit(e: FormEvent) { e.preventDefault(); setNotice("اتصال سرویس OTP هنوز فعال نشده است. پس از پیکربندی سرویس پیامک و API، ورود واقعی فعال خواهد شد."); }
  return <main className="login-page"><button className="back-link" onClick={onBack}>→ بازگشت به صفحه اصلی</button><section className="login-card"><Brand /><div className="eyebrow">ورود امن به حساب کاربری</div><h1>خوش آمدید</h1><p>برای دریافت کد یک‌بارمصرف، شماره موبایل خود را وارد کنید.</p><form onSubmit={submit}><label htmlFor="phone">شماره موبایل</label><input id="phone" inputMode="tel" autoComplete="tel" placeholder="مثلاً ۰۹۱۲۱۲۳۴۵۶۷" value={phone} onChange={e=>setPhone(e.target.value)} required minLength={8} /><button className="button button-primary button-large full" type="submit">درخواست کد ورود</button></form>{notice && <div className="notice" role="status">{notice}</div>}<button type="button" className="text-link demo-preview" onClick={onPreview}>مشاهده پیش‌نمایش داشبورد ←</button><small className="login-foot">کد ورود فقط از طریق سرویس تأییدشده ارسال می‌شود. هیچ کد آزمایشی یا ثابت برای ورود وجود ندارد.</small></section></main>;
}

function Dashboard({ onHome }: { onHome: () => void }) {
  return <RoleWorkspace onHome={onHome} />;
}

export default function App() {
  const [screen,setScreen]=useState<Screen>("home");
  if(screen==="login") return <Login onBack={()=>setScreen("home")} onPreview={()=>setScreen("dashboard")} />;
  if(screen==="dashboard") return <Dashboard onHome={()=>setScreen("home")} />;
  return <Home onLogin={()=>setScreen("login")} onPreview={()=>setScreen("dashboard")} />;
}
