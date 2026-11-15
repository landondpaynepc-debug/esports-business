import test from 'node:test';
import assert from 'node:assert/strict';
import {start, callback, result, sign, unsign, SITE_URL, ROLE, GUILD, LOG_CHANNEL} from '../lib/verification.mjs';
const env = {DISCORD_CLIENT_SECRET:'test-only-client-secret', DISCORD_BOT_TOKEN:'test-only-bot-token'};
const userID = '1152730210907725834';
const json = (data, status=200) => new Response(JSON.stringify(data), {status});
async function flow() {
  const response = await start(new Request(SITE_URL), env);
  const url = new URL(response.headers.get('Location'));
  const cookie = response.headers.getSetCookie()[0].split(';')[0];
  return {response, url, request:new Request(`${SITE_URL}/auth/discord/callback?state=${url.searchParams.get('state')}&code=example-code`, {headers:{Cookie:cookie}})};
}
async function outcome(response) {
  const cookie = response.headers.getSetCookie().find(c=>c.startsWith('__Host-esports-result=')).split(';')[0];
  return result(new Request(SITE_URL, {headers:{Cookie:cookie}}), env);
}
test('sign-in requests identify only, binds browser state, and includes PKCE', async()=>{
  const {response,url} = await flow();
  assert.equal(url.origin,'https://discord.com'); assert.equal(url.searchParams.get('scope'),'identify');
  assert.equal(url.searchParams.get('code_challenge_method'),'S256');
  assert.equal(url.searchParams.get('redirect_uri'),`${SITE_URL}/auth/discord/callback`);
  assert.match(response.headers.get('Set-Cookie'),/HttpOnly; Secure; SameSite=Lax/);
});
test('missing credentials do not start OAuth',async()=>{
  const response=await start(new Request(SITE_URL),{});
  assert.equal(response.headers.get('Location'),`${SITE_URL}/?status=unavailable`);
});
test('tampered and expired signed sessions are rejected',async()=>{
  const signed=await sign({kind:'flow',expires:Date.now()+60000},env.DISCORD_CLIENT_SECRET);
  assert.equal(await unsign(signed+'x',env.DISCORD_CLIENT_SECRET,'flow'),null);
  const expired=await sign({kind:'flow',expires:Date.now()-1},env.DISCORD_CLIENT_SECRET);
  assert.equal(await unsign(expired,env.DISCORD_CLIENT_SECRET,'flow'),null);
  assert.equal(await unsign(signed,env.DISCORD_CLIENT_SECRET,'result'),null);
});
test('missing or mismatched state never calls Discord',async()=>{
  for (const request of [new Request(`${SITE_URL}/auth/discord/callback?code=example`),
      new Request((await flow()).request.url.replace(/state=[^&]+/,'state=wrong'),{headers:(await flow()).request.headers})]) {
    let calls=0; const response=await callback(request,env,async()=>{calls++;throw Error();});
    assert.equal(calls,0);assert.equal((await outcome(response)).status,'error');
  }
});
for (const scenario of ['success','not-member','role-failure','already-verified','token-failure']) {
  test(`verification ${scenario}`,async()=>{
    const {request}=await flow(); const calls=[];
    const fetcher=async(url,init)=>{
      calls.push({url,init});
      if(url.endsWith('/oauth2/token'))return json({access_token:'ephemeral-test-token',scope:'identify'},scenario==='token-failure'?400:200);
      if(url.endsWith('/users/@me'))return json({id:userID});
      if(url.endsWith(`/members/${userID}`))return json({roles:scenario==='already-verified'?[]:[ROLE,'other-role']},scenario==='not-member'?404:200);
      if(init.method==='DELETE')return new Response(null,{status:scenario==='role-failure'?403:204});
      if(url.endsWith('/messages'))return json({id:'log'});
      if(url.endsWith('/revoke'))return new Response(null,{status:200});
      throw Error('unexpected URL');
    };
    const response=await callback(request,env,fetcher);const final=await outcome(response);
    const deletes=calls.filter(c=>c.init.method==='DELETE'), logs=calls.filter(c=>c.url.endsWith('/messages'));
    assert.equal(final.status,['success','already-verified'].includes(scenario)?'success':'error');
    assert.equal(deletes.length,['success','role-failure'].includes(scenario)?1:0);
    assert.equal(logs.length,scenario==='success'?1:0);
    if(deletes.length)assert.equal(deletes[0].url,`https://discord.com/api/v10/guilds/${GUILD}/members/${userID}/roles/${ROLE}`);
    if(logs.length){assert.equal(logs[0].url,`https://discord.com/api/v10/channels/${LOG_CHANNEL}/messages`);assert.deepEqual(JSON.parse(logs[0].init.body).allowed_mentions,{parse:[]});}
    assert.ok(!response.headers.get('Set-Cookie').includes('ephemeral-test-token'));
    if(scenario!=='token-failure')assert.ok(calls.some(c=>c.url.endsWith('/revoke')));
  });
}
