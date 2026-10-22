import { expect, test } from '@playwright/test';
const member={id:'c4ba5f4d-f224-4071-b8c0-b88491989f4c',name:'Ava',email:'ava@example.com',email_verified:true};
test('browser login, refresh, account menu, and logout', async ({ page }) => {
  let signedIn=false;
  await page.route('http://localhost:8000/api/v1/auth/**', async route => {
    const path=new URL(route.request().url()).pathname;
    const headers={'Access-Control-Allow-Origin':'http://localhost:5173','Access-Control-Allow-Credentials':'true','Access-Control-Allow-Headers':'Content-Type, X-Trace-Client'};
    if(route.request().method()==='OPTIONS') return route.fulfill({status:204,headers});
    if(path.endsWith('/login')) {
      expect(route.request().headers()['x-trace-client']).toBe('web');
      signedIn=true;
      return route.fulfill({json:member,headers});
    }
    if(path.endsWith('/logout')) {signedIn=false;return route.fulfill({status:204,headers});}
    return route.fulfill({status:signedIn?200:401,json:signedIn?member:{detail:'Not signed in'},headers});
  });
  await page.goto('/app');
  await expect(page.getByRole('heading',{name:'Sign in to Trace'})).toBeVisible();
  await page.getByLabel('Email address').fill('ava@example.com');
  await page.getByLabel('Password',{exact:true}).fill('password-for-tests');
  await page.getByRole('button',{name:/^Sign in/}).click();
  await expect(page.getByRole('heading',{name:'Welcome, Ava.'})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading',{name:'Welcome, Ava.'})).toBeVisible();
  await page.getByRole('link',{name:'My account',exact:true}).click();
  await expect(page.getByText('ava@example.com')).toBeVisible();
  await page.getByRole('button',{name:/Ava/}).click();
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Sign in to Trace'})).toBeVisible();
});
test('mobile login fits the viewport and provider URLs use backend navigation',async ({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.route('http://localhost:8000/api/v1/auth/me',route=>route.fulfill({status:401,json:{detail:'Not signed in'}}));
  await page.goto('/login');
  await expect(page.getByRole('heading',{name:'Sign in to Trace'})).toBeVisible();
  await expect(page.getByRole('link',{name:'Google',exact:true})).toHaveAttribute('href','http://localhost:8000/api/v1/auth/oauth/google/login');
  await expect(page.getByRole('link',{name:'GitHub',exact:true})).toHaveAttribute('href','http://localhost:8000/api/v1/auth/oauth/github/login');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
