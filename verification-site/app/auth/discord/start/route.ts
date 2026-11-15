import { env } from 'cloudflare:workers';
import { start } from '../../../../lib/verification.mjs';
export function GET(request:Request) { return start(request, env); }
