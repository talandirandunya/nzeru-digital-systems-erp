UI Verification Checklist

Contrast checks (in-browser):
- Open Erpis.html and navigate to Dashboard.
- Use DevTools > Rendering > Emulate vision deficiencies or use Lighthouse contrast audit.
- Verify text contrast ratios for:
  - Body text vs background (aim >= 4.5:1 for normal text).
  - KPI values and labels against `T.surface`/`T.bg`.
  - Primary buttons (`Btn` primary) text vs background (aim >= 4.5:1).
  - Small UI elements (badges, table headers) for at least 3:1 when appropriate.
- If contrast fails, adjust `T.text`, `T.muted`, or accent colors in `erpis-ui.jsx`.

Mobile layout verification:
- In Chrome DevTools toggle device toolbar (Ctrl+Shift+M).
- Test common widths: 360px (small phone), 412px (medium), 768px (tablet).
- Verify:
  - KPI grid stacks to 2 or 1 columns without overflow.
  - Buttons and touch targets are at least 44x44px tappable.
  - PriorityStack cards wrap and remain readable.
  - Tables become horizontally scrollable and do not break layout.
- Make notes of components that require responsive CSS (e.g., change `gridTemplateColumns`).

Manual interaction checks:
- Keyboard: Tab through buttons and links; ensure focus visible.
- Hover states: verify hover contrast and not essential for access.
- Screen reader: verify semantic order of headings and that buttons have labels.

Quick fixes and next steps:
- Add CSS breakpoints or helper `stack` utility to convert `gridTemplateColumns` to `1fr` on small screens.
- Centralize color tokens in `erpis-ui.jsx` (`T` and `ACCENT_COLORS`) and tweak values there.
- Consider adding a small visual test page that lists all components for quick QA.

Run these checks locally and report any failing components with screenshots and viewport sizes.
