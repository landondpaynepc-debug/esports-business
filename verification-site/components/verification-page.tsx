import { bannerUrl } from '../lib/branding';
import { DASHBOARD } from '../lib/verification.mjs';
export default async function VerificationPage({ready, outcome}: {ready:boolean; outcome?:{status:string; message:string}|null}) {
  const banner = await bannerUrl(), success = outcome?.status === 'success';
  return <main className="shell">
    <header><a className="brand" href="/"><span className="brand-mark">FCH</span> FISH COMMUNITY HUB</a><span className="header-label">MEMBER VERIFICATION</span></header>
    <section className="card">
      <img className="banner" src={banner} alt="Fish Community Hub community banner" width="736" height="414" />
      <div className="body"><div className="eyebrow"><span className="dot" /> YOUR NEXT STEP STARTS HERE</div>
        <h1>{success ? 'You’re in.' : outcome ? 'Let’s try that again.' : 'Welcome to the community.'}</h1>
        <p className="intro">{outcome?.message || 'Connect your Discord account to verify your membership and unlock Fish Community Hub.'}</p>
        {!success && <div className="steps"><div><b>01</b><span>Sign in securely<span>Continue on Discord’s official website.</span></span></div><div><b>02</b><span>Get access<span>Your unverified role is removed automatically.</span></span></div></div>}
        {success ? <a className="primary" href={DASHBOARD} target="_top">Open server dashboard</a> : ready ? <a className="primary" href="/auth/discord/start" target="_top">Continue with Discord</a> : <div className="notice" role="status">Verification is being set up. Please check back shortly.</div>}
        <p className="privacy">We only confirm your Discord identity and server membership.<br/>Your password stays with Discord.</p>
      </div></section>
    <footer><span>FISH COMMUNITY HUB</span><a href="https://discord.com/channels/1254579248237379604/1564325660313391316" target="_top">Need help? Contact support</a></footer>
  </main>;
}
