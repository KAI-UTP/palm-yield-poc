/* PalmYield agronomy knowledge base: short, sourced reference notes the assistant combines with the client's own data.
   Keep every note general and sourced; the client's agronomist confirms targets for their soils. Add notes here as sources are reviewed. */
(function () {
  const SRC = {
    liming: { name: "Mahmud & Chong (2022), Agriculture 12(3):322: liming of soils under oil palm in Malaysia", url: "https://doi.org/10.3390/agriculture12030322" },
    yieldgap: { name: "Woittiez et al. (2017), European Journal of Agronomy: yield gaps in oil palm", url: "https://doi.org/10.1016/j.eja.2016.11.002" },
    water: { name: "Carr (2011), Experimental Agriculture: water relations and irrigation of oil palm", url: "https://doi.org/10.1017/S0014479711000494" },
    chow: { name: "Chow (1992), Journal of Oil Palm Research (MPOB): season, rainfall and cycle of oil palm yield in Malaysia", url: "https://jopr.mpob.gov.my/?p=1424" },
    oettli: { name: "Oettli et al. (2018), Scientific Reports: climate and oil palm yield in Malaysia and Indonesia", url: "https://doi.org/10.1038/s41598-018-20298-0" },
    fleiss: { name: "Fleiss et al. (2022), CABI Agriculture and Bioscience: climate and yield in Malaysian plantations", url: "https://doi.org/10.1186/s43170-022-00127-1" },
    leaf: { name: "Ochs & Olvin (1977), leaf 17 critical levels, as reproduced in Better Crops International (1999)", url: "" },
  };

  const NOTES = [
    { id: "soil_ph", words: ["ph", "acid", "lime", "liming", "dolomite", "aluminium", "aluminum"],
      title: "Soil pH and liming",
      text: "Oil palm tolerates acid soils, and most Southeast Asian plantations are on acid, low-fertility soils. Very acid soils, especially peat, are usually limed: raising pH reduces aluminium toxicity and frees nutrients. Liming is costly, so the lime is chosen by soil type, price, neutralising value and fineness, and the target pH is set per soil by the agronomist.",
      steps: ["Re-test soil pH in the blocks below the best range (same depth and season as before)", "Ask the agronomist for a target pH and lime rate for that soil type (mineral or peat)", "Apply ground magnesium limestone or dolomite, which also adds Mg, away from the fertilizer round", "Re-sample soil and leaf 17 after 6 to 12 months and compare yield with age peers"],
      sources: ["liming"] },
    { id: "rainfall", words: ["rain", "rainfall", "drought", "dry", "water deficit", "deficit", "irrigat", "weather", "climate", "el nino", "monsoon"],
      title: "Rainfall and water deficit",
      text: "Oil palm does best with about 2,000 mm of rain a year or more, spread evenly with no long dry months. Water deficit lowers yield: a widely used estimate is about 10% less yield for every 100 mm of yearly soil water deficit. Very heavy rain can also hurt, through cloud cover, waterlogging and poorer pollination.",
      steps: ["Keep soil cover and mulch (e.g. empty fruit bunches) on blocks that dry out, to hold moisture", "Fix drains on blocks that waterlog in wet months", "Track rainfall and water deficit per estate every month so forecasts can use them"],
      sources: ["yieldgap", "water"] },
    { id: "rain_lag", words: ["lag", "delay", "ago", "earlier", "previous", "before", "months later", "past cycle", "two cycle", "2 cycle"],
      title: "Why rain affects yield months later",
      text: "A bunch takes years to form, so weather affects yield long after it happens. Malaysian studies link yield to rainfall about 20 to 24 and 10 to 11 months before harvest. The sensitive stages are when flowers become male or female (about 20 to 31 months before harvest), when young flowers abort (about 8 to 12 months before), and bunch failure (2 to 4 months before). Other studies find climate explains less of the yield gap than management, so both matter.",
      steps: ["Collect at least 2 years of monthly rainfall and yield per block", "Add rainfall and water deficit from 2 to 31 months earlier to the forecast model", "Warn managers early when a dry spell is likely to cut yield a year later"],
      sources: ["chow", "oettli", "fleiss"] },
    { id: "leaf_nutrients", words: ["nutrient", "leaf", "nitrogen", "potassium", "magnesium", "phosphorus", "boron", "fertili", "npk"],
      title: "Leaf nutrient critical levels",
      text: "Nutrient status is checked on leaf 17. Classic critical levels: below about 2.5% N, 0.15% P, 1.0% K and 0.20% Mg, and under 8 mg/kg boron, the palm is deficient. Critical levels shift with soil, climate and planting material, so each estate calibrates them.",
      steps: ["Sample leaf 17 on every block once a year at the same season", "Where leaf levels stay low despite fertilizer, check timing, drainage and weeds before buying more fertilizer", "Re-sample after the next fertilizer round"],
      sources: ["leaf"] },
    { id: "waterlogging", words: ["flood", "waterlog", "moisture", "wet", "drain", "water table", "peat", "organic carbon"],
      title: "Waterlogging, drainage and peat",
      text: "Roots need air: standing water and a high water table cut uptake and yield, while peat that is over-drained subsides and can dry out. Peat soils are also very acid and low in nutrients, so they need their own drainage, liming and fertilizer plan.",
      steps: ["Clear and repair field drains before the wet season", "On peat, hold the water table at the level the agronomist sets rather than draining fully", "Record flooding days per block so the effect can be measured"],
      sources: ["water", "liming"] },
  ];

  function find(q) {
    const s = q.toLowerCase();
    // short words ("ph", "dry") must match whole words, so "phosphorus" is not read as pH
    return NOTES.filter((n) => n.words.some((w) => new RegExp("\\b" + w.replace(/ /g, "\\s+") + (w.length < 4 ? "\\b" : ""), "i").test(s)));
  }
  const cite = (n) => n.sources.map((k) => SRC[k]).filter(Boolean);

  window.PYK = { NOTES, SRC, find, cite };
})();
