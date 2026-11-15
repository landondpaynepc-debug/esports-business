import { env } from 'cloudflare:workers';
import { headers } from 'next/headers';
import { configured, result } from '../../lib/verification.mjs';
import VerificationPage from '../../components/verification-page';
export const dynamic = 'force-dynamic';
export default async function Verified() {
  const request = new Request('https://local/verified', {headers:await headers()});
  const outcome = await result(request, env);
  return <VerificationPage ready={configured(env)} outcome={outcome || {status:'error', message:'Your verification session has expired. Please start again.'}} />;
}
