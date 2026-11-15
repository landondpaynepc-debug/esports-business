import { env } from 'cloudflare:workers';
import { callback } from '../../../../lib/verification.mjs';
export function GET(request:Request) { return callback(request, env); }
