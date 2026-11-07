# Retail UX/UI Design System

Status: approved design foundation; the initial four-role frontend preview and local workspace controls are implemented. Production API integration and server-side authorization remain pending.

## Product experience principles

1. Role-first: every signed-in user lands in a workspace matched to the server-authorized role and active branch.
2. Task-first: POS and operational tasks use short, low-friction flows; analytical screens prioritize context and traceability.
3. Honest data: demo, empty, stale, offline, loading and failed states are visibly distinct. Never render invented sales, stock, customer or AI metrics as live data.
4. Consistent shell: shared navigation, typography, spacing, form controls, feedback and accessibility patterns across web and PWA.
5. Responsive by intent: desktop uses persistent navigation and dense tables; tablet uses collapsible navigation; mobile uses compact navigation and task-focused screens.
6. Accessible: keyboard operation, visible focus, semantic labels, sufficient contrast, non-color status cues and reduced-motion support.

## Visual direction

- Brand character: confident, calm, precise and modern—not a trading terminal or a generic template.
- Base surfaces: warm near-white and deep navy; restrained violet for AI-related affordances; teal for positive/confirmed states; amber for attention; red only for destructive/error states.
- Typography: Persian-capable sans-serif with numerals that remain legible in financial tables. Use a consistent type scale and tabular numerals for amounts.
- Components: 8-point spacing rhythm, modest corner radius, subtle borders, restrained shadows, consistent icon family.
- Theme: light and dark themes share semantic tokens; never hard-code colors inside feature components.
- RTL: Persian and Arabic use logical CSS properties and mirrored layout where appropriate; icons with intrinsic direction are mirrored only when semantically correct.

## Semantic design tokens

| Token family | Examples | Purpose |
|---|---|---|
| Surface | canvas, panel, elevated, inverse | Page and component backgrounds |
| Text | primary, secondary, muted, inverse | Text hierarchy |
| Border | subtle, default, strong | Separators and outlines |
| Action | primary, secondary, quiet, destructive | Buttons and links |
| Status | success, warning, danger, info | State communicated with text and icon |
| Data | chart-1 through chart-6 | Consistent data visualization |
| Layout | space-1..space-8, radius-sm/md/lg | Spacing and shape |

Exact color values must be validated for WCAG contrast before implementation.

## Global information architecture

### Public website
- Home
- Product capabilities
- Retail solutions
- Plans and pricing (only when commercial terms are approved)
- Security and privacy
- Help / contact
- Language selector
- Sign in / create account

### Authenticated application
- Overview
- Sales / POS
- Products and catalog
- Inventory and warehouses
- Purchasing and suppliers
- Finance and cash management
- Customers and CRM
- Loyalty and campaigns
- Staff, shifts and tasks
- Reports and insights
- AI recommendations
- Notifications
- Settings and access management

Navigation items are filtered by server-issued permissions, not merely hidden in the client.

## Role workspaces

### Owner / Admin
- Business-wide KPI summary with date range and branch filters.
- Branch comparison, revenue and margin trends, cash position and operational alerts.
- User invitations, role assignment, branch scope, audit trail and security settings.
- Approval inbox for sensitive actions.
- AI recommendations show evidence, confidence, expected impact, expiry and approval state.

### Branch Manager
- Current branch selector (within authorized scope).
- Today's sales, shift status, cash variance, low-stock queue and pending purchase requests.
- Staff attendance, task completion and branch-level reports.
- Approvals limited to explicit permissions and configured thresholds.

### Employee
- Task launcher with POS as the primary action for cashier roles.
- Shift start/end, assigned tasks, product lookup, customer lookup and allowed inventory actions.
- Refunds, discounts, price overrides and stock adjustments require explicit permission and reason capture.
- No access to payroll, cross-branch financials or administrative controls unless separately granted.

### Customer
- Digital membership card / QR, points balance and tier progress.
- Available rewards and coupons with clear eligibility and expiry.
- Receipts, order history, support and consent/privacy controls.
- Customer account identity remains separate from workforce identity.

## Core screen specifications

### Public home
1. Header with brand, product navigation, language and sign-in.
2. Hero with a concise value proposition and primary CTA.
3. Product capability cards for POS, inventory, finance, loyalty and analytics.
4. Role-based product tour with real interface screenshots only after they exist.
5. Security, offline capability and multi-branch explanation.
6. FAQ and footer with privacy, terms and support links.

### Sign-in
- Phone number as primary identifier; verified email as alternate.
- OTP request, six-digit entry, resend countdown, expiry and neutral account-enumeration response.
- Clear loading, invalid-code, expired-code, rate-limited and provider-unavailable states.
- Never display or log production OTP values.

### Admin overview
- Global filters, KPI cards, sales trend, branch comparison, alerts and approvals.
- Every metric shows its period, currency and source/freshness.
- Empty and unavailable states explain what configuration or data is missing.

### POS
- Fast product search and barcode entry, cart, customer attachment and discount permission checks.
- Payment methods: cash, card terminal, online and split tender, only where configured.
- Confirmed receipt state is shown only after backend transaction success.
- Offline mode clearly marks queued transactions and sync state; no false payment success.

### User management
- Search, filters, role, branch scope, account status and last activity.
- Invite / deactivate / revoke sessions / change role with confirmation and audit reason where required.
- Do not expose secrets, OTP material or full sensitive identifiers in lists.

## Reusable component inventory

- AppShell, PublicHeader, Sidebar, MobileNav, BranchSwitcher, LanguageSwitcher, ThemeToggle
- PageHeader, Breadcrumbs, FilterBar, DateRangePicker
- MetricCard, TrendChart, DataTable, Pagination, EmptyState, ErrorState, Skeleton
- StatusBadge, AlertBanner, Toast, ConfirmDialog, ApprovalDrawer
- FormField, PhoneInput, OtpInput, SearchInput, MoneyInput
- PermissionGate (presentation only; backend remains authoritative)
- OfflineStatus, SyncQueueIndicator, DataFreshnessLabel
- RoleWorkspaceCard, UserTable, BranchScopePicker

## Responsive behavior

- Wide desktop: sidebar + content; dense tables with sticky headers.
- Tablet: collapsible sidebar; filters move into a drawer.
- Mobile: one-column cards, compact top bar, bottom navigation for frequent tasks; tables become labelled cards or controlled horizontal scroll.
- POS: prioritize touch targets, product search, cart visibility and payment actions.

## Localization and formatting

- Initial locales: fa-IR, en, ar, tr.
- Locale controls language, direction, date/number formatting and translated labels.
- Currency is configured per tenant/store; never assume one global currency.
- Store timestamps in UTC and render in the configured business timezone.
- Avoid concatenating translated fragments; use complete localized messages.

## Security and privacy UX

- Render only server-authorized navigation and data; every API independently enforces tenant, branch and permission scope.
- OTP verification is authentication, not authorization.
- High-risk operations require step-up and/or approval according to policy.
- Session list, logout-current, logout-all and device/session revocation are discoverable.
- Mask sensitive contact details; collect explicit consent for customer communications.
- Audit-sensitive changes with actor, time, reason and before/after references.

## Definition of done

- All four role workspaces have route maps and permission matrices.
- RTL and LTR layouts pass visual and interaction checks.
- Mobile, tablet and desktop breakpoints are tested.
- Loading, empty, error, offline and stale-data states are implemented.
- Keyboard-only navigation and focus visibility are verified.
- No fabricated live metrics, payment confirmations or AI actions.
- Critical flows have automated component and end-to-end tests.
- Accessibility contrast and labels are checked before release.
