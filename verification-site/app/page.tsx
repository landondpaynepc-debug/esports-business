import { env } from 'cloudflare:workers';
import VerificationPage from '../components/verification-page';
import { configured } from '../lib/verification.mjs';
export const dynamic = 'force-dynamic';
export default function Home() { return <VerificationPage ready={configured(env)} />; }
