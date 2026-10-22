export interface User {
  id: string;
  email: string;
  name: string;
  email_verified: boolean;
}
export interface Credentials { email: string; password: string }
export interface Registration extends Credentials { name: string }
export interface Message { message: string }
export type Provider = 'google' | 'github';
