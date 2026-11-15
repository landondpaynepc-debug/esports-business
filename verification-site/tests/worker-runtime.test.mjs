import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {Miniflare} from 'miniflare';

// Exercise the real Workers fetch implementation, rather than replacing it in Node.
// Outbound requests are intercepted; these tests never use credentials or real members.
const source = await readFile(new URL('../lib/verification.mjs', import.meta.url), 'utf8');
const wrapper = `
export default {async fetch(request, env) {
  const begin = await start(new Request(SITE_URL), env);
  const state = new URL(begin.headers.get('Location')).searchParams.get('state');
  const cookie = begin.headers.get('Set-Cookie').split(';')[0];
  const response = await callback(new Request(SITE_URL + '/auth/discord/callback?code=test-code&state=' + state,
    {headers:{Cookie:cookie}}), env);
  const resultCookie = response.headers.get('Set-Cookie').match(/__Host-esports-result=([^; ,]+)/)[1];
  return Response.json(await unsign(resultCookie, env.DISCORD_CLIENT_SECRET, 'result'));
}};`;

for (const redirects of [false, true]) {
  test(redirects ? 'Workers refuses redirected Discord requests' : 'Workers completes verification and sends its log', async()=>{
    const requests = [];
    const runtime = new Miniflare({
      modulesRoot:process.cwd(), compatibilityDate:'2026-05-15',
      modules:[
        {type:'ESModule',path:resolve('tests/runtime-entry.mjs'),contents:
          "import {start, callback, SITE_URL, unsign} from '../lib/verification.mjs';" + wrapper},
        {type:'ESModule',path:resolve('lib/verification.mjs'),contents:source},
      ],
      bindings:{DISCORD_CLIENT_SECRET:'runtime-test-secret',DISCORD_BOT_TOKEN:'runtime-test-token'},
      outboundService:async request=>{
        const url = new URL(request.url); requests.push({host:url.hostname,path:url.pathname,method:request.method});
        assert.equal(url.hostname,'discord.com');
        if(url.pathname.endsWith('/oauth2/token')) {
          if(redirects) return new Response(null,{status:302,headers:{Location:'https://untrusted.invalid/collect'}});
          return Response.json({access_token:'runtime-test-access',scope:'identify'});
        }
        if(url.pathname.endsWith('/users/@me')) return Response.json({id:'1152730210907725834'});
        if(url.pathname.endsWith('/members/1152730210907725834')) return Response.json({roles:['1564362600874254368']});
        if(request.method==='DELETE') return new Response(null,{status:204});
        if(url.pathname.endsWith('/messages')) return Response.json({id:'log'});
        if(url.pathname.endsWith('/revoke')) return new Response(null,{status:200});
        throw Error('Unexpected test request');
      },
    });
    try {
      const response = await runtime.dispatchFetch('https://local.test/');
      const outcome = await response.json();
      assert.equal(outcome.status,redirects?'error':'success');
      assert.equal(requests.filter(r=>r.method==='DELETE').length,redirects?0:1);
      assert.equal(requests.filter(r=>r.path.endsWith('/messages')).length,redirects?0:1);
      assert.ok(requests.some(r=>r.path.endsWith('/oauth2/token')));
      assert.ok(requests.every(r=>r.host==='discord.com'));
    } finally {await runtime.dispose();}
  });
}
