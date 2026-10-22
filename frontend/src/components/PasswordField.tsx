import { useState } from 'react';

export function PasswordField({ id = 'password', label = 'Password', value, onChange, newPassword = false, disabled = false }: {
  id?: string; label?: string; value: string; onChange: (value: string) => void; newPassword?: boolean; disabled?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  return <div className="field"><label htmlFor={id}>{label}</label><div className="password-control">
    <input id={id} name={id} type={visible ? 'text' : 'password'} autoComplete={newPassword ? 'new-password' : 'current-password'}
      value={value} onChange={event => onChange(event.target.value)} required minLength={newPassword ? 12 : 1}
      maxLength={128} disabled={disabled} aria-describedby={newPassword ? id + '-hint' : undefined} />
    <button type="button" className="show-password" aria-label={(visible ? 'Hide ' : 'Show ') + label.toLowerCase()}
      onClick={() => setVisible(previous => !previous)} disabled={disabled}>{visible ? 'Hide' : 'Show'}</button>
  </div>{newPassword && <small id={id + '-hint'}>Use at least 12 characters.</small>}</div>;
}
