import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { KinetixLogo } from '../../components/KinetixLogo';
import './landing.css';

const features = [
  {
    number: '01',
    label: 'TRAINING RECORD',
    title: 'The work,\nmade visible.',
    body: 'Log sessions and compare working sets. Follow observed strength changes grounded in your recorded training.',
    kind: 'strength',
    href: '/workouts',
  },
  {
    number: '02',
    label: 'NUTRITION JOURNAL',
    title: 'Details that\nadd up.',
    body: 'Record foods by grams, review intake against your targets, and see trends across the days you logged.',
    kind: 'nutrition',
    href: '/nutrition',
  },
  {
    number: '03',
    label: 'REPORTS / PLANS',
    title: 'A plan with\na point of view.',
    body: 'Explore frozen reports and seven-day plan versions. You decide whether an accepted version becomes active.',
    kind: 'planning',
    href: '/plans',
  },
  {
    number: '04',
    label: 'COACH / YOU DECIDE',
    title: 'Guidance.\nNot autopilot.',
    body: 'Your coach can use logged training and nutrition context. Proposed changes wait for your confirmation.',
    kind: 'coach',
    href: '/login',
  },
];

const steps = [
  { number: '01', title: 'Record', detail: 'Log the training and nutrition that happened.' },
  { number: '02', title: 'Review', detail: 'See your recorded history in reports and observed trends.' },
  { number: '03', title: 'Plan', detail: 'Inspect a seven-day version before choosing to accept it.' },
  { number: '04', title: 'Decide', detail: 'Confirm coach proposals only when they make sense to you.' },
];

export default function LandingPage() {
  const rootRef = useRef<HTMLElement>(null);

  useEffect(() => {
    let cancelled = false;
    let cleanup: (() => void) | undefined;
    void (async () => {
      try {
        const [{ gsap }, { ScrollTrigger }] = await Promise.all([import('gsap'), import('gsap/ScrollTrigger')]);
        if (cancelled || !rootRef.current) return;
        gsap.registerPlugin(ScrollTrigger);
        const root = rootRef.current;
        const media = gsap.matchMedia(root);
        const context = gsap.context(() => {
          media.add('(prefers-reduced-motion: no-preference)', () => {
            const intro = gsap.timeline({ defaults: { ease: 'power3.out' } });
            intro
              .fromTo('.hero-overline', { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: 0.5 })
              .fromTo('.hero-title-line', { yPercent: 110 }, { yPercent: 0, duration: 0.9, stagger: 0.1 }, '-=0.16')
              .fromTo('.hero-description, .hero-actions, .hero-scroll-cue', { autoAlpha: 0, y: 18 }, { autoAlpha: 1, y: 0, duration: 0.55, stagger: 0.08 }, '-=0.3')
              .fromTo('.hero-scene-wrap', { autoAlpha: 0, scale: 0.94, y: 24 }, { autoAlpha: 1, scale: 1, y: 0, duration: 1 }, '-=0.6')
              .fromTo('.hero-stamp', { autoAlpha: 0, scale: 0.7, rotate: -18 }, { autoAlpha: 1, scale: 1, rotate: 9, duration: 0.7, ease: 'back.out(1.6)' }, '-=0.45');

            gsap.to('.hero-lifter', {
              y: -28,
              ease: 'none',
              scrollTrigger: { trigger: '.landing-hero', start: 'top top', end: 'bottom top', scrub: 1 },
            });
            gsap.to('.hero-halo', {
              scale: 1.16,
              rotate: 24,
              ease: 'none',
              scrollTrigger: { trigger: '.landing-hero', start: 'top top', end: 'bottom top', scrub: 1 },
            });
            gsap.to('.landing-reading-progress', {
              scaleX: 1,
              ease: 'none',
              scrollTrigger: { trigger: root, start: 'top top', end: 'bottom bottom', scrub: 0.25 },
            });
            gsap.to('.landing-ticker__track', {
              xPercent: -10,
              ease: 'none',
              scrollTrigger: { trigger: '.landing-ticker', start: 'top bottom', end: 'bottom top', scrub: 1 },
            });

            gsap.utils.toArray<HTMLElement>('.landing-reveal').forEach((element, index) => {
              const direction = element.classList.contains('feature-card') ? (index % 2 === 0 ? 24 : -24) : 0;
              gsap.fromTo(element, {
                autoAlpha: 0,
                y: 30,
                x: direction,
              }, {
                autoAlpha: 1,
                y: 0,
                x: 0,
                duration: 0.7,
                ease: 'power3.out',
                scrollTrigger: { trigger: element, start: 'top 91%', toggleActions: 'play none none reverse' },
              });
            });
            gsap.fromTo('.method-step__rule', { scaleX: 0 }, {
              scaleX: 1,
              transformOrigin: 'left center',
              duration: 0.65,
              stagger: 0.12,
              ease: 'power2.out',
              scrollTrigger: { trigger: '.method-steps', start: 'top 78%', toggleActions: 'play none none reverse' },
            });
            gsap.fromTo('.hero-halo__ring', { strokeDashoffset: 80 }, {
              strokeDashoffset: 0,
              ease: 'none',
              scrollTrigger: { trigger: '.landing-hero', start: 'top top', end: 'bottom top', scrub: 1 },
            });

            const scene = root.querySelector<HTMLElement>('.hero-scene-wrap');
            const art = root.querySelector<SVGElement>('.hero-scene');
            if (scene && art && window.matchMedia('(pointer: fine)').matches) {
              const xTo = gsap.quickTo(art, 'x', { duration: 0.8, ease: 'power3.out' });
              const yTo = gsap.quickTo(art, 'y', { duration: 0.8, ease: 'power3.out' });
              const onMove = (event: PointerEvent) => {
                const rect = scene.getBoundingClientRect();
                xTo(((event.clientX - rect.left) / rect.width - 0.5) * 12);
                yTo(((event.clientY - rect.top) / rect.height - 0.5) * 12);
              };
              const onLeave = () => { xTo(0); yTo(0); };
              scene.addEventListener('pointermove', onMove);
              scene.addEventListener('pointerleave', onLeave);
              return () => {
                scene.removeEventListener('pointermove', onMove);
                scene.removeEventListener('pointerleave', onLeave);
              };
            }
          });
        }, root);
        cleanup = () => { media.revert(); context.revert(); };
      } catch {
        cleanup?.();
      }
    })();
    return () => { cancelled = true; cleanup?.(); };
  }, []);

  return (
    <main ref={rootRef} id="main-content" className="landing-page">
      <div className="landing-reading-progress" aria-hidden="true" />
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="hero-frame"><span>ATHLETE / 01</span><span>TRAINING INTELLIGENCE</span></div>
        <div className="landing-hero__inner">
          <div className="landing-hero__copy">
            <p className="landing-eyebrow hero-overline"><span /> BUILT FOR ATHLETES</p>
            <h1 id="landing-title" className="landing-display"><span className="hero-title-mask"><span className="hero-title-line">Train with</span></span><span className="hero-title-mask"><span className="hero-title-line">intent.</span></span><span className="hero-title-mask"><span className="hero-title-line hero-title-line--accent">Know your</span></span><span className="hero-title-mask"><span className="hero-title-line hero-title-line--accent">progress.</span></span></h1>
            <p className="landing-lede hero-description">Your training. Your nutrition. Your decisions.<br />One athlete-owned record.</p>
            <div className="landing-actions hero-actions">
              <Link className="landing-button landing-button--primary" to="/register">Create account <span aria-hidden="true">↗</span></Link>
              <Link className="landing-button landing-button--secondary" to="/login">Log in</Link>
            </div>
            <a className="landing-scroll-cue hero-scroll-cue" href="#features"><span className="landing-scroll-cue__line" />SCROLL TO EXPLORE</a>
          </div>
          <div className="hero-scene-wrap" role="img" aria-label="Original illustration of an athlete lifting a barbell inside a training rack">
            <div className="hero-halo" aria-hidden="true" />
            <div className="hero-scene-wrap__top"><KinetixLogo aria-hidden="true" /><span>YOUR TRAINING / YOUR RECORD</span></div>
            <svg className="hero-scene" viewBox="0 0 700 560" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
              <defs>
                <radialGradient id="hero-atmosphere"><stop stopColor="#00f0ff" stopOpacity=".2" /><stop offset=".7" stopColor="#00f0ff" stopOpacity=".035" /><stop offset="1" stopColor="#00f0ff" stopOpacity="0" /></radialGradient>
                <linearGradient id="hero-ground" x1="0" y1="0" x2="1" y2="0"><stop stopColor="#00f0ff" stopOpacity="0" /><stop offset=".5" stopColor="#00f0ff" stopOpacity=".58" /><stop offset="1" stopColor="#00f0ff" stopOpacity="0" /></linearGradient>
                <filter id="hero-blur"><feGaussianBlur stdDeviation="32" /></filter>
              </defs>
              <ellipse cx="351" cy="326" rx="230" ry="202" fill="url(#hero-atmosphere)" />
              <circle className="hero-halo__ring" cx="351" cy="282" r="180" fill="none" stroke="#00f0ff" strokeOpacity=".22" strokeWidth="1" strokeDasharray="2 10" />
              <circle cx="351" cy="282" r="136" fill="none" stroke="#f4f7f8" strokeOpacity=".11" />
              <ellipse cx="351" cy="478" rx="188" ry="20" fill="#00f0ff" fillOpacity=".1" filter="url(#hero-blur)" />
              <g className="rack-lines" fill="none" stroke="#a9bac4" strokeOpacity=".4" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M122 60v418M578 60v418M108 72h28M564 72h28M122 164h49M529 164h49M122 464h456" />
                <path d="M164 170v224M536 170v224" strokeOpacity=".15" strokeWidth="2" />
              </g>
              <path d="M85 490h530" stroke="url(#hero-ground)" strokeWidth="2" />
              <g className="hero-lifter" stroke="#e7f1f4" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="352" cy="133" r="21" fill="#e7f1f4" stroke="none" />
                <path d="M342 158c-18 18-26 45-23 71l8 62 50 8 20-59-9-50c-3-17-18-31-35-32l-11 0Z" fill="#121922" stroke="#dbe6e9" strokeWidth="5" />
                <path d="m328 194-49 54-34 8m145-57 46 54 35 5" fill="none" strokeWidth="13" />
                <path d="m245 256-17-14m246 16 15-14" fill="none" stroke="#00f0ff" strokeWidth="6" />
                <path d="m340 299-44 63-17 69m86-124 41 61 12 65" fill="none" strokeWidth="16" />
                <path d="m279 434-22 8m164-10 23 8" fill="none" stroke="#00f0ff" strokeWidth="8" />
                <path d="M214 256h272" stroke="#e7f1f4" strokeWidth="7" />
                <path d="M207 237v38m-9-30v22m301-30v38m9-30v22" stroke="#00f0ff" strokeWidth="8" />
                <path d="M326 179c17 10 39 11 57 2" fill="none" stroke="#00f0ff" strokeWidth="3" />
              </g>
              <g fill="#00f0ff"><circle cx="186" cy="112" r="2.5" /><circle cx="514" cy="101" r="2.5" /><circle cx="152" cy="343" r="2" /><circle cx="549" cy="355" r="2" /></g>
            </svg>
            <div className="hero-stamp" aria-hidden="true"><KinetixLogo /><span>YOUR<br />PACE<br />YOUR<br />PROOF</span></div>
            <div className="hero-scene-wrap__foot"><span>01 / KEEP SHOWING UP</span><span>THE ATHLETE IS THE POINT</span></div>
          </div>
        </div>
        <div className="hero-floor" aria-hidden="true" />
        <div className="hero-frame hero-frame--bottom"><span>OBSERVED, NOT ASSUMED</span><span>SCROLL TO MOVE ↓</span></div>
      </section>

      <div className="landing-ticker" aria-label="Train with intent. Keep your receipts. Own your next move.">
        <div className="landing-ticker__track" aria-hidden="true">TRAIN WITH INTENT <span>✳</span> KEEP YOUR RECEIPTS <span>✳</span> OWN YOUR NEXT MOVE <span>✳</span> TRAIN WITH INTENT <span>✳</span> KEEP YOUR RECEIPTS <span>✳</span> OWN YOUR NEXT MOVE <span>✳</span></div>
      </div>

      <section id="features" className="landing-features" aria-labelledby="features-title">
        <div className="landing-section-heading landing-reveal">
          <div className="landing-section-heading__meta"><span>02 / THE RECORD</span><span>TRAINING / NUTRITION / DECISIONS</span></div>
          <h2 id="features-title">Make every session<br /><span>count.</span></h2>
          <p>One clear view of the work you do—and the decisions you make next.</p>
        </div>
        <div className="feature-list">
          {features.map((feature) => (
            <article className={`feature-card feature-card--${feature.kind} landing-reveal`} id={`feature-${feature.kind}`} key={feature.number}>
              <div className="feature-card__visual" aria-hidden="true">
                <span className="feature-card__visual-index">{feature.number} / 04</span>
                <div className={`feature-art feature-art--${feature.kind}`}>
                  {feature.kind === 'strength' && <><span className="feature-art__axis" /><span className="feature-art__bar feature-art__bar--one" /><span className="feature-art__bar feature-art__bar--two" /><span className="feature-art__bar feature-art__bar--three" /><span className="feature-art__arc" /></>}
                  {feature.kind === 'nutrition' && <><span className="nutrition-orbit nutrition-orbit--one" /><span className="nutrition-orbit nutrition-orbit--two" /><span className="nutrition-orbit nutrition-orbit--three" /><span className="nutrition-core" /></>}
                  {feature.kind === 'planning' && <><span className="plan-ring plan-ring--one" /><span className="plan-ring plan-ring--two" /><span className="plan-dot" /><span className="plan-tick" /></>}
                  {feature.kind === 'coach' && <><span className="coach-orbit" /><span className="coach-node coach-node--one" /><span className="coach-node coach-node--two" /><span className="coach-node coach-node--three" /><span className="coach-center">K</span></>}
                </div>
                <span className="feature-card__visual-caption">KINETIX / {feature.label}</span>
              </div>
              <div className="feature-card__copy">
                <div className="feature-card__meta"><span>{feature.label}</span><span>{feature.number}</span></div>
                <h3>{feature.title.split('\n').map((line) => <span key={line}>{line}</span>)}</h3>
                <p>{feature.body}</p>
                <Link className="feature-card__link" to={feature.href}>{feature.kind === 'coach' ? 'Meet your coach' : `Explore ${feature.label.toLowerCase()}`} <span aria-hidden="true">↗</span></Link>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section id="method" className="landing-method" aria-labelledby="method-title">
        <div className="landing-method__intro landing-reveal"><p className="landing-eyebrow"><span /> 03 / HOW IT COMES TOGETHER</p><h2 id="method-title">From the log<br />to your <span>next move.</span></h2><p>Your records inform the picture. Your choices shape what happens next.</p></div>
        <ol className="method-steps">
          {steps.map((step) => <li className="method-step landing-reveal" key={step.number}><span className="method-step__number">{step.number}</span><h3>{step.title}</h3><p>{step.detail}</p><span className="method-step__rule" aria-hidden="true" /></li>)}
        </ol>
      </section>

      <section className="landing-principle landing-reveal" aria-labelledby="principle-title">
        <p className="landing-eyebrow"><span /> HUMAN IN THE LOOP</p>
        <h2 id="principle-title">Data can inform.<br /><span>You decide.</span></h2>
        <p>Coach changes stay proposals. Plan versions stay yours to accept. Your training belongs to your record.</p>
        <span className="landing-principle__mark" aria-hidden="true">K</span>
      </section>

      <section className="landing-closer landing-reveal" aria-labelledby="closer-title">
        <div className="landing-closer__top"><span>04 / BEGIN WITH ONE SESSION</span><KinetixLogo className="landing-closer__logo" aria-hidden="true" /></div>
        <h2 id="closer-title">The next rep<br /><span>is yours.</span></h2>
        <div className="landing-closer__bottom"><p>Start your record. Take it one training day at a time.</p><div className="landing-actions landing-actions--closer"><Link className="landing-button landing-button--primary" to="/register">Create account <span aria-hidden="true">↗</span></Link><Link className="landing-button landing-button--secondary" to="/login">Log in</Link></div></div>
      </section>
    </main>
  );
}
