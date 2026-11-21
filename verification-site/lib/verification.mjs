// Credentials and Discord access tokens stay on the server, never in logs or cookies.
export const SITE_URL = 'https://esports-business-verification.stellarbutterfly2.chatgpt.site';
export const GUILD = '1254579248237379604';
export const ROLE = '1564362600874254368';
export const LOG_CHANNEL = '1564364557693091951';
export const DASHBOARD = `https://discord.com/channels/${GUILD}/1564325646761467956`;
export const CLIENT_ID = '1569262699140096170';
const API = 'https://discord.com/api/v10';
const FLOW = '__Host-esports-flow', RESULT = '__Host-esports-result';
const encoder = new TextEncoder();
const b64 = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
const unb64 = value => Uint8Array.from(atob(value.replaceAll('-', '+').replaceAll('_', '/')), c => c.charCodeAt(0));
const random = () => b64(crypto.getRandomValues(new Uint8Array(32)));
const cookie = (name, value, age) => `${name}=${value}; Path=/; Max-Age=${age}; HttpOnly; Secure; SameSite=Lax`;
const readCookie = (request, name) => (request.headers.get('Cookie') || '').split('; ').find(v => v.startsWith(`${name}=`))?.slice(name.length + 1);
export const configured = env => Boolean(env.DISCORD_CLIENT_SECRET && env.DISCORD_BOT_TOKEN);
async function key(secret) {
  return crypto.subtle.importKey('raw', encoder.encode(`esports-verification-v1:${secret}`), {name:'HMAC', hash:'SHA-256'}, false, ['sign', 'verify']);
}
export async function sign(data, secret) {
  const body = b64(encoder.encode(JSON.stringify(data)));
  return `${body}.${b64(await crypto.subtle.sign('HMAC', await key(secret), encoder.encode(body)))}`;
}
export async function unsign(value, secret, kind) {
  if (!secret || !value || value.length > 4096) return null;
  try {
    const [body, signature, extra] = value.split('.');
    if (extra || !await crypto.subtle.verify('HMAC', await key(secret), unb64(signature), encoder.encode(body))) return null;
    const data = JSON.parse(new TextDecoder().decode(unb64(body)));
    return data.kind === kind && Number.isFinite(data.expires) && data.expires > Date.now() ? data : null;
  } catch { return null; }
}
function redirect(path, cookies = []) {
  const headers = new Headers({Location: path.startsWith('https://discord.com/oauth2/authorize?') ? path : `${SITE_URL}${path}`, 'Cache-Control':'no-store', 'Referrer-Policy':'no-referrer'});
  for (const value of cookies) headers.append('Set-Cookie', value);
  return new Response(null, {status:303, headers});
}
export async function start(request, env) {
  if (!configured(env)) return redirect('/?status=unavailable');
  const state = random(), verifier = random();
  const challenge = b64(await crypto.subtle.digest('SHA-256', encoder.encode(verifier)));
  const flow = await sign({kind:'flow', state, verifier, expires:Date.now() + 600_000}, env.DISCORD_CLIENT_SECRET);
  const url = new URL('https://discord.com/oauth2/authorize');
  url.search = new URLSearchParams({client_id:CLIENT_ID, response_type:'code', scope:'identify',
    redirect_uri:`${SITE_URL}/auth/discord/callback`, state, code_challenge:challenge, code_challenge_method:'S256', prompt:'consent'}).toString();
  return redirect(url.href, [cookie(FLOW, flow, 600), cookie(RESULT, '', 0)]);
}
async function finish(env, status, message) {
  const result = await sign({kind:'result', status, message, expires:Date.now() + 300_000}, env.DISCORD_CLIENT_SECRET);
  return redirect('/verified', [cookie(FLOW, '', 0), cookie(RESULT, result, 300)]);
}
async function api(fetcher, path, init = {}) {
  const headers = new Headers(init.headers);
  headers.set('User-Agent', 'DiscordBot (https://github.com/landondpaynepc-debug/esports-business, 1.0)');
  // Workers supports manual/follow only. Manual also keeps credentials from following redirects.
  const response = await fetcher(`${API}${path}`, {...init, headers, signal:AbortSignal.timeout(12000), redirect:'manual'});
  if (!response.ok) console.error('discord_request_failed', {endpoint:path.replace(/\d+/g, ':id'), status:response.status});
  return response;
}
export async function callback(request, env, fetcher = fetch) {
  if (!configured(env)) return redirect('/?status=unavailable');
  const url = new URL(request.url);
  const flow = await unsign(readCookie(request, FLOW), env.DISCORD_CLIENT_SECRET, 'flow');
  if (!flow || !url.searchParams.get('state') || flow.state !== url.searchParams.get('state') ||
      (url.searchParams.has('iss') && url.searchParams.get('iss') !== 'https://discord.com'))
    return finish(env, 'error', 'This verification link has expired or does not match your browser. Please start again.');
  if (url.searchParams.has('error')) return finish(env, 'error', 'Discord sign-in was cancelled. No roles were changed.');
  const code = url.searchParams.get('code');
  if (!code || code.length > 2048) return finish(env, 'error', 'Discord did not return a valid sign-in code. Please try again.');
  let accessToken;
  let stage = 'token_exchange';
  try {
    const tokenResponse = await api(fetcher, '/oauth2/token', {method:'POST', body:new URLSearchParams({
      client_id:CLIENT_ID, client_secret:env.DISCORD_CLIENT_SECRET, grant_type:'authorization_code',
      code, code_verifier:flow.verifier, redirect_uri:`${SITE_URL}/auth/discord/callback`})});
    if (!tokenResponse.ok) return finish(env, 'error', 'Discord sign-in could not be completed. Please start again.');
    const token = await tokenResponse.json();
    accessToken = token.access_token;
    if (typeof accessToken !== 'string' || !token.scope?.split(' ').includes('identify')) throw new Error('invalid-token');
    stage = 'identity_lookup';
    const identity = await api(fetcher, '/users/@me', {headers:{Authorization:`Bearer ${accessToken}`}});
    if (!identity.ok) throw new Error('identity-unavailable');
    const user = await identity.json();
    if (!/^\d{17,20}$/.test(user.id) || user.bot) throw new Error('invalid-identity');
    stage = 'membership_lookup';
    const botHeaders = {Authorization:`Bot ${env.DISCORD_BOT_TOKEN}`};
    const memberResponse = await api(fetcher, `/guilds/${GUILD}/members/${user.id}`, {headers:botHeaders});
    if (memberResponse.status === 404) return finish(env, 'error', 'This Discord account is not in Fish Community Hub. Join the server or sign in with the correct account.');
    if (!memberResponse.ok) throw new Error('membership-unavailable');
    const member = await memberResponse.json();
    if (!Array.isArray(member.roles)) throw new Error('invalid-membership');
    if (!member.roles.includes(ROLE)) return finish(env, 'success', 'You already have access. Your unverified role is not assigned.');
    stage = 'role_update';
    const removed = await api(fetcher, `/guilds/${GUILD}/members/${user.id}/roles/${ROLE}`, {
      method:'DELETE', headers:{...botHeaders, 'X-Audit-Log-Reason':'Completed%20official%20Discord%20sign-in%20verification'}});
    if (!removed.ok) return finish(env, 'error', 'Your account was confirmed, but the bot could not update your role. Please contact server staff.');
    try {
      const logged = await api(fetcher, `/channels/${LOG_CHANNEL}/messages`, {method:'POST',
        headers:{...botHeaders, 'Content-Type':'application/json'}, body:JSON.stringify({
          allowed_mentions:{parse:[]}, embeds:[{title:'Member Verified', description:`<@${user.id}> completed Discord sign-in.`,
            fields:[{name:'Member ID', value:user.id}, {name:'Role removed', value:`<@&${ROLE}>`}], timestamp:new Date().toISOString()}]})});
      if (!logged.ok) console.error('verification_log_failed', logged.status);
    } catch { console.error('verification_log_failed'); }
    return finish(env, 'success', 'You’re verified! Your unverified role has been removed. Welcome to Fish Community Hub.');
  } catch (error) {
    // Log only fixed stage names and exception types, never URLs, bodies, codes, or secrets.
    console.error('verification_failed', {stage, type:error instanceof Error ? error.name : 'UnknownError'});
    return finish(env, 'error', 'Verification could not be completed. Please try again shortly or contact server staff.');
  } finally {
    if (accessToken) {
      try { await api(fetcher, '/oauth2/token/revoke', {method:'POST', body:new URLSearchParams({
        client_id:CLIENT_ID, client_secret:env.DISCORD_CLIENT_SECRET, token:accessToken, token_type_hint:'access_token'})}); }
      catch { /* Never log tokens or make verification depend on revocation availability. */ }
    }
  }
}
export function result(request, env) {
  return unsign(readCookie(request, RESULT), env.DISCORD_CLIENT_SECRET, 'result');
}
