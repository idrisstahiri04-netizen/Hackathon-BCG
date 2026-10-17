/* ============================================================================
   roles.js — the same alert, read by two different organisations.

   A food bank and a ministry look at an identical IPC Phase 3 classification
   and need completely different things from it. The food bank asks "how much
   cereal do I move, to which branch, by when". The ministry asks "do I release
   the reserve, do I declare, what does it cost".

   So the recommendations are not relabelled — they are different decisions,
   with different levers, different time horizons and different money.
   ============================================================================ */

const ROLES = (() => {

  const DEFS = {
    ngo: {
      id: 'ngo',
      label: 'Food bank / NGO',
      blurb: 'Procurement, pre-positioning and distribution',
      icon: 'M12 2 3 7v10l9 5 9-5V7z',
      lens: 'operational',
      // What this role is being asked to decide
      question: 'How much stock, to which branch, by when?',
    },
    gov: {
      id: 'gov',
      label: 'Government entity',
      blurb: 'Reserves, declarations and policy levers',
      icon: 'M3 21h18M5 21V10l7-5 7 5v11M9 21v-6h6v6',
      lens: 'policy',
      question: 'Do we release the reserve, and do we declare?',
    },
  };

  // --- Next steps, per role x livelihood x level ----------------------------
  // Level 1 Watch = prepare. 2 Warning = commit resources. 3 Emergency = relief.
  const STEPS = {
    ngo: {
      pastoral: {
        1: ['Confirm which boreholes on the migration routes are working — do it now, not when herds arrive.',
            'Pre-qualify livestock traders for an offtake round so you are not negotiating under pressure.'],
        2: ['Fund commercial destocking this month. Every week of delay cuts the price herders get.',
            'Move cash, not food. Pastoral markets still have grain; households lack the money for it.',
            'Pre-position supplementary feed at the two worst-hit grazing blocks.'],
        3: ['Switch to water trucking and feed for core breeding stock — the asset, not the herd.',
            'Open nutrition screening for under-fives. Pastoral households lose milk before they lose grain.'],
      },
      agropastoral: {
        1: ['Order short-maturity sorghum and cowpea seed now; the planting window will not wait for a tender.'],
        2: ['Split the budget: seed for the next season AND cash for this one. Doing only one wastes both.',
            'Target households with both failing crops and thinning herds — they fall fastest.'],
        3: ['General food distribution plus protection of breeding stock, or next season fails too.'],
      },
      marginal: {
        1: ['Lock cereal prices with suppliers now, before the market reads the same signals you are reading.',
            'Audit branch stock against a 3-month deterioration, not current demand.'],
        2: ['Buy cereal now. This is the single highest-leverage week in your procurement calendar.',
            'Pre-position at the sub-county level, not the county warehouse — the last 40km is the bottleneck.',
            'Fund hermetic storage bags; post-harvest loss here is a quiet second shock.'],
        3: ['General food distribution and school feeding. This zone has the thinnest buffer of any cropping area.'],
      },
      crop: {
        1: ['No action needed here. Watch it as a supply source for the counties that are failing.'],
        2: ['Buy here to supply the ASALs — shorter haul, lower cost than importing.',
            'Check aflatoxin before moving any grain out of a stressed season.'],
        3: ['If this zone is in Emergency the national balance has failed. Escalate, do not absorb locally.'],
      },
      riverine: {
        1: ['Check pump and intake status before river levels drop further.'],
        2: ['Fund fuel for irrigation pumps. This is the cheapest food you will produce all season.',
            'Buy local irrigated produce for distribution instead of hauling it in.'],
        3: ['Subsidise pump fuel outright. This is the last local food source still standing.'],
      },
      fishing: {
        1: ['Flag these households now: they buy 100% of their grain and have no harvest to wait for.'],
        2: ['Cash transfers, not seed or inputs. They have no land to plant.',
            'They are fully exposed to the grain price — model them against the price curve, not the rainfall.'],
        3: ['Cash plus food. Fishing income does not stretch to a doubled grain price.'],
      },
    },

    gov: {
      pastoral: {
        1: ['Convene the County Steering Group and put the drought phase on the record.',
            'Release contingency funds for borehole repair while it is still cheap maintenance.'],
        2: ['Authorise a commercial offtake programme with a guaranteed floor price.',
            'Trigger the HSNP shock-responsive scale-up where the county is covered.',
            'Pre-authorise water trucking contracts now; procurement takes weeks you will not have.'],
        3: ['Declare, and open the national response. Delay past this point costs lives and livestock.',
            'Waive livestock movement restrictions so herds can reach surviving pasture.'],
      },
      agropastoral: {
        1: ['Instruct extension services to push drought-tolerant seed ahead of the planting window.'],
        2: ['Subsidise certified seed for the next season and fund the offtake for this one.',
            'This zone loses crop and livestock income simultaneously — budget for both.'],
        3: ['Food assistance plus breeding-stock protection, or the recovery takes two seasons not one.'],
      },
      marginal: {
        1: ['Brief the Ministry of Agriculture on the seed subsidy decision while there is still time to act on it.'],
        2: ['Release NCPB strategic reserve into local markets. This is the lever that caps the price spike.',
            'Consider a temporary duty waiver on cereal imports before prices force it.',
            'Deploy extension officers to the worst wards with drought-tolerant seed.'],
        3: ['Open subsidised sale at the sub-county level and publish the prices. Transparency limits hoarding.'],
      },
      crop: {
        1: ['Monitor. This is the national grain basket and sets the national price.'],
        2: ['Buy into the strategic reserve from this zone rather than permitting export.',
            'Enforce aflatoxin testing — a stressed season raises contamination risk.'],
        3: ['National supply failure. Move to import planning and price stabilisation.'],
      },
      riverine: {
        1: ['Verify irrigation scheme water rights and intake condition before allocation becomes contested.'],
        2: ['Allocate irrigation water by rota and publish it. Unmanaged abstraction will empty the river.',
            'These schemes are the local fallback when rainfed land fails — fund them to keep running.'],
        3: ['Fuel subsidy for irrigation pumps; protect the last local production still standing.'],
      },
      fishing: {
        1: ['Note that these households are grain buyers, not growers — seed programmes will not reach them.'],
        2: ['Route them into cash transfer schemes rather than input subsidy.',
            'Monitor lake levels alongside grain prices; both drive their food access.'],
        3: ['Cash transfer and food assistance; input subsidies are the wrong instrument here.'],
      },
    },
  };

  // Role-specific framing of the headline number.
  function headline(role, level, unitName, phase) {
    const NAMES = ['', 'Minimal', 'Stressed', 'Crisis', 'Emergency', 'Famine'];
    if (role === 'gov') {
      return level >= 3
        ? `${unitName} is at IPC ${NAMES[phase] || 'Emergency'}. A declaration decision is live.`
        : level === 2
        ? `${unitName} has crossed the reserve-release threshold.`
        : `${unitName} warrants a County Steering Group review.`;
    }
    return level >= 3
      ? `${unitName} needs relief distribution now, not procurement.`
      : level === 2
      ? `Buy and pre-position for ${unitName} this month, before the price peak.`
      : `Put ${unitName} on your procurement watchlist.`;
  }

  function steps(role, kinds, level) {
    const table = STEPS[role] || STEPS.ngo;
    const out = [];
    for (const k of kinds) {
      const byLevel = table[k] || table.marginal;
      for (let l = 1; l <= Math.max(1, level); l++) {
        for (const s of (byLevel[l] || [])) if (!out.includes(s)) out.push(s);
      }
    }
    return out;
  }

  return { DEFS, steps, headline };
})();
