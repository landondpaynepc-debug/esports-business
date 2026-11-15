declare namespace Cloudflare {
  interface Env {
    DISCORD_CLIENT_SECRET?: string;
    DISCORD_BOT_TOKEN?: string;
    DB?: D1Database;
    BUCKET?: R2Bucket;
  }
}
