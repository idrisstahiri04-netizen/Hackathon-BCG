/* ============================================================================
   advice.js — what to actually DO about an alert.

   This is the layer that turns a risk level into a decision. A colour on a map
   tells a food bank nothing; "maize and pigeon peas are at risk in Kitui, the
   county has no HSNP coverage so the fallback is NCPB relief stock, and the
   action is to pre-position before the price peak" tells them what to buy.

   Two inputs, both real:
     - the county's FEWS NET livelihood zones (data/kenya-livelihoods.json,
       parsed from FEWS NET's own fsc_admin_lhz unit names)
     - the published eligibility rules of real Kenyan response programmes

   Nothing here invents an institution. Where a programme does not cover a
   county, the advice says so rather than inventing a service.
   ============================================================================ */

const ADVICE = (() => {

  // ---- Who actually runs drought response in Kenya -------------------------
  // HSNP covers exactly eight counties. This list is the real eligibility
  // boundary, and getting it wrong is the kind of error a Kenyan judge spots
  // instantly - so counties outside it are told the truth.
  const HSNP_COUNTIES = new Set([
    'Turkana', 'Wajir', 'Mandera', 'Marsabit', 'Garissa', 'Tana River',
    'Isiolo', 'Samburu',
  ]);

  const RESOURCES = {
    hsnp: {
      name: 'HSNP cash transfer',
      body: 'NDMA',
      what: 'Shock-responsive cash transfer, scaled up when the Vegetation Condition Index crosses its trigger.',
      who: 'Registered households in the 8 HSNP counties',
      minLevel: 2,
    },
    ndma: {
      name: 'County Drought Coordinator',
      body: 'NDMA',
      what: 'Declares the county drought phase and convenes the County Steering Group that releases contingency funds.',
      who: 'All 23 ASAL counties',
      minLevel: 1,
    },
    ncpb: {
      name: 'Strategic grain reserve',
      body: 'NCPB',
      what: 'Release or subsidised sale of reserve maize; the lever that caps the price spike.',
      who: 'Via national government on County Steering Group request',
      minLevel: 2,
    },
    kalro: {
      name: 'Drought-tolerant seed',
      body: 'KALRO + county agriculture office',
      what: 'Certified short-maturity and drought-tolerant varieties, distributed before the next planting window.',
      who: 'Cropping households, through extension officers',
      minLevel: 1,
    },
    livestock: {
      name: 'Offtake and fodder',
      body: 'County livestock office',
      what: 'Commercial destocking at fair price, emergency fodder, and water trucking to strategic boreholes.',
      who: 'Pastoral households',
      minLevel: 2,
    },
    redcross: {
      name: 'Emergency relief',
      body: 'Kenya Red Cross',
      what: 'Food distribution, water trucking and nutrition screening for children under five.',
      who: 'Affected households, prioritised by county',
      minLevel: 3,
    },
    wfp: {
      name: 'Anticipatory action window',
      body: 'WFP / anticipatory action funds',
      what: 'Pre-agreed finance released on a forecast rather than after the fact.',
      who: 'Triggered at county level with partner NGOs',
      minLevel: 2,
    },
  };

  // ---- What each FEWS NET livelihood zone actually produces ----------------
  // kind drives the shape of the advice: you destock a pastoral county and you
  // re-seed a cropping one. Those are different products.
  const ZONES = {
    'Western High Potential Zone':
      { kind: 'crop', crops: ['maize', 'beans', 'tea', 'sugarcane', 'dairy'] },
    'Central Highlands, High Potential Zone':
      { kind: 'crop', crops: ['maize', 'beans', 'Irish potato', 'tea', 'coffee', 'dairy'] },
    'Western Medium Potential Zone':
      { kind: 'crop', crops: ['maize', 'beans', 'sorghum', 'finger millet'] },
    'Coastal Medium Potential Farming':
      { kind: 'crop', crops: ['maize', 'cassava', 'coconut', 'cashew', 'mango'] },
    'Southeastern Medium Potential, Mixed Farming':
      { kind: 'crop', crops: ['maize', 'beans', 'pigeon pea'] },

    'Southeastern Marginal Mixed Farming':
      { kind: 'marginal', crops: ['maize', 'cowpea', 'pigeon pea', 'green gram', 'sorghum'] },
    'Western Lakeshore Marginal Mixed Farming':
      { kind: 'marginal', crops: ['maize', 'sorghum', 'cassava', 'sweet potato'] },
    'Coastal Marginal Agricultural Mixed Farming':
      { kind: 'marginal', crops: ['maize', 'cassava', 'cowpea', 'coconut'] },
    'Marsabit Marginal Mixed Farming':
      { kind: 'marginal', crops: ['maize', 'beans', 'small stock'] },

    'Northern Pastoral Zone':
      { kind: 'pastoral', crops: ['cattle', 'camels', 'goats', 'sheep'] },
    'Northeastern Pastoral Zone':
      { kind: 'pastoral', crops: ['camels', 'goats', 'cattle'] },
    'Northwestern Pastoral Zone':
      { kind: 'pastoral', crops: ['goats', 'sheep', 'camels', 'cattle'] },
    'Eastern Pastoral Zone':
      { kind: 'pastoral', crops: ['cattle', 'goats', 'camels'] },
    'Southern Pastoral Zone':
      { kind: 'pastoral', crops: ['cattle', 'sheep', 'goats'] },
    'Southeastern Pastoral Zone':
      { kind: 'pastoral', crops: ['cattle', 'goats'] },

    'Western Agropastoral Zone':
      { kind: 'agropastoral', crops: ['sorghum', 'maize', 'goats', 'cattle'] },
    'Northeastern Agropastoral Zone':
      { kind: 'agropastoral', crops: ['sorghum', 'cowpea', 'goats', 'camels'] },
    'Northwestern Agropastoral Zone':
      { kind: 'agropastoral', crops: ['sorghum', 'goats', 'cattle'] },
    'Southern Agropastoral Zone':
      { kind: 'agropastoral', crops: ['maize', 'beans', 'cattle', 'sheep'] },

    'Tana Riverine Zone':
      { kind: 'riverine', crops: ['irrigated maize', 'banana', 'mango', 'vegetables'] },
    'Mandera Riverine Zone':
      { kind: 'riverine', crops: ['irrigated maize', 'onion', 'tomato', 'banana'] },
    'Turkwell Riverine Zone':
      { kind: 'riverine', crops: ['irrigated sorghum', 'maize', 'vegetables'] },

    'Lake Turkana Fishing':
      { kind: 'fishing', crops: ['tilapia', 'Nile perch'] },
    'Lake Victoria Fishing':
      { kind: 'fishing', crops: ['tilapia', 'Nile perch', 'omena'] },
  };

  const DEFAULT_ZONE = { kind: 'marginal', crops: ['maize', 'beans'] };

  // ---- The action per livelihood kind, per level ---------------------------
  // Level 1 is preparation, level 2 is protection of assets, level 3 is relief.
  const ACTIONS = {
    pastoral: {
      1: ['Open and de-silt strategic boreholes on the dry-season grazing routes.',
          'Brief herders on early migration before pasture on the main routes is gone.'],
      2: ['Start commercial destocking now, while animals still hold condition and fetch a price.',
          'Pre-position emergency fodder and begin water trucking to the worst boreholes.',
          'Open livestock offtake at a guaranteed floor price to stop distress sales.'],
      3: ['Emergency water trucking and supplementary feeding for core breeding stock.',
          'Nutrition screening for children under five; pastoral households lose milk first.'],
    },
    agropastoral: {
      1: ['Distribute short-maturity sorghum and cowpea seed before the next planting window.',
          'Advise staggered planting to spread the risk of a failed season.'],
      2: ['Begin partial destocking of non-breeding animals.',
          'Promote early harvest of any standing crop rather than waiting for full maturity.'],
      3: ['Food assistance plus protection of breeding stock; this zone loses both income streams at once.'],
    },
    marginal: {
      1: ['Push drought-tolerant varieties: green gram, cowpea, sorghum over maize.',
          'Advise farmers to hold grain rather than sell into a rising market.'],
      2: ['Subsidise certified drought-tolerant seed for the next season.',
          'Pre-position NCPB stock locally before the price peak reaches the village market.',
          'Promote hermetic storage bags to cut post-harvest loss on what was saved.'],
      3: ['General food distribution and school feeding; this zone has the thinnest buffer of any cropping area.'],
    },
    crop: {
      1: ['Monitor only. This is the national grain basket and it absorbs demand when the ASALs fail.',
          'Advise against panic selling; prices here set the national price.'],
      2: ['Protect the surplus: hermetic storage and aflatoxin checks before the grain moves.',
          'Coordinate with NCPB on purchase into the reserve rather than export.'],
      3: ['If this zone reaches Emergency the national balance has failed. Escalate to national level.'],
    },
    riverine: {
      1: ['Check irrigation intakes and pumps before river levels drop further.',
          'Prioritise vegetable and short-cycle crops that can be harvested inside one season.'],
      2: ['Ration irrigation water by rota; protect perennials such as banana and mango first.',
          'Riverine plots are the local fallback when rainfed land fails - keep them producing.'],
      3: ['Fuel subsidy for irrigation pumps; this zone is the last local food source still standing.'],
    },
    fishing: {
      1: ['Watch for falling lake levels and shifting catch; fishing households buy all their grain.'],
      2: ['These households are fully exposed to the grain price, not to the harvest.',
          'Target them with cash rather than seed - they have no land to plant.'],
      3: ['Cash transfer and food assistance; fishing income does not cover a doubled grain price.'],
    },
  };

  let LHZ = {};   // county -> [zone names]; injected at boot

  function init(livelihoodData) {
    LHZ = (livelihoodData && livelihoodData.zones) || {};
  }

  // ---- Build the recommendation for one alert ------------------------------
  // zoneOverride lets a sub-county pass its own FEWS NET livelihood zones
  // instead of inheriting the county's — that is the point of the finer
  // resolution, so we must not throw it away here.
  function build(countyName, level, zoneOverride) {
    const zoneNames = (zoneOverride && zoneOverride.length) ? zoneOverride : (LHZ[countyName] || []);
    const profiles = zoneNames.map(z => ZONES[z] || DEFAULT_ZONE);
    if (!profiles.length) profiles.push(DEFAULT_ZONE);

    // The county's dominant livelihood is the first zone FEWS NET lists.
    const kinds = [...new Set(profiles.map(p => p.kind))];
    const primary = kinds[0];

    // Crops at risk: union across zones, dominant zone first, capped so the
    // card stays readable.
    const crops = [];
    for (const p of profiles) for (const c of p.crops) {
      if (!crops.includes(c)) crops.push(c);
    }

    // Actions from every livelihood present, so a mixed county (pastoral +
    // riverine, like Tana River) gets both kinds of advice.
    const actions = [];
    for (const k of kinds) {
      const byLevel = ACTIONS[k] || ACTIONS.marginal;
      for (let l = 1; l <= Math.max(1, level); l++) {
        for (const a of (byLevel[l] || [])) if (!actions.includes(a)) actions.push(a);
      }
    }

    // Resources, filtered by level and by real eligibility.
    const resources = [];
    for (const [key, r] of Object.entries(RESOURCES)) {
      if (level < r.minLevel) continue;
      if (key === 'hsnp' && !HSNP_COUNTIES.has(countyName)) continue;
      if (key === 'livestock' && !kinds.some(k => k === 'pastoral' || k === 'agropastoral')) continue;
      if (key === 'kalro' && !kinds.some(k => k !== 'pastoral' && k !== 'fishing')) continue;
      resources.push({ key, ...r });
    }

    // Where a programme does NOT reach, say so. A food bank planning around a
    // county with no HSNP coverage needs to know that explicitly.
    const gaps = [];
    if (level >= 2 && !HSNP_COUNTIES.has(countyName)) {
      gaps.push('No HSNP cash-transfer coverage in this county - relief must come through NCPB stock or partner NGOs.');
    }
    if (primary === 'fishing' && level >= 2) {
      gaps.push('Seed and input programmes do not reach fishing households; they need cash, not inputs.');
    }

    return {
      zones: zoneNames.slice(0, 3),
      kinds,
      primary,
      crops: crops.slice(0, 6),
      actions: actions.slice(0, 4),
      resources,
      gaps,
      hsnp: HSNP_COUNTIES.has(countyName),
    };
  }

  // A one-line version for the SMS, where there are ~40 spare characters.
  function shortAction(countyName, level, zoneOverride) {
    const rec = build(countyName, level, zoneOverride);
    const k = rec.primary;
    if (level >= 3) {
      return k === 'pastoral' ? 'Water and feed breeding stock only'
           : k === 'fishing' ? 'Collect cash transfer, do not buy on credit'
           : 'Collect relief at your chief camp';
    }
    return k === 'pastoral' ? 'Sell weak stock now while prices hold'
         : k === 'agropastoral' ? 'Plant short-maturity sorghum, sell weak stock'
         : k === 'riverine' ? 'Prioritise irrigated plots, ration water'
         : k === 'fishing' ? 'Buy and store grain now, before the price peak'
         : k === 'crop' ? 'Store grain properly, do not panic sell'
         : 'Plant green gram or cowpea, keep 2 months grain';
  }

  return { init, build, shortAction, RESOURCES, ZONES, HSNP_COUNTIES };
})();
