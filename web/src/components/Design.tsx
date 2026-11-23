import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';

const paths = {
  home: 'M3 10 12 3l9 7M5 9v12h14V9M9 21v-7h6v7',
  map: 'm3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2ZM9 3v16M15 5v16',
  route: 'M5 18h5a5 5 0 0 0 0-10H8m0 0 3-3M8 8l3 3M5 18v.01M19 5v.01',
  compare: 'M4 21h16M6 17V9h3v8M11 17V3h3v14M16 17v-6h3v6',
  lab: 'M9 3h6M10 3v7L4 20q0 1 2 1h12q2 0 2-1l-6-10V3M8 14h8',
  drivers: 'M16 21H3v-3c0-5 13-5 13 0ZM9.5 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M18 4a3 3 0 0 1 0 6M19 14q3 1 3 4v3',
  pin: 'M12 22S4 14 4 9a8 8 0 1 1 16 0c0 5-8 13-8 13ZM12 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  arrow: 'M4 12h16m-6-6 6 6-6 6', check: 'm5 12 4 4 10-10', close: 'm6 6 12 12M6 18 18 6',
  focus: 'M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5M8 12h8M12 8v8',
  layers: 'm12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 17l10 5 10-5',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l4 2',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 11v6M12 7v.1',
  settings: 'M4 6h16M4 12h16M4 18h16M8 3v6M16 9v6M10 15v6',
};
export type IconName = keyof typeof paths;
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg className="ui-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
export function BrandMark() {
  return <svg width="42" height="42" viewBox="0 0 44 44" fill="none" aria-hidden="true"><path d="M4 32C13 14 21 35 38 21M5 39c12-13 25-4 34-14" stroke="#2F7C7B" strokeWidth="2" strokeLinecap="round"/><path d="M22 4a8 8 0 0 0-8 8c0 6 8 14 8 14s8-8 8-14a8 8 0 0 0-8-8Z" fill="#C26346"/><circle cx="22" cy="12" r="3" fill="#F8F4E8"/></svg>;
}
export function Tip({ text }: { text: string }) {
  return <span className="tooltip"><button type="button" className="tip-trigger" aria-label={text}><Icon name="info" size={15} /></button><span role="tooltip">{text}</span></span>;
}

type Confirm = (message: string) => Promise<boolean>;
const ConfirmContext = createContext<Confirm>(async message => window.confirm(message));
export const useConfirm = () => useContext(ConfirmContext);
export function ConfirmationProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const answer = useRef<((value: boolean) => void) | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const previous = useRef<HTMLElement | null>(null);
  const settle = (value: boolean) => { dialog.current?.close(); answer.current?.(value); answer.current = null; setMessage(null); previous.current?.focus(); };
  useEffect(() => { if (message) dialog.current?.showModal(); }, [message]);
  useEffect(() => () => { answer.current?.(false); }, []);
  const confirm: Confirm = text => {
    if (answer.current) return Promise.resolve(false);
    previous.current = document.activeElement as HTMLElement;
    return new Promise(resolve => { answer.current = resolve; setMessage(text); });
  };
  return <ConfirmContext.Provider value={confirm}>{children}<dialog ref={dialog} className="confirm-dialog" aria-labelledby="confirm-title" aria-describedby="confirm-copy" onCancel={event => { event.preventDefault(); settle(false); }}>
    <span className="dialog-symbol"><Icon name="layers" size={26}/></span><p className="eyebrow">Keep your plan intentional</p><h2 id="confirm-title">Confirm this change</h2><p id="confirm-copy">{message}</p><div className="actions"><button className="button secondary" autoFocus onClick={() => settle(false)}>Keep current plan</button><button className="button primary" data-confirm onClick={() => settle(true)}>Confirm change <Icon name="arrow" size={17}/></button></div>
  </dialog></ConfirmContext.Provider>;
}
