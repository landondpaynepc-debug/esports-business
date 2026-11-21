export const defaultBanner = 'https://raw.githubusercontent.com/landondpaynepc-debug/esports-business/main/assets/banner.jpg?v=8c85038a6d9c2234';
export async function bannerUrl() {
  try {
    const response = await fetch('https://raw.githubusercontent.com/landondpaynepc-debug/esports-business/main/branding.json',
      {signal:AbortSignal.timeout(4000), cache:'no-store'});
    if (!response.ok) return defaultBanner;
    const data = await response.json() as {banner_url?:string};
    const url = new URL(data.banner_url || '');
    if (url.protocol === 'https:' && url.hostname === 'raw.githubusercontent.com' &&
        url.pathname.startsWith('/landondpaynepc-debug/esports-business/')) return url.href;
  } catch { /* Retain the last shipped banner during a temporary GitHub outage. */ }
  return defaultBanner;
}
