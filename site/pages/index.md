---
title: Cairn
description: An auditable, queryable benchmark over official EU/NL climate data — every figure traces back to a pinned official source.
hide_title: true
---

```sql sector_headline
select
    max(year) as latest_year,
    count(distinct nace_section) as sections,
    sum(case when year = (select max(year) from cairn.sector_emissions)
        then sector_emissions_mt_co2eq end) as national_total_mt
from cairn.sector_emissions
```

```sql installation_headline
select
    max(year) as latest_year,
    count(distinct case when year = (select max(year) from cairn.installation_emissions)
        then installation_id end) as installations,
    sum(case when year = (select max(year) from cairn.installation_emissions)
        then installation_emissions_t_co2eq end) / 1e6 as verified_total_mt
from cairn.installation_emissions
```

```sql country_headline
select count(distinct country) as countries
from cairn.country_sector_emissions
```

```sql provenance_headline
select
    count(distinct source || '/' || dataset) as datasets,
    count(distinct case when is_pinned then source || '/' || dataset end) as pinned
from cairn.data_provenance
```

<div class="flex flex-wrap items-center gap-2 mb-6">
<a href="https://fabiandemoel.nl" class="inline-flex items-center gap-1.5 rounded-full border border-stone-300 dark:border-stone-700 px-3 py-1 text-sm text-stone-600 dark:text-stone-300 no-underline transition-colors hover:border-stone-500 dark:hover:border-stone-500"><span aria-hidden="true">←</span><span>fabiandemoel.nl</span></a>
<a href="https://github.com/fabiandemoel/Cairn" class="inline-flex items-center gap-1.5 rounded-full border border-stone-300 dark:border-stone-700 px-3 py-1 text-sm text-stone-600 dark:text-stone-300 no-underline transition-colors hover:border-stone-500 dark:hover:border-stone-500"><span class="font-medium">Cairn v1.2.0</span><span class="text-stone-400">·</span><span>Phase 4</span></a>
</div>

<section class="cairn-hero not-prose relative overflow-hidden rounded-3xl border border-stone-200 dark:border-stone-800 px-6 py-10 sm:px-10 sm:py-14">
<div class="cairn-grid" aria-hidden="true"></div>
<div class="relative grid grid-cols-1 md:grid-cols-12 gap-8 items-center">
<div class="md:col-span-7">
<div class="inline-flex items-center gap-2 rounded-full bg-white/70 dark:bg-stone-900/70 ring-1 ring-stone-200 dark:ring-stone-700 px-3 py-1 text-xs font-medium tracking-wide text-stone-600 dark:text-stone-300 backdrop-blur"><span class="cairn-pulse h-1.5 w-1.5 rounded-full bg-emerald-500"></span>Open climate-data benchmark · NL &amp; EU</div>
<h1 class="cairn-display mt-5 font-serif text-4xl sm:text-5xl leading-[1.05] tracking-tight text-stone-900 dark:text-stone-50">Every climate figure, <em class="cairn-ink not-italic">traceable</em> to its source.</h1>
<p class="mt-5 max-w-xl text-base sm:text-lg leading-relaxed text-stone-600 dark:text-stone-300">Cairn turns public climate data into auditable, reproducible datasets with full lineage. Each number is chained — by hash — to a pinned official release, transformed by reviewed code, and guarded by tests.</p>
<div class="mt-8 flex flex-wrap gap-3">
<a href="/sectors" class="inline-flex items-center gap-2 rounded-full bg-stone-900 dark:bg-stone-50 px-5 py-2.5 text-sm font-medium text-white dark:text-stone-900 no-underline shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">Explore the benchmarks <span aria-hidden="true">→</span></a>
<a href="/disclosure" class="inline-flex items-center gap-2 rounded-full bg-white/80 dark:bg-stone-900/80 ring-1 ring-stone-300 dark:ring-stone-700 px-5 py-2.5 text-sm font-medium text-stone-800 dark:text-stone-100 no-underline backdrop-blur transition hover:-translate-y-0.5 hover:ring-stone-500">ESRS E1 disclosure bundle</a>
</div>
</div>
<div class="md:col-span-5 flex justify-center">
<svg class="cairn-stack w-full max-w-[340px]" viewBox="0 0 340 340" role="img" aria-labelledby="cairn-svg-title">
<title id="cairn-svg-title">A cairn of four stones: official source, pinned raw data, tested model, and your figure</title>
<defs>
<linearGradient id="st1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a8a29e"/><stop offset="1" stop-color="#57534e"/></linearGradient>
<linearGradient id="st2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#d6d3d1"/><stop offset="1" stop-color="#78716c"/></linearGradient>
<linearGradient id="st3" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e7e5e4"/><stop offset="1" stop-color="#a8a29e"/></linearGradient>
<linearGradient id="st4" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#60a5fa"/><stop offset="1" stop-color="#1d4ed8"/></linearGradient>
</defs>
<ellipse cx="110" cy="318" rx="100" ry="9" class="cairn-shadow"/>
<g class="cairn-stone s1"><path d="M22 300 C 18 268, 60 250, 112 252 C 168 254, 204 268, 200 296 C 196 318, 150 322, 108 320 C 62 318, 26 316, 22 300 Z" fill="url(#st1)"/></g>
<g class="cairn-stone s2"><path d="M44 244 C 42 220, 76 206, 114 207 C 156 208, 182 220, 178 242 C 175 258, 144 262, 110 261 C 76 260, 46 258, 44 244 Z" fill="url(#st2)"/></g>
<g class="cairn-stone s3"><path d="M64 198 C 62 178, 88 168, 114 169 C 142 170, 160 180, 158 198 C 156 212, 136 215, 111 214 C 86 213, 66 211, 64 198 Z" fill="url(#st3)"/></g>
<g class="cairn-stone s4 cairn-float"><path d="M84 158 C 82 140, 98 132, 113 132 C 130 133, 142 141, 140 157 C 138 169, 126 172, 112 171 C 96 170, 86 168, 84 158 Z" fill="url(#st4)"/></g>
<g class="cairn-labels" font-size="15" font-family="Inter, ui-sans-serif, system-ui">
<line x1="146" y1="150" x2="214" y2="112" class="cairn-lead"/><circle cx="214" cy="112" r="2.5" class="cairn-dot"/>
<text x="220" y="106" class="cairn-k">04</text><text x="220" y="124" class="cairn-t">Your figure</text>
<line x1="162" y1="190" x2="214" y2="178"  class="cairn-lead"/><circle cx="214" cy="178" r="2.5" class="cairn-dot"/>
<text x="220" y="172" class="cairn-k">03</text><text x="220" y="190" class="cairn-t">Tested dbt mart</text>
<line x1="182" y1="236" x2="214" y2="240" class="cairn-lead"/><circle cx="214" cy="240" r="2.5" class="cairn-dot"/>
<text x="220" y="234" class="cairn-k">02</text><text x="220" y="252" class="cairn-t">Pinned · sha256</text>
<line x1="202" y1="290" x2="214" y2="296" class="cairn-lead"/><circle cx="214" cy="296" r="2.5" class="cairn-dot"/>
<text x="220" y="290" class="cairn-k">01</text><text x="220" y="308" class="cairn-t">Official source</text>
</g>
</svg>
</div>
</div>
</section>

<section class="not-prose mt-6 grid grid-cols-2 lg:grid-cols-4 gap-px overflow-hidden rounded-2xl border border-stone-200 dark:border-stone-800 bg-stone-200 dark:bg-stone-800">
<div class="cairn-stat bg-white dark:bg-stone-950 p-5">
<div class="text-xs font-medium uppercase tracking-wider text-stone-500">NL emissions · CBS {#if sector_headline?.length}<Value data={sector_headline} column=latest_year fmt='0'/>{:else}—{/if}</div>
<div class="mt-2 font-serif text-3xl text-stone-900 dark:text-stone-50">{#if sector_headline?.length}<Value data={sector_headline} column=national_total_mt fmt='#,##0.0'/>{:else}—{/if}<div class="mt-1 text-xs text-stone-500">Mt CO₂-eq</div></div>
</div>
<div class="cairn-stat bg-white dark:bg-stone-950 p-5">
<div class="text-xs font-medium uppercase tracking-wider text-stone-500">ETS installations · {#if installation_headline?.length}<Value data={installation_headline} column=latest_year fmt='0'/>{:else}—{/if}</div>
<div class="mt-2 font-serif text-3xl text-stone-900 dark:text-stone-50">{#if installation_headline?.length}<Value data={installation_headline} column=installations fmt='#,##0'/>{:else}—{/if}<div class="mt-1 text-xs text-stone-500">benchmarked</div></div>
</div>
<div class="cairn-stat bg-white dark:bg-stone-950 p-5">
<div class="text-xs font-medium uppercase tracking-wider text-stone-500">EU comparison · Eurostat</div>
<div class="mt-2 font-serif text-3xl text-stone-900 dark:text-stone-50">{#if country_headline?.length}<Value data={country_headline} column=countries fmt='#,##0'/>{:else}—{/if}<div class="mt-1 text-xs text-stone-500">countries</div></div>
</div>
<div class="cairn-stat bg-white dark:bg-stone-950 p-5">
<div class="text-xs font-medium uppercase tracking-wider text-stone-500">Official datasets</div>
<div class="mt-2 font-serif text-3xl text-stone-900 dark:text-stone-50">{#if provenance_headline?.length}<Value data={provenance_headline} column=pinned fmt='#,##0'/>{:else}—{/if}<span class="text-stone-400">/</span>{#if provenance_headline?.length}<Value data={provenance_headline} column=datasets fmt='#,##0'/>{:else}—{/if}<div class="mt-1 text-xs text-stone-500">pinned</div></div>
</div>
</section>

<p class="mt-3 text-xs leading-relaxed text-stone-500">"Benchmarked" counts stationary, NACE-mapped installations only — installations without a NACE section in the pinned euets.info snapshot have no peer group and are excluded; see <a href="/data-quality#how-complete-is-the-coverage">coverage on Data quality</a> for how much of the EEA aggregate the included set captures. Pin status per dataset lives on <a href="/data-quality">Data quality</a>.</p>

<section class="not-prose mt-14">
<div class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">For</div>
<p class="mt-2 max-w-3xl font-serif text-2xl sm:text-3xl leading-snug text-stone-800 dark:text-stone-100">Sustainability teams and auditors who need to prove every number back to an official source. CSRD/ESRS reporting is one application.</p>
<p class="mt-3 max-w-3xl text-sm text-stone-600 dark:text-stone-400">Integrators can build directly on the <a href="/disclosure" class="underline decoration-stone-300 underline-offset-4 hover:decoration-stone-600">disclosure CSV bundle</a> and the <a href="https://github.com/fabiandemoel/Cairn" class="underline decoration-stone-300 underline-offset-4 hover:decoration-stone-600">open repository</a> — Cairn ships no hosted API.</p>
</section>

<section class="not-prose mt-14">
<div class="flex items-end justify-between gap-4 flex-wrap">
<div>
<div class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">The NL benchmark spine</div>
<h2 class="mt-2 font-serif text-3xl text-stone-900 dark:text-stone-50">Two altitudes, one question</h2>
</div>
<p class="max-w-md text-sm text-stone-600 dark:text-stone-400">The whole-economy <strong>denominator</strong> and the installation-level <strong>numerator</strong>, from two official sources.</p>
</div>
<div class="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4">
<a href="/sectors" class="cairn-card group relative block overflow-hidden rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 p-6 no-underline">
<div class="flex items-center justify-between"><span class="rounded-full bg-blue-50 dark:bg-blue-950 px-2.5 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300">CBS · 85669NED</span><span class="text-stone-400 transition group-hover:translate-x-1 group-hover:text-stone-900 dark:group-hover:text-stone-50" aria-hidden="true">→</span></div>
<h3 class="mt-4 font-serif text-2xl text-stone-900 dark:text-stone-50">Sector benchmark</h3>
<p class="mt-2 text-sm leading-relaxed text-stone-600 dark:text-stone-400">Greenhouse-gas emissions per NACE section and year, with each sector's share of the national total. The whole-economy sector average, from CBS StatLine (IPCC method, annual).</p>
</a>
<a href="/installations" class="cairn-card group relative block overflow-hidden rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 p-6 no-underline">
<div class="flex items-center justify-between"><span class="rounded-full bg-amber-50 dark:bg-amber-950 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:text-amber-300">EU ETS · euets.info</span><span class="text-stone-400 transition group-hover:translate-x-1 group-hover:text-stone-900 dark:group-hover:text-stone-50" aria-hidden="true">→</span></div>
<h3 class="mt-4 font-serif text-2xl text-stone-900 dark:text-stone-50">Installation benchmark</h3>
<p class="mt-2 text-sm leading-relaxed text-stone-600 dark:text-stone-400">Per NL stationary installation, its verified emissions versus its NACE-section peers — the large-emitter benchmark from the reprocessed EU Transaction Log, cross-checked against the EEA Union Registry aggregate.</p>
</a>
</div>
</section>

<section class="not-prose mt-14">
<div class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">EU context &amp; cross-checks</div>
<h2 class="mt-2 font-serif text-3xl text-stone-900 dark:text-stone-50">Widen the view, check it twice</h2>
<p class="mt-2 max-w-2xl text-sm text-stone-600 dark:text-stone-400">Four more official views widen the picture and cross-check it from independent sources and accounting principles.</p>
<div class="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
<a href="/sectors-eu" class="cairn-card group block rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 p-5 no-underline">
<div class="text-xs font-medium text-stone-500">Eurostat AEA</div>
<h3 class="mt-2 font-serif text-xl text-stone-900 dark:text-stone-50">EU sector benchmark <span class="inline-block transition group-hover:translate-x-1" aria-hidden="true">→</span></h3>
<p class="mt-2 text-sm leading-relaxed text-stone-600 dark:text-stone-400">The same NACE-section cut for every EU member state, on the residence principle.</p>
</a>
<a href="/countries-ghg" class="cairn-card group block rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 p-5 no-underline">
<div class="text-xs font-medium text-stone-500">Eurostat GGE</div>
<h3 class="mt-2 font-serif text-xl text-stone-900 dark:text-stone-50">Country GHG totals <span class="inline-block transition group-hover:translate-x-1" aria-hidden="true">→</span></h3>
<p class="mt-2 text-sm leading-relaxed text-stone-600 dark:text-stone-400">National totals (territorial principle, UNFCCC submissions) for the EU27 plus peers — comparable to CBS.</p>
</a>
<a href="/namea-bridge" class="cairn-card group block rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 p-5 no-underline">
<div class="text-xs font-medium text-stone-500">CBS NAMEA</div>
<h3 class="mt-2 font-serif text-xl text-stone-900 dark:text-stone-50">NAMEA bridge <span class="inline-block transition group-hover:translate-x-1" aria-hidden="true">→</span></h3>
<p class="mt-2 text-sm leading-relaxed text-stone-600 dark:text-stone-400">Residence-principle emissions bridged against the territorial benchmark — same emissions, two principles.</p>
</a>
<a href="/transport" class="cairn-card group block rounded-2xl border border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-950 p-5 no-underline">
<div class="text-xs font-medium text-stone-500">EU ETS operators</div>
<h3 class="mt-2 font-serif text-xl text-stone-900 dark:text-stone-50">Transport benchmark <span class="inline-block transition group-hover:translate-x-1" aria-hidden="true">→</span></h3>
<p class="mt-2 text-sm leading-relaxed text-stone-600 dark:text-stone-400">NL aviation and maritime operators, benchmarked by operator type rather than industry sector.</p>
</a>
</div>
</section>

<section class="cairn-dark not-prose mt-14 overflow-hidden rounded-3xl bg-stone-900 dark:bg-stone-900/60 dark:ring-1 dark:ring-stone-800 px-6 py-10 sm:px-10">
<div class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-400">Why it is auditable</div>
<h2 class="mt-2 max-w-2xl font-serif text-3xl sm:text-4xl leading-tight text-stone-50">Four load-bearing rules, so a number can never drift from its source.</h2>
<ol class="mt-8 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 list-none p-0">
<li class="border-t border-stone-700 pt-4"><div class="font-mono text-xs text-blue-300">01</div><div class="mt-2 font-medium text-stone-50">Raw data is immutable</div><p class="mt-1 text-sm leading-relaxed text-stone-400">Every ingest writes a new, versioned path. Nothing is overwritten.</p></li>
<li class="border-t border-stone-700 pt-4"><div class="font-mono text-xs text-blue-300">02</div><div class="mt-2 font-medium text-stone-50">The manifest is append-only</div><p class="mt-1 text-sm leading-relaxed text-stone-400">Each source pins its exact release by <code class="text-stone-300">sha256</code>; a data change without a manifest change is impossible.</p></li>
<li class="border-t border-stone-700 pt-4"><div class="font-mono text-xs text-blue-300">03</div><div class="mt-2 font-medium text-stone-50">Mappings are code</div><p class="mt-1 text-sm leading-relaxed text-stone-400">The CBS category → NACE mapping is a reviewed seed, so its numeric impact shows up in a CI diff.</p></li>
<li class="border-t border-stone-700 pt-4"><div class="font-mono text-xs text-blue-300">04</div><div class="mt-2 font-medium text-stone-50">CI guards the methodology</div><p class="mt-1 text-sm leading-relaxed text-stone-400">Reconciliation and coverage tests fail the build if a source shifts under us.</p></li>
</ol>
<div class="mt-10 flex flex-wrap gap-2">
<a href="/architecture" class="rounded-full bg-white/10 px-4 py-2 text-sm text-stone-100 no-underline ring-1 ring-white/15 transition hover:bg-white/20">Architecture →</a>
<a href="/methodology" class="rounded-full bg-white/10 px-4 py-2 text-sm text-stone-100 no-underline ring-1 ring-white/15 transition hover:bg-white/20">Methodology &amp; sources →</a>
<a href="/data-quality" class="rounded-full bg-white/10 px-4 py-2 text-sm text-stone-100 no-underline ring-1 ring-white/15 transition hover:bg-white/20">Data quality →</a>
<a href="/data-dictionary" class="rounded-full bg-white/10 px-4 py-2 text-sm text-stone-100 no-underline ring-1 ring-white/15 transition hover:bg-white/20">Data dictionary &amp; glossary →</a>
</div>
</section>

<section class="not-prose mt-14 grid grid-cols-1 md:grid-cols-5 gap-6 items-center rounded-3xl border border-stone-200 dark:border-stone-800 p-6 sm:p-10">
<div class="md:col-span-3">
<div class="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500">CSRD / ESRS E1</div>
<h2 class="mt-2 font-serif text-3xl text-stone-900 dark:text-stone-50">An auditable basis for gross Scope 1</h2>
<p class="mt-3 text-sm leading-relaxed text-stone-600 dark:text-stone-400">The disclosure supports ESRS E1-6 reporting with verified EU ETS Scope 1 emissions per installation — downloadable as a self-contained bundle whose metadata chains every row back to the source pin, the methodology commit, and a hash of the CSV.</p>
</div>
<div class="md:col-span-2 md:text-right">
<a href="/disclosure" class="inline-flex items-center gap-2 rounded-full bg-blue-600 dark:bg-blue-500 px-5 py-2.5 text-sm font-medium text-white no-underline shadow-sm transition hover:-translate-y-0.5 hover:bg-blue-700 dark:hover:bg-blue-600">Open the disclosure <span aria-hidden="true">→</span></a>
</div>
</section>

<div class="not-prose mt-10 mb-4 rounded-2xl bg-stone-100 dark:bg-stone-900 p-5 text-sm leading-relaxed text-stone-600 dark:text-stone-400">
<span class="font-medium text-stone-900 dark:text-stone-100">What Cairn is not.</span> A verified data source, not a reporting product — not a CSRD reporting platform, not a double-materiality assessment, not Scope 2/3 calculation, not an assurance opinion, and not legal advice.
</div>

<style>
	.cairn-hero {
		background:
			radial-gradient(60% 80% at 85% 20%, rgb(59 130 246 / 0.16), transparent 60%),
			radial-gradient(50% 70% at 10% 100%, rgb(245 158 11 / 0.10), transparent 60%),
			linear-gradient(180deg, #fafaf9, #f5f5f4);
	}
	:global([data-theme='dark']) .cairn-hero {
		background:
			radial-gradient(60% 80% at 85% 20%, rgb(59 130 246 / 0.22), transparent 60%),
			radial-gradient(50% 70% at 10% 100%, rgb(245 158 11 / 0.10), transparent 60%),
			linear-gradient(180deg, #1c1917, #0c0a09);
	}
	.cairn-grid {
		position: absolute;
		inset: 0;
		background-image: radial-gradient(rgb(120 113 108 / 0.25) 1px, transparent 1px);
		background-size: 22px 22px;
		mask-image: radial-gradient(70% 70% at 70% 40%, black, transparent);
		-webkit-mask-image: radial-gradient(70% 70% at 70% 40%, black, transparent);
	}
	.cairn-display {
		font-feature-settings: 'lnum';
	}
	.cairn-ink {
		background: linear-gradient(90deg, #2563eb, #0ea5e9);
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
		font-style: italic;
	}
	:global([data-theme='dark']) .cairn-ink {
		background-image: linear-gradient(90deg, #60a5fa, #67e8f9);
	}
	.cairn-shadow { fill: rgb(28 25 23 / 0.12); }
	:global([data-theme='dark']) .cairn-shadow { fill: rgb(0 0 0 / 0.5); }
	.cairn-lead { stroke: #a8a29e; stroke-width: 1; stroke-dasharray: 2 3; }
	.cairn-dot { fill: #78716c; }
	.cairn-k { fill: #a8a29e; font-family: ui-monospace, monospace; font-size: 11px; letter-spacing: 0.08em; }
	.cairn-t { fill: #44403c; font-weight: 500; }
	:global([data-theme='dark']) .cairn-t { fill: #e7e5e4; }
	.cairn-stone {
		opacity: 0;
		transform-box: fill-box;
		transform-origin: center;
		animation: cairn-drop 0.7s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;
	}
	.s1 { animation-delay: 0.05s; }
	.s2 { animation-delay: 0.25s; }
	.s3 { animation-delay: 0.45s; }
	.s4 { animation-delay: 0.65s; }
	.cairn-labels { opacity: 0; animation: cairn-fade 0.8s ease 1.1s forwards; }
	.cairn-float path { animation: cairn-float 5s ease-in-out 1.6s infinite; transform-box: fill-box; }
	.cairn-pulse { box-shadow: 0 0 0 0 rgb(16 185 129 / 0.6); animation: cairn-pulse 2.4s ease-out infinite; }
	.cairn-card { transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease; }
	.cairn-card:hover { transform: translateY(-2px); box-shadow: 0 12px 30px -12px rgb(28 25 23 / 0.25); border-color: #a8a29e; }
	:global([data-theme='dark']) .cairn-card:hover { border-color: #57534e; box-shadow: 0 12px 30px -12px rgb(0 0 0 / 0.8); }
	.cairn-dark {
		background-image: radial-gradient(70% 90% at 100% 0%, rgb(59 130 246 / 0.18), transparent 60%);
	}
	@keyframes cairn-drop {
		from { opacity: 0; transform: translateY(-28px); }
		to { opacity: 1; transform: translateY(0); }
	}
	@keyframes cairn-fade { to { opacity: 1; } }
	@keyframes cairn-float {
		0%, 100% { transform: translateY(0) rotate(0deg); }
		50% { transform: translateY(-4px) rotate(-1.5deg); }
	}
	@keyframes cairn-pulse {
		0% { box-shadow: 0 0 0 0 rgb(16 185 129 / 0.55); }
		80%, 100% { box-shadow: 0 0 0 7px rgb(16 185 129 / 0); }
	}
	@media (prefers-reduced-motion: reduce) {
		.cairn-stone, .cairn-labels { animation: none; opacity: 1; }
		.cairn-float path, .cairn-pulse { animation: none; }
	}
</style>
