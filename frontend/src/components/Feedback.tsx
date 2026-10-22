import type { ReactNode } from 'react';

export function Feedback({ children, success = false }: { children: ReactNode; success?: boolean }) {
  return <div className={'feedback' + (success ? ' success' : '')} role={success ? 'status' : 'alert'}>{children}</div>;
}
