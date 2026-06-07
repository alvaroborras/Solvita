import { ReactNode } from 'react';

interface LayoutProps {
  header: ReactNode;
  main: ReactNode;
  sidebar: ReactNode;
  footer: ReactNode;
  showFooter?: boolean;
}

export default function Layout({ header, main, sidebar, footer, showFooter = false }: LayoutProps) {
  return (
    <div className="layout">
      <div className="layout__backdrop" aria-hidden="true" />
      <header className="layout__header">{header}</header>
      <main className="layout__main">{main}</main>
      <aside className="layout__sidebar layout__sidebar--prominent-scrollbar">{sidebar}</aside>
      <footer className={`layout__footer ${showFooter ? 'layout__footer--visible' : ''}`}>
        {footer}
      </footer>

      <style>{`
        .layout {
          display: grid;
          grid-template-rows: auto minmax(0, 1fr) auto;
          grid-template-columns: minmax(0, 1fr) 380px;
          grid-template-areas:
            "header header"
            "main sidebar"
            "footer footer";
          min-height: 100vh;
          width: 100%;
          gap: 0;
          background: var(--color-bg-primary);
          position: relative;
          overflow: hidden;
        }
        .layout__backdrop {
          position: absolute;
          inset: 0;
          background:
            radial-gradient(circle at top left, rgba(40, 131, 255, 0.18), transparent 34%),
            radial-gradient(circle at 78% 18%, rgba(83, 208, 168, 0.16), transparent 26%),
            linear-gradient(180deg, rgba(255,255,255,0.02), transparent 28%);
          pointer-events: none;
          z-index: 0;
        }
        .layout__header {
          grid-area: header;
          position: relative;
          z-index: 2;
          padding: var(--space-xl) var(--space-2xl) var(--space-lg);
        }
        .layout__main {
          grid-area: main;
          position: relative;
          z-index: 1;
          overflow-y: auto;
          padding: 0 var(--space-2xl) var(--space-2xl);
        }
        .layout__sidebar {
          grid-area: sidebar;
          position: relative;
          z-index: 1;
          border-left: 1px solid var(--color-border-subtle);
          background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
          overflow-y: auto;
          overflow-x: hidden;
          padding: 0 var(--space-xl) var(--space-2xl);
        }
        .layout__sidebar--prominent-scrollbar {
          scrollbar-gutter: stable;
          scrollbar-width: auto;
          scrollbar-color: rgba(157, 176, 199, 0.72) rgba(255, 255, 255, 0.06);
        }
        .layout__sidebar--prominent-scrollbar::-webkit-scrollbar {
          width: 12px;
        }
        .layout__sidebar--prominent-scrollbar::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.04);
          border-radius: 999px;
        }
        .layout__sidebar--prominent-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(157, 176, 199, 0.72);
          border-radius: 999px;
          border: 2px solid rgba(7, 16, 25, 0.35);
        }
        .layout__sidebar--prominent-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(238, 246, 255, 0.82);
        }
        .layout__footer {
          grid-area: footer;
          border-top: 1px solid var(--color-border-subtle);
          background: var(--color-bg-glass);
          backdrop-filter: blur(8px);
          max-height: 0;
          overflow: hidden;
          transition: max-height var(--transition-normal), padding var(--transition-normal);
        }
        .layout__footer--visible {
          max-height: 120px;
          padding: var(--space-sm) 0;
        }
        @media (max-width: 1180px) {
          .layout {
            grid-template-columns: 1fr;
            grid-template-areas:
              "header"
              "main"
              "sidebar"
              "footer";
          }
          .layout__header {
            padding: var(--space-lg);
          }
          .layout__main {
            padding: 0 var(--space-lg) var(--space-lg);
          }
          .layout__sidebar {
            border-left: none;
            border-top: 1px solid var(--color-border-subtle);
            padding: var(--space-lg);
          }
        }
      `}</style>
    </div>
  );
}
