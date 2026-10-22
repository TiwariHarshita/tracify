import { Link } from 'react-router-dom';

export function Brand({ to = '/login', inverse = false }: { to?: string; inverse?: boolean }) {
  return <Link className={'brand' + (inverse ? ' inverse' : '')} to={to} aria-label="Trace home">
    <span className="brand-bars" aria-hidden="true"><i /><i /><i /></span>
    trace<span className="brand-dot">.</span>
  </Link>;
}
